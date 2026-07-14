"""run() must log timing (start/end/per-node duration) and, on an unhandled
exception, a run_error record with elapsed time and which node it happened on
-- while still re-raising the exception exactly as before (the run stops the
same way; only a log record is added first).

The failure is injected in PageExplorer's LLM call, not browser_factory/
reset(): a browser navigation failure (flaky/slow/unreachable URL) is now
caught and skipped per-node (see test_node_error_resilience.py) rather than
crashing the whole run, so this test's "still crashes on an unhandled
exception" contract needs a genuinely unexpected failure point instead."""

import json

import pytest

from hsge.llm import HashingEmbedder
from hsge.webarena.runtime import WebArenaExplorer


class _RaisingLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        raise RuntimeError("boom")


class _StubBrowser:
    def __init__(self, url):
        self.url = url

    def reset(self):
        return {"url": self.url, "axtree": "page", "bids": []}

    def links(self):
        return []

    def page_hrefs(self, limit=100):
        return []

    def close(self):
        pass


def test_run_logs_run_error_and_reraises(tmp_path):
    explorer = WebArenaExplorer(
        browser_factory=_StubBrowser,
        llm=_RaisingLLM(),
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
