"""build_sft_dataset.py: prompt parity with the live Solver, outcome- and
prior-thought-annotated history, GOAL tag stripping, trajectory/step
metadata, and exclusion of steps whose action errored at collection time.

Run:  python -m pytest hsge/tests/test_build_sft_dataset.py -q
 (or) PYTHONPATH=. python hsge/tests/test_build_sft_dataset.py
"""
import json
import os
import tempfile

from build_sft_dataset import SYSTEM, episode_to_examples
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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
