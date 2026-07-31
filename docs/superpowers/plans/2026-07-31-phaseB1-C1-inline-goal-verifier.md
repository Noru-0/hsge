# Inline GOAL Verifier (B1) + goal_max_steps (C1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make GOAL success trustworthy — an inline LLM verifier re-checks every self-graded GOAL "success" against its final page and overrides it — and give multi-step GOALs a fair step budget, so the next real run is a *measurable* experiment.

**Architecture:** After a GOAL episode declares success via self-grading (`goal_predicate is None`), a verifier LLM (reusing `judge_episodes.py`'s grader prompt, run live) judges the final observation against the goal; a FAIL flips the recorded outcome to fail. GOAL episodes never fed Discovery, so "block from Discovery" is automatic for this GOAL-only scope. Separately, GOAL/composite tasks get their own `goal_max_steps` budget. Both gated by config, default-off, mock-deterministic.

**Tech Stack:** Python 3, numpy-only mock core, `LLM.complete_json` seam, pytest. Conda env `go-browse`.

## Confirmed design decisions (from review)

- **Verifier source:** reuse `judge_episodes.py`'s `_SYS` + `_judge_prompt` verbatim (import them), run inline — no second prompt to maintain.
- **Fail handling:** an unverified success becomes a fail. (GOAL episodes already do not call `discovery.on_trajectory`, so "block from Discovery" needs no extra code at GOAL scope — noted, not implemented.)
- **Scope:** GOAL episodes only (LOCAL untouched — bigger volume/cost).
- **Step budget:** a separate `run.goal_max_steps` knob (GOAL only); LOCAL keeps `max_steps`.

## Global Constraints

- Run from repo root; `conda activate go-browse`. English only. TDD, red before green, full suite green after each task (currently **184 passed**). One commit per task, `Co-Authored-By:` trailer, no push.
- Mock determinism: verifier is LLM-backed and reached only when `run.verify_goals` is on; `goal_max_steps` defaults to `max_steps` (no behavior change unless set). Default-off paths must be byte-for-byte the old behavior.
- Verifier only runs on GOAL episodes with `goal_predicate is None` (a deterministic `reached()` result is already trustworthy — never re-judge it).

## Prompts for review

**No new prompt.** B1 reuses the grader system prompt verbatim — moved to `hsge/webarena/verify.py` (Task 3a) so both `judge_episodes.py` and `runtime.py` import it, not copied:

```
You are a strict grader of a web agent's completed task. You are given the GOAL
the agent was told to accomplish, the actions it took before declaring the task
done, and the FINAL page (URL + accessibility tree) where it declared done.
Decide whether the goal was genuinely achieved by the final state -- not whether
the agent SAID it was done. Common false positives: the agent gave up and
declared done anyway; it answered an INFO question with a guess not actually
shown on the final page; it navigated to the wrong page.
Return JSON {"verdict": "PASS"|"FAIL", "reason": "<one sentence>"}.
```

The only new prompt-routing text is the dry-run `_DryLLM` stub that answers it (Task 3), which must let the plan demonstrate a caught false-positive.

## File structure

- `hsge/webarena/verify.py` — **new, tiny, dependency-free** module holding `JUDGE_SYS` + `judge_prompt(goal, history, final_url, final_axtree)`, moved out of `judge_episodes.py`. **Required:** `runtime.py` cannot import `judge_episodes` (confirmed circular: `runtime → judge_episodes → run_webarena → runtime`), so the shared prompt must live in a leaf module both import.
- `hsge/webarena/agents.py` — `Solver.solve` gains a per-call `max_steps` override (C1).
- `hsge/webarena/runtime.py` — `goal_max_steps` + `verify_goals` params; `_verify_episode()` (uses `verify.JUDGE_SYS`/`judge_prompt`); apply verifier in the GOAL loop; write `judge_verified`/`judge_reason` into `episode_meta`; route `episode_judge` role.
- `judge_episodes.py` — re-imports `JUDGE_SYS`/`judge_prompt` from `hsge/webarena/verify.py` (keeps `_SYS`/`_judge_prompt` aliases so its own tests/usage are unchanged).
- `run_webarena.py` — `episode_judge` in `AGENT_ROLES`; `run.goal_max_steps`/`run.verify_goals` defaults + wiring; `_DryLLM` grader branch (+ a wandering-then-declare-done scenario so the dry run exercises a FAIL).
- `config.yaml` — document `goal_max_steps`, `verify_goals`.
- Tests: `test_page_explorer.py`? no — `test_solver.py` (or existing solver test) for the budget override; a new `test_goal_verifier.py`; extend the dry-run test.

---

## Task 1: `Solver.solve` per-call `max_steps` override (C1)

**Files:**
- Modify: `hsge/webarena/agents.py` (`Solver.solve`)
- Test: `hsge/tests/test_solver_budget.py` (create)

**Interfaces:**
- Produces: `Solver.solve(self, browser, goal, goal_predicate=None, max_steps=None)` — `max_steps` overrides `self.max_steps` for this call only; `None` keeps current behavior.

- [ ] **Step 1: Write the failing test**

```python
# hsge/tests/test_solver_budget.py
"""Solver.solve accepts a per-call max_steps override (used to give GOAL tasks a
larger budget than LOCAL). Run: PYTHONPATH=. python -m pytest hsge/tests/test_solver_budget.py -q
"""
from hsge.webarena.agents import Solver


class _Browser:
    terminated = False

    def __init__(self):
        self.n = 0
        self.url = "http://x/0"

    def observation(self):
        return {"url": self.url, "axtree": f"page {self.n}"}

    def act(self, action):
        self.n += 1
        self.url = f"http://x/{self.n}"
        return self.observation()

    def screenshot_b64(self, som=True):
        return None


class _NeverDoneLLM:
    """Always returns a non-terminal action, so the episode runs to the budget."""
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"thought": "go", "action": "click('1')"}


def test_solve_max_steps_override_extends_budget():
    llm = _NeverDoneLLM()
    solver = Solver(llm, max_steps=3)

    steps_default, *_ = solver.solve(_Browser(), "goal")
    steps_override, *_ = solver.solve(_Browser(), "goal", max_steps=7)

    # a non-terminal episode runs exactly one action per step until the budget
    assert len(steps_default) == 3
    assert len(steps_override) == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda activate go-browse && PYTHONPATH=. python -m pytest hsge/tests/test_solver_budget.py -q`
Expected: FAIL — `solve()` got an unexpected keyword argument `max_steps`.

- [ ] **Step 3: Write minimal implementation**

In `Solver.solve`, add the param and use it for the loop bound (the wrap-up call and everything else are unchanged):

```python
    def solve(self, browser, goal: str, goal_predicate: str | None = None,
              max_steps: int | None = None):
        budget = max_steps if max_steps is not None else self.max_steps
        # ...unchanged setup...
        for _ in range(budget):        # was: range(self.max_steps)
            # ...unchanged loop body...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_solver_budget.py -q`
Expected: PASS (2 assertions).

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/agents.py hsge/tests/test_solver_budget.py
git commit -m "feat(solver): per-call max_steps override for solve()"
```

---

## Task 2: Wire `goal_max_steps` through the runtime (C1)

**Files:**
- Modify: `hsge/webarena/runtime.py` (`__init__`, `_solve_with_retries`, GOAL call site)
- Modify: `run_webarena.py` (`run.goal_max_steps` default + wiring)
- Test: `hsge/tests/test_goal_task.py` or a small runtime test asserting the GOAL call uses `goal_max_steps`.

**Interfaces:**
- Consumes: `Solver.solve(..., max_steps=)` (Task 1).
- Produces: `WebArenaExplorer(..., goal_max_steps: int | None = None)`; `_solve_with_retries(..., max_steps=None)` forwards to `solve`; the GOAL loop passes `self.goal_max_steps`.

- [ ] **Step 1: Write the failing test**

```python
# hsge/tests/test_goal_budget.py
"""GOAL tasks are solved with goal_max_steps, LOCAL with the shared max_steps."""
import tempfile
from unittest import mock

from hsge.llm import HashingEmbedder, MockLLM
from hsge.webarena.runtime import WebArenaExplorer


def _ex(**kw):
    return WebArenaExplorer(browser_factory=lambda u: None, llm=MockLLM(),
                            embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
                            allow_pattern=".*", terminal_goal=None, **kw)


def test_goal_task_solved_with_goal_max_steps():
    ex = _ex(max_steps=15, goal_max_steps=25)
    ex.site_seed = {"description": "d", "capabilities": [{"name": "c", "goal": "do the thing"}]}
    seen = {}
    with mock.patch.object(ex.solver, "solve",
                           return_value=([], [], [], {"url": ""}, False, False)) as m, \
         mock.patch.object(ex, "browser_factory"):
        browser = mock.MagicMock()
        for gt in ex._goal_task():
            ex._solve_with_retries(browser, gt["goal"], difficulty=gt["difficulty"],
                                   tag="GOAL", goal_predicate=gt["goal_predicate"],
                                   max_steps=ex.goal_max_steps)
        seen["kw"] = m.call_args.kwargs
    assert seen["kw"].get("max_steps") == 25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_goal_budget.py -q`
Expected: FAIL — `WebArenaExplorer` has no `goal_max_steps`, or `_solve_with_retries` has no `max_steps`.

- [ ] **Step 3: Write minimal implementation**

`runtime.py __init__`: add `goal_max_steps: int | None = None` and `self.goal_max_steps = goal_max_steps if goal_max_steps is not None else max_steps`.

`_solve_with_retries`: add `max_steps=None` param; in its `self.solver.solve(...)` call pass `max_steps=max_steps`.

GOAL call site (run() section 2): pass `max_steps=self.goal_max_steps` to `_solve_with_retries`.

`run_webarena.py`: `DEFAULTS["run"]["goal_max_steps"] = None`; in `main()`: `goal_max_steps = _pick(args.goal_max_steps, run["goal_max_steps"])` (add a `--goal-max-steps` argparse int, default None) and pass `goal_max_steps=goal_max_steps` to `WebArenaExplorer`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_goal_budget.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/runtime.py run_webarena.py hsge/tests/test_goal_budget.py
git commit -m "feat(runtime): goal_max_steps budget for GOAL tasks"
```

---

## Task 3: Inline GOAL verifier (B1)

**Files:**
- Create: `hsge/webarena/verify.py` (shared `JUDGE_SYS`/`judge_prompt`)
- Modify: `judge_episodes.py` (import the moved prompt, keep `_SYS`/`_judge_prompt` aliases)
- Modify: `hsge/webarena/runtime.py` (`_verify_episode`, GOAL loop, `_record` judge fields, `episode_judge` routing)
- Modify: `run_webarena.py` (`episode_judge` in `AGENT_ROLES`; `run.verify_goals` default; `_DryLLM` grader branch + wandering scenario)
- Test: `hsge/tests/test_goal_verifier.py` (create)

**Interfaces:**
- Consumes: `hsge.webarena.verify.JUDGE_SYS`, `hsge.webarena.verify.judge_prompt`; `self.judge_llm = role("episode_judge")`.
- Produces: `hsge/webarena/verify.py` with `JUDGE_SYS: str` and `judge_prompt(goal, history, final_url, final_axtree) -> str`; `WebArenaExplorer._verify_episode(goal, steps, final_obs) -> tuple[bool, str]` (PASS→(True,reason)); `WebArenaExplorer(..., verify_goals: bool = False)`; `_record(..., judge_verified=None, judge_reason=None)` writes `outcome.judge_verified`/`judge_reason` when provided.

- [ ] **Step 1: Write the failing test**

```python
# hsge/tests/test_goal_verifier.py
"""Inline GOAL verifier flips a self-declared success to fail when the final
page does not satisfy the goal (reuses the judge_episodes grader prompt)."""
import json, os, tempfile
from hsge.llm import HashingEmbedder, MockLLM
from hsge.schema import Step
from hsge.webarena.runtime import WebArenaExplorer


class _Judge:
    def __init__(self, verdict): self.verdict = verdict
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"verdict": self.verdict, "reason": "r"}


def _ex(judge, **kw):
    ex = WebArenaExplorer(browser_factory=lambda u: None, llm=MockLLM(),
                          embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
                          allow_pattern=".*", terminal_goal=None, verify_goals=True, **kw)
    ex.judge_llm = judge
    return ex


def test_verify_episode_pass_and_fail():
    steps = [Step(action="click('1')", url="http://x/1", axtree="a"),
             Step(action="send_msg_to_user('done')", url="http://x/2", axtree="b")]
    obs = {"url": "http://x/2", "axtree": "b"}
    assert _ex(_Judge("PASS"))._verify_episode("goal", steps, obs)[0] is True
    assert _ex(_Judge("FAIL"))._verify_episode("goal", steps, obs)[0] is False


def test_record_writes_judge_fields():
    ex = _ex(_Judge("FAIL"))
    steps = [Step(action="send_msg_to_user('done')", url="http://x", axtree="b")]
    ex._record("goal", steps, ["b"], [None], success=True, difficulty=2, tag="GOAL",
               judge_verified=False, judge_reason="gave up")
    meta = json.load(open(os.path.join(ex.out_dir, "episodes", "ep_0000",
                                       "episode_meta.json"), encoding="utf-8"))
    assert meta["outcome"]["judge_verified"] is False
    assert meta["outcome"]["judge_reason"] == "gave up"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_goal_verifier.py -q`
Expected: FAIL — no `_verify_episode`; `_record` has no `judge_verified` kwarg.

- [ ] **Step 3a: Extract the shared prompt module (breaks the circular import)**

Create `hsge/webarena/verify.py` by moving the grader prompt out of `judge_episodes.py` (this module must import nothing from `run_webarena`/`build_sft_dataset` — keep it a leaf):

```python
# hsge/webarena/verify.py
"""Shared grader prompt for the offline judge (judge_episodes.py) and the live
inline GOAL verifier (runtime.py). A leaf module -- no run_webarena import -- so
runtime.py can use it without the runtime -> judge_episodes -> run_webarena ->
runtime cycle."""
import json

JUDGE_SYS = (
    "You are a strict grader of a web agent's completed task. You are given "
    "the GOAL the agent was told to accomplish, the actions it took before "
    "declaring the task done, and the FINAL page (URL + accessibility tree) "
    "where it declared done. Decide whether the goal was genuinely achieved "
    "by the final state -- not whether the agent SAID it was done. Common "
    "false positives: the agent gave up and declared done anyway; it "
    "answered an INFO question with a guess not actually shown on the final "
    "page; it navigated to the wrong page. "
    'Return JSON {"verdict": "PASS"|"FAIL", "reason": "<one sentence>"}.'
)

_AXTREE_CAP = 4000


def judge_prompt(goal, history, final_url, final_axtree) -> str:
    payload = {"goal": goal, "actions_taken": history,
               "final_url": final_url, "final_page": (final_axtree or "")[:_AXTREE_CAP]}
    return f"<payload>{json.dumps(payload)}</payload>"
```

In `judge_episodes.py`, replace the local `_SYS`/`_judge_prompt`/`_AXTREE_CAP` definitions with `from hsge.webarena.verify import JUDGE_SYS as _SYS, judge_prompt as _judge_prompt` (keep the `_SYS`/`_judge_prompt` names so the rest of the file is unchanged).

- [ ] **Step 3b: Wire the verifier into the runtime**

`runtime.py` imports: `from .verify import JUDGE_SYS, judge_prompt`.

`__init__`: `self.verify_goals = verify_goals`; `self.judge_llm = role("episode_judge")`.

New method:

```python
    def _verify_episode(self, goal, steps, final_obs) -> tuple[bool, str]:
        """LLM re-check of a self-declared GOAL success against its final page.
        Reuses the offline judge prompt, run live."""
        history = [st.action for st in steps[:-1]]
        prompt = judge_prompt(goal, history, final_obs.get("url", ""),
                              final_obs.get("axtree", ""))
        out = self.judge_llm.complete_json(JUDGE_SYS, prompt)
        verdict = str(out.get("verdict", "")).strip().upper()
        return verdict == "PASS", str(out.get("reason", ""))[:200]
```

`_record`: add `judge_verified=None, judge_reason=None`; after building `meta["outcome"]`, `if judge_verified is not None: meta["outcome"]["judge_verified"] = judge_verified; meta["outcome"]["judge_reason"] = judge_reason`.

GOAL loop (run() section 2): after `_solve_with_retries` returns, when `self.verify_goals and success and gt["goal_predicate"] is None` and `steps`: call `_verify_episode`, and if not verified set `success = False` before the `bucket`/`task_stats`/`node_rec` lines; pass `judge_verified`/`judge_reason` down so they land in `episode_meta`. (Threading the judge result into the already-recorded episode: simplest is to verify *inside* `_solve_with_retries` when a `verify_fn` is passed, so `_record` gets the fields in the same call — implement `_solve_with_retries(..., verify_fn=None)` that runs `verify_fn(goal, steps, final_obs)` on a self-graded success and forwards the result to `_record`, returning the corrected success.)

`run_webarena.py`: add `"episode_judge"` to `AGENT_ROLES`; `DEFAULTS["run"]["verify_goals"] = False`; `main()` reads `verify_goals` (True in dry-run to exercise it) and passes it. `_DryLLM`: add a grader branch and make the scripted solver *wander then declare done* so the judge returns FAIL in the dry run:

```python
        if system.startswith("You are a strict grader"):        # inline verifier
            # in the dry run the solver declares done without reaching success ->
            # the judge catches the false positive
            return {"verdict": "FAIL", "reason": "goal not satisfied on final page"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_goal_verifier.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/verify.py judge_episodes.py hsge/webarena/runtime.py run_webarena.py hsge/tests/test_goal_verifier.py
git commit -m "feat(verify): inline GOAL verifier gate reusing the judge prompt"
```

---

## Task 4: Dry-run e2e + config + changelog

**Files:**
- Modify: `hsge/tests/test_dry_run_seed.py` (assert the verifier flips a GOAL success)
- Modify: `config.yaml` (`goal_max_steps`, `verify_goals` docs)
- Modify: `.claude/memory/changelog.md`

**Interfaces:** consumes everything above.

- [ ] **Step 1: Extend the dry-run assertion**

The dry run now enables `verify_goals`; with the `_DryLLM` grader returning FAIL and a wander-then-done solver scenario, the previously-passing GOAL should now be caught. Add:

```python
def test_dry_run_verifier_catches_false_positive_goal(tmp_path):
    import json, os, subprocess, sys
    out = str(tmp_path / "wa_dry")
    subprocess.run([sys.executable, "run_webarena.py", "--dry-run",
                    "--out", out, "--max-nodes", "2"], check=True, cwd=REPO)
    summary = json.load(open(os.path.join(out, "summary.json"), encoding="utf-8"))
    goal = summary["tasks"]["GOAL"]
    # the verifier turned the self-declared GOAL success into a fail
    assert goal["fail"] >= 1
```

> If the existing dry-run scenario makes the judge PASS instead (depends on the scripted solver path), adjust the `_DryLLM` scenario so the GOAL episode wanders then declares done and the grader FAILs it — the point is to prove the gate demotes a false positive end-to-end. Keep the existing `test_dry_run_produces_seed_and_goal_episode` (seed.json still written; a GOAL episode still ran, now judged).

- [ ] **Step 2: Run the dry run + test**

Run: `python run_webarena.py --dry-run --out /tmp/wa_dry_verify --max-nodes 2` then `PYTHONPATH=. python -m pytest hsge/tests/test_dry_run_seed.py -q`.
Expected: the GOAL bucket now shows a verifier-caught fail.

- [ ] **Step 3: Config + changelog + full suite**

`config.yaml` under `run:`:
```yaml
  goal_max_steps: 25         # step budget for GOAL/composite tasks (null -> max_steps);
                             # multi-step GOALs need more room than LOCAL lookups
  verify_goals: true         # re-check every self-graded GOAL success with the
                             # episode_judge model; a FAIL demotes it to fail (stops
                             # the solver grading its own homework). false = old behavior
```
(Optional: `llm.agents.episode_judge` already exists — it now also drives the live gate.)

Run the whole suite: `PYTHONPATH=. python -m pytest hsge/tests/ -q` → all green (184 + new).

Append a `changelog.md` entry (real timestamp): B1 inline verifier + C1 goal_max_steps, gated by `verify_goals`/`goal_max_steps`, dry-run proves a false-positive GOAL is caught; real-run confirmation of *trustworthy* GOAL success still pending.

- [ ] **Step 4: Commit**

```bash
git add hsge/tests/test_dry_run_seed.py config.yaml .claude/memory/changelog.md
git commit -m "feat(verify): dry-run e2e for inline GOAL verifier + goal_max_steps docs"
```

---

## Self-review checklist

1. **Coverage:** C1 = Tasks 1-2 (`goal_max_steps`); B1 = Task 3 (verifier + role + flag + `_record` fields); e2e = Task 4. Confirmed decisions all reflected (reuse judge prompt, GOAL-only, fail-demote, separate knob).
2. **Type consistency:** `Solver.solve(..., max_steps=None)`, `_solve_with_retries(..., max_steps=None, verify_fn=None)`, `WebArenaExplorer(..., goal_max_steps=None, verify_goals=False)`, `_verify_episode(goal, steps, final_obs) -> (bool, str)`, `_record(..., judge_verified=None, judge_reason=None)`, role `"episode_judge"` in `AGENT_ROLES`.
3. **Circular import — RESOLVED in plan:** `runtime.py` must NOT import `judge_episodes` (confirmed cycle `runtime → judge_episodes → run_webarena → runtime`). Task 3a moves the prompt to leaf module `hsge/webarena/verify.py`; both `judge_episodes.py` and `runtime.py` import from there. After Task 3, run the full suite to confirm `judge_episodes.py` still imports cleanly.

## Not in this slice (later plans)

- B2 auto verify-predicate (deterministic where a crisp end-state exists).
- C2 bottom-up refinement, C3 anti-wandering, C4 grounding-gated operators.
- Extending the verifier to LOCAL episodes.
