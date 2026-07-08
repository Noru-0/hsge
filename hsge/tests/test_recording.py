"""record_episode writes the run-dir episode layout build_sft_dataset.py reads,
and merges extra_meta (verified/task_id/eval) into episode_meta.json."""
import json

from hsge.schema import Step
from hsge.webarena.recording import record_episode


def test_record_episode_writes_meta_steps_and_extra_meta(tmp_path):
    steps = [Step(action="click('1')", url="http://s/a", obs_summary="go", axtree="ax1"),
             Step(action="send_msg_to_user('done: 45')", url="http://s/b",
                  obs_summary="answer", axtree="ax2")]
    ep_id = record_episode(str(tmp_path), 7, "find the count", steps,
                           ["ax1", "ax2"], [None, None], True, 3, "GEN",
                           extra_meta={"task_id": "gen_0001", "verified": True,
                                       "answer": "45"})
    assert ep_id == "ep_0007"
    ep = tmp_path / "episodes" / ep_id
    meta = json.load(open(ep / "episode_meta.json"))
    assert meta["goal"] == "find the count"
    assert meta["outcome"]["success"] is True
    assert meta["metadata"] == {"difficulty": 3, "tags": ["GEN"]}
    assert meta["task_id"] == "gen_0001" and meta["verified"] is True
    assert meta["answer"] == "45"
    lines = [json.loads(l) for l in open(ep / "episode.jsonl")]
    assert [l["parsed_action"] for l in lines] == ["click('1')", "send_msg_to_user('done: 45')"]
    assert (ep / "page_state" / "step_000_axtree.txt").read_text() == "ax1"


def test_record_episode_no_extra_meta_matches_legacy_shape(tmp_path):
    ep_id = record_episode(str(tmp_path), 0, "g", [Step(action="a", url="u", axtree="x")],
                           ["x"], [None], False, 1, "LOCAL")
    meta = json.load(open(tmp_path / "episodes" / ep_id / "episode_meta.json"))
    assert set(meta) == {"kind", "goal", "outcome", "metadata", "step_count"}
    assert meta["outcome"]["reward"] == 0.0


def test_step_carries_hints_and_last_error_defaults():
    from hsge.schema import Step
    s = Step(action="click('1')", url="u", axtree="ax")
    assert s.hints == ""
    assert s.last_error == ""


def test_step_accepts_hints_and_last_error_explicitly():
    from hsge.schema import Step
    s = Step(action="click('1')", url="u", axtree="ax",
              hints="KNOWN PROCEDURES: ...", last_error="TimeoutError: click failed")
    assert s.hints == "KNOWN PROCEDURES: ..."
    assert s.last_error == "TimeoutError: click failed"
