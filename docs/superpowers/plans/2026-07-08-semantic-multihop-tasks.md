# Semantic Multi-Hop Tasks (Part B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSGE's phase-2 generated tasks genuinely multi-hop (BFS-verified
navigation, not self-reported) and diversify the type mix (quota, dedup, MOD
variety), so verified GEN episodes carry longer, richer trajectories for SFT.

**Architecture:** All enforcement is code-side inside `hsge/webarena/composer.py`'s
`validate_task`/`TaskComposer.generate()` — "code shapes the semantics, the LLM
only phrases." `real_hops` (a BFS distance over the SiteKB link graph) replaces
the LLM's self-reported `hops` as the SFT `difficulty` signal. A new
comparison-task generator adds the pipeline's first genuine two-source INFO
shape. `hsge/webarena/collect.py`'s `GenerationRunner` gains a site-map hint to
offset the verified-rate cost of forcing INFO/NAV to start far from their
answer.

**Tech Stack:** Python 3, pytest, no new dependencies (reuses the project's
existing `Embedder`/cosine-similarity convention already used by
`hsge/predicate_registry.py` and `hsge/webarena/collect.py`'s
`top_k_skill_hints`).

**Spec:** `docs/superpowers/specs/2026-07-07-semantic-multihop-tasks-design.md`

## Global Constraints

- All code, comments, docstrings, and commit messages in English.
- TDD: write the failing test before the implementation in every task.
- The full existing suite (`python -m pytest hsge/tests/ -q`) must stay green
  after every task — this plan touches heavily-shared fixtures
  (`test_composer.py::_kb()`), so re-run the whole file, not just new tests.
- No new dependencies; reuse `hsge.llm.Embedder`'s `encode(texts) -> np.ndarray`
  (L2-normalized, so cosine similarity is a plain dot product — see
  `hsge/webarena/collect.py`'s `top_k_skill_hints` for the existing pattern).
- Config precedence stays CLI flag > `config.yaml` > built-in `DEFAULTS` dict
  in `run_webarena.py`. No secrets in `config.yaml`.
- Commit after each task (see each task's final step).

## Resolved open questions (from the spec, decided here)

- **Rebalanced type quota:** `INFO: 40, NAV: 20, MOD: 40`.
- **Depth budget:** minimum 50% of accepted tasks must have `real_hops >= 2`
  (`min_hops2_share = 0.5`), enforced globally across all types, not per-type.
- **Far-start override:** both **INFO and NAV** get `start_url` forced to
  `kb.site`; MOD keeps its LLM-proposed `start_url` (its trajectories are
  already long; forcing it isn't needed and would fight the existing
  `MOD target collides` dedup which is keyed by URL).
- **Site-map hint:** one example URL per URL-template (reusing
  `WebArenaExplorer._url_template`), capped at 15 lines.
- **`intent_sim` threshold:** `0.6`, matching the project's existing
  cosine-threshold convention (`hsge/clustering.py`'s `OnlineClusterer`
  default, `config.yaml`'s `predicate_sim: 0.6`) — not "PageExplorer's",
  which turns out to use plain string normalization, not embeddings, once you
  read `hsge/webarena/agents.py::PageExplorer._seen` closely.
- **Run_05 MOD inspection:** already done (see spec's "Caveat, now
  root-caused" section) — Task 6 below implements the fix directly, no
  separate investigation task needed.

---

### Task 1: `real_hops` — computed BFS distance replaces self-reported `hops`

**Files:**
- Modify: `hsge/webarena/composer.py`
- Modify: `hsge/webarena/collect.py:146`
- Test: `hsge/tests/test_composer.py`
- Test: `hsge/tests/test_collect.py`

**Interfaces:**
- Produces: `build_link_graph(kb) -> dict[str, set[str]]`, `real_hops(task: dict, kb, graph: dict[str, set[str]]) -> int | None`, `validate_task(task, kb, accepted, graph: dict | None = None) -> str | None` (new optional 4th param, backward compatible), `TaskComposer.generate()` restructured around a local `try_accept(t: dict) -> bool` closure that later tasks extend.

- [ ] **Step 1: Write the failing tests**

Add to `hsge/tests/test_composer.py`. First, replace `_kb()` so `kb.site`
("http://s") is itself a real graph vertex — every existing INFO/NAV/MOD test
in this file already sets `start_url` to `"http://s"`, so this fixture change
is what makes the BFS graph connect from the root, not a workaround:

```python
def _kb():
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 0, "url": "http://s", "page_type": "home",
                 "title": "home", "outlinks": ["http://s/f/gaming", "http://s/f/movies"],
                 "entities": [], "facts": []})
    kb.add_node({"node_index": 1, "url": "http://s/f/gaming",
                 "page_type": "forum", "title": "gaming",
                 "outlinks": ["http://s/f/gaming/post1", "http://s",
                              "http://s/f/gaming/15/a-slug"],
                 "entities": [{"type": "post", "name": "Best budget GPU",
                               "attrs": {"author": "hlz0"}, "grounded": True,
                               "evidence": "Best budget GPU submitted by hlz0"}],
                 "facts": [{"q": "top post?", "a": "Best budget GPU",
                            "grounded": True,
                            "evidence": "top post 'Best budget GPU'"},
                           {"q": "mods?", "a": "bob", "grounded": False,
                            "evidence": "moderated by bob"}]})
    kb.add_node({"node_index": 2, "url": "http://s/f/movies", "page_type": "forum",
                 "title": "movies", "outlinks": [],
                 "entities": [{"type": "post", "name": "Dune review",
                               "attrs": {}, "grounded": True,
                               "evidence": "Dune review"}], "facts": []})
    return kb
```

Then append new tests at the end of the file:

```python
def test_build_link_graph_and_real_hops():
    from hsge.webarena.composer import build_link_graph, real_hops
    kb = _kb()
    graph = build_link_graph(kb)
    assert graph["http://s"] == {"http://s/f/gaming", "http://s/f/movies"}
    info = _info(["n1.e0.attrs.author"], {"exact_match": "hlz0"})  # start_url "http://s"
    assert real_hops(info, kb, graph) == 1        # http://s -> http://s/f/gaming
    nav = {"type": "NAV", "start_url": "http://s",
           "eval": {"reference_url": "http://s/f/gaming/post1"}}
    assert real_hops(nav, kb, graph) == 2          # http://s -> gaming -> post1
    mod_last = {"type": "MOD", "start_url": "http://s",
                "eval": {"program_html": [{"url": "last"}]}}
    assert real_hops(mod_last, kb, graph) == 0     # no real target -> trivially 0
    unreachable = {"type": "NAV", "start_url": "http://s",
                   "eval": {"reference_url": "http://s/f/movies/9/re"}}
    assert real_hops(unreachable, kb, graph) is None


def test_validate_task_rejects_unreachable_target():
    kb = _kb()
    nav = {"intent": "go to a page nothing links to", "type": "NAV",
           "start_url": "http://s", "hops": 1, "source_nodes": [1],
           "answer_fact_refs": [],
           "eval": {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/f/movies", "program_html": []}}
    kb.add_node({"node_index": 3, "url": "http://s/f/movies/9/re",
                 "outlinks": [], "entities": [], "facts": [
                     {"q": "?", "a": "x", "grounded": True, "evidence": "x here"}]})
    unreachable = dict(nav, eval=dict(nav["eval"], reference_url="http://s/f/movies/9/re"))
    # not linked from anywhere in the KB -> unreachable
    assert "unreachable" in validate_task(unreachable, kb, [])


def test_validate_task_rejects_info_zero_hop_start():
    kb = _kb()
    info = _info(["n1.e0.attrs.author"], {"exact_match": "hlz0"})
    # start_url IS the answer page itself -> 0 real hops, must be rejected
    zero_hop = dict(info, start_url="http://s/f/gaming")
    assert "0 real hops" in validate_task(zero_hop, kb, [])
    # start_url = site root (kb.site) -> 1 real hop, passes
    assert validate_task(info, kb, []) is None


def test_generate_forces_info_start_url_to_site_root_and_sets_real_hops():
    class _LLM:
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            return {"tasks": [
                dict(_info_task("find the author of the top gaming post"),
                     start_url="http://s/f/gaming"),      # LLM proposed the answer page itself
            ]}
    comp = TaskComposer(_LLM(), _kb(), quota={"INFO": 5, "NAV": 0, "MOD": 0})
    accepted, rejected = comp.generate()
    # the override happens BEFORE validation, so start_url is forced back to
    # "http://s" (the site root) regardless of what the LLM proposed, giving
    # a real BFS distance of 1 hop (http://s -> http://s/f/gaming) instead of
    # the LLM's claimed 2 -- and instead of the 0-hop rejection it would have
    # gotten had the LLM's own start_url been trusted
    assert len(accepted) == 1
    assert accepted[0]["start_url"] == "http://s"
    assert accepted[0]["hops"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_composer.py -v`
Expected: `build_link_graph`/`real_hops` tests FAIL with `ImportError` (names
don't exist yet); `validate_task` tests FAIL because no "unreachable"/"0 real
hops" reason is ever returned; several **pre-existing** tests in the file
(`test_validate_info_gates`, `test_validate_nav_mod_and_dedup`,
`test_generate_assigns_ids_and_collects_rejections`, etc.) will also show
different pass/fail behavior once `_kb()` changes — that's expected and
addressed in Step 4; confirm none of them are failing for a reason unrelated
to the fixture change (e.g. a typo).

- [ ] **Step 3: Implement `build_link_graph`, `real_hops`, and wire into `validate_task`**

In `hsge/webarena/composer.py`, add `from collections import deque` to the
imports, then add these functions after `_mod_target_urls` and before
`sample_bundles`:

```python
def build_link_graph(kb) -> dict[str, set[str]]:
    """url -> outlink urls, directly from SiteKB nodes (the same adjacency
    sample_bundles' link-neighborhoods use). The BFS graph for `real_hops`."""
    graph: dict[str, set[str]] = {}
    for n in kb.nodes:
        u = n.get("url")
        if u:
            graph.setdefault(u, set()).update(n.get("outlinks") or [])
    return graph


def _bfs_hops(graph: dict[str, set[str]], start: str, target: str) -> int | None:
    """Shortest #hops from start to target over `graph`, or None if
    unreachable. 0 when start == target."""
    if start == target:
        return 0
    seen = {start}
    queue = deque([(start, 0)])
    while queue:
        u, d = queue.popleft()
        for v in graph.get(u, ()):
            if v == target:
                return d + 1
            if v not in seen:
                seen.add(v)
                queue.append((v, d + 1))
    return None


def _target_urls(task: dict, kb) -> list[str]:
    """URLs the task's answer/target must be reached at, by type."""
    ttype = task.get("type")
    if ttype == "INFO":
        urls = [kb.node_url_of_ref(r) for r in task.get("answer_fact_refs") or []]
    elif ttype == "NAV":
        ref = (task.get("eval") or {}).get("reference_url")
        urls = [ref] if ref else []
    elif ttype == "MOD":
        urls = [p.get("url") for p in (task.get("eval") or {}).get("program_html") or []]
    else:
        urls = []
    return [u for u in urls if u and u != "last"]


def real_hops(task: dict, kb, graph: dict[str, set[str]]) -> int | None:
    """Ground truth for `hops`/SFT difficulty: the actual BFS distance the
    Solver must traverse from `start_url` to reach every target the task's
    eval checks -- never the LLM's self-reported claim. None if any target
    is unreachable through known links (the task is unwinnable as
    specified)."""
    start = task.get("start_url") or kb.site
    targets = _target_urls(task, kb)
    if not targets:
        return 0
    dists = [_bfs_hops(graph, start, t) for t in targets]
    if any(d is None for d in dists):
        return None
    return max(dists)
```

Change `validate_task`'s signature and add the graph-based gates. The full
updated function:

```python
def validate_task(task, kb, accepted: list[dict], graph: dict | None = None) -> str | None:
    """Rejection reason, or None when the task passes every code gate."""
    if not isinstance(task, dict):
        return "not an object"
    intent = str(task.get("intent") or "")
    ttype = task.get("type")
    if ttype not in ("INFO", "NAV", "MOD"):
        return "bad type"
    if not intent.strip():
        return "empty intent"
    key = _norm_intent(intent)
    if any(_norm_intent(a.get("intent", "")) == key for a in accepted):
        return "duplicate intent"
    if RELATIVE_TIME_RE.search(intent):
        return "relative-time reference in intent"
    graph = graph if graph is not None else build_link_graph(kb)
    ev = task.get("eval") or {}
    types = ev.get("eval_types") or []
    if ttype == "INFO":
        if INFO_META_RE.search(intent):
            return "site-mechanics INFO intent"
        if "string_match" not in types:
            return "INFO without string_match"
        refs = task.get("answer_fact_refs") or []
        if not refs:
            return "INFO without answer_fact_refs"
        resolved, evidences = [], []
        for r in refs:
            got = kb.resolve_ref(r)
            if got is None:
                return f"unknown ref {r}"
            val, grounded = got
            if not grounded:
                return f"ungrounded ref {r}"
            resolved.append(normalize_answer(val))
            evidences.append(normalize_answer(kb.resolve_ref_evidence(r) or ""))
        ra = ev.get("reference_answers") or {}
        targets = ([ra["exact_match"]] if "exact_match" in ra
                   else ra.get("must_include") or [])
        if not targets:
            return "INFO without reference answer"
        for t in targets:
            nt = normalize_answer(str(t))
            if not any(nt == v or nt in v for v in resolved):
                return f"reference answer {t!r} not backed by refs"
            if not any(nt in e for e in evidences if e):
                return f"reference answer {t!r} not inside cited evidence"
        rh = real_hops(task, kb, graph)
        if rh is None:
            return "target unreachable from start_url"
        if rh < 1:
            return "INFO start_url is the answer page (0 real hops)"
    elif ttype == "NAV":
        if "url_match" not in types:
            return "NAV without url_match"
        if ev.get("reference_url") not in kb.known_urls():
            return "reference_url not in SiteKB"
        if url_key(ev.get("reference_url") or "") == url_key(
                task.get("start_url") or kb.site):
            return "NAV reference_url equals start_url"
        if real_hops(task, kb, graph) is None:
            return "target unreachable from start_url"
    else:  # MOD
        if MOD_DENY_RE.search(intent):
            return "destructive MOD intent"
        if MOD_READONLY_RE.search(intent):
            return "read-only intent typed as MOD"
        if "program_html" not in types or not ev.get("program_html"):
            return "MOD without program_html"
        ni = normalize_answer(intent)
        known = kb.known_urls()
        for spec in ev.get("program_html") or []:
            if spec.get("locator"):
                return "MOD locator must be empty (whole-page check)"
            url = spec.get("url") or "last"
            if url != "last" and url not in known:
                return "MOD program_html url not in SiteKB"
            required = (spec.get("required_contents") or {}).get("must_include") or []
            if not required:
                return "MOD without must_include"
            for s in required:
                if normalize_answer(str(s)) not in ni:
                    return f"must_include {s!r} not quoted in intent"
        mine = _mod_target_urls(task)
        for a in accepted:
            if a.get("type") == "MOD" and mine & _mod_target_urls(a):
                return "MOD target collides with an accepted MOD task"
        if real_hops(task, kb, graph) is None:
            return "target unreachable from start_url"
    return None
```

Now restructure `TaskComposer.generate()` around a `try_accept` closure (this
is what later tasks extend rather than re-editing the bundle loop each time):

```python
    def generate(self) -> tuple[list[dict], list[dict]]:
        accepted: list[dict] = []
        rejected: list[dict] = []
        remaining = dict(self.quota)
        graph = build_link_graph(self.kb)

        def try_accept(t) -> bool:
            if not isinstance(t, dict) or remaining.get(t.get("type"), 0) <= 0:
                rejected.append({"task": t, "reason": "quota exhausted for type"})
                return False
            t.setdefault("start_url", self.kb.site)
            if t.get("type") in ("INFO", "NAV"):
                t["start_url"] = self.kb.site
            reason = validate_task(t, self.kb, accepted, graph=graph)
            if reason:
                rejected.append({"task": t, "reason": reason})
                return False
            t["task_id"] = f"gen_{len(accepted):04d}"
            t["hops"] = real_hops(t, self.kb, graph)
            accepted.append(t)
            remaining[t["type"]] -= 1
            return True

        for bundle in sample_bundles(self.kb, self.rng):
            if all(v <= 0 for v in remaining.values()):
                break
            prompt = (f"SITE: {self.kb.site}\nQUOTA REMAINING: {remaining}\n"
                      f"PREFERRED HOPS: {self.hops[0]}-{self.hops[1]}\n\n"
                      f"SITE KNOWLEDGE (this bundle):\n{self._render_bundle(bundle)}\n\n"
                      "ALREADY GENERATED:\n"
                      + ("\n".join(f"- {a['intent']}" for a in accepted[-30:]) or "(none)")
                      + f"\n\nGenerate up to {self.tasks_per_call} tasks from THIS bundle.")
            out = self.llm.complete_json(COMPOSER_SYS, prompt) or {}
            for t in out.get("tasks") or []:
                try_accept(t)
        return accepted, rejected
```

Fix the `difficulty` computation in `hsge/webarena/collect.py:146` — `hops`
can now legitimately be `0`, and `task.get("hops") or 1` incorrectly coerces
`0` to `1` (Python's `or` treats `0` as falsy). Change:

```python
                verified, difficulty=int(task.get("hops") or 1), tag="GEN",
```

to:

```python
                verified, difficulty=int(task.get("hops", 1)), tag="GEN",
```

(`dict.get`'s own default only applies when the key is *missing*, not when
its value is falsy — so a present `hops: 0` now survives correctly.)

- [ ] **Step 4: Run tests, verify the full suite**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_composer.py hsge/tests/test_collect.py -v`
Expected: all PASS, including every pre-existing test in both files (the
`_kb()` fixture change and the new gates must not break
`test_validate_info_gates`, `test_validate_nav_mod_and_dedup`,
`test_sample_bundles_links_and_types`, `test_validate_mod_self_verifying_gates`,
`test_validate_nav_rejects_self_referential_target`,
`test_relative_time_and_site_mechanics_gates`,
`test_info_reference_must_be_inside_cited_evidence` — trace through each by
hand if any fails: most existing NAV/MOD assertions are rejected by an
*earlier* gate than the new reachability check, so they should be unaffected;
if one now fails on "unreachable"/"0 real hops" instead of its original
reason, add the missing edge to that test's local kb rather than loosening
the new gate).

Add a difficulty-fix regression test to `hsge/tests/test_collect.py` (after
`test_dump_stats_does_not_clobber_existing_summary_keys`):

```python
def test_zero_hops_task_records_difficulty_zero(tmp_path):
    # a task with real_hops == 0 (e.g. a same-page MOD) must record
    # difficulty=0, not be coerced to 1 by a falsy-value fallback bug
    t = dict(_task("gen_0000", ra={"must_include": ["42"]}), hops=0)
    GenerationRunner(_Browser, _Solver(), str(tmp_path), HashingEmbedder(),
                     SiteKB(), skill_hints=False).run([t])
    meta = json.load(open(next((tmp_path / "episodes").glob("*/episode_meta.json"))))
    assert meta["metadata"]["difficulty"] == 0
```

Run: `PYTHONPATH=. python -m pytest hsge/tests/ -q`
Expected: all PASS (74+ tests, no regressions elsewhere).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/composer.py hsge/webarena/collect.py hsge/tests/test_composer.py hsge/tests/test_collect.py
git commit -m "$(cat <<'EOF'
composer: compute real_hops via BFS instead of trusting self-reported hops

INFO/NAV start_url is now forced to the site root and any task whose target
is unreachable through known links is rejected, so `hops` (and the SFT
difficulty it feeds) is a real navigation distance, not an LLM guess.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Rebalance the type quota + global single-hop depth budget

**Files:**
- Modify: `hsge/webarena/composer.py`
- Test: `hsge/tests/test_composer.py`

**Interfaces:**
- Consumes: `try_accept` closure and `real_hops`/`build_link_graph` from Task 1.
- Produces: `TaskComposer.__init__` gains `min_hops2_share: float = 0.5`; `try_accept` now also rejects with reason `"single-hop budget exhausted"`.

- [ ] **Step 1: Write the failing test**

Append to `hsge/tests/test_composer.py`:

```python
def test_single_hop_depth_budget_rejects_surplus_after_share_met():
    # 1 comparable pair setup: 4 nodes total; force a scenario where 3 of 4
    # candidate INFO tasks are 1-hop (same page as start after override is
    # impossible since INFO is always forced to site root -- so use NAV
    # candidates, which can be 1-hop from the root, to fill the single-hop
    # budget, then confirm a further 1-hop NAV gets the new rejection reason).
    kb = _kb()   # http://s -[1 hop]-> gaming, movies; gaming -[1 hop]-> post1 (2 hops)

    def nav(url):
        return {"intent": f"go to {url}", "type": "NAV", "start_url": "http://s",
                "hops": 1, "source_nodes": [1], "answer_fact_refs": [],
                "eval": {"eval_types": ["url_match"], "reference_answers": None,
                         "reference_url": url, "program_html": []}}

    class _LLM:
        def __init__(self):
            self.calls = 0
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            self.calls += 1
            if self.calls == 1:
                return {"tasks": [nav("http://s/f/gaming"), nav("http://s/f/movies")]}
            return {"tasks": [dict(nav("http://s/f/gaming"),
                                    intent="go to gaming forum again")]}

    # total_quota=2 -> min_hops2_share=0.5 -> max_single_hop = round(2*0.5) = 1
    comp = TaskComposer(_LLM(), kb, quota={"INFO": 0, "NAV": 2, "MOD": 0},
                        min_hops2_share=0.5)
    accepted, rejected = comp.generate()
    assert len(accepted) == 1                       # only the budget-allowed 1-hop task
    assert accepted[0]["hops"] == 1
    reasons = [r["reason"] for r in rejected]
    assert "single-hop budget exhausted" in reasons
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_composer.py::test_single_hop_depth_budget_rejects_surplus_after_share_met -v`
Expected: FAIL — both 1-hop NAV tasks get accepted (no budget mechanism yet).

- [ ] **Step 3: Implement the depth budget**

In `hsge/webarena/composer.py`, update `TaskComposer.__init__`:

```python
    def __init__(self, llm, kb, quota: dict | None = None, hops: tuple = (2, 4),
                 tasks_per_call: int = 5, seed: int = 0,
                 min_hops2_share: float = 0.5):
        self.llm = llm
        self.kb = kb
        self.quota = dict(quota or {"INFO": 40, "NAV": 20, "MOD": 40})
        self.hops = hops
        self.tasks_per_call = tasks_per_call
        self.rng = random.Random(seed)
        self.min_hops2_share = min_hops2_share
```

Update `generate()`'s `try_accept` closure (full function, replacing Task 1's version):

```python
    def generate(self) -> tuple[list[dict], list[dict]]:
        accepted: list[dict] = []
        rejected: list[dict] = []
        remaining = dict(self.quota)
        graph = build_link_graph(self.kb)
        max_single_hop = round(sum(self.quota.values()) * (1 - self.min_hops2_share))
        single_hop_accepted = 0

        def try_accept(t) -> bool:
            nonlocal single_hop_accepted
            if not isinstance(t, dict) or remaining.get(t.get("type"), 0) <= 0:
                rejected.append({"task": t, "reason": "quota exhausted for type"})
                return False
            t.setdefault("start_url", self.kb.site)
            if t.get("type") in ("INFO", "NAV"):
                t["start_url"] = self.kb.site
            reason = validate_task(t, self.kb, accepted, graph=graph)
            if reason:
                rejected.append({"task": t, "reason": reason})
                return False
            hops = real_hops(t, self.kb, graph)
            if hops < 2 and single_hop_accepted >= max_single_hop:
                rejected.append({"task": t, "reason": "single-hop budget exhausted"})
                return False
            t["task_id"] = f"gen_{len(accepted):04d}"
            t["hops"] = hops
            accepted.append(t)
            remaining[t["type"]] -= 1
            if hops < 2:
                single_hop_accepted += 1
            return True

        for bundle in sample_bundles(self.kb, self.rng):
            if all(v <= 0 for v in remaining.values()):
                break
            prompt = (f"SITE: {self.kb.site}\nQUOTA REMAINING: {remaining}\n"
                      f"PREFERRED HOPS: {self.hops[0]}-{self.hops[1]}\n\n"
                      f"SITE KNOWLEDGE (this bundle):\n{self._render_bundle(bundle)}\n\n"
                      "ALREADY GENERATED:\n"
                      + ("\n".join(f"- {a['intent']}" for a in accepted[-30:]) or "(none)")
                      + f"\n\nGenerate up to {self.tasks_per_call} tasks from THIS bundle.")
            out = self.llm.complete_json(COMPOSER_SYS, prompt) or {}
            for t in out.get("tasks") or []:
                try_accept(t)
        return accepted, rejected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_composer.py -v`
Expected: all PASS, including the new budget test and every pre-existing test
(pre-existing tests use small quotas like `{"INFO": 5, "NAV": 0, "MOD": 0}`
with 1-2 accepted tasks, so `max_single_hop = round(5*0.5) = 2` or similar
never binds them — confirm this by inspection if any fails).

Run: `PYTHONPATH=. python -m pytest hsge/tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/composer.py hsge/tests/test_composer.py
git commit -m "$(cat <<'EOF'
composer: enforce a global single-hop depth budget across accepted tasks

At least min_hops2_share (default 50%) of accepted tasks must have
real_hops >= 2; surplus single-hop tasks are rejected once the budget is
spent, the same mechanism the per-type quota already uses.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Comparison/aggregation tasks — the first two-source INFO shape

**Files:**
- Modify: `hsge/webarena/composer.py`
- Test: `hsge/tests/test_composer.py`

**Interfaces:**
- Consumes: `try_accept` closure, `find_comparable_pairs`/`real_hops` (this task adds the former).
- Produces: `find_comparable_pairs(kb) -> list[dict]`, `TaskComposer._phrase_comparison(pair) -> str`, `TaskComposer._try_comparisons(try_accept) -> None`, `COMPARISON_SYS` prompt constant.

- [ ] **Step 1: Write the failing tests**

Append to `hsge/tests/test_composer.py`:

```python
def test_find_comparable_pairs_across_different_nodes():
    from hsge.webarena.composer import find_comparable_pairs
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 1, "url": "http://s/f/gaming/1", "outlinks": [],
                 "entities": [{"type": "post", "name": "Post A",
                               "attrs": {"comments": "45"}, "grounded": True,
                               "evidence": "Post A has 45 comments"}], "facts": []})
    kb.add_node({"node_index": 2, "url": "http://s/f/gaming/2", "outlinks": [],
                 "entities": [{"type": "post", "name": "Post B",
                               "attrs": {"comments": "10"}, "grounded": True,
                               "evidence": "Post B has 10 comments"}], "facts": []})
    pairs = find_comparable_pairs(kb)
    assert len(pairs) == 1
    assert pairs[0]["attr"] == "comments"
    assert pairs[0]["winner"]["entity"]["name"] == "Post A"
    assert pairs[0]["loser"]["entity"]["name"] == "Post B"


def test_find_comparable_pairs_skips_same_node_and_ungrounded():
    from hsge.webarena.composer import find_comparable_pairs
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 1, "url": "http://s/x", "outlinks": [],
                 "entities": [
                     {"type": "post", "name": "A", "attrs": {"n": "5"}, "grounded": True},
                     {"type": "post", "name": "B", "attrs": {"n": "1"}, "grounded": True}],
                 "facts": []})
    kb.add_node({"node_index": 2, "url": "http://s/y", "outlinks": [],
                 "entities": [{"type": "post", "name": "C", "attrs": {"n": "9"},
                               "grounded": False}], "facts": []})
    pairs = find_comparable_pairs(kb)
    assert pairs == []   # A/B share a node (skipped); C is ungrounded (skipped)


def test_comparison_task_generated_and_verified_by_existing_gates():
    kb = _kb()
    kb.add_node({"node_index": 3, "url": "http://s/f/movies/2", "outlinks": [],
                 "entities": [{"type": "post", "name": "Dune review 2",
                               "attrs": {"comments": "50"}, "grounded": True,
                               "evidence": "Dune review 2 has 50 comments"}], "facts": []})
    # give node 2's "Dune review" a comparable, lower attr value too
    kb.nodes[2]["entities"][0]["attrs"] = {"comments": "10"}
    kb.nodes[2]["entities"][0]["evidence"] = "Dune review has 10 comments"

    class _LLM:
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            if system.startswith("Phrase"):
                return {"intent": "Which movie post has more comments, "
                                  "'Dune review' or 'Dune review 2'?"}
            return {"tasks": []}

    comp = TaskComposer(_LLM(), kb, quota={"INFO": 5, "NAV": 0, "MOD": 0})
    accepted, rejected = comp.generate()
    assert len(accepted) == 1
    task = accepted[0]
    assert task["type"] == "INFO"
    assert task["eval"]["reference_answers"] == {"exact_match": "Dune review 2"}
    assert sorted(task["source_nodes"]) == [2, 3]
    assert task["start_url"] == "http://s"
    assert task["hops"] >= 1


def test_comparison_task_falls_back_to_template_when_llm_phrasing_fails_gates():
    kb = _kb()
    kb.add_node({"node_index": 3, "url": "http://s/f/movies/2", "outlinks": [],
                 "entities": [{"type": "post", "name": "Dune review 2",
                               "attrs": {"comments": "50"}, "grounded": True,
                               "evidence": "Dune review 2 has 50 comments"}], "facts": []})
    kb.nodes[2]["entities"][0]["attrs"] = {"comments": "10"}
    kb.nodes[2]["entities"][0]["evidence"] = "Dune review has 10 comments"

    class _BadLLM:
        """Phrases the comparison with a relative-time reference, which
        RELATIVE_TIME_RE rejects -- the composer must fall back to the
        code-generated template intent instead of dropping the task."""
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            if system.startswith("Phrase"):
                return {"intent": "Which had more comments 5 minutes ago, "
                                  "'Dune review' or 'Dune review 2'?"}
            return {"tasks": []}

    comp = TaskComposer(_BadLLM(), kb, quota={"INFO": 5, "NAV": 0, "MOD": 0})
    accepted, rejected = comp.generate()
    assert len(accepted) == 1
    assert "minutes ago" not in accepted[0]["intent"]   # template used instead
    assert accepted[0]["intent"].startswith("Which has a higher comments")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_composer.py -k comparison -v`
Expected: FAIL with `ImportError: cannot import name 'find_comparable_pairs'`.

- [ ] **Step 3: Implement comparison-task generation**

In `hsge/webarena/composer.py`, add near the top (after the regex constants,
before `_norm_intent`):

```python
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

COMPARISON_SYS = (
    "Phrase ONE natural user question comparing two named things by a given "
    'attribute. Return JSON {"intent": str}. Ask which one is higher/greater/'
    "more recent for the attribute; do NOT state either value or reveal the "
    "answer; do NOT reference relative time (e.g. 'X minutes ago').")


def _numeric(val: str) -> float | None:
    m = _NUM_RE.search(val or "")
    return float(m.group()) if m else None


def find_comparable_pairs(kb) -> list[dict]:
    """Grounded same-type entity pairs on different nodes sharing a numeric
    attribute with different values -- material for a code-computed
    comparison INFO task (the code decides the winner; the LLM only phrases
    the question)."""
    by_type: dict[str, list[dict]] = {}
    for n in kb.nodes:
        for i, e in enumerate(n.get("entities") or []):
            if e.get("grounded"):
                by_type.setdefault(str(e.get("type") or ""), []).append(
                    {"node_index": n["node_index"], "ent_index": i, "entity": e})
    pairs = []
    for items in by_type.values():
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                x, y = items[a], items[b]
                if x["node_index"] == y["node_index"]:
                    continue
                for key, xv in (x["entity"].get("attrs") or {}).items():
                    yv = (y["entity"].get("attrs") or {}).get(key)
                    if yv is None:
                        continue
                    nx, ny = _numeric(xv), _numeric(yv)
                    if nx is None or ny is None or nx == ny:
                        continue
                    winner, loser = (x, y) if nx > ny else (y, x)
                    pairs.append({"attr": key, "winner": winner, "loser": loser})
    return pairs


def _comparison_task(pair: dict, kb, intent: str) -> dict:
    w, l = pair["winner"], pair["loser"]
    return {
        "type": "INFO", "intent": intent, "start_url": kb.site,
        "source_nodes": [w["node_index"], l["node_index"]],
        "answer_fact_refs": [f"n{w['node_index']}.e{w['ent_index']}",
                             f"n{l['node_index']}.e{l['ent_index']}"],
        "eval": {"eval_types": ["string_match"],
                 "reference_answers": {"exact_match": w["entity"]["name"]},
                 "reference_url": None, "program_html": []},
    }
```

Add two methods to `TaskComposer` (place right before `generate`):

```python
    def _phrase_comparison(self, pair: dict) -> str:
        w, l = pair["winner"], pair["loser"]
        template = (f"Which has a higher {pair['attr']}: "
                    f"{w['entity']['name']!r} or {l['entity']['name']!r}?")
        prompt = (f"ATTRIBUTE: {pair['attr']}\nA: {w['entity']['name']}\n"
                  f"B: {l['entity']['name']}")
        out = self.llm.complete_json(COMPARISON_SYS, prompt) or {}
        phrased = str(out.get("intent") or "").strip()
        return phrased or template

    def _try_comparisons(self, try_accept) -> None:
        for pair in find_comparable_pairs(self.kb):
            phrased = self._phrase_comparison(pair)
            if try_accept(_comparison_task(pair, self.kb, phrased)):
                continue
            template = (f"Which has a higher {pair['attr']}: "
                        f"{pair['winner']['entity']['name']!r} or "
                        f"{pair['loser']['entity']['name']!r}?")
            if template != phrased:
                try_accept(_comparison_task(pair, self.kb, template))
```

In `generate()`, call `self._try_comparisons(try_accept)` once, right after
defining `try_accept` and before the `for bundle in sample_bundles(...)` loop:

```python
        def try_accept(t) -> bool:
            ...   # unchanged from Task 2

        self._try_comparisons(try_accept)

        for bundle in sample_bundles(self.kb, self.rng):
            ...   # unchanged from Task 2
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_composer.py -v`
Expected: all PASS. If
`test_comparison_task_falls_back_to_template_when_llm_phrasing_fails_gates`
fails because the "5 minutes ago" phrasing passes some gate it shouldn't,
double check `RELATIVE_TIME_RE` matches `"minutes ago"` (it does, per the
existing regex) — the LLM-phrased version should hit
`validate_task`'s `RELATIVE_TIME_RE` check.

Run: `PYTHONPATH=. python -m pytest hsge/tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/composer.py hsge/tests/test_composer.py
git commit -m "$(cat <<'EOF'
composer: add code-computed comparison/aggregation INFO tasks

Scans the SiteKB for grounded same-type entity pairs on different nodes with
a comparable numeric attribute; code decides the winner (never the LLM), the
LLM only phrases the question, with a template fallback when the phrasing
fails an existing validation gate. The pipeline's first genuine two-source
task shape.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Site-map hint for the Solver

**Files:**
- Modify: `hsge/webarena/collect.py`
- Test: `hsge/tests/test_collect.py`

**Interfaces:**
- Consumes: `WebArenaExplorer._url_template(url: str) -> str` (staticmethod, `hsge/webarena/runtime.py:204-224`).
- Produces: `build_site_map(known_urls: set[str], max_lines: int = 15) -> str`; `GenerationRunner.__init__` computes `self.site_map` once.

- [ ] **Step 1: Write the failing test**

Append to `hsge/tests/test_collect.py`:

```python
def test_build_site_map_groups_by_template_and_caps_lines():
    from hsge.webarena.collect import build_site_map
    urls = {"http://s/f/gaming", "http://s/f/movies",
            "http://s/f/gaming/comments/1/title", "http://s/f/gaming/comments/2/other"}
    site_map = build_site_map(urls, max_lines=15)
    lines = site_map.splitlines()
    assert len(lines) == 3   # /f/gaming, /f/movies, /f/gaming/comments/*/* templates
    assert any("f/gaming/comments" in l for l in lines)


def test_build_site_map_empty_for_no_urls():
    from hsge.webarena.collect import build_site_map
    assert build_site_map(set()) == ""


def test_runner_passes_site_map_alongside_skill_hints(tmp_path):
    captured = {}
    class _CapturingSolver:
        def solve(self, browser, goal, goal_predicate=None, hints=None):
            captured["hints"] = hints
            return ([Step(action="send_msg_to_user('42')", url=browser.url, axtree="ax")],
                    ["ax"], [None], browser.observation(), True)
    kb = _kb_two_pages()
    t = _task("gen_0000", ra={"must_include": ["42"]})
    GenerationRunner(_Browser, _CapturingSolver(), str(tmp_path), HashingEmbedder(),
                     kb, skill_hints=False).run([t])
    assert "http://s/home" in captured["hints"] or "http://s/page2" in captured["hints"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_collect.py -k site_map -v`
Expected: FAIL with `ImportError: cannot import name 'build_site_map'`.

- [ ] **Step 3: Implement `build_site_map` and wire it into `GenerationRunner`**

In `hsge/webarena/collect.py`, add the import and function (after the
existing imports, before `top_k_skill_hints`):

```python
from .runtime import WebArenaExplorer


def build_site_map(known_urls: set[str], max_lines: int = 15) -> str:
    """One example URL per URL-template (grouped via WebArenaExplorer's own
    per-template shape logic), for the Solver's general site orientation --
    never leaks any specific task's answer."""
    by_template: dict[str, str] = {}
    for u in sorted(known_urls):
        by_template.setdefault(WebArenaExplorer._url_template(u), u)
    lines = [f"- {t} (e.g. {u})" for t, u in sorted(by_template.items())[:max_lines]]
    return "\n".join(lines)
```

Update `GenerationRunner.__init__` to compute the site map once:

```python
    def __init__(self, browser_factory, solver, out_dir: str, embedder, kb,
                 judge_llm=None, discovery=None, root_url: str = "",
                 reset_fn=None, skill_hints: bool = True):
        self.browser_factory = browser_factory
        self.solver = solver
        self.out_dir = out_dir
        self.embedder = embedder
        self.kb = kb
        self.judge_llm = judge_llm
        self.discovery = discovery
        self.root_url = root_url
        self.reset_fn = reset_fn
        self.skill_hints = skill_hints
        self.site_map = build_site_map(kb.known_urls())
        os.makedirs(os.path.join(out_dir, "episodes"), exist_ok=True)
        # continue numbering after phase-1 episodes (never overwrite them)
        self.episode = len(glob.glob(os.path.join(out_dir, "episodes", "ep_*")))
```

Update `run()`'s hints assembly (replace the two relevant lines inside the
`for task in order:` loop):

```python
                stats["attempted"] += 1
                hints = (top_k_skill_hints(self.embedder, self.kb.skills, task["intent"])
                         if self.skill_hints else None)
                combined_hints = "\n".join(h for h in (hints, self.site_map) if h) or None
                steps, obs_texts, shots, final_obs, _ = self.solver.solve(
                    browser, task["intent"], hints=combined_hints)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_collect.py -v`
Expected: all PASS.

Run: `PYTHONPATH=. python -m pytest hsge/tests/ -q`
Expected: all PASS (confirms no circular import between `collect.py` and
`runtime.py` — `runtime.py` does not import `collect.py`, so this is safe).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/collect.py hsge/tests/test_collect.py
git commit -m "$(cat <<'EOF'
collect: give the Solver a compact site map alongside skill hints

Built once per run from the SiteKB's known URLs (one example per
URL-template, capped at 15 lines). General orientation only -- never leaks a
specific task's answer -- meant to offset the verified-rate cost of forcing
INFO/NAV tasks to start far from their target page.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Composer near-duplicate suppression via embeddings

**Files:**
- Modify: `hsge/webarena/composer.py`
- Test: `hsge/tests/test_composer.py`

**Interfaces:**
- Consumes: `hsge.llm.Embedder.encode(texts: list[str]) -> np.ndarray` (L2-normalized).
- Produces: `validate_task(..., embedder=None, intent_sim: float = 0.6)` (two new optional params); `TaskComposer.__init__` gains `embedder=None, intent_sim: float = 0.6`.

- [ ] **Step 1: Write the failing tests**

Append to `hsge/tests/test_composer.py`:

```python
class _StubEmbedder:
    """Deterministic 2D embedder: intents sharing a keyword land close."""
    def encode(self, texts):
        import numpy as np
        vecs = []
        for t in texts:
            tl = t.lower()
            x = 1.0 if "gaming" in tl else 0.0
            y = 1.0 if "movies" in tl else 0.0
            v = np.array([x, y], dtype=np.float32)
            n = (v[0]**2 + v[1]**2) ** 0.5
            vecs.append(v / n if n > 0 else v)
        return np.vstack(vecs)


def test_validate_task_rejects_near_duplicate_intent_via_embedder():
    kb = _kb()
    info = _info(["n1.e0.attrs.author"], {"exact_match": "hlz0"})
    accepted = [dict(info, intent="Find the author of the top gaming post")]
    near_dup = dict(info, intent="Who wrote the top gaming submission?")
    assert validate_task(near_dup, kb, accepted,
                         embedder=_StubEmbedder(), intent_sim=0.6) is not None
    assert "near-duplicate" in validate_task(
        near_dup, kb, accepted, embedder=_StubEmbedder(), intent_sim=0.6)
    # a genuinely different topic still passes
    different = dict(info, intent="Find the author of the top movies post",
                     answer_fact_refs=["n1.e0.attrs.author"])
    assert validate_task(different, kb, accepted, embedder=_StubEmbedder(),
                         intent_sim=0.6) is None


def test_generate_wires_embedder_into_dedup():
    class _LLM:
        def __init__(self):
            self.calls = 0
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            self.calls += 1
            if self.calls == 1:
                return {"tasks": [_info_task("Find the author of the top gaming post")]}
            return {"tasks": [dict(_info_task("Who wrote the top gaming submission?"),
                                    answer_fact_refs=["n1.e0.attrs.author"])]}
    comp = TaskComposer(_LLM(), _kb(), quota={"INFO": 5, "NAV": 0, "MOD": 0},
                        embedder=_StubEmbedder(), intent_sim=0.6)
    accepted, rejected = comp.generate()
    assert len(accepted) == 1
    assert any(r["reason"] == "near-duplicate intent" for r in rejected)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_composer.py -k near_duplicate -v`
Expected: FAIL — `validate_task` raises `TypeError: unexpected keyword argument 'embedder'`.

- [ ] **Step 3: Implement embedding-based near-dup rejection**

In `hsge/webarena/composer.py`, update `validate_task`'s signature and add
the check right after the existing exact-string dedup check (cheap check
stays first, per the spec's "keep the exact-string check as a cheap
pre-filter"):

```python
def validate_task(task, kb, accepted: list[dict], graph: dict | None = None,
                  embedder=None, intent_sim: float = 0.6) -> str | None:
    """Rejection reason, or None when the task passes every code gate."""
    if not isinstance(task, dict):
        return "not an object"
    intent = str(task.get("intent") or "")
    ttype = task.get("type")
    if ttype not in ("INFO", "NAV", "MOD"):
        return "bad type"
    if not intent.strip():
        return "empty intent"
    key = _norm_intent(intent)
    if any(_norm_intent(a.get("intent", "")) == key for a in accepted):
        return "duplicate intent"
    if embedder is not None and accepted:
        others = [a.get("intent", "") for a in accepted]
        vecs = embedder.encode([intent] + others)
        q = vecs[0]
        if max(float(v @ q) for v in vecs[1:]) >= intent_sim:
            return "near-duplicate intent"
    if RELATIVE_TIME_RE.search(intent):
        return "relative-time reference in intent"
    ...   # unchanged below
```

Update `TaskComposer.__init__` (full signature, extending Task 2's version):

```python
    def __init__(self, llm, kb, quota: dict | None = None, hops: tuple = (2, 4),
                 tasks_per_call: int = 5, seed: int = 0,
                 min_hops2_share: float = 0.5, embedder=None,
                 intent_sim: float = 0.6):
        self.llm = llm
        self.kb = kb
        self.quota = dict(quota or {"INFO": 40, "NAV": 20, "MOD": 40})
        self.hops = hops
        self.tasks_per_call = tasks_per_call
        self.rng = random.Random(seed)
        self.min_hops2_share = min_hops2_share
        self.embedder = embedder
        self.intent_sim = intent_sim
```

Update `try_accept`'s `validate_task` call (inside `generate()`) to pass the
new params:

```python
            reason = validate_task(t, self.kb, accepted, graph=graph,
                                   embedder=self.embedder, intent_sim=self.intent_sim)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_composer.py -v`
Expected: all PASS. Every pre-existing `validate_task(...)` call in the file
omits `embedder`, defaulting to `None` — the near-dup branch is skipped
entirely (`embedder is not None` is `False`), so no pre-existing test is
affected.

Run: `PYTHONPATH=. python -m pytest hsge/tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/composer.py hsge/tests/test_composer.py
git commit -m "$(cat <<'EOF'
composer: reject near-duplicate intents via embedding cosine similarity

Exact-string dedup alone let paraphrased repeats through ("duplicate intent"
was the #1 composer rejection reason in run_06). Reuses the project's
existing Embedder interface and 0.6 cosine-threshold convention
(hsge/clustering.py, config.yaml's predicate_sim) rather than introducing a
new one.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: MOD variety — feasibility gates + collision-key relaxation

**Files:**
- Modify: `hsge/webarena/composer.py`
- Test: `hsge/tests/test_composer.py`

**Interfaces:**
- Produces: `validate_task(..., permission_re=None)` (new optional param); `TaskComposer.__init__` gains `permission_deny_re: str | None = None`; `_mod_target_urls` renamed to `_mod_target_keys` (URL + action-shape).

- [ ] **Step 1: Write the failing tests**

First, fix the shared `_kb()` fixture: node 2 ("Dune review") must be a
plausible comment target (a submission/thread page), not a `"forum"`
(listing) page — this is what the new page-type gate will now correctly
reject if left as-is, and every pre-existing MOD test in this file targets
node 2 assuming it's a valid comment target:

```python
    kb.add_node({"node_index": 2, "url": "http://s/f/movies", "page_type": "post",
                 "title": "movies", "outlinks": [],
                 "entities": [{"type": "post", "name": "Dune review",
                               "attrs": {}, "grounded": True,
                               "evidence": "Dune review"}], "facts": []})
```

(Only the `"page_type"` value changes from `"forum"` to `"post"` — this
reflects reality more accurately anyway: `_kb()`'s node 2 represents one
specific submission, not a listing.)

Append new tests:

```python
def test_validate_mod_rejects_comment_on_listing_page_type():
    kb = _kb()
    kb.add_node({"node_index": 4, "url": "http://s/f/tv", "page_type": "forum_listing",
                 "title": "tv", "outlinks": [], "entities": [], "facts": []})
    mod = {"intent": "post a comment saying hello on the tv forum page", "type": "MOD",
           "start_url": "http://s", "hops": 1, "source_nodes": [4], "answer_fact_refs": [],
           "eval": {"eval_types": ["program_html"], "reference_answers": None,
                    "reference_url": None,
                    "program_html": [{"url": "http://s/f/tv", "locator": "",
                                      "required_contents": {"must_include": ["hello"]}}]}}
    assert "listing page" in validate_task(mod, kb, [])
    # a non-comment MOD on the same listing page is unaffected (e.g. subscribe)
    subscribe = dict(mod, intent="subscribe to the tv forum",
                     eval=dict(mod["eval"], program_html=[
                         {"url": "http://s/f/tv", "locator": "",
                          "required_contents": {"must_include": ["Unsubscribe"]}}]))
    assert validate_task(subscribe, kb, []) is None


def test_validate_mod_rejects_permission_gated_action():
    kb = _kb()
    mod = {"intent": "Create a new forum titled 'Classics'", "type": "MOD",
           "start_url": "http://s", "hops": 1, "source_nodes": [0], "answer_fact_refs": [],
           "eval": {"eval_types": ["program_html"], "reference_answers": None,
                    "reference_url": None,
                    "program_html": [{"url": "http://s/create_forum", "locator": "",
                                      "required_contents": {"must_include": ["Classics"]}}]}}
    kb.add_node({"node_index": 5, "url": "http://s/create_forum", "outlinks": [],
                 "entities": [], "facts": []})
    assert "permission-gated" in validate_task(mod, kb, [])


def test_mod_collision_relaxed_to_url_plus_action_shape():
    kb = _kb()
    comment = {"intent": 'post a comment saying "great movie" under Dune review',
               "type": "MOD", "start_url": "http://s", "hops": 1, "source_nodes": [2],
               "answer_fact_refs": [],
               "eval": {"eval_types": ["program_html"], "reference_answers": None,
                        "reference_url": None,
                        "program_html": [{"url": "http://s/f/movies", "locator": "",
                                          "required_contents": {"must_include": ["great movie"]}}]}}
    edit_title = dict(comment, intent="edit the title to say Updated Dune review",
                      eval=dict(comment["eval"], program_html=[
                          {"url": "http://s/f/movies", "locator": "",
                           "required_contents": {"must_include": ["Updated Dune review"]}}]))
    # same target URL, different action shape (comment vs edit) -> no collision
    assert validate_task(edit_title, kb, [dict(comment, task_id="gen_0000")]) is None
    # same target URL, SAME action shape -> still collides
    comment2 = dict(comment, intent='post another comment saying "nice" under Dune review',
                    eval=dict(comment["eval"], program_html=[
                        {"url": "http://s/f/movies", "locator": "",
                         "required_contents": {"must_include": ["nice"]}}]))
    assert "collides" in validate_task(comment2, kb, [dict(comment, task_id="gen_0000")])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_composer.py -k "listing_page_type or permission_gated or collision_relaxed" -v`
Expected: FAIL — no page_type gate, no permission gate exist yet; the
collision test may spuriously pass or fail depending on current
`_mod_target_urls` behavior (confirm by inspection, not assumption).

- [ ] **Step 3: Implement the two feasibility gates + collision relaxation**

In `hsge/webarena/composer.py`, add near the other MOD-related constants
(after `MOD_READONLY_RE`):

```python
# Postmill has no comment affordance on an index/listing page -- comments
# belong to a specific submission/thread. A run_05 episode (gen_0089) showed
# the Solver either loop forever looking for one or improvise a wrong action
# (create a whole new submission) when the composer targeted a listing page.
COMMENT_SHAPED_RE = re.compile(r"\b(comment|repl(?:y|ies))\b", re.I)
LISTING_PAGE_TYPES = {"forum_listing", "forum", "listing", "index", "home", "category"}
# Admin/permission-gated actions the seeded test account plausibly can't
# perform (run_05 gen_0096: "Create a new forum" silently failed 4x). Override
# via TaskComposer(permission_deny_re=...) / config.yaml's
# gen.mod_permission_denylist for a site whose account has different rights.
MOD_PERMISSION_RE = re.compile(
    r"\b(create\s+(?:a\s+)?(?:new\s+)?(?:sub)?forum|ban\b|"
    r"promote\s+to\s+admin|site\s+settings|admin\s+panel|"
    r"delete\s+(?:another|other)('s)?\b)", re.I)
_MOD_VERB_RE = re.compile(
    r"\b(comment|repl(?:y|ies)|edit|subscribe|unsubscribe|vote|upvote|downvote|"
    r"post|submit|create|toggle|check|uncheck|select|save|favorite)\b", re.I)
```

Replace `_mod_target_urls` with an action-shape-aware version:

```python
def _mod_action_shape(intent: str) -> str:
    m = _MOD_VERB_RE.search(intent or "")
    return m.group(1).lower() if m else "other"


def _mod_target_keys(task: dict) -> set[tuple[str, str]]:
    shape = _mod_action_shape(str(task.get("intent") or ""))
    urls = {p.get("url") for p in (task.get("eval") or {}).get("program_html") or []}
    return {(u, shape) for u in urls if u and u != "last"}
```

Update `validate_task`'s signature and MOD branch (full function, extending
Task 5's version):

```python
def validate_task(task, kb, accepted: list[dict], graph: dict | None = None,
                  embedder=None, intent_sim: float = 0.6,
                  permission_re=None) -> str | None:
    """Rejection reason, or None when the task passes every code gate."""
    if not isinstance(task, dict):
        return "not an object"
    intent = str(task.get("intent") or "")
    ttype = task.get("type")
    if ttype not in ("INFO", "NAV", "MOD"):
        return "bad type"
    if not intent.strip():
        return "empty intent"
    key = _norm_intent(intent)
    if any(_norm_intent(a.get("intent", "")) == key for a in accepted):
        return "duplicate intent"
    if embedder is not None and accepted:
        others = [a.get("intent", "") for a in accepted]
        vecs = embedder.encode([intent] + others)
        q = vecs[0]
        if max(float(v @ q) for v in vecs[1:]) >= intent_sim:
            return "near-duplicate intent"
    if RELATIVE_TIME_RE.search(intent):
        return "relative-time reference in intent"
    graph = graph if graph is not None else build_link_graph(kb)
    ev = task.get("eval") or {}
    types = ev.get("eval_types") or []
    if ttype == "INFO":
        if INFO_META_RE.search(intent):
            return "site-mechanics INFO intent"
        if "string_match" not in types:
            return "INFO without string_match"
        refs = task.get("answer_fact_refs") or []
        if not refs:
            return "INFO without answer_fact_refs"
        resolved, evidences = [], []
        for r in refs:
            got = kb.resolve_ref(r)
            if got is None:
                return f"unknown ref {r}"
            val, grounded = got
            if not grounded:
                return f"ungrounded ref {r}"
            resolved.append(normalize_answer(val))
            evidences.append(normalize_answer(kb.resolve_ref_evidence(r) or ""))
        ra = ev.get("reference_answers") or {}
        targets = ([ra["exact_match"]] if "exact_match" in ra
                   else ra.get("must_include") or [])
        if not targets:
            return "INFO without reference answer"
        for t in targets:
            nt = normalize_answer(str(t))
            if not any(nt == v or nt in v for v in resolved):
                return f"reference answer {t!r} not backed by refs"
            if not any(nt in e for e in evidences if e):
                return f"reference answer {t!r} not inside cited evidence"
        rh = real_hops(task, kb, graph)
        if rh is None:
            return "target unreachable from start_url"
        if rh < 1:
            return "INFO start_url is the answer page (0 real hops)"
    elif ttype == "NAV":
        if "url_match" not in types:
            return "NAV without url_match"
        if ev.get("reference_url") not in kb.known_urls():
            return "reference_url not in SiteKB"
        if url_key(ev.get("reference_url") or "") == url_key(
                task.get("start_url") or kb.site):
            return "NAV reference_url equals start_url"
        if real_hops(task, kb, graph) is None:
            return "target unreachable from start_url"
    else:  # MOD
        if MOD_DENY_RE.search(intent):
            return "destructive MOD intent"
        if MOD_READONLY_RE.search(intent):
            return "read-only intent typed as MOD"
        perm_re = permission_re if permission_re is not None else MOD_PERMISSION_RE
        if perm_re.search(intent):
            return "permission-gated MOD intent"
        if COMMENT_SHAPED_RE.search(intent):
            for idx in task.get("source_nodes") or []:
                node = kb.node_by_index(idx)
                if node and str(node.get("page_type") or "").lower() in LISTING_PAGE_TYPES:
                    return "comment MOD targets a listing page, not a submission/thread"
        if "program_html" not in types or not ev.get("program_html"):
            return "MOD without program_html"
        ni = normalize_answer(intent)
        known = kb.known_urls()
        for spec in ev.get("program_html") or []:
            if spec.get("locator"):
                return "MOD locator must be empty (whole-page check)"
            url = spec.get("url") or "last"
            if url != "last" and url not in known:
                return "MOD program_html url not in SiteKB"
            required = (spec.get("required_contents") or {}).get("must_include") or []
            if not required:
                return "MOD without must_include"
            for s in required:
                if normalize_answer(str(s)) not in ni:
                    return f"must_include {s!r} not quoted in intent"
        mine = _mod_target_keys(task)
        for a in accepted:
            if a.get("type") == "MOD" and mine & _mod_target_keys(a):
                return "MOD target collides with an accepted MOD task"
        if real_hops(task, kb, graph) is None:
            return "target unreachable from start_url"
    return None
```

Update `TaskComposer.__init__` (full signature, extending Task 5's version):

```python
    def __init__(self, llm, kb, quota: dict | None = None, hops: tuple = (2, 4),
                 tasks_per_call: int = 5, seed: int = 0,
                 min_hops2_share: float = 0.5, embedder=None,
                 intent_sim: float = 0.6, permission_deny_re: str | None = None):
        self.llm = llm
        self.kb = kb
        self.quota = dict(quota or {"INFO": 40, "NAV": 20, "MOD": 40})
        self.hops = hops
        self.tasks_per_call = tasks_per_call
        self.rng = random.Random(seed)
        self.min_hops2_share = min_hops2_share
        self.embedder = embedder
        self.intent_sim = intent_sim
        self.permission_re = (re.compile(permission_deny_re, re.I)
                              if permission_deny_re else MOD_PERMISSION_RE)
```

Update `try_accept`'s `validate_task` call to pass `permission_re`:

```python
            reason = validate_task(t, self.kb, accepted, graph=graph,
                                   embedder=self.embedder, intent_sim=self.intent_sim,
                                   permission_re=self.permission_re)
```

- [ ] **Step 4: Run tests, verify no regression across the whole file**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_composer.py -v`
Expected: all PASS. Pay close attention to
`test_validate_nav_mod_and_dedup`, `test_validate_mod_self_verifying_gates`,
and `test_generate_assigns_ids_and_collects_rejections` — these all use MOD
tasks targeting node 2 (now `page_type: "post"`, not `"forum"`), so they
should be unaffected by the new listing-page gate; if any now fails on
"listing page" instead of its original assertion, the `_kb()` fixture edit in
Step 1 didn't take effect everywhere it's needed.

Run: `PYTHONPATH=. python -m pytest hsge/tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/composer.py hsge/tests/test_composer.py
git commit -m "$(cat <<'EOF'
composer: add MOD feasibility gates, relax collision to URL+action-shape

Root-caused the run_05 MOD verified-rate regression (80% -> 65%): 5/7
solve-time failures were comment-shaped intents targeting a listing page
(no such affordance exists) or an admin-only action the seed account can't
perform. Both are now code-side gates instead of solve-time failures.
Separately, the collision-dedup key widens from target URL alone to
(URL, action-shape) so distinct actions on the same page (comment vs edit)
can coexist -- MOD variety was capped at one accepted task per URL.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Config/CLI wiring, full dry-run verification, docs

**Files:**
- Modify: `config.yaml`
- Modify: `run_webarena.py`
- Modify: `.claude/rules/architecture.md`

**Interfaces:**
- Consumes: every `TaskComposer` constructor param introduced in Tasks 1–6 (`min_hops2_share`, `embedder`, `intent_sim`, `permission_deny_re`) and the rebalanced default `quota`.

- [ ] **Step 1: Update `config.yaml`'s `gen:` block**

```yaml
gen:                         # phase 2 (run_webarena.py --phase generate|all)
  quota: {INFO: 40, NAV: 20, MOD: 40}   # generated-task budget per type
  hops_min: 2                # preferred multi-hop range for composed tasks
  hops_max: 4
  min_hops2_share: 0.5       # min fraction of accepted tasks with real_hops>=2
  intent_sim: 0.6            # cosine threshold for composer near-dup rejection
  mod_permission_denylist: null   # regex override for admin/permission-gated MOD verbs
  max_steps: 25              # solver step budget per generated task
  skill_hints: true          # inject top-k discovered skills into the solver prompt
```

- [ ] **Step 2: Update `run_webarena.py`'s `DEFAULTS` and `TaskComposer` instantiation**

Update the `"gen"` entry in `DEFAULTS` (near the top of the file):

```python
    "gen": {"quota": {"INFO": 40, "NAV": 20, "MOD": 40}, "hops_min": 2, "hops_max": 4,
            "min_hops2_share": 0.5, "intent_sim": 0.6, "mod_permission_denylist": None,
            "max_steps": 25, "skill_hints": True},
```

Update the `_DryLLM`'s `COMPOSE` fixture (still needs to satisfy the new
gates -- `start_url` will be overridden to `kb.site` regardless, but the
fixture should reflect that reality rather than a value that's silently
replaced) -- no change needed here since `_DryLLM`'s scripted `start_url`
("http://shop/home") already equals the dry run's `root_url`/`kb.site`; only
confirm this holds in Step 4.

Update the composer instantiation inside the `--phase generate|all` branch:

```python
        else:
            composer = TaskComposer(agent_llms["task_composer"], kb,
                                    quota=gen_cfg["quota"],
                                    hops=(gen_cfg["hops_min"], gen_cfg["hops_max"]),
                                    min_hops2_share=gen_cfg["min_hops2_share"],
                                    embedder=embedder, intent_sim=gen_cfg["intent_sim"],
                                    permission_deny_re=gen_cfg.get("mod_permission_denylist"))
            tasks, rejected = composer.generate()
            json.dump({"accepted": tasks, "rejected": rejected},
                      open(gt_path, "w"), indent=2)
            print(f"[gen] composed {len(tasks)} tasks ({len(rejected)} rejected) -> {gt_path}")
```

- [ ] **Step 3: Full pipeline dry-run verification**

Run: `PYTHONPATH=. python run_webarena.py --dry-run --out /tmp/wa_dry_multihop --phase all --max-nodes 3`
Expected: exits cleanly, prints `[gen] composed N tasks (...)` and
`[gen] done: V verified / A attempted`. If it errors with
`"target unreachable from start_url"` for the dry run's single scripted INFO
task, that means `kb.site` ("http://shop/home") isn't landing on the same
node the digester actually visited first -- inspect
`/tmp/wa_dry_multihop/sitekb.json`'s node 0 `url` field; it must equal
`root_url` exactly for `real_hops` to find a path. This is expected to
already hold (the dry run's frontier always visits `root_url` first), but
confirm empirically rather than assuming.

Run: `cat /tmp/wa_dry_multihop/gen_tasks.json` and confirm `accepted[0]["hops"]`
is a real integer (not the old hardcoded default) and `accepted[0]["start_url"]`
equals `kb.site`.

Run: `PYTHONPATH=. python -m pytest hsge/tests/ -q`
Expected: all tests still pass (should already be true from Task 6, this is
the final full-suite confirmation).

- [ ] **Step 4: Update `.claude/rules/architecture.md`**

In the `.claude/rules/architecture.md` section describing phase 2 (the
paragraph starting "Phase 2 (`run_webarena.py --phase generate|all`)..."),
add a short paragraph after the existing "A run_04 measurement..." paragraph:

```markdown
A 2026-07-08 package (`docs/superpowers/specs/2026-07-07-semantic-multihop-tasks-design.md`)
replaced the LLM's self-reported `hops` with `real_hops`, a BFS distance over
the SiteKB's link graph (`composer.py`'s `build_link_graph`/`real_hops`):
INFO/NAV `start_url` is now forced to the site root regardless of what the
composer proposes, and any task whose target is unreachable through known
links is rejected outright. A new comparison/aggregation INFO shape
(`find_comparable_pairs`) is the pipeline's first genuine two-source task --
code computes the answer from two grounded entities on different nodes, the
LLM only phrases the question, with a template fallback. `GenerationRunner`
now also gives the Solver a compact site-map hint (one example URL per
template) alongside skill hints, to offset the verified-rate cost of the
far-start policy. Separately, the composer's type quota widened past a fixed
60% INFO share, gained a global depth budget (minimum share of accepted
tasks with `real_hops >= 2`), embedding-based near-duplicate intent
rejection (the exact-string check alone let paraphrases through), and two
MOD-specific feasibility gates -- a comment/reply-shaped intent may not
target a listing-type page (`page_type` from the digest), and a small
permission denylist rejects admin-gated actions the seed account can't
perform -- plus a widened MOD collision key (URL + action-shape, not URL
alone) for more MOD variety.
```

- [ ] **Step 5: Commit**

```bash
git add config.yaml run_webarena.py .claude/rules/architecture.md
git commit -m "$(cat <<'EOF'
wire semantic-multihop gen config through run_webarena.py; docs

Rebalances the default type quota (INFO:40/NAV:20/MOD:40), threads the new
TaskComposer params (min_hops2_share, embedder, intent_sim,
permission_deny_re) from config.yaml through to the composer, and documents
the whole package in architecture.md. Verified end-to-end via
--dry-run --phase all.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## After implementation

Run a real collection pass (`run_07`) per the spec's acceptance metrics
(`docs/superpowers/specs/2026-07-07-semantic-multihop-tasks-design.md`,
section 9): `python run_webarena.py --phase generate --out outputs/wa_run_07`
against an existing `sitekb.json`, then compare against `run_06`'s numbers
(median verified-INFO step count, share of `real_hops >= 2`, type mix, MOD
verified rate). This is measurement, not implementation — do it as a
follow-up session once this plan's 7 tasks are merged.
