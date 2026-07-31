# Subgoal-Guided GOAL Solving (C2) + Progress Anti-Wandering (C3) Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the solver actually complete multi-step, state-changing GOALs (run v2: 4/4 such GOALs churned to budget then reported infeasible) by (C2) planning the GOAL into ordered subgoals it pursues one at a time, and (C3) stopping a churning episode early when it stops reaching new pages.

**Architecture:** A `GoalPlanner` LLM turns a GOAL into an ordered subgoal list; `Solver.solve` gains a subgoal mode that shows only the current subgoal, advances on the solver's own `subgoal_done` signal or a per-subgoal step cap, and keeps `goal_max_steps` as the outer bound. Independently, `solve` tracks observation-novelty and hard-stops after K non-novel steps. Both gated/inert by default so mock determinism and LOCAL behavior are unchanged.

**Tech Stack:** Python 3, numpy-only mock core, `LLM.complete_json` seam, pytest, conda env `go-browse`.

## Confirmed design decisions (from review)

- **C2 approach:** upfront planner-decompose (one LLM call: goal → ordered subgoals), not per-action refinement.
- **C2 advance:** the solver's own `subgoal_done` signal AND a per-subgoal step cap (whichever first).
- **C5** (stronger GOAL solver model): **deferred** — see if C2 alone lifts completion first.
- **Scope:** subgoal mode is used for GOAL tasks only (LOCAL keeps the plain loop). C3 anti-wandering applies to every `solve` (it only ever stops a genuinely stuck episode earlier).

## Global Constraints

- Run from repo root; `conda activate go-browse` (via `source ~/miniconda3/etc/profile.d/conda.sh`). English only. TDD, red before green, full suite green after each task (currently **193 passed**). One commit per task, `Co-Authored-By:` trailer, no push.
- Mock determinism: `GoalPlanner` is LLM-backed and only invoked when `run.plan_subgoals` is on; `solve(subgoals=None)` reproduces today's loop exactly; C3's novelty guard must not fire on a legitimate progressing episode (only when observations repeat).
- New role name exactly `goal_planner`. Planner prompt must start with a distinct token for `_DryLLM` routing and avoid MockLLM tokens `SEGMENT`/`ABSTRACT`/`GROUND`.

## Prompts for review

### 1. `PLANNER_SYS` — new, `hsge/webarena/agents.py`

```
DECOMPOSE the user's GOAL into an ordered list of concrete subgoals a web agent
will complete one at a time, in order, to achieve the GOAL on the current site.
You are given the GOAL and the current page (URL + accessibility tree).
Return JSON {"subgoals": ["<subgoal 1>", "<subgoal 2>", ...]}.
Rules:
- 2-5 subgoals. Each is a single, concrete, checkable step stated as an intent
  (e.g. "Open the Electronics category page", "Select the first in-stock product",
  "Add it to the cart"), NOT a click-by-click script.
- Order them so each subgoal leaves the page in the state the next one needs.
- The LAST subgoal must correspond to the GOAL's final end-state (what a grader
  would check), so completing it means the whole GOAL is done.
- Ground subgoals in what THIS page/site actually offers; do not invent steps for
  features you cannot see.
- If the GOAL is already a single concrete step, return it as one subgoal.
```

### 2. Subgoal block appended to the Solver **user** prompt (subgoal mode only)

`SOLVER_SYS` is unchanged (keeps its tests); the subgoal guidance goes in the user prompt when `subgoals` is passed:

```
OVERALL GOAL: <goal>
CURRENT SUBGOAL (<i>/<N>): <subgoal i>
Work ONLY on the current subgoal right now. When THIS subgoal is done, output
{"subgoal_done": true, "thought": "...", "action": "<next action or noop>"} to
advance to the next subgoal. Call send_msg_to_user ONLY after the LAST subgoal is
complete.
```

### 3. Dry-run `_DryLLM` planner stub (Task 4)

Returns a 2-subgoal decomposition so `--dry-run` exercises subgoal mode end-to-end (routed by the `DECOMPOSE` prefix).

## File structure

- `hsge/webarena/agents.py` — `PLANNER_SYS` + `GoalPlanner` class (C2); `Solver.solve` subgoal mode + `_SUBGOAL_CAP` (C2); observation-novelty guard + `_NOVELTY_WARN`/`_NOVELTY_MAX` (C3).
- `hsge/webarena/runtime.py` — `plan_subgoals` flag + `goal_planner` role; plan subgoals in the GOAL loop and pass through `_solve_with_retries(subgoals=...)` → `solve`.
- `run_webarena.py` — `goal_planner` in `AGENT_ROLES`; `run.plan_subgoals` default; `_DryLLM` planner branch; main wiring.
- `config.yaml` — document `plan_subgoals`; optional `llm.agents.goal_planner`.
- Tests: `test_goal_planner.py`, `test_solver_subgoals.py`, `test_solver_novelty.py` (new); extend `test_dry_run_seed.py`.

---

## Task 1: `GoalPlanner` (C2 planner)

**Files:** Modify `hsge/webarena/agents.py`; Test `hsge/tests/test_goal_planner.py` (create).

**Interfaces:**
- Produces: `PLANNER_SYS: str`; `class GoalPlanner(llm)` with `plan(goal: str, obs: dict) -> list[str]` — returns an ordered subgoal list (empty on garbage). Calls `llm.complete_json(PLANNER_SYS, prompt)`.

- [ ] **Step 1: Write the failing test**

```python
# hsge/tests/test_goal_planner.py
from hsge.webarena.agents import PLANNER_SYS, GoalPlanner


class _Stub:
    def __init__(self, out): self._out = out; self.calls = []
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls.append(prompt); return self._out


def test_planner_prompt_prefix_and_no_mock_tokens():
    assert PLANNER_SYS.startswith("DECOMPOSE")
    for tok in ("SEGMENT", "ABSTRACT", "GROUND"):
        assert tok not in PLANNER_SYS


def test_plan_returns_ordered_subgoals():
    llm = _Stub({"subgoals": ["Open the Electronics category",
                              "Select the first in-stock product",
                              "Add it to the cart"]})
    subs = GoalPlanner(llm).plan("add first electronics item to cart",
                                 {"url": "http://x/", "axtree": "cats"})
    assert subs == ["Open the Electronics category",
                    "Select the first in-stock product", "Add it to the cart"]
    assert "http://x/" in llm.calls[0]


def test_plan_returns_empty_on_garbage():
    assert GoalPlanner(_Stub({"nope": 1})).plan("g", {"url": "", "axtree": ""}) == []
```

- [ ] **Step 2: Run — expect FAIL** (`cannot import name 'PLANNER_SYS'`).

- [ ] **Step 3: Implement** in `agents.py` (near `SEEDER_SYS`):

```python
PLANNER_SYS = (
    "DECOMPOSE the user's GOAL into an ordered list of concrete subgoals a web "
    "agent will complete one at a time, in order, to achieve the GOAL on the "
    "current site. You are given the GOAL and the current page (URL + "
    "accessibility tree).\n"
    "Return JSON {\"subgoals\": [\"<subgoal 1>\", \"<subgoal 2>\", ...]}.\n"
    "Rules:\n"
    "- 2-5 subgoals. Each is a single, concrete, checkable step stated as an "
    "intent (e.g. 'Open the Electronics category page', 'Select the first "
    "in-stock product', 'Add it to the cart'), NOT a click-by-click script.\n"
    "- Order them so each subgoal leaves the page in the state the next needs.\n"
    "- The LAST subgoal must correspond to the GOAL's final end-state (what a "
    "grader would check), so completing it means the whole GOAL is done.\n"
    "- Ground subgoals in what THIS page/site actually offers; do not invent "
    "steps for features you cannot see.\n"
    "- If the GOAL is already a single concrete step, return it as one subgoal.")


class GoalPlanner:
    """Turns a multi-step GOAL into an ordered subgoal list the Solver pursues
    one at a time. LLM-backed; only used when run.plan_subgoals is on."""

    def __init__(self, llm):
        self.llm = llm

    def plan(self, goal: str, obs: dict) -> list[str]:
        prompt = f"GOAL: {goal}\n\nURL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}"
        out = self.llm.complete_json(PLANNER_SYS, prompt)
        subs = out.get("subgoals")
        if not isinstance(subs, list):
            return []
        return [s.strip() for s in subs if isinstance(s, str) and s.strip()]
```

- [ ] **Step 4: Run — expect PASS (3).**
- [ ] **Step 5: Commit** `feat(plan): GoalPlanner + PLANNER_SYS to decompose a GOAL into subgoals`

---

## Task 2: `Solver.solve` subgoal mode (C2)

**Files:** Modify `hsge/webarena/agents.py`; Test `hsge/tests/test_solver_subgoals.py` (create).

**Interfaces:**
- Consumes: subgoal list from Task 1.
- Produces: `Solver.solve(..., subgoals: list[str] | None = None)`; class const `Solver._SUBGOAL_CAP = 8`. When `subgoals` is given: the prompt shows the current subgoal; the solver advances on `subgoal_done: true` in its JSON or after `_SUBGOAL_CAP` steps on one subgoal; `send_msg_to_user` still ends the episode. `subgoals=None` → today's loop, unchanged.

- [ ] **Step 1: Write the failing test**

```python
# hsge/tests/test_solver_subgoals.py
from hsge.webarena.agents import Solver


class _Browser:
    terminated = False
    def __init__(self): self.n = 0
    def observation(self): return {"url": f"http://x/{self.n}", "axtree": f"p{self.n}"}
    def act(self, a): self.n += 1; return self.observation()
    def screenshot_b64(self, som=True): return None


class _ScriptLLM:
    """Emits subgoal_done for the first subgoal, then finishes on the second."""
    def __init__(self): self.calls = 0; self.prompts = []
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt); self.calls += 1
        if self.calls == 1:
            return {"thought": "did subgoal 1", "action": "click('1')", "subgoal_done": True}
        return {"thought": "done", "action": "send_msg_to_user('done')"}


def test_subgoal_mode_shows_current_subgoal_and_advances():
    llm = _ScriptLLM()
    solver = Solver(llm, max_steps=10)
    steps, _, _, _, success, _ = solver.solve(
        _Browser(), "overall goal", subgoals=["do A", "do B"])
    # first prompt shows subgoal 1/2, and after subgoal_done a later prompt shows 2/2
    assert "CURRENT SUBGOAL (1/2): do A" in llm.prompts[0]
    assert any("CURRENT SUBGOAL (2/2): do B" in p for p in llm.prompts)
    assert success is True


def test_no_subgoals_is_unchanged_behavior():
    class _Done:
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            return {"thought": "done", "action": "send_msg_to_user('done')"}
    steps, *_rest, success, _ = Solver(_Done(), max_steps=5).solve(_Browser(), "g")
    assert success is True
    assert "CURRENT SUBGOAL" not in _  # no subgoal block leaked; see note
```

> The last assertion is illustrative — replace with a prompt-capturing stub asserting `"CURRENT SUBGOAL"` never appears when `subgoals` is None.

- [ ] **Step 2: Run — expect FAIL** (`solve()` has no `subgoals` kwarg).

- [ ] **Step 3: Implement** — add to `Solver` and thread through the loop:

```python
    _SUBGOAL_CAP = 8   # max steps on one subgoal before auto-advancing

    def solve(self, browser, goal, goal_predicate=None, max_steps=None, subgoals=None):
        budget = max_steps if max_steps is not None else self.max_steps
        sg = list(subgoals) if subgoals else None
        sg_idx, sg_steps = 0, 0
        # ...unchanged setup (steps/history/obs/...)...
        for _ in range(budget):
            # ...unchanged stuck-streak + C3 novelty checks...
            subgoal_block = ""
            if sg is not None and sg_idx < len(sg):
                subgoal_block = (
                    f"\n\nOVERALL GOAL: {goal}\nCURRENT SUBGOAL "
                    f"({sg_idx + 1}/{len(sg)}): {sg[sg_idx]}\n"
                    "Work ONLY on the current subgoal right now. When THIS subgoal "
                    'is done, output {"subgoal_done": true, ...} to advance. Call '
                    "send_msg_to_user ONLY after the LAST subgoal is complete.")
            prompt = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n" + ...  # unchanged body
                      + subgoal_block
                      + f"\n\nURL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}")
            out = self.llm.complete_json(SOLVER_SYS, prompt, image_b64=..., ...)
            # advance subgoal on the model's signal (except past the last one)
            if sg is not None and out.get("subgoal_done") and sg_idx < len(sg) - 1:
                sg_idx += 1; sg_steps = 0
                continue
            action = (out.get("action") or "").strip()
            # ...unchanged: append Step, terminal-action check, browser.act, guards...
            if sg is not None:
                sg_steps += 1
                if sg_steps >= self._SUBGOAL_CAP and sg_idx < len(sg) - 1:
                    sg_idx += 1; sg_steps = 0
```

> Care: `subgoal_done` advance uses `continue` *before* executing/recording an action, so an advance step doesn't consume a browser action (it still consumes one budget iteration — acceptable). The per-subgoal cap advances *after* a normal step. Keep every other line of the loop identical.

- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit** `feat(solver): subgoal mode (planner-guided multi-step solving)`

---

## Task 3: Progress-based anti-wandering (C3)

**Files:** Modify `hsge/webarena/agents.py` (`Solver.solve`); Test `hsge/tests/test_solver_novelty.py` (create).

**Interfaces:**
- Produces: class consts `Solver._NOVELTY_WARN = 4`, `Solver._NOVELTY_MAX = 8`. `solve` tracks a set of seen `(url, axtree)` observations; a trailing run of `_NOVELTY_MAX` executed actions that reach no *new* observation hard-stops the episode (a warning is added to the prompt at `_NOVELTY_WARN`). This is in addition to the existing same-target `_stuck_streak` guard.

- [ ] **Step 1: Write the failing test**

```python
# hsge/tests/test_solver_novelty.py
from hsge.webarena.agents import Solver


class _FrozenBrowser:
    """act() never changes the observation -> pure churn across DIFFERENT targets."""
    terminated = False
    def observation(self): return {"url": "http://x/same", "axtree": "same page"}
    def act(self, a): return self.observation()
    def screenshot_b64(self, som=True): return None


class _WanderLLM:
    """Different target each step, never terminal -> not caught by same-target guard."""
    def __init__(self): self.n = 0
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.n += 1
        return {"thought": "try", "action": f"click('{self.n}')"}


def test_novelty_guard_stops_pure_churn_before_budget():
    solver = Solver(_WanderLLM(), max_steps=50)
    steps, *_rest = solver.solve(_FrozenBrowser(), "goal")
    # hard-stops around _NOVELTY_MAX, well before the 50-step budget
    assert len(steps) <= Solver._NOVELTY_MAX + 2
```

- [ ] **Step 2: Run — expect FAIL** (runs to 50 without the novelty guard).

- [ ] **Step 3: Implement** — in `solve`, track novelty and hard-stop:

```python
        seen_obs = set()          # (url, axtree) observations already reached
        novelty_streak = 0        # trailing executed actions with no NEW observation
        # ...inside the loop, at the top, alongside the existing stuck-streak check:
        if novelty_streak >= self._NOVELTY_MAX:
            print(f"    [solver] giving up: {novelty_streak} steps with no new page reached")
            break
        novelty_warning = ""
        if novelty_streak >= self._NOVELTY_WARN:
            novelty_warning = ("\n\nWARNING: your last actions have not reached any "
                               "new page. Try a genuinely different approach, or "
                               "report_infeasible if the subgoal cannot be done here.")
        # ...append novelty_warning into the prompt (next to repeat_warning)...
        # ...after browser.act(action) succeeds and obs updates:
        key = (obs["url"], obs["axtree"])
        if key in seen_obs:
            novelty_streak += 1
        else:
            seen_obs.add(key); novelty_streak = 0
```

> The novelty guard is orthogonal to subgoals (helps LOCAL and GOAL alike). It only ever fires when observations genuinely stop changing, so a progressing episode is unaffected — assert that in a second test with a browser whose `act` advances the url each step (expect it runs full budget / to a terminal action, not stopped early).

- [ ] **Step 4: Run — expect PASS** (both the churn-stop and the progress-not-stopped tests).
- [ ] **Step 5: Commit** `feat(solver): progress-based anti-wandering (observation-novelty hard stop)`

---

## Task 4: Wire the planner into the runtime + dry-run e2e

**Files:** Modify `hsge/webarena/runtime.py`, `run_webarena.py`, `config.yaml`, `hsge/tests/test_dry_run_seed.py`, `.claude/memory/changelog.md`.

**Interfaces:**
- Consumes: `GoalPlanner` (Task 1), `Solver.solve(subgoals=)` (Task 2).
- Produces: `WebArenaExplorer(..., plan_subgoals: bool = False)`; `self.planner = GoalPlanner(role("goal_planner"))`; `_solve_with_retries(..., subgoals=None)` forwards to `solve`; the GOAL loop plans subgoals (when `plan_subgoals`) from the node's current obs and passes them. `run.plan_subgoals` (default false, on in `--dry-run`); `goal_planner` in `AGENT_ROLES`.

- [ ] **Step 1: Write the failing test** — extend `test_dry_run_seed.py`:

```python
def test_dry_run_plans_subgoals_for_goal(tmp_path):
    import json, os, subprocess, sys
    out = str(tmp_path / "wa_dry")
    subprocess.run([sys.executable, "run_webarena.py", "--dry-run",
                    "--out", out, "--max-nodes", "2"], check=True, cwd=REPO)
    # the planner ran (subgoal event logged) for at least one GOAL task
    log = [json.loads(l) for l in open(os.path.join(out, "run_log.jsonl"), encoding="utf-8")]
    assert any(e.get("event") == "goal_subgoals_planned" for e in log)
```

- [ ] **Step 2: Run — expect FAIL** (no such event / `plan_subgoals` unknown).

- [ ] **Step 3: Implement**

`runtime.py`: `__init__` gains `plan_subgoals: bool = False`; `self.plan_subgoals = plan_subgoals`; `self.planner = GoalPlanner(role("goal_planner"))`. `_solve_with_retries` gains `subgoals=None`, forwarded to `solve(..., subgoals=subgoals)`. In the GOAL loop, before solving:

```python
                    subgoals = None
                    if self.plan_subgoals:
                        subgoals = self.planner.plan(gt["goal"], obs)
                        self._log("goal_subgoals_planned", node_index=node_index,
                                   goal=gt["goal"][:80], n=len(subgoals))
                    ... _solve_with_retries(..., subgoals=subgoals, verify_fn=...)
```

`run_webarena.py`: add `"goal_planner"` to `AGENT_ROLES`; `DEFAULTS["run"]["plan_subgoals"] = False`; `plan_subgoals = True if args.dry_run else run["plan_subgoals"]`; pass to `WebArenaExplorer`. `_DryLLM`: add a `DECOMPOSE` branch returning `{"subgoals": ["open the item", "add it to the cart"]}`, and make the scripted solver emit `subgoal_done` once so the advance path runs.

`config.yaml`: document `plan_subgoals: true` and optional `llm.agents.goal_planner`.

- [ ] **Step 4: Run the dry run + full suite**

`python run_webarena.py --dry-run --out /tmp/wa_dry_c2 --max-nodes 2` then `PYTHONPATH=. python -m pytest hsge/tests/ -q` — all green (193 + new).

Append a `changelog.md` entry (real timestamp): C2 planner + subgoal-mode solve + C3 novelty guard, gated by `plan_subgoals`; dry-run shows subgoals planned; real-run confirmation of a *completed multi-step* GOAL still pending.

- [ ] **Step 5: Commit** `feat(runtime): plan subgoals for GOAL tasks + dry-run e2e; docs`

---

## Self-review checklist

1. **Coverage:** C2 = Tasks 1 (planner) + 2 (solve subgoal mode) + 4 (wiring); C3 = Task 3. Confirmed decisions reflected (upfront decompose, signal + `_SUBGOAL_CAP`, C5 deferred, GOAL-only subgoal use).
2. **Type consistency:** `GoalPlanner(llm).plan(goal, obs) -> list[str]`; `Solver.solve(..., subgoals=None)`, `_SUBGOAL_CAP`, `_NOVELTY_WARN`/`_NOVELTY_MAX`; `WebArenaExplorer(..., plan_subgoals=False)`; `_solve_with_retries(..., subgoals=None)`; role `"goal_planner"`.
3. **Risk to watch:** the `solve` loop is now dense (stuck guard + novelty guard + subgoal advance + wrap-up). Keep every pre-existing line intact and add the new branches around them; re-run `test_solver_budget`/`test_goal_verifier`/`test_task_retries` after Task 3 to confirm no regression in the shared loop.

## Not in this slice

- C5 (stronger GOAL solver model) — revisit after measuring C2's lift.
- C4 (grounding-gated operator admission) — separate small slice.
- Seed-goal independence/ordering (v2 ep_0020 depended on ep_0009).
