# Seed-Conditioned GOAL Curriculum (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give HSGE a top-down, site-seed-derived GOAL source so a live run produces a **non-zero GOAL bucket** (`summary.json` `GOAL.success + GOAL.fail > 0`) for the first time — bypassing the currently edgeless operator graph (open bug O2).

**Architecture:** At the first node of a run, an LLM `SiteSeeder` self-summarizes the real site into `{description, capabilities[]}`. That seed (a) is given to `PageExplorer.propose()` as **extra context** that *adds* seed-aligned COMPOSITE tasks without replacing the diverse page-specific INFO/**NAV**/MOD tasks, and (b) is emitted **directly as GOAL tasks** in `_goal_task()` — one per capability, attempted once per run, verified self-graded (`goal_predicate=None`), independent of `all_chains()`. Every node therefore runs BOTH task sets. Everything is gated behind `run.use_site_seed` (default `false`) so the deterministic mock pipeline and existing runs are untouched.

**Task diversity & frontier (design intent):** frontier growth comes **primarily from COMPOSITE / MOD / GOAL** tasks — they navigate to new URLs *as a side effect of doing something meaningful*, and every URL the agent lands on becomes a **tier-0 "reached" node** (higher-signal than a **tier-1 mined `<a href>`**). Because those tasks already feed the frontier, dedicated **NAV** tasks are demoted to a **thin capped reserve** (`_NAV_CAP = 1` per page): NAV exists only to reach an important page when no action task on this page would, so a node is never left crawl-only, but pure-NAV skills (low value, prone to sitewide-menu boilerplate — ~46% of proposals in a real run) no longer flood the task set. This rebalance is **not** gated by `use_site_seed` — it is a general local-task priority change (Task 2).

**INFO is kept as a benchmark-aligned reserve, not dropped.** INFO tasks don't grow the frontier, but a solved INFO task is recorded as an **episode → SFT training example**, and the target eval (WebArena) is heavy on information-seeking tasks. So INFO gets its own guaranteed reserve (`_INFO_RESERVE = 2`) so a busy page still yields INFO training data; only INFO **beyond** the reserve is dropped first. This trades off two goals deliberately: exploration coverage (favours COMPOSITE/MOD/NAV, which move the agent) vs. SFT data distribution (favours INFO, which matches the benchmark).

New keep-priority when a page overflows `max_tasks`: **COMPOSITE (reserve ≤3) → MOD (all) → INFO (reserve ≤`_INFO_RESERVE`) → NAV (≤`_NAV_CAP`) → COMPOSITE (extra) → UNKNOWN → INFO (extra, dropped first)**. Seed conditioning stays strictly **additive**: it adds seed-aligned COMPOSITE, never crowds out page-specific tasks.

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

Three new/changed prompts in Phase A. Everything downstream (GOAL task text) reuses `capabilities[i].goal` **as-is**, so the seeder prompt is where GOAL quality is decided — review it hardest.

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

### 2. `EXPLORER_SYS` ordering rule — CHANGED, `hsge/webarena/agents.py`

Only the one "List ... FIRST" rule changes (de-emphasize NAV to a single reserve). Everything else in `EXPLORER_SYS` is untouched.

Old:
```
List COMPOSITE tasks FIRST, then MOD, then NAV, then INFO, and include at least
2-3 COMPOSITE tasks whenever the page affords a multi-step goal -- these are how
reusable, chainable skills get discovered.
```
New:
```
List COMPOSITE tasks FIRST, then MOD, then INFO. Include at least 2-3 COMPOSITE
tasks whenever the page affords a multi-step goal -- these are how reusable,
chainable skills get discovered -- and include a few INFO fact-lookup tasks
specific to this page (information-seeking is common in real use). Propose AT MOST
ONE NAV task (list it LAST), and only to reach an important page that no
COMPOSITE/MOD task here would visit: COMPOSITE and MOD tasks already navigate to
new pages as they act, so a single NAV is enough as a reserve.
```

### 3. Seed block appended to the `PageExplorer.propose()` **user** prompt — `hsge/webarena/agents.py`

The rest of `EXPLORER_SYS` (the system prompt) is otherwise unchanged; the seed is per-site data, so it goes in the user prompt beside `URL`/`PAGE`. The block is added only when a non-empty seed is passed, and is worded to be **additive** — seed goals add COMPOSITE tasks, they never replace the diverse page-specific tasks:

```
SITE GOALS (what this whole site is for) -- use as EXTRA context, NOT as a
replacement for page-specific tasks:
<description>
Capabilities a user comes here to accomplish:
- <name>: <goal>
- <name>: <goal>
...
Still propose a DIVERSE mix of page-specific tasks grounded in THIS page
(COMPOSITE, MOD, INFO, and at most one reserve NAV). In ADDITION, when this page
affords it, include 1-2 COMPOSITE tasks that advance one of the site goals above.
Do NOT let the site goals crowd out page-specific tasks, and do NOT propose a
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

## Task 2: Seed-condition `PageExplorer.propose()` + rebalance local task priority (fewer NAV)

Two changes to the same method, done together because both touch `propose()` and `EXPLORER_SYS`:
- **(a) Seed conditioning** — additive `SITE GOALS` block in the user prompt (gated on a non-empty `site_seed`).
- **(b) NAV rebalance** — de-emphasize NAV to a single reserve, in `EXPLORER_SYS` (generation) and in the truncation keep-order (safety net). This part is **always on** (not gated by `use_site_seed`): it is a general local-task priority change.

**Files:**
- Modify: `hsge/webarena/agents.py` (`EXPLORER_SYS` ordering rule, `_NAV_CAP` const, `PageExplorer.propose` signature + seed block + NAV cap + new truncation keep-order)
- Test: `hsge/tests/test_page_explorer.py` (add cases; update existing truncation cases to the new keep-order)

**Interfaces:**
- Consumes: seed shape from Task 1 (`{"description": str, "capabilities": [{"name","goal"}]}`).
- Produces: `PageExplorer.propose(self, obs, screenshot_b64=None, site_seed=None)` — new optional keyword `site_seed`; when it carries capabilities, a `SITE GOALS` block is appended. New class consts `PageExplorer._NAV_CAP = 1` and `PageExplorer._INFO_RESERVE = 2`. Keep-priority on overflow: **COMPOSITE(≤`_COMPOSITE_RESERVE`) → MOD → INFO(≤`_INFO_RESERVE`) → NAV(≤`_NAV_CAP`) → COMPOSITE(extra) → UNKNOWN → INFO(extra)**; NAV is also capped to `_NAV_CAP` **unconditionally** (even when under `max_tasks`).

- [ ] **Step 1: Write the failing tests**

```python
# append to hsge/tests/test_page_explorer.py
from hsge.webarena.agents import EXPLORER_SYS   # already imported at top; keep one import


class _PromptCapturingLLM:
    def __init__(self, tasks=None):
        self.prompt = None
        self._tasks = tasks if tasks is not None else ["[NAV] a"]

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompt = prompt
        return {"tasks": self._tasks}


def test_explorer_sys_demotes_nav_to_one_reserve():
    # generation-side: the ordering rule must ask for at most one NAV, listed last
    assert "AT MOST ONE NAV" in EXPLORER_SYS
    # the old "then NAV, then INFO" ordering must be gone
    assert "then NAV, then INFO" not in EXPLORER_SYS


def test_propose_caps_nav_to_one_even_under_budget():
    # 3 NAV proposed, max_tasks high enough that overflow truncation does NOT fire
    llm = _PromptCapturingLLM(["[NAV] a", "[NAV] b", "[NAV] c", "[MOD] m", "[COMPOSITE] c1"])
    tasks = PageExplorer(llm, max_tasks=10).propose({"url": "http://x", "axtree": ""})
    assert sum(t.startswith("[NAV]") for t in tasks) == 1
    # non-NAV tasks are all kept
    assert "[MOD] m" in tasks and "[COMPOSITE] c1" in tasks


def test_propose_keep_order_reserves_info_and_one_nav_on_overflow():
    # 2 COMPOSITE, 1 MOD, 2 NAV, 4 INFO; max_tasks=6.
    # NAV cap -> 1 NAV. keep-order: COMPOSITE[:3] + MOD + INFO[:2] + NAV[:1] + ...
    # -> 2 COMPOSITE + 1 MOD + 2 INFO (reserve) + 1 NAV = 6; extra INFO dropped.
    llm = _PromptCapturingLLM([
        "[COMPOSITE] c1", "[COMPOSITE] c2", "[MOD] m1",
        "[NAV] n1", "[NAV] n2",
        "[INFO] i1", "[INFO] i2", "[INFO] i3", "[INFO] i4"])
    tasks = PageExplorer(llm, max_tasks=6).propose({"url": "http://x", "axtree": ""})
    assert len(tasks) == 6
    assert sum(t.startswith("[COMPOSITE]") for t in tasks) == 2
    assert sum(t.startswith("[MOD]") for t in tasks) == 1
    assert sum(t.startswith("[INFO]") for t in tasks) == 2   # INFO reserve honored
    assert sum(t.startswith("[NAV]") for t in tasks) == 1    # NAV capped to reserve


def test_info_reserve_survives_a_mod_heavy_page():
    # INFO reserve is placed before extra COMPOSITE/UNKNOWN, so a page with some
    # MOD + lots of COMPOSITE still keeps >=1 INFO for training data.
    llm = _PromptCapturingLLM([
        "[COMPOSITE] c1", "[COMPOSITE] c2", "[COMPOSITE] c3", "[COMPOSITE] c4",
        "[MOD] m1", "[INFO] i1", "[INFO] i2"])
    tasks = PageExplorer(llm, max_tasks=6).propose({"url": "http://x", "axtree": ""})
    assert sum(t.startswith("[INFO]") for t in tasks) >= 1


def test_propose_injects_site_goals_when_seed_present():
    llm = _PromptCapturingLLM(["[NAV] a"])
    seed = {"description": "A shop for gadgets.",
            "capabilities": [{"name": "checkout", "goal": "Buy a gadget and confirm the order."}]}
    PageExplorer(llm).propose({"url": "http://x", "axtree": "tree"}, site_seed=seed)
    assert "SITE GOALS" in llm.prompt
    assert "A shop for gadgets." in llm.prompt
    assert "Buy a gadget and confirm the order." in llm.prompt
    # additive, not suppressive
    assert "crowd out" in llm.prompt


def test_propose_omits_site_goals_when_seed_absent_or_empty():
    for seed in (None, {"description": "", "capabilities": []}):
        llm = _PromptCapturingLLM(["[NAV] a"])
        PageExplorer(llm).propose({"url": "http://x", "axtree": "tree"}, site_seed=seed)
        assert "SITE GOALS" not in llm.prompt
```

> **Also update existing truncation tests** in `test_page_explorer.py` (the ones added on 2026-07-22, e.g. "reserve honored against a NAV flood", "reserve doesn't starve NAV") to the new keep-order: NAV is now capped at 1 and INFO now has a reserve of 2, so any assertion expecting multiple NAV kept must change to ≤1 NAV, and any assertion expecting INFO fully dropped must change to expect up to `_INFO_RESERVE` INFO kept. Read them first; adjust expectations, don't delete coverage.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_page_explorer.py -q`
Expected: FAIL — `_NAV_CAP`/new ordering not present; `propose()` has no `site_seed` kwarg.

- [ ] **Step 3: Write minimal implementation**

3a. In `EXPLORER_SYS`, replace the one ordering rule (lines ~47-49):

```python
    # OLD:
    "List COMPOSITE tasks FIRST, then MOD, then NAV, then INFO, and include at "
    "least 2-3 COMPOSITE tasks whenever the page affords a multi-step goal -- "
    "these are how reusable, chainable skills get discovered.\n"
    # NEW:
    "List COMPOSITE tasks FIRST, then MOD, then INFO. Include at least 2-3 "
    "COMPOSITE tasks whenever the page affords a multi-step goal -- these are how "
    "reusable, chainable skills get discovered -- and include a few INFO fact-lookup "
    "tasks specific to this page (information-seeking is common in real use). "
    "Propose AT MOST ONE NAV task (list it LAST), and only to reach an important "
    "page that no COMPOSITE/MOD task here would visit: COMPOSITE and MOD tasks "
    "already navigate to new pages as they act, so a single NAV is enough as a "
    "reserve.\n"
```

3b. Add the class consts next to `_COMPOSITE_RESERVE`:

```python
    _NAV_CAP = 1       # NAV is a thin reserve; COMPOSITE/MOD already grow the frontier
    _INFO_RESERVE = 2  # keep some INFO for SFT data (WebArena is info-seeking heavy)
```

3c. Change the `propose` signature + seed block + NAV cap + new keep-order:

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
                "Still propose a DIVERSE mix of page-specific tasks grounded in THIS "
                "page (COMPOSITE, MOD, INFO, and at most one reserve NAV). In "
                "ADDITION, when this page affords it, include 1-2 COMPOSITE tasks "
                "that advance one of the site goals above. Do NOT let the site goals "
                "crowd out page-specific tasks, and do NOT propose a capability this "
                "page cannot support.")
        if self._seen:
            recent = list(self._seen.values())[-self._SEEN_HINT_SIZE:]
            prompt += ("\n\nALREADY PROPOSED (do not repeat these or near-duplicates):\n"
                       + "\n".join(f"- {s}" for s in recent))
        image = screenshot_b64 if self.vision else None
        out = self.llm.complete_json(system, prompt, image_b64=image, image_detail=self.image_detail)
        if image and not out.get("tasks"):
            print("    [explorer] empty response with image attached, retrying text-only")
            out = self.llm.complete_json(system, prompt, image_b64=None, image_detail=self.image_detail)
        parsed = [p for p in map(self._parse_task, out.get("tasks", [])) if p]
        if self.read_only:
            parsed = [(text, tag) for text, tag in parsed if tag in ("INFO", "NAV")]
        fresh = []
        for text, tag in parsed:
            key = self._normalize(text)
            if key in self._seen:
                continue
            self._seen[key] = text
            fresh.append((text, tag))
        parsed = fresh
        # NAV is a thin reserve, capped UNCONDITIONALLY: COMPOSITE/MOD tasks
        # already navigate to new pages as they act (adding tier-0 frontier
        # URLs), and pure-NAV skills are low value + prone to sitewide-menu
        # boilerplate, so keep at most _NAV_CAP NAV tasks regardless of budget.
        nav_kept = 0
        capped = []
        for text, tag in parsed:
            if tag == "NAV":
                if nav_kept >= self._NAV_CAP:
                    continue
                nav_kept += 1
            capped.append((text, tag))
        parsed = capped
        if len(parsed) > self.max_tasks:
            # Keep-priority on overflow:
            #   COMPOSITE(reserve) -> MOD -> INFO(reserve) -> NAV(<=cap, already
            #   enforced above) -> COMPOSITE(extra) -> UNKNOWN -> INFO(extra).
            # INFO gets a guaranteed reserve (it is the WebArena-aligned SFT data),
            # but INFO beyond the reserve is dropped first (it never grows frontier).
            composite = [p for p in parsed if p[1] == "COMPOSITE"]
            mod = [p for p in parsed if p[1] == "MOD"]
            nav = [p for p in parsed if p[1] == "NAV"]
            unknown = [p for p in parsed if p[1] == "UNKNOWN"]
            info = [p for p in parsed if p[1] == "INFO"]
            parsed = (composite[: self._COMPOSITE_RESERVE]
                      + mod
                      + info[: self._INFO_RESERVE]
                      + nav
                      + composite[self._COMPOSITE_RESERVE:]
                      + unknown
                      + info[self._INFO_RESERVE:])[: self.max_tasks]
        return [f"[{tag}] {text}" if tag != "UNKNOWN" else text for text, tag in parsed]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_page_explorer.py -q`
Expected: PASS (all existing-and-updated + 6 new).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/agents.py hsge/tests/test_page_explorer.py
git commit -m "feat(explorer): seed-conditioned proposals + demote NAV to one reserve"
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

1. **Spec coverage:** P1 = Task 1+3 (derive+persist); P2 = Task 4 (seed→GOAL); P3 = Task 2a (conditioned proposals); **local-task rebalance = Task 2b** (`_NAV_CAP=1` + `_INFO_RESERVE=2`, always on, both `EXPLORER_SYS` and truncation keep-order); default-off + mock-determinism = Global Constraints + the `use_site_seed` guard on the seed-only parts. Verification criterion (non-zero GOAL bucket) = Task 5.
2. **Type consistency:** seed shape `{"description": str, "capabilities": [{"name": str, "goal": str}]}` is identical in Tasks 1/2/3/4. `SiteSeeder(llm).derive(obs)`, `PageExplorer.propose(obs, screenshot_b64=None, site_seed=None)`, `PageExplorer._NAV_CAP`, `PageExplorer._INFO_RESERVE`, `WebArenaExplorer(..., use_site_seed=False)`, role name `"site_seeder"` — consistent across tasks. **Note:** the local-task rebalance (Task 2b) is NOT behind `use_site_seed`; the seed block (Task 2a) is.
3. **Open risk to watch during implementation:** the exact `summary.json` GOAL-bucket key path (Task 5) — confirm against a real `--dry-run` output before locking the assertion. Everything else is unit-covered.

## What Phase A does NOT do (deferred to later plans)

- **Bottom-up refinement** (Explorer): the Solver may still finish a seed GOAL in few actions → the discovered skill can stay atomic. Phase A proves GOAL *plumbing*, not skill *depth*.
- **Deterministic verification** of seed GOALs: they are self-graded (`goal_predicate=None`); the auto verify-predicate (P6) is Phase C.
- **Coverage-driven frontier steering** (P7) and **inline Verifier gate** (P5): later plans.
