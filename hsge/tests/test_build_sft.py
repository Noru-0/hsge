"""build_sft_dataset gates on verification (only verified GEN episodes are
kept by default) and rebuilds each example's prompt via the same
build_solver_prompt() Solver.solve() uses live, so training data matches
what the Solver actually saw."""
import json

from hsge.schema import Step
from hsge.webarena.agents import SOLVER_SYS, build_solver_prompt
from hsge.webarena.recording import record_episode
from build_sft_dataset import build, episode_to_examples, load_episodes


def _mk(tmp_path, idx, tag, success, extra=None, difficulty=1, steps=None):
    steps = steps or [Step(action="click('1')", url="u", axtree="ax", hints="", last_error="")]
    record_episode(str(tmp_path), idx, f"goal {idx}", steps,
                   [s.axtree for s in steps], [None] * len(steps),
                   success, difficulty, tag, extra_meta=extra)


def test_default_keeps_only_verified_gen(tmp_path):
    _mk(tmp_path, 0, "GEN", True, {"task_id": "gen_0000", "verified": True}, difficulty=3)
    _mk(tmp_path, 1, "GEN", False, {"task_id": "gen_0001", "verified": False})
    _mk(tmp_path, 2, "LOCAL", True)
    out = tmp_path / "train.jsonl"
    stats = build(str(tmp_path), str(out))
    assert stats["kept"] == 1
    (ex,) = [json.loads(l) for l in open(out)]
    assert ex["difficulty"] == 3


def test_include_local_admits_self_reported_successes(tmp_path):
    _mk(tmp_path, 0, "GEN", True, {"task_id": "gen_0000", "verified": True})
    _mk(tmp_path, 1, "LOCAL", True)
    _mk(tmp_path, 2, "LOCAL", False)     # failures never enter
    stats = build(str(tmp_path), str(tmp_path / "t.jsonl"), include_local=True)
    assert stats["kept"] == 2


def test_example_messages_match_build_solver_prompt_exactly(tmp_path):
    steps = [Step(action="click('1')", url="http://s/a", axtree="[1] link 'next'",
                   hints="try the nav menu", last_error="")]
    _mk(tmp_path, 0, "LOCAL", True, steps=steps)
    examples = episode_to_examples("find the price", [
        {"action": "click('1')", "url": "http://s/a", "hints": "try the nav menu",
         "last_error": "", "observation": {"axtree_txt": {"path": "page_state/step_000_axtree.txt"}}},
    ], str(tmp_path / "episodes" / "ep_0000"), difficulty=1)

    expected_prompt = build_solver_prompt("find the price", "try the nav menu", [], [],
                                          "", "http://s/a", "[1] link 'next'")
    assert examples == [{
        "messages": [
            {"role": "system", "content": SOLVER_SYS},
            {"role": "user", "content": expected_prompt},
            {"role": "assistant", "content": "click('1')"},
        ],
        "difficulty": 1,
    }]


def test_history_uses_bare_parsed_action_not_json_blob(tmp_path):
    # record_episode writes "action" as a JSON blob ({"thought":..., "action":...})
    # but "parsed_action" as the bare action string -- that bare string is what
    # live Solver.solve() actually appends to its own history and what shows up
    # in the real RECENT ACTIONS section of the prompt. episode_to_examples must
    # replay history with the bare string, not the JSON blob, to match inference.
    steps = [
        Step(action="click('1')", url="http://s/a", axtree="[1] link 'next'",
             hints="", last_error="", obs_summary="open the link"),
        Step(action="fill('2', 'x')", url="http://s/b", axtree="[2] textbox",
             hints="", last_error="", obs_summary="fill the box"),
    ]
    _mk(tmp_path, 0, "LOCAL", True, steps=steps)

    (goal, loaded_steps, ep_dir, diff, meta), = list(load_episodes(str(tmp_path)))
    examples = episode_to_examples(goal, loaded_steps, ep_dir, diff)

    assert len(examples) == 2
    recent = examples[1]["messages"][1]["content"]
    assert "click('1')" in recent
    assert '"thought"' not in recent


def test_step_missing_prompt_fidelity_fields_is_skipped(tmp_path):
    # Simulates a pre-change episode: no "hints"/"last_error"/"url" keys at all.
    legacy_steps = [{"action": "click('1')", "parsed_action": "click('1')",
                     "observation": {"axtree_txt": {"path": "page_state/step_000_axtree.txt"}}}]
    examples = episode_to_examples("goal", legacy_steps, str(tmp_path), difficulty=1)
    assert examples == []


def test_error_step_is_excluded_from_next_steps_history():
    # step 0 (click('nav')) succeeds -- proven by step 1's last_error being "".
    # step 1 (click('bad')) fails -- proven by step 2's last_error being set.
    # step 2's prompt must show the failure and must list click('nav') but not
    # click('bad') in RECENT ACTIONS.
    steps = [
        {"action": "click('nav')", "url": "http://s/a", "hints": "", "last_error": "",
         "observation": {}},
        {"action": "click('bad')", "url": "http://s/b", "hints": "", "last_error": "",
         "observation": {}},
        {"action": "send_msg_to_user('done')", "url": "http://s/b", "hints": "",
         "last_error": "element not found", "observation": {}},
    ]
    examples = episode_to_examples("goal", steps, "/nonexistent", difficulty=1)
    assert len(examples) == 3
    recent = examples[2]["messages"][1]["content"]
    assert "LAST ACTION ERROR: element not found" in recent
    assert "click('nav')" in recent
    assert "click('bad')" not in recent
