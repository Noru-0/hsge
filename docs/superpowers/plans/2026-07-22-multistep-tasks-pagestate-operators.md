# Multi-step tasks + page-state operators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unlock non-zero GOAL tasks on live WebArena runs by proposing multi-step tasks (so adjacent, chainable skills form) and inducing operators whose exit page-state matches the next skill's entry page-state.

**Architecture:** Two surgical, prompt-level changes. (A) A new `COMPOSITE` task type in `PageExplorer` (`EXPLORER_SYS` + tag regex + `_parse_task`) makes the LLM propose 2–3 step tasks; the Solver's multi-step trajectory then segments into adjacent sub-trajectories. (B) `operator_induction._SYS` is reshaped to express preconditions/effects as consistent *page states*, so one operator's effect satisfies another's precondition and `operators.py::edges()` (unchanged) forms the edge that `all_chains` needs.

**Tech Stack:** Python, pytest, numpy-only mock pipeline. Real backends (OpenAI-compatible LLM, BrowserGym) are the live path; no code here touches them directly.

## Global Constraints

- All code, comments, docstrings, and commit messages in **English** (repo convention).
- Run everything from the **repo root** with the conda env active: `conda activate go-browse`; tests via `PYTHONPATH=. python -m pytest hsge/tests/ -q`.
- **Do not perturb the deterministic mock pipeline** — existing tests assert exact skill/operator counts; the prompt strings edited here are ignored by `MockLLM` (it routes only on the substrings `SEGMENT`/`ABSTRACT`/`GROUND` in the *system* prompt), and none of the new prompt text may contain those three tokens.
- Changes are **additive** for existing `INFO`/`NAV`/`MOD` behavior — no existing tag path changes.
- Commit **locally only** (no push). Fold the `.claude/memory/changelog.md` entry into the same commit as the change it describes; get the real time with `date "+%Y-%m-%d %H:%M"`.
- `.claude/memory/bugs.md` stays **Open** — it moves to Fixed only after a live run confirms GOAL > 0 (that run is the acceptance step, outside this plan).

---

### Task 1: COMPOSITE task type (part A)

Add a fourth task type `COMPOSITE` so `PageExplorer` proposes 2–3 step tasks. Truncation (`!= "INFO"`) already keeps non-INFO tags, and `read_only` (`in ("INFO","NAV")`) already fail-closed drops COMPOSITE — both are verified by tests below, not edited.

**Files:**
- Modify: `hsge/webarena/agents.py` — `EXPLORER_SYS` (~line 25), `PageExplorer._TAG_RE` (line 102), `PageExplorer._parse_task` (line 150).
- Test: `hsge/tests/test_page_explorer.py` (append).
- Modify: `.claude/memory/changelog.md`.

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `PageExplorer._parse_task(entry)` now returns tag `"COMPOSITE"` for a `{"type": "COMPOSITE"}` dict or a leading `[COMPOSITE]` bracket; `propose()` emits `"[COMPOSITE] <text>"` strings. Downstream `runtime.py` already treats the `[TAG]` prefix opaquely (buckets every non-GOAL task under `LOCAL`, tag="LOCAL" at runtime.py:673) — no runtime change.

- [ ] **Step 1: Write the failing tests**

Append to `hsge/tests/test_page_explorer.py`:

```python
def test_parse_task_accepts_composite_type_and_bracket():
    assert PageExplorer._parse_task(
        {"text": "open post then reply", "type": "COMPOSITE"}
    ) == ("open post then reply", "COMPOSITE")
    assert PageExplorer._parse_task(
        "[COMPOSITE] open post then reply"
    ) == ("open post then reply", "COMPOSITE")


def test_read_only_drops_composite_task():
    llm = _StubLLM([
        {"text": "read the count", "type": "INFO"},
        {"text": "go to forums", "type": "NAV"},
        {"text": "open post then reply", "type": "COMPOSITE"},
    ])
    explorer = PageExplorer(llm, read_only=True)
    tasks = explorer.propose({"url": "http://x", "axtree": ""})
    assert tasks == ["[INFO] read the count", "[NAV] go to forums"]


def test_truncation_keeps_composite_over_info():
    llm = _StubLLM([
        {"text": "info one", "type": "INFO"},
        {"text": "info two", "type": "INFO"},
        {"text": "open post then reply", "type": "COMPOSITE"},
    ])
    explorer = PageExplorer(llm, max_tasks=1)
    tasks = explorer.propose({"url": "http://x", "axtree": ""})
    assert tasks == ["[COMPOSITE] open post then reply"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_page_explorer.py -q`
Expected: the three new tests FAIL — `_parse_task` returns tag `"UNKNOWN"` for COMPOSITE (so the parse test's tuple mismatches, read-only keeps it as UNKNOWN-dropped or mis-tagged, and truncation ordering differs).

- [ ] **Step 3: Add COMPOSITE to the tag regex and parser**

In `hsge/webarena/agents.py`, line 102, change:

```python
    _TAG_RE = re.compile(r"^\s*\[(INFO|NAV|MOD)\]\s*", re.I)
```

to:

```python
    _TAG_RE = re.compile(r"^\s*\[(INFO|NAV|MOD|COMPOSITE)\]\s*", re.I)
```

In `hsge/webarena/agents.py`, line 150, change:

```python
            if isinstance(raw_type, str) and raw_type.strip().upper() in ("INFO", "NAV", "MOD"):
```

to:

```python
            if isinstance(raw_type, str) and raw_type.strip().upper() in ("INFO", "NAV", "MOD", "COMPOSITE"):
```

- [ ] **Step 4: Add the COMPOSITE type to the explorer prompt**

In `hsge/webarena/agents.py`, `EXPLORER_SYS` (starts line 25), change the JSON contract line (currently):

```python
    "Return JSON {\"tasks\": [{\"text\": \"...\", \"type\": \"INFO\"|\"NAV\"|\"MOD\"}, ...]}.\n"
```

to:

```python
    "Return JSON {\"tasks\": [{\"text\": \"...\", \"type\": \"INFO\"|\"NAV\"|\"MOD\"|\"COMPOSITE\"}, ...]}.\n"
```

Then change the type-definition sentence (currently):

```python
    "- \"type\" must be exactly one of: INFO (read/extract info), NAV (go to a "
    "specific page), MOD (change content/state). List them INFO first, then NAV, "
    "then MOD.\n"
```

to:

```python
    "- \"type\" must be exactly one of: INFO (read/extract info), NAV (go to a "
    "specific page), MOD (change content/state), COMPOSITE (a 2-3 step sequence a "
    "real user chains on one flow, e.g. 'Open the post \"Best budget GPU\", upvote "
    "it, then post a reply' or 'Add the Sony PS5 to the cart, then open the cart' "
    "-- each step concrete and named from THIS page). List them INFO first, then "
    "NAV, then MOD, then COMPOSITE.\n"
```

Then, immediately after the existing line (line ~48):

```python
    "- Prefer tasks that make progress or reveal new pages over pure search/sort/filter.\n"
```

insert a new rule line:

```python
    "- Prefer a COMPOSITE task when the page affords a natural next step after the "
    "first action; keep it to 2-3 concrete steps. Multi-step tasks are how "
    "reusable, chainable skills get discovered.\n"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_page_explorer.py -q`
Expected: PASS (all tests in the file, including the three new ones).

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `PYTHONPATH=. python -m pytest hsge/tests/ -q`
Expected: PASS — previously 152 passed, now 155 (three new tests). No existing test changes count.

- [ ] **Step 7: Update changelog and commit**

Get the time: `date "+%Y-%m-%d %H:%M"`. Append to `.claude/memory/changelog.md` under today's date heading (create if missing, newest day first) an entry naming `hsge/webarena/agents.py` + `hsge/tests/test_page_explorer.py` and what changed (added COMPOSITE task type: prompt, `_TAG_RE`, `_parse_task`; truncation/read_only unchanged and now test-covered).

```bash
git add hsge/webarena/agents.py hsge/tests/test_page_explorer.py .claude/memory/changelog.md
git commit -m "Add COMPOSITE task type so PageExplorer proposes multi-step tasks

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Page-state precondition/effect vocabulary (part B)

Reshape `operator_induction._SYS` so preconditions/effects are consistent *page states*, letting one operator's effect satisfy another's precondition. No schema change; `operators.py::edges()`/`all_chains` unchanged (already covered by `test_goal_task.py`). Side effect: navigating skills get entry ≠ exit, so the anti-tautology gate stops rejecting them.

**Files:**
- Modify: `hsge/operator_induction.py` — `_SYS` (lines 20–34).
- Create: `hsge/tests/test_operator_induction_prompt.py`.
- Modify: `.claude/memory/changelog.md`.

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `_SYS` string now instructs page-state vocabulary. The semantic effect (matching predicates across operators) is only verifiable against a real LLM; the deterministic guarantee here is a contract test that the instruction is present and collision-free with `MockLLM` routing.

- [ ] **Step 1: Write the failing contract test**

Create `hsge/tests/test_operator_induction_prompt.py`:

```python
"""The operator-induction system prompt must ask for page-state
precondition/effect vocabulary (part B of the multi-step/page-state design),
and must not collide with MockLLM's system-prompt routing keywords.

Run:  PYTHONPATH=. python -m pytest hsge/tests/test_operator_induction_prompt.py -q
"""
from hsge.operator_induction import _SYS


def test_sys_prompt_requires_page_state_vocabulary():
    s = _SYS.lower()
    assert "page state" in s or "page-state" in s
    assert "entry" in s and "exit" in s


def test_sys_prompt_does_not_collide_with_mockllm_routing():
    # MockLLM.complete_json routes on these exact substrings in the system
    # prompt; if the induction prompt contained one it would be mis-handled
    # in the deterministic pipeline.
    for token in ("SEGMENT", "ABSTRACT", "GROUND"):
        assert token not in _SYS
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_operator_induction_prompt.py -q`
Expected: `test_sys_prompt_requires_page_state_vocabulary` FAILS (current `_SYS` has no "page state"/"entry"/"exit"). The collision test passes already.

- [ ] **Step 3: Rewrite `_SYS`**

In `hsge/operator_induction.py`, replace the `_SYS` block (lines 20–34) with:

```python
_SYS = (
    "You convert a reusable web skill into a PLANNING OPERATOR. Given the skill "
    "and the page state before/after it ran on a few sites, state the world "
    "conditions in short, site-agnostic natural language. Preconditions = what "
    "must already be true to apply the skill; effects = what becomes true after. "
    "State preconditions and effects as PAGE STATES -- what page or screen the "
    "user is on and what is visible on it (e.g. 'on the product listing page', "
    "'the cart page is shown', 'the checkout page is shown') -- NOT the mere "
    "presence of one element ('a cart link is present'). Include at least one "
    "precondition naming the ENTRY page-state and at least one effect naming the "
    "EXIT page-state, worded so a later skill starting from that exit state would "
    "phrase its own entry precondition identically. This shared page-state "
    "vocabulary is what lets one skill's effect satisfy another skill's "
    "precondition so the planner can chain them. Keep each predicate a terse "
    "phrase. Mark terminal=true only if an effect is a final/transactional state "
    "(order placed, purchase confirmed). "
    "A list of KNOWN predicates from previously induced operators may be "
    "provided. If a precondition or effect you want to state is semantically "
    "equivalent to a known predicate, you MUST reuse that predicate's exact "
    "text verbatim instead of rephrasing it. Only coin a new phrase when no "
    "known predicate matches. "
    'Return JSON {"preconditions": ["..."], "effects": ["..."], "terminal": bool}.'
)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_operator_induction_prompt.py -q`
Expected: PASS (both tests).

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `PYTHONPATH=. python -m pytest hsge/tests/ -q`
Expected: PASS — 157 (Task 1's 155 + two new tests here). No existing test changes count.

- [ ] **Step 6: Update changelog and commit**

Get the time: `date "+%Y-%m-%d %H:%M"`. Append a `.claude/memory/changelog.md` entry naming `hsge/operator_induction.py` + `hsge/tests/test_operator_induction_prompt.py` and what changed (page-state precondition/effect vocabulary so operators chain; also relieves the anti-tautology gate for navigating skills).

```bash
git add hsge/operator_induction.py hsge/tests/test_operator_induction_prompt.py .claude/memory/changelog.md
git commit -m "Induce operators with page-state precondition/effect vocabulary

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Acceptance (outside this plan — user runs it)

After both tasks land, a live re-run is the real test of the design:

```bash
python run_webarena.py --site shopping --max-nodes 80   # + reddit run, per-run key
```

Success = `summary.json` GOAL bucket non-zero and `goal_task`/`GOAL[...]` events in `run_log.jsonl`. Only then: move the bugs.md entry to Fixed, and reword the three thesis overstatements (O2 in Chapter1/Chapter6, §5.1 in Chapter5). If GOAL is still 0, the fallback is the rejected-in-brainstorming compositional generator — revisit then, do not add it pre-emptively.

## Self-Review

- **Spec coverage:** A (COMPOSITE prompt/regex/parser) → Task 1. B (page-state `_SYS`) → Task 2. Testing cases 1–3 → Task 1 Steps 1/5. Spec test case 4 (operators-level chain) is intentionally **not** re-implemented — `hsge/tests/test_goal_task.py::test_deep_graph_yields_depth_task_with_generated_instruction` already proves edge→chain→GOAL when eff/pre match (DRY). Acceptance/thesis steps → "Acceptance" section. `runtime.py` tag-enum verification from the spec → resolved during planning (no assertion exists; runtime buckets by its own LOCAL/GOAL tag), so no runtime task.
- **Placeholder scan:** none — every code/edit step shows exact before/after text.
- **Type consistency:** `_parse_task` returns `(text, tag)` tuples throughout; `propose()` returns `"[TAG] text"` strings; `_TAG_RE` alternation and the `_parse_task` type tuple both list the same four tags.
