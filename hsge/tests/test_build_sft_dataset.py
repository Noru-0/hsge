"""build_sft_dataset.py: prompt parity with the live Solver, outcome- and
prior-thought-annotated history, GOAL tag stripping, trajectory/step
metadata, and exclusion of steps whose action errored at collection time.

Run:  python -m pytest hsge/tests/test_build_sft_dataset.py -q
 (or) PYTHONPATH=. python hsge/tests/test_build_sft_dataset.py
"""
import json
import os
import tempfile

from build_sft_dataset import SYSTEM, _include_episode, episode_to_examples, load_episodes
from hsge.webarena.agents import SOLVER_SYS


def _write_axtree(ep_dir, index, text):
    os.makedirs(os.path.join(ep_dir, "page_state"), exist_ok=True)
    rel = f"page_state/step_{index:03d}_axtree.txt"
    open(os.path.join(ep_dir, rel), "w").write(text)
    return rel


def _step(ep_dir, index, url, axtree, thought, action):
    rel = _write_axtree(ep_dir, index, axtree)
    return {"record_type": "step", "index": index, "url": url,
            "action": json.dumps({"thought": thought, "action": action}),
            "parsed_action": action, "thought": thought,
            "observation": {"axtree_txt": {"path": rel}}}


def _write_episode_dir(run_dir, ep_name, goal, success, infeasible, steps):
    ep_dir = os.path.join(run_dir, "episodes", ep_name)
    os.makedirs(ep_dir, exist_ok=True)
    meta = {"kind": "low_level_trajectory", "goal": goal,
            "outcome": {"success": success, "reward": 1.0 if success else 0.0,
                        "response": "", "infeasible": infeasible},
            "metadata": {"difficulty": 1, "tags": ["LOCAL"]}, "step_count": len(steps)}
    json.dump(meta, open(os.path.join(ep_dir, "episode_meta.json"), "w"))
    with open(os.path.join(ep_dir, "episode.jsonl"), "w") as f:
        for st in steps:
            f.write(json.dumps(st) + "\n")
    return ep_dir


def test_system_prompt_is_imported_from_solver_not_duplicated():
    assert SYSTEM is SOLVER_SYS
    assert "report_infeasible" in SYSTEM
    assert "go_back" in SYSTEM


def test_goal_tag_is_stripped_but_rest_of_text_preserved():
    ep_dir = tempfile.mkdtemp()
    steps = [_step(ep_dir, 0, "http://x/wiki", "[1] heading 'Wiki'",
                   "arrived", "send_msg_to_user('done')")]

    examples = episode_to_examples("[MOD] Edit the page by clicking 'Edit page'",
                                    steps, ep_dir, difficulty=1, trajectory_id="ep_0000")

    assert examples[0]["messages"][1]["content"].startswith(
        "GOAL: Edit the page by clicking 'Edit page'")


def test_history_carries_outcome_annotation_matching_solver_format():
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://x/", "[24] link 'Wiki'", "go to wiki", "click('24')"),
        _step(ep_dir, 1, "http://x/wiki", "[7] heading 'Wiki'", "arrived",
             "send_msg_to_user('done')"),
    ]

    examples = episode_to_examples("go to the wiki page", steps, ep_dir,
                                    difficulty=1, trajectory_id="ep_0000")

    assert "- click('24') -> now at http://x/wiki" in examples[1]["messages"][1]["content"]


def test_current_page_prompt_includes_url():
    ep_dir = tempfile.mkdtemp()
    steps = [_step(ep_dir, 0, "http://x/wiki", "[7] heading 'Wiki'",
                   "arrived", "send_msg_to_user('done')")]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1, trajectory_id="ep_0000")

    assert "URL: http://x/wiki" in examples[0]["messages"][1]["content"]


def test_trajectory_and_step_metadata_present():
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://x/", "ax0", "t0", "click('1')"),
        _step(ep_dir, 1, "http://x/2", "ax1", "t1", "send_msg_to_user('done')"),
    ]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=3,
                                    trajectory_id="ep_0042")

    assert [e["trajectory_id"] for e in examples] == ["ep_0042", "ep_0042"]
    assert [e["step_index"] for e in examples] == [0, 1]
    assert all(e["total_steps"] == 2 for e in examples)
    assert all(e["difficulty"] == 3 for e in examples)


def test_error_step_excluded_from_targets_and_from_later_history():
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://x/", "ax0",
             "clicking the submit button [action error: element not found]",
             "click('999')"),
        _step(ep_dir, 1, "http://x/", "ax0", "recovered, clicking something else",
             "click('1')"),
    ]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    targets = [e["step_index"] for e in examples]
    assert 0 not in targets
    assert 1 in targets
    step1_prompt = next(e for e in examples if e["step_index"] == 1)["messages"][1]["content"]
    assert "click('999')" not in step1_prompt


def test_step_after_action_error_carries_last_action_error_block():
    """Prompt parity: when the previous action errored, the live Solver's next
    prompt contains a `LAST ACTION ERROR: ...` block (agents.py:562). The SFT
    prompt omitted it entirely, so the recovery step was trained without the
    evidence that motivated it -- the model learned an unexplained action change
    instead of error recovery, and at eval time repeated one dead action until
    the stuck guard fired (9/57 reddit episodes)."""
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://x/", "ax0",
             "clicking the submit button [action error: bid 999 not found]",
             "click('999')"),
        _step(ep_dir, 1, "http://x/", "ax0", "that bid is invalid, using the real one",
             "click('1')"),
    ]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    step1_prompt = next(e for e in examples if e["step_index"] == 1)["messages"][1]["content"]
    assert "LAST ACTION ERROR: bid 999 not found" in step1_prompt
    # ... and it sits where the live Solver puts it: after history, before URL.
    assert step1_prompt.index("LAST ACTION ERROR") < step1_prompt.index("URL:")


def test_last_action_error_block_absent_when_previous_step_was_clean():
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://x/", "ax0", "open it", "click('24')"),
        _step(ep_dir, 1, "http://x/2", "ax1", "done", "send_msg_to_user('done')"),
    ]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    assert "LAST ACTION ERROR" not in examples[1]["messages"][1]["content"]


def test_off_origin_goto_is_not_a_training_target():
    """A `goto` to a host other than the site being explored is an instant
    reward-0 termination in WebArena (BrowserGym ends the episode). One such
    target survived collection -- goto('https://www.reddit.com/r/AskReddit/')
    against a self-hosted Postmill -- and the fine-tuned model reproduced it in
    10 of 57 reddit eval episodes. The step stays in later history (it really
    did execute, and the live Solver saw it) but must never be imitated."""
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://192.168.1.31:8080/f/pics", "ax0", "open the forum",
             "click('24')"),
        _step(ep_dir, 1, "http://192.168.1.31:8080/f/pics", "ax1", "go to reddit",
             "goto('https://www.reddit.com/r/AskReddit/')"),
        _step(ep_dir, 2, "http://192.168.1.31:8080/f/AskReddit", "ax2", "done",
             "send_msg_to_user('done')"),
    ]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    assert 1 not in [e["step_index"] for e in examples]
    assert [0, 2] == [e["step_index"] for e in examples]
    last_prompt = examples[-1]["messages"][1]["content"]
    assert "goto('https://www.reddit.com/r/AskReddit/')" in last_prompt   # kept in history


def test_same_origin_goto_is_kept_as_a_target():
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://192.168.1.31:8080/f/pics", "ax0", "jump to the forum",
             "goto('http://192.168.1.31:8080/f/AskReddit')"),
        _step(ep_dir, 1, "http://192.168.1.31:8080/f/AskReddit", "ax1", "done",
             "send_msg_to_user('done')"),
    ]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    assert [0, 1] == [e["step_index"] for e in examples]


def test_require_judge_drops_infeasible_episodes():
    """`--require-judge` documents itself as fail-safe: an episode that was
    never judged is dropped, not silently trusted. Infeasible episodes short-
    circuited before that check, and judge_episodes.py never judges them, so
    136 unverified give-ups (23% of the examples) entered the dataset -- 75 of
    them on COMPOSITE tasks, whose reasons were rate limits and misread pages,
    not real impossibility ('askscience forum not found' on a site that has
    it). The fine-tuned model then reported infeasible on 39% of reddit eval
    tasks, matching the 39% give-up rate among COMPOSITE training trajectories."""
    assert _include_episode(success=False, infeasible=True, judge_verified=None,
                            require_judge=True, stop_reason="") is False


def test_infeasible_still_kept_without_require_judge():
    assert _include_episode(success=False, infeasible=True, judge_verified=None,
                            require_judge=False, stop_reason="") is True


def test_require_judge_keeps_judge_confirmed_infeasible():
    assert _include_episode(success=False, infeasible=True, judge_verified=True,
                            require_judge=True, stop_reason="") is True


def test_history_window_capped_at_six_matching_solver():
    ep_dir = tempfile.mkdtemp()
    steps = [_step(ep_dir, i, f"http://x/{i}", f"ax{i}", f"t{i}", f"click('{i}')")
            for i in range(8)]
    steps.append(_step(ep_dir, 8, "http://x/8", "ax8", "done", "send_msg_to_user('done')"))

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    last_prompt = examples[-1]["messages"][1]["content"]
    assert "click('0')" not in last_prompt
    assert "click('1')" not in last_prompt
    assert "click('2') ->" in last_prompt
    assert "click('7') ->" in last_prompt


def test_prefers_thought_v2_over_thought_when_present():
    ep_dir = tempfile.mkdtemp()
    rec = _step(ep_dir, 0, "http://x/wiki", "ax", "original thought",
               "send_msg_to_user('done')")
    rec["thought_v2"] = "State: on the wiki page. original thought"

    examples = episode_to_examples("goal", [rec], ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    assistant = json.loads(examples[0]["messages"][2]["content"])
    assert assistant["thought"] == "State: on the wiki page. original thought"


def test_load_episodes_yields_infeasible_flag():
    run_dir = tempfile.mkdtemp()
    ep_dir = _write_episode_dir(
        run_dir, "ep_0000", "delete another user's account", False, True,
        [_step(os.path.join(run_dir, "episodes", "ep_0000"), 0, "http://x/",
              "ax", "not possible without admin rights",
              "report_infeasible('requires admin rights')")])

    results = list(load_episodes(run_dir))

    assert len(results) == 1
    (goal, steps, yielded_ep_dir, trajectory_id, diff, success, infeasible,
     judge_verified, stop_reason) = results[0]
    assert success is False
    assert infeasible is True
    assert judge_verified is None


def test_report_infeasible_is_a_valid_training_target():
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://x/", "ax0", "checking if this is possible",
             "click('1')"),
        _step(ep_dir, 1, "http://x/settings", "ax1", "requires admin rights, "
             "cannot proceed", "report_infeasible('requires admin rights')"),
    ]

    examples = episode_to_examples("delete another user's account", steps, ep_dir,
                                    difficulty=1, trajectory_id="ep_0000")

    assert len(examples) == 2
    last_assistant = json.loads(examples[-1]["messages"][2]["content"])
    assert last_assistant["action"] == "report_infeasible('requires admin rights')"


def test_include_episode_success_without_require_judge():
    assert _include_episode(success=True, infeasible=False, judge_verified=None,
                            require_judge=False) is True


def test_include_episode_infeasible_included_when_judging_is_not_required():
    """Superseded contract: an unjudged infeasible episode used to be admitted
    even under --require-judge. See test_require_judge_drops_infeasible_episodes
    for why that was the dataset's single largest defect. Without the flag the
    old permissive behavior still stands."""
    assert _include_episode(success=False, infeasible=True, judge_verified=None,
                            require_judge=False) is True


def test_include_episode_require_judge_drops_unjudged_success():
    assert _include_episode(success=True, infeasible=False, judge_verified=None,
                            require_judge=True) is False


def test_include_episode_require_judge_drops_failed_judgment():
    assert _include_episode(success=True, infeasible=False, judge_verified=False,
                            require_judge=True) is False


def test_include_episode_require_judge_keeps_verified_success():
    assert _include_episode(success=True, infeasible=False, judge_verified=True,
                            require_judge=True) is True


def test_include_episode_plain_failure_excluded():
    assert _include_episode(success=False, infeasible=False, judge_verified=None,
                            require_judge=False) is False


def test_page_block_is_capped_like_the_live_solver():
    ep_dir = tempfile.mkdtemp()
    long_axtree = "x" * 7000
    steps = [_step(ep_dir, 0, "http://x/wiki", long_axtree,
                   "arrived", "send_msg_to_user('done')")]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    prompt = examples[0]["messages"][1]["content"]
    assert "TRUNCATED" in prompt
    assert len(prompt) < 7000 + 500   # not the raw 7000-char tree


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
