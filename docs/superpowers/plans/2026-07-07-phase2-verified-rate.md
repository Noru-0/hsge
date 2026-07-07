# Phase-2 Verified-Rate Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the phase-2 verified rate by fixing the four false-negative / unsatisfiable-spec classes from the run_03 review (spec: `docs/superpowers/specs/2026-07-07-phase2-verified-rate-design.md`).

**Architecture:** Four independent, code-side changes: (1) slug-tolerant `url_match` in `evaluator.py`; (2) question-aware judge in `evaluator.py`; (3) a `SiteKB.node_url_of_ref` helper + extended solve-time stale-check in `collect.py` (multi-hop INFO evidence re-check, NAV dead-target probe); (4) self-verifying-MOD gates in `composer.py` (prompt + `validate_task`). All are mock-testable; no browser or API needed.

**Tech Stack:** Python 3, pytest, existing mock fakes in `hsge/tests/`.

## Global Constraints

- Run everything from the repo root; activate the env first: `conda activate go-browse`.
- Test command form: `python -m pytest hsge/tests/<file>.py -q` (pytest is available in the env).
- All code/comments/commit messages in English. Match existing style (compact, docstring-commented modules).
- The mock pipeline is deterministic — do not touch `hsge/` mock modules outside the four files named below.
- Commit after each task (local only, never push). End commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Real failure shapes from run_03 (use them verbatim in tests where cited): prose assertion `"comment posted successfully"`, jQuery locator `a:contains('Create forum')`, slug-drift pair `/f/movies/15/your-title-here` vs `/f/movies/15/new-title-here`, judge miss `"Yes"` vs `"the moderation log is currently empty"`.

---

### Task 1: Slug-tolerant `url_match`

**Files:**
- Modify: `hsge/webarena/evaluator.py:66-70`
- Test: `hsge/tests/test_evaluator.py`

**Interfaces:**
- Produces: `url_match(final_url: str, reference_url: str) -> bool` — same signature, new behavior: the path segment immediately after the **first** purely-numeric segment is wildcarded on both sides (Postmill slug position, incl. the `-` placeholder). Segment count and all other segments still compare exactly.

- [ ] **Step 1: Write the failing test**

Append to `hsge/tests/test_evaluator.py`:

```python
def test_url_match_ignores_slug_after_first_numeric_id():
    # Postmill slug drift: post retitled between compose and solve (run_03 gen_0076)
    assert url_match("http://s/f/movies/15/new-title-here",
                     "http://s/f/movies/15/your-title-here")
    # '-' is Postmill's empty-slug placeholder
    assert url_match("http://s/f/movies/15/-", "http://s/f/movies/15/some-slug")
    # only the slug slot is blind: comment sub-path still compares exactly
    assert url_match("http://s/f/movies/13/-/comment/56/edit",
                     "http://s/f/movies/13/old-slug/comment/56/edit")
    # structurally different paths must NOT match
    assert not url_match("http://s/f/movies/13/slug",
                         "http://s/f/movies/13/slug/comment/56")
    assert not url_match("http://s/f/movies/14/slug", "http://s/f/movies/15/slug")
    # no numeric segment -> behavior unchanged
    assert not url_match("http://s/p", "http://s/q")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_evaluator.py::test_url_match_ignores_slug_after_first_numeric_id -q`
Expected: FAIL on the first assert (exact-path compare).

- [ ] **Step 3: Implement**

Replace `url_match` in `hsge/webarena/evaluator.py` (currently lines 66-70) with:

```python
def url_match(final_url: str, reference_url: str) -> bool:
    def slug_blind(path: str) -> str:
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

    def key(u: str):
        p = urlsplit(u or "")
        return (p.netloc, slug_blind(p.path.rstrip("/") or "/"),
                tuple(sorted(parse_qsl(p.query))))
    return bool(reference_url) and key(final_url) == key(reference_url)
```

- [ ] **Step 4: Run the evaluator tests**

Run: `python -m pytest hsge/tests/test_evaluator.py -q`
Expected: all PASS (including pre-existing `test_url_match_normalizes`).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/evaluator.py hsge/tests/test_evaluator.py
git commit -m "url_match: wildcard the slug segment after the first numeric id

Postmill retitles change the slug, not the id; run_03 lost ~4 NAV episodes
to exact-path compare against a drifted slug.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Question-aware judge

**Files:**
- Modify: `hsge/webarena/evaluator.py` (`JUDGE_SYS`, `_judge_match`, `string_match`, `evaluate`)
- Test: `hsge/tests/test_evaluator.py`

**Interfaces:**
- Produces: `string_match(answer, reference_answers, judge=None, question="") -> bool` and `_judge_match(answer, references, judge, question="") -> bool`. `evaluate()` passes `question=str(task.get("intent") or "")`. Judge payload becomes `{"question", "answer", "references"}`.
- Consumes: nothing from other tasks (independent of Task 1).

- [ ] **Step 1: Write the failing tests**

Append to `hsge/tests/test_evaluator.py` (add `import json` at the top of the file — it is not imported there yet):

```python
class _PayloadJudge:
    def __init__(self, match=True):
        self.match, self.prompts = match, []
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        return {"match": self.match}


def test_judge_receives_question():
    # run_03 gen_0001: reference "Yes" is meaningless without the question
    j = _PayloadJudge()
    assert string_match("done: the moderation log is currently empty",
                        {"exact_match": "Yes"}, judge=j,
                        question="Check if the moderation log is currently empty.")
    payload = json.loads(j.prompts[0])
    assert payload["question"] == "Check if the moderation log is currently empty."
    assert payload["answer"].startswith("done:")
    assert payload["references"] == ["Yes"]


def test_evaluate_passes_intent_to_judge():
    j = _PayloadJudge()
    task = {"intent": "what is the score?",
            "eval": {"eval_types": ["string_match"],
                     "reference_answers": {"exact_match": "1 point"}}}
    ok, _ = evaluate(task, "done: score is 1", "http://s/p", None, judge=j)
    assert ok
    assert json.loads(j.prompts[0])["question"] == "what is the score?"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_evaluator.py::test_judge_receives_question hsge/tests/test_evaluator.py::test_evaluate_passes_intent_to_judge -q`
Expected: FAIL — `KeyError: 'question'` (payload has no such field yet).

- [ ] **Step 3: Implement**

In `hsge/webarena/evaluator.py`:

Replace `JUDGE_SYS`:

```python
JUDGE_SYS = (
    "You judge whether a web agent's ANSWER to the given QUESTION conveys the "
    "same information as any of the REFERENCE answers. Return JSON "
    "{\"match\": true|false}. Judge meaning, not wording; a short reference "
    "(\"Yes\", a bare number) is judged as an answer to the QUESTION; numbers "
    "and names must actually agree.")
```

Replace `_judge_match` and thread `question` through `string_match`:

```python
def _judge_match(answer: str, references: list, judge, question: str = "") -> bool:
    if judge is None or not references or not normalize_answer(answer):
        return False
    out = judge.complete_json(JUDGE_SYS, json.dumps(
        {"question": question, "answer": answer, "references": references}))
    return bool(out.get("match"))


def string_match(answer: str, reference_answers: dict, judge=None,
                 question: str = "") -> bool:
    refs = reference_answers or {}
    na = normalize_answer(answer)
    if "exact_match" in refs:
        ref = normalize_answer(str(refs["exact_match"]))
        if ref and (na == ref or ref in na):
            return True
        # that fails, fall back to the judge -- most misses are format drift
        return _judge_match(answer, [str(refs["exact_match"])], judge, question)
    if "must_include" in refs:
        items = refs["must_include"] or []
        if items and all(normalize_answer(str(x)) in na for x in items):
            return True
        # judge is documented to accept a match against ANY one reference
        return _judge_match(answer, ["; ".join(str(x) for x in items)] if items else [],
                            judge, question)
    if "fuzzy_match" in refs:
        return _judge_match(answer, refs["fuzzy_match"] or [], judge, question)
    return False
```

(Note: keep the exact body of the existing exact/must_include/fuzzy logic — the only change is the extra `question` parameter on the signature and the three `_judge_match` calls.)

In `evaluate()`, change the `string_match` dispatch line to:

```python
            details[t] = string_match(answer, ev.get("reference_answers") or {},
                                      judge=judge,
                                      question=str(task.get("intent") or ""))
```

- [ ] **Step 4: Run the evaluator tests**

Run: `python -m pytest hsge/tests/test_evaluator.py -q`
Expected: all PASS (the pre-existing `_Judge`/`_CountingJudge` tests still pass — default `question=""` keeps their call sites valid).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/evaluator.py hsge/tests/test_evaluator.py
git commit -m "Judge receives the task intent: short references judged in context

run_03 gen_0001: reference 'Yes' vs answer 'the moderation log is currently
empty' could never match with the question absent from the judge payload.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `SiteKB.node_url_of_ref`

**Files:**
- Modify: `hsge/webarena/digest.py` (add method to `SiteKB`, next to `resolve_ref_evidence`)
- Test: `hsge/tests/test_digest.py`

**Interfaces:**
- Produces: `SiteKB.node_url_of_ref(ref: str) -> str | None` — the `url` of the node a ref like `n12.f3` / `n13.e1` / `n13.e1.attrs.author` points at, or `None` for an unparsable ref / unknown node / empty url. Task 4 consumes this.

- [ ] **Step 1: Write the failing test**

Append to `hsge/tests/test_digest.py`:

```python
def test_node_url_of_ref():
    kb = SiteKB()
    kb.add_node({"node_index": 3, "url": "http://s/p3",
                 "entities": [{"name": "x", "grounded": True, "evidence": "x"}],
                 "facts": [{"q": "?", "a": "y", "grounded": True, "evidence": "y"}]})
    assert kb.node_url_of_ref("n3.f0") == "http://s/p3"
    assert kb.node_url_of_ref("n3.e0.attrs.author") == "http://s/p3"
    assert kb.node_url_of_ref("n9.f0") is None
    assert kb.node_url_of_ref("garbage") is None
```

(If `test_digest.py` does not already import `SiteKB`, add `from hsge.webarena.digest import SiteKB` to its imports.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_digest.py::test_node_url_of_ref -q`
Expected: FAIL — `AttributeError: 'SiteKB' object has no attribute 'node_url_of_ref'`.

- [ ] **Step 3: Implement**

In `hsge/webarena/digest.py`, add to `SiteKB` directly below `resolve_ref_evidence`:

```python
    def node_url_of_ref(self, ref: str) -> str | None:
        """URL of the node a ref points at (where its evidence was captured)."""
        m = _REF_RE.match(ref or "")
        if not m:
            return None
        node = self.node_by_index(int(m.group(1)))
        return (node or {}).get("url") or None
```

- [ ] **Step 4: Run the digest tests**

Run: `python -m pytest hsge/tests/test_digest.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/digest.py hsge/tests/test_digest.py
git commit -m "SiteKB.node_url_of_ref: map a ref to the URL its evidence lives on

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Extended solve-time stale-check (multi-hop INFO + NAV)

**Files:**
- Modify: `hsge/webarena/collect.py` (`_is_stale`, its call site in `run()`)
- Test: `hsge/tests/test_collect.py`

**Interfaces:**
- Consumes: `SiteKB.node_url_of_ref` (Task 3), `evidence_grounded` (already imported in `collect.py`).
- Produces: `GenerationRunner._is_stale(task, axtree, browser=None) -> bool` — now checks **all** INFO tasks (navigating to each ref's node URL when it differs from `start_url`) and NAV tasks (probing `reference_url` for a not-found page). When it navigated and the task is not stale, it restores the browser to `task["start_url"]` before returning. Module-level constant `_NOT_FOUND_MARKERS: tuple[str, ...]`.

- [ ] **Step 1: Write the failing tests**

Append to `hsge/tests/test_collect.py` (add `import re` to its imports):

```python
class _SiteBrowser:
    """URL-addressed fake: per-page axtrees, goto() switches pages; a URL not
    in `pages` renders a not-found page (dead link)."""
    def __init__(self, url, pages):
        self.url, self.pages, self.gotos = url, pages, []
    def reset(self): return self.observation()
    def observation(self):
        return {"url": self.url,
                "axtree": self.pages.get(self.url, "404 Not Found")}
    def act(self, action):
        m = re.match(r"goto\('([^']+)'\)", action or "")
        if m:
            self.url = m.group(1)
            self.gotos.append(self.url)
        return self.observation()
    def eval_js(self, expr): return ""
    def close(self): pass


def _kb_two_pages():
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 1, "url": "http://s/home",
                 "outlinks": ["http://s/page2"], "entities": [], "facts": []})
    kb.add_node({"node_index": 2, "url": "http://s/page2", "outlinks": [],
                 "entities": [],
                 "facts": [{"q": "fact?", "a": "42", "grounded": True,
                            "evidence": "old fact"}]})
    return kb


def test_multihop_info_stale_evidence_on_linked_node_skips(tmp_path):
    # evidence "old fact" no longer on page2 -> stale skip, no solve spent
    pages = {"http://s/home": "home page", "http://s/page2": "fresh content only"}
    task = dict(_task("gen_0000", ra={"must_include": ["42"]}),
                hops=3, answer_fact_refs=["n2.f0"])
    runner = GenerationRunner(lambda url: _SiteBrowser(url, pages), _Solver(),
                              str(tmp_path), HashingEmbedder(), _kb_two_pages(),
                              skill_hints=False)
    stats = runner.run([task])
    assert stats["stale_skipped"] == 1 and stats["attempted"] == 0


def test_multihop_info_live_evidence_solves_from_start_url(tmp_path):
    pages = {"http://s/home": "home page",
             "http://s/page2": "page still shows old fact here"}
    browsers = []
    def factory(url):
        b = _SiteBrowser(url, pages); browsers.append(b); return b
    task = dict(_task("gen_0000", ra={"must_include": ["42"]}),
                hops=3, answer_fact_refs=["n2.f0"])
    runner = GenerationRunner(factory, _Solver(), str(tmp_path),
                              HashingEmbedder(), _kb_two_pages(),
                              skill_hints=False)
    stats = runner.run([task])
    assert stats["attempted"] == 1 and stats["verified"] == 1
    # stale check visited the evidence node, then restored start_url pre-solve
    assert browsers[0].gotos == ["http://s/page2", "http://s/home"]


def test_nav_dead_reference_url_skips_as_stale(tmp_path):
    task = dict(_task("gen_0000", "NAV"), hops=2)
    task["eval"] = {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/gone", "program_html": []}
    runner = GenerationRunner(
        lambda url: _SiteBrowser(url, {"http://s/home": "home page"}), _Solver(),
        str(tmp_path), HashingEmbedder(), _kb_two_pages(), skill_hints=False)
    stats = runner.run([task])
    assert stats["stale_skipped"] == 1 and stats["attempted"] == 0


def test_nav_live_reference_url_still_attempted(tmp_path):
    pages = {"http://s/home": "home page", "http://s/target": "target page"}
    browsers = []
    def factory(url):
        b = _SiteBrowser(url, pages); browsers.append(b); return b
    task = dict(_task("gen_0000", "NAV"), hops=2)
    task["eval"] = {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/target", "program_html": []}
    stats = GenerationRunner(factory, _Solver(), str(tmp_path),
                             HashingEmbedder(), _kb_two_pages(),
                             skill_hints=False).run([task])
    assert stats["attempted"] == 1
    assert browsers[0].gotos == ["http://s/target", "http://s/home"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_collect.py -q`
Expected: the four new tests FAIL (multi-hop INFO and NAV are not checked today: `stale_skipped == 0`, no gotos); the pre-existing tests still pass.

- [ ] **Step 3: Implement**

In `hsge/webarena/collect.py`, add near the imports:

```python
_NOT_FOUND_MARKERS = ("page not found", "404 not found")
```

Replace `_is_stale` (currently lines 58-69) with:

```python
    def _is_stale(self, task: dict, axtree: str, browser=None) -> bool:
        """A task's ground truth may have been mutated by a later phase-1/2
        write to the shared, mutable site since its digest was captured:
        re-check an INFO task's cited evidence on the node page it came from,
        and probe a NAV task's reference_url for a dead page, before spending
        a solve+score on what would be a false failure. May navigate; restores
        start_url before returning when the task is live."""
        ttype = task.get("type")
        start_url = task.get("start_url") or ""
        moved, stale = False, False
        if ttype == "NAV" and browser is not None:
            ref_url = (task.get("eval") or {}).get("reference_url") or ""
            if ref_url:
                moved = True
                tree = str(browser.act(f"goto('{ref_url}')").get("axtree", ""))
                stale = any(m in tree.lower() for m in _NOT_FOUND_MARKERS)
        elif ttype == "INFO":
            for ref in task.get("answer_fact_refs") or []:
                evidence = self.kb.resolve_ref_evidence(ref)
                if not evidence:
                    continue
                node_url = self.kb.node_url_of_ref(ref)
                tree = axtree
                if node_url and node_url != start_url and browser is not None:
                    moved = True
                    tree = str(browser.act(f"goto('{node_url}')").get("axtree", ""))
                if not evidence_grounded(evidence, tree):
                    stale = True
                    break
        if moved and not stale:
            browser.act(f"goto('{start_url}')")
        return stale
```

In `run()`, change the call site (currently line 98) to pass the browser:

```python
                if self._is_stale(task, obs.get("axtree", ""), browser):
```

Also update the module docstring's stale sentence if present, and the class-level
comment stays as is.

- [ ] **Step 4: Run the collect tests**

Run: `python -m pytest hsge/tests/test_collect.py -q`
Expected: all PASS (old tests: their tasks have empty `answer_fact_refs` and no NAV type, so behavior is unchanged for them).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/collect.py hsge/tests/test_collect.py
git commit -m "Stale-check every INFO ref on its own node page and probe NAV targets

run_03: ~5 INFO failures were mutated ground truth outside the single-hop
window, and NAV solves burned 25-step budgets on reference URLs that no
longer exist. _is_stale now navigates to each ref's node, requires the
quoted evidence live, probes NAV reference_url for a not-found page, and
restores start_url before the solve.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Self-verifying MOD gates in the composer

**Files:**
- Modify: `hsge/webarena/composer.py` (`COMPOSER_SYS` MOD rule, `validate_task` MOD branch)
- Test: `hsge/tests/test_composer.py` (two existing cases must be updated — see Step 1)

**Interfaces:**
- Consumes: `normalize_answer` (already imported in `composer.py`), `kb.known_urls()`.
- Produces: `validate_task` rejects a MOD task when any `program_html` entry has a non-empty `locator`, a `url` that is neither `"last"` nor in `kb.known_urls()`, an empty `must_include`, or any `must_include` string that is not a normalized substring of the intent. Rejection reasons (exact strings, used by tests): `"MOD locator must be empty (whole-page check)"`, `"MOD program_html url not in SiteKB"`, `"MOD without must_include"`, `f"must_include {s!r} not quoted in intent"`.

- [ ] **Step 1: Update the two existing test cases the new gate breaks**

In `hsge/tests/test_composer.py::test_validate_nav_mod_and_dedup`:

The `"Check the 'notify me' box under Dune review"` case currently inherits `mod`'s eval (`must_include: ["hello"]`, not in that intent). Replace that assertion with one carrying its own matching eval:

```python
    # ... but an imperative "Check the X box" is a real MOD and still passes
    mod_check = dict(mod, intent="Check the 'notify me' box under Dune review",
                     eval={"eval_types": ["program_html"], "reference_answers": None,
                           "reference_url": None,
                           "program_html": [{"url": "http://s/f/movies", "locator": "",
                                             "required_contents":
                                                 {"must_include": ["notify me"]}}]})
    assert validate_task(mod_check, kb, []) is None
```

The collision case `mod2 = dict(mod, intent="post another comment under Dune review")` no longer contains "hello"; change it so the substring gate passes and the collision gate is what fires:

```python
    mod2 = dict(mod, intent="post another comment saying hello under the Dune thread")
    assert "collides" in validate_task(mod2, kb, [dict(mod, task_id="gen_0000")])
```

(The base `mod` task — intent "post a comment saying hello under Dune review", `must_include: ["hello"]`, `locator: ""`, url `http://s/f/movies` ∈ known_urls — already satisfies every new gate and stays as is.)

- [ ] **Step 2: Write the failing tests for the new gates**

Append to `hsge/tests/test_composer.py`:

```python
def test_validate_mod_self_verifying_gates():
    kb = _kb()
    def mod(intent, ph):
        return {"intent": intent, "type": "MOD", "start_url": "http://s", "hops": 2,
                "source_nodes": [2], "answer_fact_refs": [],
                "eval": {"eval_types": ["program_html"], "reference_answers": None,
                         "reference_url": None, "program_html": ph}}
    good = mod('post a comment saying "great movie" under Dune review',
               [{"url": "http://s/f/movies", "locator": "",
                 "required_contents": {"must_include": ["great movie"]}}])
    assert validate_task(good, kb, []) is None
    # run_03 gen_0091: prose assertion the DOM will never contain
    prose = mod("post a new comment on the Dune review",
                [{"url": "last", "locator": "",
                  "required_contents": {"must_include": ["comment posted successfully"]}}])
    assert "not quoted in intent" in validate_task(prose, kb, [])
    # run_03 gen_0099: jQuery pseudo-selector locator
    jq = mod('add a comment saying "nice" under Dune review',
             [{"url": "last", "locator": "a:contains('Create forum')",
               "required_contents": {"must_include": ["nice"]}}])
    assert "locator" in validate_task(jq, kb, [])
    unknown = mod('post a comment saying "nice" under Dune review',
                  [{"url": "http://elsewhere/x", "locator": "",
                    "required_contents": {"must_include": ["nice"]}}])
    assert "not in SiteKB" in validate_task(unknown, kb, [])
    empty = mod('post a comment saying "nice" under Dune review',
                [{"url": "last", "locator": "",
                  "required_contents": {"must_include": []}}])
    assert "without must_include" in validate_task(empty, kb, [])
```

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `python -m pytest hsge/tests/test_composer.py -q`
Expected: `test_validate_mod_self_verifying_gates` FAILS (prose/jq/unknown/empty all return `None` today); `test_validate_nav_mod_and_dedup` PASSES already with its Step-1 updates (they were written to be forward-compatible; if it fails here, the Step-1 edit is wrong — fix it, not the gate).

- [ ] **Step 4: Implement**

In `hsge/webarena/composer.py`:

Replace the MOD rule line in `COMPOSER_SYS` (the `'- MOD: ...'` string) with:

```python
    '- MOD: must PERFORM a state-changing action (post, edit, subscribe, vote, ...); '
    'a read-only question ("check if/whether ...") is INFO, not MOD. The intent MUST '
    'quote, verbatim, the literal text the change will leave visible on the page '
    '(the comment/reply body you choose, or the expected button/label text after '
    'the toggle). eval_types=["program_html"]; entries are {"url": <a knowledge URL '
    'where the change will be visible, or "last">, "locator": "", '
    '"required_contents": {"must_include": [<exactly that quoted text>]}}. '
    'Never destructive (no delete/remove/logout/password/ban).\n'
```

In `validate_task`'s MOD branch, after the existing `"MOD without program_html"` check and **before** the collision check, insert:

```python
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
```

Update the module docstring line "MOD intents pass a denylist and must not collide on program_html targets." to "MOD intents pass a denylist, are self-verifying (must_include quoted in the intent, empty locator, known target URL), and must not collide on program_html targets."

- [ ] **Step 5: Run the composer tests**

Run: `python -m pytest hsge/tests/test_composer.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add hsge/webarena/composer.py hsge/tests/test_composer.py
git commit -m "Composer: self-verifying MOD tasks (must_include quoted in intent)

run_03's real MODs failed on unsatisfiable specs: prose must_include
('comment posted successfully'), jQuery :contains locators, invented
attributes. The intent now embeds the literal post-change text; code gates
require must_include be a substring of the intent, an empty locator, and a
'last'/known target URL.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Full suite, docs, wrap-up

**Files:**
- Modify: `.claude/rules/architecture.md` (phase-2 paragraph)
- Test: whole suite

**Interfaces:** none (documentation + verification only).

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all PASS, no skips introduced by this work.

- [ ] **Step 2: Update the architecture rule**

In `.claude/rules/architecture.md`, in the phase-2 paragraph (the one beginning "Scoring learned three lessons from `wa_run_03`"), append after the stale-evidence sentence (ending "...so digests go stale."):

```
The run_03 phase-2 re-run added four more: `_is_stale` now re-checks every
INFO task's cited evidence on the node page it came from (goto + literal
substring, restoring `start_url` when live) and probes a NAV task's
`reference_url` for a not-found page before solving; MOD tasks are
self-verifying — `validate_task` requires every `program_html` `must_include`
to be quoted verbatim in the intent, an empty `locator`, and a `"last"`/known
target URL, so prose assertions and pseudo-selectors never reach the runner;
`url_match` wildcards the path segment after the first numeric segment
(Postmill retitles change the slug, not the id); and the `judge` role receives
the task intent, so short references ("Yes") are judged in context.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/architecture.md
git commit -m "Document the phase-2 verified-rate package in the architecture rule

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Post-implementation handoff (user-run; the sandbox cannot reach the LAN WebArena)

Measurement run, per the spec (fresh out-dir avoids the `_done_task_ids` /
recomposed-`gen_0000` id collision):

```bash
conda activate go-browse
mkdir -p outputs/wa_run_04
cp outputs/wa_run_03/{sitekb.json,skills.json,operators.json,graph.json} outputs/wa_run_04/
python run_webarena.py --phase generate --out outputs/wa_run_04
```

Compare `outputs/wa_run_04/summary.json`'s `gen` block against run_03's
58/89 (INFO 41/49, NAV 11/20, MOD 6/20); MOD is the headline number.
