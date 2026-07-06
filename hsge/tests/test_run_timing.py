"""run() must log timing (start/end/per-node duration) and, on an unhandled
exception, a run_error record with elapsed time and which node it happened on
-- while still re-raising the exception exactly as before (the run stops the
same way; only a log record is added first)."""

import json

import pytest

from hsge.llm import HashingEmbedder
from hsge.webarena.runtime import WebArenaExplorer


class _NeverCalledLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        raise AssertionError("LLM must not be called before the browser factory raises")


def _raising_browser_factory(url):
    raise RuntimeError("boom")


def test_run_logs_run_error_and_reraises(tmp_path):
    explorer = WebArenaExplorer(
        browser_factory=_raising_browser_factory,
        llm=_NeverCalledLLM(),
        embedder=HashingEmbedder(),
        out_dir=str(tmp_path),
        allow_pattern=".*",
    )

    with pytest.raises(RuntimeError, match="boom"):
        explorer.run("http://example.com")

    log_records = [json.loads(line) for line in open(tmp_path / "run_log.jsonl")]
    events = [r["event"] for r in log_records]
    assert "run_start" in events
    assert "run_error" in events

    start_rec = next(r for r in log_records if r["event"] == "run_start")
    assert isinstance(start_rec["started_at_epoch"], float)
    assert isinstance(start_rec["started_at_iso"], str)

    error_rec = next(r for r in log_records if r["event"] == "run_error")
    assert error_rec["error"] == "boom"
    assert error_rec["error_type"] == "RuntimeError"
    assert error_rec["last_node_index"] == 1
    assert error_rec["last_node_url"] == "http://example.com"
    assert error_rec["duration_sec"] >= 0

    summary = json.load(open(tmp_path / "summary.json"))
    assert summary["status"] == "error"
    assert summary["error"] == "boom"
    assert summary["duration_sec"] >= 0
    assert summary["ended_at_epoch"] is not None
