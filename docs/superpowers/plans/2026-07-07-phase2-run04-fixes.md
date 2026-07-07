# Phase-2 run_04 Fixes (Part A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five failure classes found in the run_04 measurement with compose-time gates and one solve-time probe extension (spec: `docs/superpowers/specs/2026-07-07-phase2-run04-fixes-design.md`).

**Architecture:** Five small, independent guards: (1) a public `url_key` helper refactored out of `evaluator.url_match`, used by a new NAV self-reference gate in `composer.validate_task`; (2) a landed-URL redirect check added to the NAV probe in `collect._is_stale`; (3+4) two intent regex gates in `composer.py` (site-mechanics INFO ban, relative-time ban) plus one prompt rule; (5) an evidence-containment gate on INFO references. No Solver changes.

**Tech Stack:** Python 3, pytest, existing mock fakes in `hsge/tests/`.

## Global Constraints

- Run everything from the repo root; activate the env first: `conda activate go-browse`.
- Test command form: `python -m pytest hsge/tests/<file>.py -q`.
- All code/comments/commit messages in English. Match existing style.
- Commit after each task (local only, never push). End commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Rejection-reason strings are load-bearing (tests assert substrings) — copy them exactly: `"NAV reference_url equals start_url"`, `"site-mechanics INFO intent"`, `"relative-time reference in intent"`, `f"reference answer {t!r} not inside cited evidence"`.
- Real run_04 failure shapes to use verbatim in tests where cited: `gen_0004` (NAV ref == start page), permission-gated `/f/movies/13/-/comment/56/edit` (redirects for the logged-in account), "Find the short URL for the post titled 'New Edited Title Here'", "Find the text of the comment by MarvelsGrantMan136 written 17 minutes ago", `gen_0064` (reference "-1" not inside its evidence quote).

---

### Task 1: `url_key` helper + NAV self-reference gate

**Files:**
- Modify: `hsge/webarena/evaluator.py` (refactor `url_match`)
- Modify: `hsge/webarena/composer.py` (import + NAV branch gate, fixture-visible)
- Test: `hsge/tests/test_evaluator.py`, `hsge/tests/test_composer.py`

**Interfaces:**
- Produces: `url_key(u: str) -> tuple` in `hsge/webarena/evaluator.py` — the slug-blind comparison key (netloc, wildcarded path, sorted query) formerly private inside `url_match`. Task 2 imports it into `collect.py`. `url_match` behavior is unchanged.
- Produces: `validate_task` rejects NAV when `url_key(reference_url) == url_key(task.get("start_url") or kb.site)` with reason `"NAV reference_url equals start_url"`.

- [ ] **Step 1: Write the failing tests**

Append to `hsge/tests/test_evaluator.py` (extend the existing import line from `hsge.webarena.evaluator` with `url_key`):

```python
def test_url_key_public_helper_slug_blind():
    assert url_key("http://s/f/movies/15/a-slug") == url_key("http://s/f/movies/15/b-slug")
    assert url_key("http://s/p?a=1&b=2") == url_key("http://s/p?b=2&a=1")
    assert url_key("http://s/p") != url_key("http://s/q")
```

In `hsge/tests/test_composer.py`, first extend the `_kb()` fixture's node 1 with two extra outlinks so the new gate is reachable through the existing `known_urls` check — change the `"outlinks"` line of node 1 to:

```python
                 "outlinks": ["http://s/f/gaming/post1", "http://s",
                              "http://s/f/gaming/15/a-slug"],
```

Then append:

```python
def test_validate_nav_rejects_self_referential_target():
    kb = _kb()
    # run_04 gen_0004: "Go to the Messages page from the notifications page"
    # with reference_url == start_url -- unwinnable as specified
    nav = {"intent": "Go to the Messages page from the notifications page.",
           "type": "NAV", "start_url": "http://s/f/gaming", "hops": 1,
           "source_nodes": [1], "answer_fact_refs": [],
           "eval": {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/f/gaming", "program_html": []}}
    assert "equals start_url" in validate_task(nav, kb, [])
    # slug drift must not hide the self-reference (slug-blind compare)
    slugged = dict(nav, start_url="http://s/f/gaming/15/b-slug",
                   eval=dict(nav["eval"],
                             reference_url="http://s/f/gaming/15/a-slug"))
    assert "equals start_url" in validate_task(slugged, kb, [])
    # missing start_url falls back to kb.site
    rootless = dict(nav, eval=dict(nav["eval"], reference_url="http://s"))
    del rootless["start_url"]
    assert "equals start_url" in validate_task(rootless, kb, [])
    # a genuine target elsewhere still passes
    ok = dict(nav, eval=dict(nav["eval"],
                             reference_url="http://s/f/gaming/post1"))
    assert validate_task(ok, kb, []) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_evaluator.py::test_url_key_public_helper_slug_blind hsge/tests/test_composer.py::test_validate_nav_rejects_self_referential_target -q`
Expected: FAIL — `ImportError`/`NameError` for `url_key`, and the composer test fails because `validate_task` currently accepts all three self-referential shapes.

- [ ] **Step 3: Implement**

In `hsge/webarena/evaluator.py`, replace the whole `url_match` function (the version with inner `slug_blind`/`key` helpers) with:

```python
def _slug_blind(path: str) -> str:
    # Postmill puts a mutable slug (or '-') right after the numeric id
    # (/f/movies/15/<slug>); a retitle changes the slug, not the id, so
    # that one segment is wildcarded. Everything else compares exactly.
    segs = path.split("/")
    for i, s in enumerate(segs):
        if s.isdigit():
            if i + 1 < len(segs) and segs[i + 1]:
                segs[i + 1] = "*"
            break
    return "/".join(segs)


def url_key(u: str) -> tuple:
    """Slug-blind comparison key: two URLs with the same key are the same
    page for eval purposes (netloc, wildcarded path, sorted query)."""
    p = urlsplit(u or "")
    return (p.netloc, _slug_blind(p.path.rstrip("/") or "/"),
            tuple(sorted(parse_qsl(p.query))))


def url_match(final_url: str, reference_url: str) -> bool:
    return bool(reference_url) and url_key(final_url) == url_key(reference_url)
```

In `hsge/webarena/composer.py`, extend the evaluator import:

```python
from .evaluator import normalize_answer, url_key
```

and in `validate_task`'s NAV branch, directly after the existing `"reference_url not in SiteKB"` check, add:

```python
        if url_key(ev.get("reference_url") or "") == url_key(
                task.get("start_url") or kb.site):
            return "NAV reference_url equals start_url"
```

(`generate()` applies `setdefault("start_url", kb.site)` only *after* validation, hence the in-gate fallback to `kb.site`.)

- [ ] **Step 4: Run the two test files**

Run: `python -m pytest hsge/tests/test_evaluator.py hsge/tests/test_composer.py -q`
Expected: all PASS (existing `test_url_match_*` tests prove `url_match` behavior is unchanged by the refactor).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/evaluator.py hsge/webarena/composer.py hsge/tests/test_evaluator.py hsge/tests/test_composer.py
git commit -m "Reject NAV tasks whose reference_url is the start page

run_04 gen_0004: the composer set reference_url to the task's own
start_url; membership in known_urls can't catch that. url_key (the
slug-blind compare) is now a public evaluator helper shared by the gate.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: NAV probe landed-URL check

**Files:**
- Modify: `hsge/webarena/collect.py` (`_is_stale` NAV branch, import)
- Test: `hsge/tests/test_collect.py`

**Interfaces:**
- Consumes: `url_key` from Task 1 (`from .evaluator import ... url_key`).
- Produces: `_is_stale` additionally treats a NAV probe that *lands on a different page than requested* (slug-blind compare) as stale/unreachable — catches login redirects and permission bounces that render no not-found phrase.

- [ ] **Step 1: Write the failing tests**

Append to `hsge/tests/test_collect.py` (the file already has `import re`, `_SiteBrowser`, `_kb_two_pages`, `_task`, `_Solver` from the earlier stale-check work):

```python
class _RedirectBrowser(_SiteBrowser):
    """goto() lands on redirects[target] when mapped (login bounce)."""
    def __init__(self, url, pages, redirects):
        super().__init__(url, pages)
        self.redirects = redirects
    def act(self, action):
        m = re.match(r"goto\('([^']+)'\)", action or "")
        if m:
            self.url = self.redirects.get(m.group(1), m.group(1))
            self.gotos.append(self.url)
        return self.observation()


def test_nav_redirected_reference_url_skips_as_stale(tmp_path):
    # run_04 class: another user's comment-edit page bounces to /login --
    # page exists (no 404 copy), but is unreachable for this account
    pages = {"http://s/home": "home page", "http://s/login": "log in please"}
    redirects = {"http://s/secret/edit": "http://s/login"}
    task = dict(_task("gen_0000", "NAV"), hops=2)
    task["eval"] = {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/secret/edit", "program_html": []}
    runner = GenerationRunner(
        lambda url: _RedirectBrowser(url, pages, redirects), _Solver(),
        str(tmp_path), HashingEmbedder(), _kb_two_pages(), skill_hints=False)
    stats = runner.run([task])
    assert stats["stale_skipped"] == 1 and stats["attempted"] == 0


def test_nav_slug_redirect_is_not_stale(tmp_path):
    # Postmill redirects a stale slug to the canonical one -- same page,
    # slug-blind equal -> must still be attempted
    pages = {"http://s/home": "home page",
             "http://s/f/m/15/real-slug": "target page"}
    redirects = {"http://s/f/m/15/-": "http://s/f/m/15/real-slug"}
    task = dict(_task("gen_0000", "NAV"), hops=2)
    task["eval"] = {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/f/m/15/-", "program_html": []}
    stats = GenerationRunner(
        lambda url: _RedirectBrowser(url, pages, redirects), _Solver(),
        str(tmp_path), HashingEmbedder(), _kb_two_pages(),
        skill_hints=False).run([task])
    assert stats["attempted"] == 1 and stats["stale_skipped"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_collect.py -q`
Expected: `test_nav_redirected_reference_url_skips_as_stale` FAILS (`stale_skipped == 0` — the login page contains no not-found marker, so today's probe says live); `test_nav_slug_redirect_is_not_stale` already PASSES (guards against over-rejection once the check lands); all pre-existing tests still pass.

- [ ] **Step 3: Implement**

In `hsge/webarena/collect.py`, extend the evaluator import:

```python
from .evaluator import evaluate, extract_answer, url_key
```

In `_is_stale`, replace the NAV branch body:

```python
        if ttype == "NAV" and browser is not None:
            ref_url = (task.get("eval") or {}).get("reference_url") or ""
            if ref_url:
                moved = True
                obs = browser.act(f"goto('{ref_url}')")
                tree = str(obs.get("axtree", ""))
                stale = any(m in tree.lower() for m in _NOT_FOUND_MARKERS)
                # landing somewhere else (login page, permission bounce)
                # means the target is unreachable for this account
                if not stale and url_key(str(obs.get("url", ""))) != url_key(ref_url):
                    stale = True
```

- [ ] **Step 4: Run the collect tests**

Run: `python -m pytest hsge/tests/test_collect.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/collect.py hsge/tests/test_collect.py
git commit -m "NAV probe: a redirect away from reference_url means unreachable

run_04 had 0/8 failed NAVs marked stale: permission-gated pages (another
user's comment-edit URL) bounce to /login and render no not-found phrase.
Compare the landed URL slug-blind (url_key) against the requested one.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Site-mechanics INFO ban + relative-time gate

**Files:**
- Modify: `hsge/webarena/composer.py` (two regexes, one prompt rule, two gate checks)
- Test: `hsge/tests/test_composer.py`

**Interfaces:**
- Produces: module-level `INFO_META_RE` and `RELATIVE_TIME_RE` in `composer.py`; `validate_task` rejects any intent matching `RELATIVE_TIME_RE` (reason `"relative-time reference in intent"`, checked before the type branches) and INFO intents matching `INFO_META_RE` (reason `"site-mechanics INFO intent"`, first check of the INFO branch).
- Consumes: nothing from Tasks 1-2.

- [ ] **Step 1: Write the failing test**

Append to `hsge/tests/test_composer.py`:

```python
def test_relative_time_and_site_mechanics_gates():
    kb = _kb()
    info = _info(["n1.e0.attrs.author"], {"exact_match": "hlz0"})
    # run_04 gen_0074: intent goes stale the moment it is written
    assert "relative-time" in validate_task(
        dict(info, intent="Find the text of the comment by MarvelsGrantMan136 "
                          "written 17 minutes ago"), kb, [])
    nav = {"intent": "Go to the post submitted yesterday", "type": "NAV",
           "start_url": "http://s", "hops": 2, "source_nodes": [1],
           "answer_fact_refs": [],
           "eval": {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/f/gaming/post1",
                    "program_html": []}}
    assert "relative-time" in validate_task(nav, kb, [])
    # run_04 gen_0014/0048/0082: Postmill UI trivia the solver misreads
    assert "site-mechanics" in validate_task(
        dict(info, intent="Find the short URL for the post titled "
                          "'New Edited Title Here'"), kb, [])
    assert "site-mechanics" in validate_task(
        dict(info, intent="Is there an RSS link on the gaming forum page"),
        kb, [])
    # content questions with absolute wording still pass
    assert validate_task(
        dict(info, intent="Find the author of the top gaming post"),
        kb, []) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_composer.py::test_relative_time_and_site_mechanics_gates -q`
Expected: FAIL — all four bad shapes currently return `None` (accepted).

- [ ] **Step 3: Implement**

In `hsge/webarena/composer.py`, below `MOD_READONLY_RE`, add:

```python
# Postmill UI trivia ("What is the short URL...") -- the solver reads the
# permalink instead every time, and the answer is site mechanics, not
# content; worthless as SFT signal (run_04: 3/3 such tasks failed).
INFO_META_RE = re.compile(
    r"\b(short\s*url|rss|formatting\s+help|keyboard\s+shortcut)\b", re.I)
# "written 17 minutes ago" is true at digest time and false at solve time:
# the intent itself goes stale, which no page-content re-check can catch.
RELATIVE_TIME_RE = re.compile(
    r"\b\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago\b"
    r"|\b(?:yesterday|today|last\s+(?:week|month|year))\b", re.I)
```

In `validate_task`, directly after the duplicate-intent check (before the `ev`/`types` lines), add:

```python
    if RELATIVE_TIME_RE.search(intent):
        return "relative-time reference in intent"
```

At the top of the INFO branch (before the `"INFO without string_match"` check), add:

```python
        if INFO_META_RE.search(intent):
            return "site-mechanics INFO intent"
```

In `COMPOSER_SYS`, after the existing INFO rule line (the one ending `-- ONLY items shown with grounded=true.\n'`), insert one new rule line:

```python
    '- INFO questions ask about page CONTENT (posts, comments, authors, counts, '
    "dates), never the site's own UI mechanics (short URL, RSS links, formatting "
    'help, keyboard shortcuts), and never relative to now ("posted 17 minutes ago").\n'
```

- [ ] **Step 4: Run the composer tests**

Run: `python -m pytest hsge/tests/test_composer.py -q`
Expected: all PASS (existing fixture intents contain no banned phrase — verified: "hello", "notify me", "great movie", "Dune review" shapes are all clean).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/composer.py hsge/tests/test_composer.py
git commit -m "Composer gates: ban site-mechanics INFO and relative-time intents

run_04: all three 'short URL' INFO tasks failed on Postmill UI trivia,
and 'written 17 minutes ago' made the intent itself stale at solve time.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Evidence-containment gate for INFO references

**Files:**
- Modify: `hsge/webarena/composer.py` (`validate_task` INFO branch)
- Modify: `hsge/tests/test_composer.py` (`_kb()` fixture gains `evidence` fields — required, see Step 1)
- Test: `hsge/tests/test_composer.py`

**Interfaces:**
- Consumes: `kb.resolve_ref_evidence(ref) -> str | None` (existing `SiteKB` method), `normalize_answer` (already imported).
- Produces: `validate_task` additionally rejects an INFO task when a reference target is not a normalized substring of at least one cited ref's `evidence` quote. Reason: `f"reference answer {t!r} not inside cited evidence"`.

- [ ] **Step 1: Update the `_kb()` fixture (existing tests would otherwise break)**

The production digester always writes an `evidence` quote per entity/fact, but `test_composer.py::_kb()` omits it — under the new gate every existing passing INFO fixture would be rejected with empty evidence. Replace the two `add_node` calls in `_kb()` with:

```python
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
```

(The extra node-1 outlinks are Task 1's; if Task 1 already added them, keep them as shown.)

- [ ] **Step 2: Write the failing test**

Append to `hsge/tests/test_composer.py`:

```python
def test_info_reference_must_be_inside_cited_evidence():
    kb = _kb()
    # run_04 gen_0064: score "-1" backed by the fact value but absent from
    # the evidence quote -- _is_stale re-grounding can never protect it
    kb.add_node({"node_index": 3, "url": "http://s/f/movies/9/re",
                 "outlinks": [], "entities": [],
                 "facts": [{"q": "score?", "a": "-1", "grounded": True,
                            "evidence": "Re: Your Comment"}]})
    bad = _info(["n3.f0"], {"exact_match": "-1"})
    assert "not inside cited evidence" in validate_task(bad, kb, [])
    # value quoted inside its evidence still passes
    good = _info(["n1.e0.attrs.author"], {"exact_match": "hlz0"})
    assert validate_task(good, kb, []) is None
```

- [ ] **Step 3: Run tests to verify the new one fails and old ones pass**

Run: `python -m pytest hsge/tests/test_composer.py -q`
Expected: only `test_info_reference_must_be_inside_cited_evidence` FAILS (`bad` is accepted today because "-1" matches the fact *value*); every other test PASSES with the enriched fixture — proving the fixture edit is neutral pre-gate.

- [ ] **Step 4: Implement**

In `validate_task`'s INFO branch, extend the ref-resolution loop to collect evidence, and add the containment check to the target loop. The full updated region:

```python
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
```

- [ ] **Step 5: Run the composer tests**

Run: `python -m pytest hsge/tests/test_composer.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add hsge/webarena/composer.py hsge/tests/test_composer.py
git commit -m "INFO references must appear inside their cited evidence quote

run_04 gen_0064: reference score '-1' matched the digested fact value but
not the evidence quote, so the solve-time re-grounding could not detect
the drifted live value. A reference the stale-check cannot protect must
not be composed.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Full suite, docs, wrap-up

**Files:**
- Modify: `.claude/rules/architecture.md` (phase-2 paragraph)
- Test: whole suite

**Interfaces:** none (documentation + verification only).

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all PASS, no new skips or warnings.

- [ ] **Step 2: Update the architecture rule**

In `.claude/rules/architecture.md`, in the phase-2 paragraph, directly after the sentence block added by the previous package (the one ending `...so short references ("Yes") are judged in context.`), append:

```
A run_04 measurement (77% verified, up from 65%) added five more guards:
NAV tasks whose `reference_url` is the start page itself are rejected
(`url_key`, the slug-blind compare, is now a public evaluator helper); the
NAV probe treats a redirect away from the requested URL (login/permission
bounce) as unreachable; INFO intents about site UI mechanics (short URL,
RSS) and any intent with relative times ("17 minutes ago") are rejected;
and an INFO reference must appear inside its cited `evidence` quote —
otherwise the solve-time re-grounding could never protect it from drift.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/architecture.md
git commit -m "Document the run_04 fix package (Part A) in the architecture rule

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Post-implementation handoff (user-run; the sandbox cannot reach the LAN WebArena)

1. **One-time 404 capture (spec fix #2b):** on a machine that can reach the
   instance, `curl -s http://192.168.1.31:8880/f/movies/99999 | grep -io
   '<title>[^<]*\|not found\|could not be found'` (or open it in a browser)
   and report the distinctive phrase; if it is not already covered by
   `_NOT_FOUND_MARKERS` in `hsge/webarena/collect.py`, add it in a one-line
   follow-up commit.
2. **Measurement run (run_05):**

```bash
conda activate go-browse
mkdir -p outputs/wa_run_05
cp outputs/wa_run_03/{sitekb.json,skills.json,operators.json,graph.json} outputs/wa_run_05/
python run_webarena.py --phase generate --out outputs/wa_run_05
```

Baseline: run_04's 71/92 (INFO 43/52, NAV 12/20, MOD 16/20, 8 stale-skipped).
Expected: the `gen_0004`/short-URL/relative-time classes appear in
`gen_tasks.json`'s `rejected` list instead of `accepted`; NAV
`stale_skipped` > 0 if permission-gated refs recur. Part B (semantic
multi-hop redesign) is decided after these numbers are in.
