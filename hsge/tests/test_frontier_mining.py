"""Frontier href-mining + template-priority (docs/superpowers/specs/
2026-07-07-frontier-href-mining-design.md).

Covers the two behaviors that keep a run from starving the frontier early
without flooding it: (1) `_url_template` groups same-kind pages so the cap can
bound them; (2) with no navigating episodes at all, mined <a href> links alone
grow the frontier, and the per-template cap limits how many near-identical pages
get visited; the master toggle reproduces the old navigated-only behavior.
"""

import json

from hsge.llm import HashingEmbedder
from hsge.webarena.runtime import WebArenaExplorer


def test_url_template_wildcards_ids_keeps_type_segments():
    t = WebArenaExplorer._url_template
    # digit-bearing id/slug segments collapse to '*'
    assert t("http://site/f/AskReddit/comments/12345/some-title") == "site/f/AskReddit/comments/*/*"
    assert t("http://site/user/alice/comments") == "site/user/alice/comments"
    # query/fragment dropped; two posts in the same forum share a template
    a = t("http://site/f/gaming/comments/7/a?sort=hot#c")
    b = t("http://site/f/gaming/comments/99/b")
    assert a == b == "site/f/gaming/comments/*/*"
    # different forums stay different templates (type segment preserved)
    assert t("http://site/f/gaming/x1") != t("http://site/f/news/x1")


class _NoTasksLLM:
    """PageExplorer proposes nothing, so no Solver episodes run -- the frontier
    can only grow from mined hrefs, isolating tier-1 behavior."""

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"tasks": []}


class _MiningBrowser:
    """Every page exposes the same 5 same-template + 2 distinct-template hrefs.
    axtree embeds the URL so distinct URLs never collide on content-dedup."""

    HREFS = ([f"http://site/item/{i}" for i in range(5)]      # template site/item/*
             + [f"http://site/cat/{j}" for j in range(2)])    # template site/cat/*

    def __init__(self, url):
        self.url = url

    def reset(self):
        return {"url": self.url, "axtree": f"page {self.url}", "bids": []}

    def links(self):
        return []

    def page_hrefs(self, limit=100):
        return self.HREFS[:limit]

    def close(self):
        pass


def _run(tmp_path, **kw):
    explorer = WebArenaExplorer(
        browser_factory=_MiningBrowser,
        llm=_NoTasksLLM(),
        embedder=HashingEmbedder(),
        out_dir=str(tmp_path),
        allow_pattern=r"http://site",
        max_nodes=50, max_depth=10, terminal_goal=None,
        **kw,
    )
    explorer.run("http://site/home")
    return [n for n in json.load(open(tmp_path / "nodes.json")) if not n.get("duplicate")]


def test_mined_hrefs_grow_frontier_and_cap_limits_templates(tmp_path):
    nodes = _run(tmp_path, mine_hrefs=True, per_template_cap=2)
    urls = [n["url"] for n in nodes]
    tmpl = WebArenaExplorer._url_template

    # frontier grew purely from mining (no episodes navigated anywhere)
    assert len(urls) > 1
    # the flooded template is capped at 2 despite 5 candidate hrefs
    assert sum(1 for u in urls if tmpl(u) == "site/item/*") == 2
    # the distinct template is explored too, within its own cap
    assert sum(1 for u in urls if tmpl(u) == "site/cat/*") == 2


def test_mine_hrefs_toggle_off_reproduces_navigated_only(tmp_path):
    # no episodes + no mining => frontier never grows past the root
    nodes = _run(tmp_path, mine_hrefs=False)
    assert [n["url"] for n in nodes] == ["http://site/home"]
