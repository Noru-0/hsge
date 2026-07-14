"""A single node whose browser fails to load (real-world example: Playwright
`Page.goto` timing out on a slow/unreachable mined URL) must not crash the
whole exploration run. Regression for a real run where a gitlab tree page
timed out on `browser.reset()` and killed a multi-hour exploration with an
uncaught TimeoutError propagating out of `WebArenaExplorer.run()`.
"""
import json

from hsge.llm import HashingEmbedder
from hsge.webarena.runtime import WebArenaExplorer


class _NoTasksLLM:
    """PageExplorer proposes nothing, so the frontier only grows from mined
    hrefs -- isolates the node-error path from Solver/task machinery."""

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"tasks": []}


class _FlakyBrowser:
    """reset() raises for one specific URL (simulating a real navigation
    timeout), succeeds normally for every other URL."""

    FAIL_URL = "http://site/broken"

    def __init__(self, url):
        self.url = url

    def reset(self):
        if self.url == self.FAIL_URL:
            raise TimeoutError("Page.goto: Timeout 10000ms exceeded.")
        return {"url": self.url, "axtree": f"page {self.url}", "bids": []}

    def links(self):
        return []

    def page_hrefs(self, limit=100):
        if self.url == "http://site/home":
            return ["http://site/broken", "http://site/ok"]
        return []

    def close(self):
        pass


class _FailsToConstructBrowser:
    """browser_factory() itself raises for one URL (simulating a browser
    launch failure), before reset() is ever reached."""

    FAIL_URL = "http://site/broken"

    def __init__(self, url):
        if url == self.FAIL_URL:
            raise RuntimeError("failed to launch browser context")
        self.url = url

    def reset(self):
        return {"url": self.url, "axtree": f"page {self.url}", "bids": []}

    def links(self):
        return []

    def page_hrefs(self, limit=100):
        if self.url == "http://site/home":
            return ["http://site/broken", "http://site/ok"]
        return []

    def close(self):
        pass


def _run(tmp_path, browser_cls):
    explorer = WebArenaExplorer(
        browser_factory=browser_cls, llm=_NoTasksLLM(), embedder=HashingEmbedder(),
        out_dir=str(tmp_path), allow_pattern=r"http://site",
        max_nodes=50, max_depth=10, terminal_goal=None, mine_hrefs=True)
    explorer.run("http://site/home")
    return json.load(open(tmp_path / "nodes.json"))


def test_reset_failure_on_one_node_does_not_crash_the_run(tmp_path):
    nodes = _run(tmp_path, _FlakyBrowser)

    urls = [n["url"] for n in nodes]
    assert "http://site/ok" in urls           # exploration continued past the failure

    failed = [n for n in nodes if n["url"] == _FlakyBrowser.FAIL_URL]
    assert len(failed) == 1
    assert failed[0].get("error")             # failure recorded, not silently dropped
    assert failed[0]["duplicate"] is False


def test_browser_construction_failure_on_one_node_does_not_crash_the_run(tmp_path):
    nodes = _run(tmp_path, _FailsToConstructBrowser)

    urls = [n["url"] for n in nodes]
    assert "http://site/ok" in urls

    failed = [n for n in nodes if n["url"] == _FailsToConstructBrowser.FAIL_URL]
    assert len(failed) == 1
    assert failed[0].get("error")


def test_summary_status_is_done_not_error_after_a_recovered_node_failure(tmp_path):
    _run(tmp_path, _FlakyBrowser)

    summary = json.load(open(tmp_path / "summary.json"))
    assert summary["status"] == "done"


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
