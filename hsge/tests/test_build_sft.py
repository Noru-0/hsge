"""build_sft_dataset gates on verification: by default only verified GEN
episodes are kept (self-reported LOCAL successes need --include-local)."""
import json

from hsge.schema import Step
from hsge.webarena.recording import record_episode
from build_sft_dataset import build


def _mk(tmp_path, idx, tag, success, extra=None, difficulty=1):
    record_episode(str(tmp_path), idx, f"goal {idx}",
                   [Step(action="click('1')", url="u", obs_summary="t", axtree="ax")],
                   ["ax"], [None], success, difficulty, tag, extra_meta=extra)


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
