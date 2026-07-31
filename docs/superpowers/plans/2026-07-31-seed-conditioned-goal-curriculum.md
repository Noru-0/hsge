# Seed-Conditioned GOAL Curriculum (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give HSGE a top-down, site-seed-derived GOAL source so a live run produces a **non-zero GOAL bucket** (`summary.json` `GOAL.success + GOAL.fail > 0`) for the first time — bypassing the currently edgeless operator graph (open bug O2).

**Architecture:** At the first node of a run, an LLM `SiteSeeder` self-summarizes the real site into `{description, capabilities[]}`. That seed (a) is given to `PageExplorer.propose()` as **extra context** that *adds* seed-aligned COMPOSITE tasks without replacing the diverse page-specific INFO/**NAV**/MOD tasks, and (b) is emitted **directly as GOAL tasks** in `_goal_task()` — one per capability, attempted once per run, verified self-graded (`goal_predicate=None`), independent of `all_chains()`. Every node therefore runs BOTH task sets. Everything is gated behind `run.use_site_seed` (default `false`) so the deterministic mock pipeline and existing runs are untouched.

**Task diversity & frontier (design intent, must be preserved):** each node keeps proposing a diverse set of *local* tasks — crucially the **NAV** tasks, because a solved NAV task adds a **tier-0 "reached" URL** to the frontier (a page the agent actually landed on), which is a higher-signal exploration node than a **tier-1 mined `<a href>`**. Seed conditioning is strictly **additive**: it must never nudge the explorer to drop NAV/INFO/MOD in favor of COMPOSITE, or the frontier degrades to crawl-only and meaningful nodes shrink. The existing `propose()` truncation already protects this (drops INFO first, keeps NAV/MOD + a COMPOSITE reserve); the seed prompt wording below is worded to protect it on the *generation* side too.

**Tech Stack:** Python 3, numpy-only mock core, `LLM.complete_json` backend seam, pytest. Conda env `go-browse`.

## Global Constraints

- Run everything from repo root (dir containing `hsge/`). Activate env: `conda activate go-browse`.
- All code/comments/docstrings in **English** (repo convention).
- Mock pipeline stays **deterministic**: every new capability is LLM-backed and reached only when `use_site_seed=True`; default-off path must be byte-for-byte the old behavior.
- New role name is exactly `site_seeder` (must match across `AGENT_ROLES`, config `llm.agents.site_seeder`, and `WebArenaExplorer.role("site_seeder")`).
- `SEEDER_SYS` must start with the literal token `SUMMARIZE` (the dry-run `_DryLLM` routes on system-prompt prefix) and must contain **none** of MockLLM's routing tokens `SEGMENT` / `ABSTRACT` / `GROUND`.
- TDD: red before green, full suite green after each task (currently **165 passed**). Frequent commits (one per task).
- `git commit` messages end with the repo's `Co-Authored-By:` trailer. Do NOT push. Update `.claude/memory/changelog.md` in the final task's commit.

---

## Prompts for review (verbatim)

These are the only two new/changed prompts in Phase A. Everything downstream (GOAL task text) reuses `capabilities[i].goal` **as-is**, so the seeder prompt is where GOAL quality is decided — review it hardest.

### 1. `SEEDER_SYS` — new, `hsge/webarena/agents.py`

```
SUMMARIZE this website into a reusable profile for an exploration agent. You are
shown the landing page (its URL and accessibility tree). Infer what KIND of site
this is and the main GOALS a real user comes here to accomplish.
Return JSON: {"description": "<one or two sentences: what this site is and who
uses it>", "capabilities": [{"name": "<short slug, e.g. 'checkout'>", "goal":
"<one natural user intent that exercises this capability>"}, ...]}.
Rules:
- List 4-8 capabilities, ordered from most central to most peripheral.
- Each "goal" must be a concrete, self-contained user intent phrased the way a
  real user would state it (WHAT they want), NOT a click-by-click script.
- Each "goal" must inherently take SEVERAL actions to satisfy -- a multi-step
  flow, not a one-shot lookup. GOOD: "Buy the cheapest in-stock wireless mouse
  and reach the order confirmation", "Post a new question to the most active
  forum and add a first comment". BAD (single lookup): "Find the store's phone
  number". BAD (step script): "Click Cart, then click Checkout, then click Pay".
- Ground every capability in what THIS site actually offers -- use section/menu
  names visible in the tree. Do NOT invent features you cannot see on the page.
- Prefer capabilities whose completion CHANGES site state or reaches a NEW page
  (these yield chainable, reusable skills) over pure read-only lookups.
- NEVER include an account/authentication goal -- log in/out, sign in/up,
  register, create an account, change/reset/forgot password, edit email/username,
  manage security settings, or delete/deactivate the account. The session is
  already authenticated and the account is shared across runs, so these are
  useless and risk locking the run out.
```

### 2. Seed block appended to the `PageExplorer.propose()` **user** prompt — `hsge/webarena/agents.py`

`EXPLORER_SYS` (the system prompt) is **not** modified — the seed is per-site data, so it belongs in the user prompt beside `URL`/`PAGE`, and keeping `EXPLORER_SYS` unchanged preserves its existing prompt-assertion tests. The block is added only when a non-empty seed is passed. It is worded to be **additive** — seed goals add COMPOSITE tasks, they never replace the diverse page-specific tasks (especially NAV, which grows the tier-0 frontier):

```
SITE GOALS (what this whole site is for) -- use as EXTRA context, NOT as a
replacement for page-specific tasks:
<description>
Capabilities a user comes here to accomplish:
- <name>: <goal>
- <name>: <goal>
...
Still propose a DIVERSE mix grounded in THIS page: keep the NAV tasks that reach
other pages (they are what makes exploration discover new pages) and the
INFO/MOD tasks specific to this page. In ADDITION, when this page affords it,
include 1-2 COMPOSITE tasks that advance one of the site goals above. Do NOT let
the site goals crowd out page-specific NAV/INFO/MOD tasks, and do NOT propose a
capability this page cannot support.
```

---

## File structure

- `hsge/webarena/agents.py` — add `SEEDER_SYS` + `SiteSeeder` class (P1); add `site_seed` param + seed block to `PageExplorer.propose()` (P3). Same file: both are prompt-owning agents.
- `hsge/webarena/runtime.py` — wire `site_seeder` role, derive seed once in `run()`, persist `seed.json`, checkpoint `site_seed`/`_attempted_capabilities`, add seed source to `_goal_task()` (P2 + wiring).
- `run_webarena.py` — register `site_seeder` in `AGENT_ROLES`, add `run.use_site_seed` default, pass it through, enable it in `--dry-run`, add the `SUMMARIZE` branch to `_DryLLM`.
- `config.yaml` — document `run.use_site_seed: false` and an optional `llm.agents.site_seeder` example (commented).
- Tests: `hsge/tests/test_site_seeder.py` (new), additions to `hsge/tests/test_page_explorer.py`, `hsge/tests/test_goal_task.py`, `hsge/tests/test_multi_llm.py`, `hsge/tests/test_resume.py`, and the dry-run test.

**Scope note:** Phase B (Explorer bottom-up refinement + inline Verifier) and Phase C (auto verify-predicate + coverage-driven frontier) are deferred to their own plans — each is an independent subsystem. This plan alone produces working, testable software: GOAL tasks that actually run on a live site.

---

## Task 1: `SiteSeeder` — derive a site profile from the landing page

**Files:**
- Modify: `hsge/webarena/agents.py` (add `SEEDER_SYS`, `SiteSeeder`)
- Test: `hsge/tests/test_site_seeder.py` (create)

**Interfaces:**
- Produces: `SEEDER_SYS: str`; `class SiteSeeder(llm)` with
  `derive(obs: dict) -> dict` returning `{"description": str, "capabilities": [{"name": str, "goal": str}, ...]}` (empty `{"description": "", "capabilities": []}` on refusal/garbage). Consumes `obs["url"]`, `obs["axtree"]`; calls `llm.complete_json(SEEDER_SYS, prompt)`.

- [ ] **Step 1: Write the failing test**

```python
# hsge/tests/test_site_seeder.py
"""SiteSeeder turns a landing page into a {description, capabilities[]} profile.
Run: PYTHONPATH=. python -m pytest hsge/tests/test_site_seeder.py -q
"""
from hsge.webarena.agents import SEEDER_SYS, SiteSeeder


class _StubLLM:
    def __init__(self, out):
        self._out = out
        self.calls = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls.append((system, prompt))
        return self._out


def test_seeder_prompt_prefix_and_no_mock_tokens():
    # dry-run _DryLLM routes on this prefix; MockLLM routes on SEGMENT/ABSTRACT/GROUND
    assert SEEDER_SYS.startswith("SUMMARIZE")
    for tok in ("SEGMENT", "ABSTRACT", "GROUND"):
        assert tok not in SEEDER_SYS


def test_derive_parses_description_and_capabilities():
    llm = _StubLLM({
        "description": "A demo shopping site for electronics.",
        "capabilities": [
            {"name": "checkout", "goal": "Buy the cheapest in-stock mouse and confirm the order."},
            {"name": "search", "goal": "Find all laptops under $500 and open the first."},
        ],
    })
    seed = SiteSeeder(llm).derive({"url": "http://shop/", "axtree": "Home ..."})
    assert seed["description"].startswith("A demo shopping")
    assert [c["name"] for c in seed["capabilities"]] == ["checkout", "search"]
    # the page axtree and url reach the model
    assert "http://shop/" in llm.calls[0][1]


def test_derive_drops_auth_capabilities_and_entries_without_goal():
    llm = _StubLLM({
        "description": "d",
        "capabilities": [
            {"name": "login", "goal": "Log in to your account."},   # auth -> dropped
            {"name": "broken"},                                       # no goal -> dropped
            {"name": "cart", "goal": "Add three books to the cart."},
        ],
    })
    seed = SiteSeeder(llm).derive({"url": "http://x/", "axtree": ""})
    assert [c["name"] for c in seed["capabilities"]] == ["cart"]


def test_derive_returns_empty_on_garbage():
    seed = SiteSeeder(_StubLLM({"nonsense": 1})).derive({"url": "http://x/", "axtree": ""})
    assert seed == {"description": "", "capabilities": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda activate go-browse && PYTHONPATH=. python -m pytest hsge/tests/test_site_seeder.py -q`
Expected: FAIL with `ImportError: cannot import name 'SEEDER_SYS'` (or `SiteSeeder`).

- [ ] **Step 3: Write minimal implementation**

Add near `EXPLORER_SYS` in `hsge/webarena/agents.py`:

```python
SEEDER_SYS = (
    "SUMMARIZE this website into a reusable profile for an exploration agent. "
    "You are shown the landing page (its URL and accessibility tree). Infer what "
    "KIND of site this is and the main GOALS a real user comes here to accomplish.\n"
    "Return JSON: {\"description\": \"<one or two sentences: what this site is and "
    "who uses it>\", \"capabilities\": [{\"name\": \"<short slug, e.g. 'checkout'>\", "
    "\"goal\": \"<one natural user intent that exercises this capability>\"}, ...]}.\n"
    "Rules:\n"
    "- List 4-8 capabilities, ordered from most central to most peripheral.\n"
    "- Each \"goal\" must be a concrete, self-contained user intent phrased the way "
    "a real user would state it (WHAT they want), NOT a click-by-click script.\n"
    "- Each \"goal\" must inherently take SEVERAL actions to satisfy -- a multi-step "
    "flow, not a one-shot lookup. GOOD: 'Buy the cheapest in-stock wireless mouse "
    "and reach the order confirmation', 'Post a new question to the most active "
    "forum and add a first comment'. BAD (single lookup): 'Find the store's phone "
    "number'. BAD (step script): 'Click Cart, then click Checkout, then click Pay'.\n"
    "- Ground every capability in what THIS site actually offers -- use section/menu "
    "names visible in the tree. Do NOT invent features you cannot see on the page.\n"
    "- Prefer capabilities whose completion CHANGES site state or reaches a NEW page "
    "(these yield chainable, reusable skills) over pure read-only lookups.\n"
    "- NEVER include an account/authentication goal -- log in/out, sign in/up, "
    "register, create an account, change/reset/forgot password, edit email/username, "
    "manage security settings, or delete/deactivate the account. The session is "
    "already authenticated and the account is shared across runs, so these are "
    "useless and risk locking the run out.")


class SiteSeeder:
    """One-shot per run: turns a landing page into a {description, capabilities[]}
    profile that conditions task proposals and seeds top-down GOAL tasks. LLM-backed;
    only used when run.use_site_seed is on, so the mock pipeline is untouched."""

    _AUTH_RE = re.compile(
        r"\b(log ?in|log ?out|sign ?in|sign ?up|register|create an account|"
        r"password|deactivate|delete (the |your )?account)\b", re.I)

    def __init__(self, llm):
        self.llm = llm

    def derive(self, obs: dict) -> dict:
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}"
        out = self.llm.complete_json(SEEDER_SYS, prompt)
        description = out.get("description")
        raw = out.get("capabilities")
        if not isinstance(description, str) or not isinstance(raw, list):
            return {"description": "", "capabilities": []}
        caps = []
        for c in raw:
            if not isinstance(c, dict):
                continue
            goal = c.get("goal")
            name = c.get("name") or (goal or "")
            if not isinstance(goal, str) or not goal.strip():
                continue
            if self._AUTH_RE.search(goal) or self._AUTH_RE.search(str(name)):
                continue
            caps.append({"name": str(name).strip(), "goal": goal.strip()})
        return {"description": description.strip(), "capabilities": caps}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_site_seeder.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/agents.py hsge/tests/test_site_seeder.py
git commit -m "feat(seed): add SiteSeeder + SEEDER_SYS to derive a site profile"
```

---

## Task 2: Seed-condition `PageExplorer.propose()`

**Files:**
- Modify: `hsge/webarena/agents.py` (`PageExplorer.propose` signature + user-prompt block)
- Test: `hsge/tests/test_page_explorer.py` (add cases)

**Interfaces:**
- Consumes: seed shape from Task 1 (`{"description": str, "capabilities": [{"name","goal"}]}`).
- Produces: `PageExplorer.propose(self, obs, screenshot_b64=None, site_seed=None)` — new optional keyword `site_seed`; when it carries capabilities, a `SITE GOALS` block is appended to the user prompt. `None`/empty → prompt identical to today.

- [ ] **Step 1: Write the failing test**

```python
# append to hsge/tests/test_page_explorer.py
class _PromptCapturingLLM:
    def __init__(self):
        self.prompt = None

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompt = prompt
        return {"tasks": ["[NAV] a"]}


def test_propose_injects_site_goals_when_seed_present():
    llm = _PromptCapturingLLM()
    seed = {"description": "A shop for gadgets.",
            "capabilities": [{"name": "checkout", "goal": "Buy a gadget and confirm the order."}]}
    PageExplorer(llm).propose({"url": "http://x", "axtree": "tree"}, site_seed=seed)
    assert "SITE GOALS" in llm.prompt
    assert "A shop for gadgets." in llm.prompt
    assert "Buy a gadget and confirm the order." in llm.prompt
    # additive, not suppressive: the block must protect NAV / page-specific tasks
    assert "NAV" in llm.prompt
    assert "crowd out" in llm.prompt


def test_propose_omits_site_goals_when_seed_absent_or_empty():
    for seed in (None, {"description": "", "capabilities": []}):
        llm = _PromptCapturingLLM()
        PageExplorer(llm).propose({"url": "http://x", "axtree": "tree"}, site_seed=seed)
        assert "SITE GOALS" not in llm.prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_page_explorer.py -q`
Expected: FAIL — `propose()` got an unexpected keyword argument `site_seed`.

- [ ] **Step 3: Write minimal implementation**

Change the `propose` signature and add the block after the `PAGE` section (before the `ALREADY PROPOSED` block) in `hsge/webarena/agents.py`:

```python
    def propose(self, obs: dict, screenshot_b64: str | None = None,
                site_seed: dict | None = None) -> list[str]:
        system = EXPLORER_SYS + (READONLY_NOTE if self.read_only else "")
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}"
        caps = (site_seed or {}).get("capabilities") or []
        if caps:
            cap_lines = "\n".join(f"- {c['name']}: {c['goal']}" for c in caps)
            prompt += (
                "\n\nSITE GOALS (what this whole site is for) -- use as EXTRA "
                "context, NOT as a replacement for page-specific tasks:\n"
                f"{site_seed.get('description', '')}\n"
                "Capabilities a user comes here to accomplish:\n"
                f"{cap_lines}\n"
                "Still propose a DIVERSE mix grounded in THIS page: keep the NAV "
                "tasks that reach other pages (they are what makes exploration "
                "discover new pages) and the INFO/MOD tasks specific to this page. "
                "In ADDITION, when this page affords it, include 1-2 COMPOSITE tasks "
                "that advance one of the site goals above. Do NOT let the site goals "
                "crowd out page-specific NAV/INFO/MOD tasks, and do NOT propose a "
                "capability this page cannot support.")
        if self._seen:
            recent = list(self._seen.values())[-self._SEEN_HINT_SIZE:]
            prompt += ("\n\nALREADY PROPOSED (do not repeat these or near-duplicates):\n"
                       + "\n".join(f"- {s}" for s in recent))
        # ...rest of the method is unchanged...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_page_explorer.py -q`
Expected: PASS (all existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/agents.py hsge/tests/test_page_explorer.py
git commit -m "feat(seed): condition PageExplorer proposals on the site seed"
```

---

## Task 3: Wire `site_seeder` into the runtime + persistence

**Files:**
- Modify: `run_webarena.py` (`AGENT_ROLES`, `DEFAULTS`, main wiring, `_DryLLM`)
- Modify: `hsge/webarena/runtime.py` (`__init__`, `run()` derivation, `_dump_artifacts`, checkpoint round-trip)
- Test: `hsge/tests/test_multi_llm.py` (role routing), `hsge/tests/test_resume.py` (checkpoint round-trip)

**Interfaces:**
- Consumes: `SiteSeeder` (Task 1).
- Produces: `WebArenaExplorer(..., use_site_seed: bool = False)`; instance attrs `self.use_site_seed`, `self.seeder` (a `SiteSeeder`), `self.site_seed` (`None` until derived, then a dict), `self._attempted_capabilities: set[str]`. `run_webarena.AGENT_ROLES` includes `"site_seeder"`.

- [ ] **Step 1: Write the failing tests**

```python
# append to hsge/tests/test_multi_llm.py
def test_site_seeder_role_is_wired():
    assert "site_seeder" in AGENT_ROLES
    llms = {role: _RoleLLM(role) for role in AGENT_ROLES}
    import tempfile
    from hsge.llm import HashingEmbedder
    from hsge.webarena.runtime import WebArenaExplorer
    rt = WebArenaExplorer(
        browser_factory=lambda url: None, llm=_RoleLLM("shared"),
        embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
        allow_pattern=".*", agent_llms=llms, use_site_seed=True)
    assert rt.seeder.llm is llms["site_seeder"]
```

```python
# append to hsge/tests/test_resume.py  (mirror the existing round-trip test's setup)
def test_checkpoint_round_trips_site_seed(tmp_path):
    from hsge.llm import HashingEmbedder, MockLLM
    from hsge.webarena.runtime import WebArenaExplorer
    out = str(tmp_path / "run")
    import os; os.makedirs(out, exist_ok=True)
    ex = WebArenaExplorer(browser_factory=lambda u: None, llm=MockLLM(),
                          embedder=HashingEmbedder(), out_dir=out,
                          allow_pattern=".*", use_site_seed=True)
    ex.site_seed = {"description": "d", "capabilities": [{"name": "c", "goal": "g"}]}
    ex._attempted_capabilities = {"c"}
    ex.run_started_epoch, ex.run_started_iso = 1.0, "iso"
    ex._write_checkpoint({k: v for k, v in zip(
        WebArenaExplorer._LOOP_KEYS,
        ([], set(), set(), {}, set(), 0, 0, 0,
         {"LOCAL": {}, "GOAL": {}}, []))})
    ex2 = WebArenaExplorer(browser_factory=lambda u: None, llm=MockLLM(),
                           embedder=HashingEmbedder(), out_dir=out,
                           allow_pattern=".*", use_site_seed=True)
    ex2.load_checkpoint(os.path.join(out, "checkpoint.pkl"))
    assert ex2.site_seed == {"description": "d", "capabilities": [{"name": "c", "goal": "g"}]}
    assert ex2._attempted_capabilities == {"c"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_multi_llm.py::test_site_seeder_role_is_wired hsge/tests/test_resume.py::test_checkpoint_round_trips_site_seed -q`
Expected: FAIL — `site_seeder` not in `AGENT_ROLES` / `WebArenaExplorer` has no `use_site_seed`.

- [ ] **Step 3: Write minimal implementation**

3a. `run_webarena.py` — register role + default + wiring:

```python
# AGENT_ROLES: add "site_seeder" (order: put it first, it runs first)
AGENT_ROLES = (
    "site_seeder",
    "page_explorer",
    "solver",
    "trajectory_segmenter",
    "skill_abstractor",
    "skill_verifier",
    "operator_inducer",
)

# DEFAULTS["run"]: add
    "use_site_seed": False,
```

In `main()`, resolve and pass it (dry-run turns it ON so `--dry-run` exercises the path):

```python
    # after run = cfg["run"] is available and near other _pick calls:
    if args.dry_run:
        use_site_seed = True
    else:
        use_site_seed = run["use_site_seed"]
    # ... in the WebArenaExplorer(...) call, add:
        use_site_seed=use_site_seed,
```

`_DryLLM.complete_json` — add a `SUMMARIZE` branch as the FIRST check:

```python
        if system.startswith("SUMMARIZE"):                      # site seeder
            return {"description": "A demo shopping site.",
                    "capabilities": [{"name": "checkout",
                                      "goal": "Buy an item and reach the order confirmation page."}]}
```

3b. `hsge/webarena/runtime.py` — imports, `__init__`, derivation, persistence:

```python
# import
from .agents import PageExplorer, Solver, SiteSeeder   # SiteSeeder is new

# __init__ signature: add a keyword (place next to agent_llms)
                 use_site_seed: bool = False,

# __init__ body (near self.explorer / self.solver construction):
        self.use_site_seed = use_site_seed
        self.seeder = SiteSeeder(role("site_seeder"))
        self.site_seed = None            # None = not derived yet; dict once derived
        self._attempted_capabilities: set[str] = set()
```

Derive once, in `run()`, right after `visited_landed.add(landed)` (currently line ~671, inside the try, after the duplicate-skip block so `obs` is a fresh node):

```python
                if self.use_site_seed and self.site_seed is None:
                    self.site_seed = self.seeder.derive(obs) or {"description": "", "capabilities": []}
                    n = len(self.site_seed.get("capabilities", []))
                    self._log("site_seed_derived", capabilities=n)
                    print(f"    [seed] derived site profile with {n} capabilities")
```

Pass the seed to the explorer at its call site (currently line ~700):

```python
                for task in self.explorer.propose(obs, screenshot_b64=node_screenshot_b64,
                                                  site_seed=self.site_seed):
```

Persist to `seed.json` — inside `_dump_artifacts` (add one line among the other `json.dump`s):

```python
        if self.site_seed is not None:
            json.dump(self.site_seed, open(os.path.join(self.out_dir, "seed.json"), "w",
                                           encoding="utf-8"), indent=2)
```

Checkpoint round-trip — in `_write_checkpoint`'s `state = {...}` add:

```python
                "site_seed": self.site_seed,
                "_attempted_capabilities": self._attempted_capabilities,
```

In `load_checkpoint`, after the other explicit restores (e.g. after `self._attempted_chains = ...`) add back-compat `.get` restores:

```python
        self.site_seed = state.get("site_seed")
        self._attempted_capabilities = state.get("_attempted_capabilities", set())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_multi_llm.py hsge/tests/test_resume.py -q`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add run_webarena.py hsge/webarena/runtime.py hsge/tests/test_multi_llm.py hsge/tests/test_resume.py
git commit -m "feat(seed): wire site_seeder role, derive once, persist + checkpoint"
```

---

## Task 4: Emit seed capabilities as GOAL tasks in `_goal_task()`

**Files:**
- Modify: `hsge/webarena/runtime.py` (`_goal_task`)
- Test: `hsge/tests/test_goal_task.py` (add cases)

**Interfaces:**
- Consumes: `self.site_seed`, `self._attempted_capabilities`, `self.goal_chains_per_node` (all from Task 3).
- Produces: `_goal_task()` returns, when the operator graph yields no chains, one dict per uncovered capability: `{"goal": <capability goal>, "difficulty": 2, "chain": (), "kind": "seed", "goal_predicate": None}`, bounded by `goal_chains_per_node`, each capability emitted at most once per run.

- [ ] **Step 1: Write the failing test**

```python
# append to hsge/tests/test_goal_task.py
def _seed(ex, caps):
    ex.site_seed = {"description": "d", "capabilities": caps}


def test_seed_capabilities_become_goal_tasks_when_no_chains():
    ex = _explorer(terminal_goal=None)          # empty operator graph -> no chains
    _seed(ex, [{"name": "checkout", "goal": "Buy a mouse and confirm the order."},
               {"name": "review", "goal": "Write a review for a purchased item."}])

    tasks = ex._goal_task()

    assert [t["kind"] for t in tasks] == ["seed", "seed"]
    assert tasks[0]["goal"] == "Buy a mouse and confirm the order."
    assert tasks[0]["goal_predicate"] is None
    assert tasks[0]["chain"] == ()


def test_seed_capabilities_attempted_once_per_run():
    ex = _explorer(terminal_goal=None)
    _seed(ex, [{"name": "checkout", "goal": "Buy a mouse and confirm the order."}])

    assert len(ex._goal_task()) == 1        # first node emits it
    assert ex._goal_task() == []            # second node: already attempted


def test_seed_respects_goal_chains_per_node_cap():
    ex = _explorer(terminal_goal=None, goal_chains_per_node=1)
    _seed(ex, [{"name": "a", "goal": "goal a"}, {"name": "b", "goal": "goal b"}])

    assert len(ex._goal_task()) == 1        # capped at 1 per node


def test_chains_take_precedence_over_seed():
    ex = _explorer(terminal_goal=None)
    _add_chain_ops(ex)                       # yields a depth chain
    _seed(ex, [{"name": "x", "goal": "seed goal"}])

    kinds = [t["kind"] for t in ex._goal_task()]
    assert "depth" in kinds and "seed" not in kinds
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_goal_task.py -q`
Expected: FAIL — `_goal_task()` returns `[]` for a seeded empty graph (no seed source yet).

- [ ] **Step 3: Write minimal implementation**

In `_goal_task()`, insert the seed source **after the chains `for` loop and before `if tasks: return tasks`** (so a real depth chain still wins when one exists):

```python
        # Seed capabilities: a top-down GOAL source that does NOT need the
        # operator graph to have edges (attacks bug O2). Fill remaining
        # per-node budget with uncovered capabilities, each attempted once.
        if self.site_seed and len(tasks) < self.goal_chains_per_node:
            for cap in self.site_seed.get("capabilities", []):
                if len(tasks) >= self.goal_chains_per_node:
                    break
                goal = cap.get("goal")
                name = cap.get("name") or goal or ""
                if not goal or name in self._attempted_capabilities:
                    continue
                self._attempted_capabilities.add(name)
                tasks.append({"goal": goal, "difficulty": 2, "chain": (),
                              "kind": "seed", "goal_predicate": None})
        if tasks:
            return tasks
```

(The existing terminal-backup block below `if tasks: return tasks` is unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_goal_task.py -q`
Expected: PASS (existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/runtime.py hsge/tests/test_goal_task.py
git commit -m "feat(seed): emit seed capabilities as GOAL tasks (bypass edgeless graph)"
```

---

## Task 5: End-to-end dry run + config docs + changelog

**Files:**
- Modify: `config.yaml` (document `run.use_site_seed`)
- Test: the existing dry-run test (find it: `grep -rl "dry" hsge/tests/`) — assert `seed.json` exists and a GOAL episode ran.
- Modify: `.claude/memory/changelog.md`

**Interfaces:**
- Consumes: everything from Tasks 1-4. No new production interface.

- [ ] **Step 1: Write the failing test**

First locate the dry-run test: `grep -rln "dry_run\|--dry-run\|_DryLLM\|dry" hsge/tests/`. Add to it (adapt the harness it already uses to invoke `run_webarena.main()` / `WebArenaExplorer.run` in dry mode; the assertion is the new part):

```python
def test_dry_run_produces_seed_and_goal_episode(tmp_path):
    import json, os, subprocess, sys
    out = str(tmp_path / "wa_dry")
    subprocess.run([sys.executable, "run_webarena.py", "--dry-run",
                    "--out", out, "--max-nodes", "2"],
                   check=True, cwd=os.getcwd())
    # seed was derived and persisted
    seed = json.load(open(os.path.join(out, "seed.json"), encoding="utf-8"))
    assert seed["capabilities"], "expected at least one seed capability"
    # a GOAL episode actually ran (the whole point: non-zero GOAL bucket)
    summary = json.load(open(os.path.join(out, "summary.json"), encoding="utf-8"))
    goal = summary["task_stats"]["GOAL"] if "task_stats" in summary else summary["GOAL"]
    assert goal["success"] + goal["fail"] + goal["infeasible"] > 0
```

> If the existing dry-run test already shells out with a fixed arg set, mirror that exact invocation instead of the one above; only the two assertions (seed.json, non-zero GOAL) are essential. Confirm the `summary.json` key path for the GOAL bucket by reading one from a prior `--dry-run` before finalizing the assertion.

- [ ] **Step 2: Run test to verify it fails (or run the dry run manually first)**

Run: `python run_webarena.py --dry-run --out /tmp/wa_dry_seed --max-nodes 2`
Expected before Tasks 1-4 wired end-to-end: no `seed.json`, `GOAL` bucket all-zero. After: `seed.json` present, GOAL bucket non-zero.
Then: `PYTHONPATH=. python -m pytest <dry_test_file> -q` — Expected: FAIL first (asserting seed/GOAL) if any wiring gap remains.

- [ ] **Step 3: Make it pass**

If the dry run doesn't emit a GOAL episode, verify: (a) `use_site_seed=True` reaches `WebArenaExplorer` in the dry-run branch; (b) `_DryLLM` returns the `SUMMARIZE` seed; (c) `_goal_task()` sees `self.site_seed` populated before the GOAL loop in `run()`. No new code beyond Tasks 1-4 should be needed — this task is the integration gate.

- [ ] **Step 4: Full suite + document**

Run the whole suite:
```bash
PYTHONPATH=. python -m pytest hsge/tests/ -q
```
Expected: all green (was 165; now 165 + new tests).

Add to `config.yaml` under `run:` (documentation for real runs):
```yaml
  # Derive a site-level {description, capabilities[]} seed on the first node and
  # (a) condition task proposals on it, (b) emit each capability as a top-down
  # GOAL task -- independent of the operator graph. Off by default.
  use_site_seed: false
```
(Optional, commented, under `llm.agents:`): show `site_seeder:` can override the model, same as any other role.

Append an entry to `.claude/memory/changelog.md` under a `## 2026-07-31` heading (get the time with `date "+%Y-%m-%d %H:%M"`): files touched, the seed-conditioned GOAL curriculum, and that Phase A is done — real-run confirmation of a non-zero GOAL bucket still pending an API-keyed WebArena run.

- [ ] **Step 5: Commit**

```bash
git add config.yaml hsge/tests/ .claude/memory/changelog.md
git commit -m "feat(seed): dry-run e2e for seed-conditioned GOAL curriculum + docs"
```

---

## Self-review checklist (run before handing off)

1. **Spec coverage:** P1 = Task 1+3 (derive+persist); P2 = Task 4 (seed→GOAL); P3 = Task 2 (conditioned proposals); default-off + mock-determinism = Global Constraints + the `use_site_seed` guard in every task. Verification criterion (non-zero GOAL bucket) = Task 5.
2. **Type consistency:** seed shape `{"description": str, "capabilities": [{"name": str, "goal": str}]}` is identical in Tasks 1/2/3/4. `SiteSeeder(llm).derive(obs)`, `PageExplorer.propose(obs, screenshot_b64=None, site_seed=None)`, `WebArenaExplorer(..., use_site_seed=False)`, role name `"site_seeder"` — consistent across tasks.
3. **Open risk to watch during implementation:** the exact `summary.json` GOAL-bucket key path (Task 5) — confirm against a real `--dry-run` output before locking the assertion. Everything else is unit-covered.

## What Phase A does NOT do (deferred to later plans)

- **Bottom-up refinement** (Explorer): the Solver may still finish a seed GOAL in few actions → the discovered skill can stay atomic. Phase A proves GOAL *plumbing*, not skill *depth*.
- **Deterministic verification** of seed GOALs: they are self-graded (`goal_predicate=None`); the auto verify-predicate (P6) is Phase C.
- **Coverage-driven frontier steering** (P7) and **inline Verifier gate** (P5): later plans.
