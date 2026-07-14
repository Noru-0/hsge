# Solver Success-Rate Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert "achieved but never declared" episodes into successes (outcome-annotated history + one wrap-up LLM call), make `report_infeasible` a first-class non-fail outcome, and add config-gated retries for failed tasks.

**Architecture:** Components 1–3 (annotated history, wrap-up call, infeasible outcome, NAV prompt rule) all live inside `hsge/webarena/agents.py::Solver`; `solve()` grows from a 5-tuple to a 6-tuple return (`+ infeasible`). Component 4 (retries) lives in `hsge/webarena/runtime.py` as a `_solve_with_retries` helper that replaces both `solver.solve` call sites and records every attempt as its own episode, wired through `run_webarena.py` config/CLI as `task_retries`.

**Tech Stack:** Python 3.10+, no new dependencies. Tests follow the repo's standalone-or-pytest pattern.

**Spec:** `docs/superpowers/specs/2026-07-14-solver-success-rate-design.md`

## Global Constraints

- Run everything from the repo root; activate the conda env first: `conda activate go-browse`.
- All code/comments/commit messages in English.
- Commit after each task; end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` (exact trailer, do not substitute another model name).
- Mock pipeline stays deterministic; the full suite (`python -m pytest hsge/tests/ -q`) must be green at the end of every task.
- `task_retries`: built-in default **0** (off); CLI `--task-retries`; precedence CLI > config.yaml > default. `config.yaml` gets `task_retries: 2`.
- GOAL-task success semantics unchanged: `reached()` only. The wrap-up call fires only when `goal_predicate is None`.
- Infeasible episodes: `success=False`, counted in a separate `infeasible` bucket (not `fail`), never fed to Discovery, never retried.

---

### Task 1: Solver — annotated history, wrap-up call, `report_infeasible`, NAV rule

**Files:**
- Modify: `hsge/webarena/agents.py` (`ACTIONS_DOC`, `SOLVER_SYS`, `Solver.solve`)
- Modify: `hsge/webarena/runtime.py` (ONLY the two `self.solver.solve(...)` unpack lines — minimal compatibility so the suite stays green; Task 2 rewrites these properly)
- Test: `hsge/tests/test_solver.py`

**Interfaces:**
- Produces: `Solver.solve(browser, goal, goal_predicate=None) -> (steps, obs_texts, obs_screenshots, final_obs, success: bool, infeasible: bool)` — the 6-tuple Task 2 consumes. Wrap-up prompt contains the literal phrase `"budget is exhausted"` (tests key off it). History lines render as `- <action> -> <outcome>` where outcome is `now at <url>` / `page changed` / `no change`.

- [ ] **Step 1: Update existing tests to the 6-tuple and write the new failing tests**

In `hsge/tests/test_solver.py`, change all four existing unpack lines from

```python
    steps, obs_texts, obs_screenshots, final_obs, success = solver.solve(browser, "goal")
```

to

```python
    steps, obs_texts, obs_screenshots, final_obs, success, infeasible = solver.solve(browser, "goal")
```

Then update the two hard-stop tests for the wrap-up call (one extra LLM call whose non-terminal answer is discarded):

```python
def test_solver_gives_up_after_max_repeats_when_model_ignores_the_warning():
    """A soft nudge isn't always obeyed -- once the same target has been
    interacted with _MAX_REPEATS times in a row with no progress, the
    solver stops the action loop, then makes exactly one wrap-up call; a
    non-terminal wrap-up answer (this mock still says click) is discarded."""
    llm = _StubbornRepeatLLM()
    solver = Solver(llm, max_steps=15)
    browser = _FakeBrowser()

    steps, obs_texts, obs_screenshots, final_obs, success, infeasible = solver.solve(browser, "goal")

    assert success is False
    assert infeasible is False
    assert len(steps) == Solver._MAX_REPEATS      # wrap-up click was discarded
    assert llm.calls == Solver._MAX_REPEATS + 1   # action loop + 1 wrap-up call
```

and in `test_solver_gives_up_on_same_target_repeated_with_different_arguments` keep the
existing assertions but change the unpack line as above and add
`assert llm.calls == Solver._MAX_REPEATS + 1` (the mock's `calls` counter already exists).

Append the new tests:

```python
class _NavOnceBrowser:
    """First act() navigates to /wiki; every later act() changes nothing
    (the sitewide 'Wiki' link is still on the destination page)."""

    def __init__(self):
        self.i = 0

    def observation(self):
        if self.i == 0:
            return {"url": "http://x/", "axtree": "[24] link 'Wiki'"}
        return {"url": "http://x/wiki", "axtree": "[7] heading 'Wiki'\n[24] link 'Wiki'"}

    def screenshot_b64(self, som=False):
        return None

    def act(self, action):
        self.i += 1
        return self.observation()


class _ArrivesButKeepsClickingLLM:
    """Clicks the same nav link forever (never realizes it arrived); only
    the wrap-up prompt makes it declare done. Mirrors the dominant real-run
    NAV failure (wa_run_07: 116 NAV fails, model on the right page but
    still clicking)."""

    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        if "budget is exhausted" in prompt:
            return {"thought": "already on the wiki page",
                    "action": "send_msg_to_user('done: on the wiki page')"}
        return {"thought": "go to wiki", "action": "click('24')"}


def test_wrapup_call_converts_arrived_but_undeclared_into_success():
    llm = _ArrivesButKeepsClickingLLM()
    solver = Solver(llm, max_steps=15)

    steps, obs_texts, obs_screenshots, final_obs, success, infeasible = solver.solve(
        _NavOnceBrowser(), "[NAV] Go to the Wiki page")

    assert success is True
    assert infeasible is False
    assert steps[-1].action.startswith("send_msg_to_user")


def test_history_lines_carry_outcome_annotations():
    llm = _ArrivesButKeepsClickingLLM()
    solver = Solver(llm, max_steps=15)
    solver.solve(_NavOnceBrowser(), "[NAV] Go to the Wiki page")

    # the 2nd action-loop prompt must show the first click actually navigated
    assert any("click('24') -> now at http://x/wiki" in p for p in llm.prompts)
    # and later repeats must be visibly inert
    assert any("click('24') -> no change" in p for p in llm.prompts)


class _InfeasibleLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"thought": "requires admin rights",
                "action": "report_infeasible('requires admin rights')"}


def test_report_infeasible_ends_episode_without_acting():
    browser = _FakeBrowser()
    steps, obs_texts, obs_screenshots, final_obs, success, infeasible = Solver(
        _InfeasibleLLM()).solve(browser, "goal")

    assert infeasible is True
    assert success is False
    assert len(steps) == 1
    assert browser.acted == []   # report_infeasible is never sent to the browser


def test_no_wrapup_for_predicate_goals():
    """GOAL tasks are verified by reached(); the wrap-up call must not fire."""
    llm = _StubbornRepeatLLM()
    solver = Solver(llm, max_steps=15)

    steps, obs_texts, obs_screenshots, final_obs, success, infeasible = solver.solve(
        _FakeBrowser(), "goal", goal_predicate="order_confirmed")

    assert success is False
    assert llm.calls == Solver._MAX_REPEATS   # no +1: wrap-up skipped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_solver.py -q`
Expected: FAIL — existing tests error with "not enough values to unpack (expected 6, got 5)"; new tests fail likewise.

- [ ] **Step 3: Implement the Solver changes**

In `hsge/webarena/agents.py`:

Replace `ACTIONS_DOC`:

```python
ACTIONS_DOC = ("Allowed actions (return exactly one): click('bid'), "
               "fill('bid','text'), select_option('bid','opt'), goto('url'), "
               "go_back(), send_msg_to_user('done message'), "
               "report_infeasible('reason') -- report_infeasible ONLY when the "
               "task cannot be done on this site/page.")
```

Append one rule to `SOLVER_SYS` (after the final "Call send_msg_to_user ONLY when the goal is fully achieved." sentence, inside the same string):

```python
    " For 'go to page X' goals: once the URL/page has changed to the requested "
    "destination the goal is DONE -- call send_msg_to_user immediately; do NOT "
    "click the same link again.")
```

Rewrite `Solver.solve` (whole method):

```python
    def solve(self, browser, goal: str, goal_predicate: str | None = None):
        """Drive the browser toward `goal`.

        Returns (steps, obs_texts, obs_screenshots, final_obs, success, infeasible).
        """
        steps: list[Step] = []
        obs_texts: list[str] = []
        obs_screenshots: list[str | None] = []
        history: list[str] = []
        outcomes: list[str] = []     # human-readable result of history[i]
        progressed: list[bool] = []  # did url/axtree change as a result of history[i]?
        obs = browser.observation()
        last_error = ""
        success = False
        exhausted = True   # loop ended by budget/hard-stop, not by a terminal action
        for _ in range(self.max_steps):
            streak = self._stuck_streak(history, progressed)
            if streak >= self._MAX_REPEATS:
                # A text nudge alone isn't reliably obeyed (verified against a
                # real run: the warning was present in the prompt from the 3rd
                # call onward and the model kept issuing the exact same click
                # anyway for all 15 steps). Stop spending steps on a target
                # that clearly isn't moving instead of exhausting max_steps.
                print(f"    [solver] giving up: target {self._action_target(history[-1])!r} "
                      f"hit {streak}x in a row with no progress")
                break
            repeat_warning = ""
            if streak >= self._WARN_AFTER_REPEATS:
                # The same target just got hit >=2 times in a row with no error --
                # e.g. clicking a nav link that navigated fine but re-appears
                # under a new bid on the destination page, so the model keeps
                # clicking it without realizing it already arrived. Nudge
                # instead of silently repeating the same prompt.
                repeat_warning = (
                    f"\n\nWARNING: your last {streak} actions all targeted "
                    f"{self._action_target(history[-1])!r} with no visible progress -- "
                    "repeating it again will not help. If the goal is already achieved, "
                    "call send_msg_to_user(...) now instead. Otherwise choose a "
                    "genuinely different action/target.")
            recent = [f"- {h} -> {o}" for h, o in zip(history[-6:], outcomes[-6:])]
            prompt = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n"
                      + ("\n".join(recent) or "(none)")
                      + (f"\n\nLAST ACTION ERROR: {last_error}" if last_error else "")
                      + repeat_warning
                      + f"\n\nURL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}")
            screenshot_b64 = browser.screenshot_b64(som=self.som) if self.vision else None
            out = self.llm.complete_json(SOLVER_SYS, prompt,
                                          image_b64=screenshot_b64, image_detail=self.image_detail)
            if screenshot_b64 and not (out.get("action") or "").strip():
                # same rationale as PageExplorer.propose(): don't let a refused/
                # empty vision call silently end the episode -- try text-only.
                print("    [solver] empty response with image attached, retrying text-only")
                out = self.llm.complete_json(SOLVER_SYS, prompt,
                                              image_b64=None, image_detail=self.image_detail)
            action = (out.get("action") or "").strip()
            thought = out.get("thought", "")
            steps.append(Step(action=action, url=obs["url"], obs_summary=thought[:100],
                              axtree=obs["axtree"]))
            obs_texts.append(obs["axtree"])
            obs_screenshots.append(screenshot_b64)
            if (not action or action.startswith("send_msg_to_user")
                    or action.startswith("report_infeasible")):
                exhausted = False
                break
            pre_url, pre_axtree = obs["url"], obs["axtree"]
            try:
                obs = browser.act(action)
                last_error = ""
            except Exception as e:
                # feed the error back so the agent can recover, instead of aborting
                last_error = str(e)[:200]
                steps[-1].obs_summary += f" [action error: {last_error}]"
                continue
            history.append(action)
            if obs["url"] != pre_url:
                outcomes.append(f"now at {obs['url']}")
            elif obs["axtree"] != pre_axtree:
                outcomes.append("page changed")
            else:
                outcomes.append("no change")
            progressed.append(obs["url"] != pre_url or obs["axtree"] != pre_axtree)
            if getattr(browser, "terminated", False):
                exhausted = False
                break
            if goal_predicate and reached(goal_predicate, obs["url"], obs["axtree"]):
                success = True
                exhausted = False
                break

        if exhausted and goal_predicate is None and steps:
            # One last chance: real runs (wa_run_07) showed the dominant NAV
            # failure is arriving at the right page and then looping on the
            # same sitewide nav link until the budget dies -- achieved, but
            # never declared. Ask once, accept ONLY a terminal action, never
            # execute it in the browser.
            recent = [f"- {h} -> {o}" for h, o in zip(history, outcomes)]
            wrap_prompt = (f"GOAL: {goal}\n\nACTIONS TAKEN:\n"
                           + ("\n".join(recent) or "(none)")
                           + f"\n\nURL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}"
                           + "\n\nYour action budget is exhausted. If the goal has "
                             "ALREADY been achieved (e.g. you are on the requested "
                             "page), call send_msg_to_user('done: ...') NOW. If the "
                             "goal cannot be achieved, call report_infeasible('why'). "
                             "Answer with one of those two actions only.")
            out = self.llm.complete_json(SOLVER_SYS, wrap_prompt)
            action = (out.get("action") or "").strip()
            if action.startswith("send_msg_to_user") or action.startswith("report_infeasible"):
                steps.append(Step(action=action, url=obs["url"],
                                  obs_summary=str(out.get("thought", ""))[:100],
                                  axtree=obs["axtree"]))
                obs_texts.append(obs["axtree"])
                obs_screenshots.append(None)

        infeasible = bool(steps) and steps[-1].action.startswith("report_infeasible")
        # success for non-predicate goals = agent declared done without error
        if goal_predicate is None and steps and steps[-1].action.startswith("send_msg_to_user"):
            success = True
        return steps, obs_texts, obs_screenshots, obs, success, infeasible
```

- [ ] **Step 4: Minimal runtime compatibility unpack**

In `hsge/webarena/runtime.py`, change the two call sites so the runtime loop
(and the tests that drive it: `test_run_timing.py`, `test_frontier_mining.py`,
`test_multi_llm.py`) keeps working. Task 2 replaces these lines wholesale —
here they only absorb the extra tuple element:

Local-task site:

```python
                    (steps, obs_texts, obs_screenshots, final_obs, success,
                     _infeasible) = self.solver.solve(browser, task)
```

Goal-task site:

```python
                    (steps, obs_texts, obs_screenshots, final_obs, success,
                     _infeasible) = self.solver.solve(
                        browser, gt["goal"], goal_predicate=self.terminal_goal)
```

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all pass (test_solver now has 8 tests).

- [ ] **Step 6: Commit**

```bash
git add hsge/webarena/agents.py hsge/webarena/runtime.py hsge/tests/test_solver.py
git commit -m "Solver: outcome-annotated history, wrap-up call, report_infeasible outcome

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Runtime — infeasible accounting, `_solve_with_retries`, config/CLI wiring, docs

**Files:**
- Modify: `hsge/webarena/runtime.py` (`__init__`, `_record`, both task blocks in `run()`, `task_stats` init)
- Modify: `run_webarena.py` (DEFAULTS, argparse, `main()`)
- Modify: `config.yaml` (add `task_retries: 2` under `run:`)
- Modify: `.claude/rules/architecture.md` (Solver + runtime bullets), `.claude/memory/changelog.md`, `docs/superpowers/specs/2026-07-14-solver-success-rate-design.md` (Status line)
- Test: Create `hsge/tests/test_task_retries.py`

**Interfaces:**
- Consumes: the 6-tuple `Solver.solve` from Task 1.
- Produces: `WebArenaExplorer(..., task_retries: int = 0)`;
  `WebArenaExplorer._solve_with_retries(browser, task, difficulty, tag, goal_predicate=None) -> (episode_id, steps, final_obs, success, infeasible, attempts, urls_seen)` where `episode_id` is the LAST attempt's id, `attempts >= 1`, and `urls_seen` is the union of `Step.url` + final URL across ALL attempts (frontier signal must not lose earlier attempts); `_record(..., infeasible=False)` kwarg; config key `run.task_retries`; CLI `--task-retries`; `task_stats` buckets `{"success", "fail", "infeasible"}` per tag.

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_task_retries.py`:

```python
"""_solve_with_retries: retry failed tasks up to task_retries times, record
every attempt as its own episode, never retry infeasible, accumulate URLs
across attempts.

Run:  python -m pytest hsge/tests/test_task_retries.py -q
 (or) PYTHONPATH=. python hsge/tests/test_task_retries.py
"""
import os
import tempfile

from hsge.llm import HashingEmbedder, MockLLM
from hsge.schema import Step
from hsge.webarena.runtime import WebArenaExplorer


class _ScriptedSolver:
    """Yields scripted (success, infeasible) outcomes, one per attempt."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def solve(self, browser, task, goal_predicate=None):
        success, infeasible = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        action = ("send_msg_to_user('done')" if success
                  else "report_infeasible('nope')" if infeasible
                  else "click('1')")
        url = f"http://x/attempt{self.calls}"
        steps = [Step(action=action, url=url, obs_summary="", axtree="ax")]
        return steps, ["ax"], [None], {"url": url, "axtree": "ax"}, success, infeasible


class _Browser:
    def reset(self):
        return {"url": "http://x/", "axtree": "ax"}


def _explorer(retries):
    ex = WebArenaExplorer(
        browser_factory=lambda url: None, llm=MockLLM(),
        embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
        allow_pattern=".*", task_retries=retries)
    return ex


def test_fail_then_success_retries_and_records_every_attempt():
    ex = _explorer(retries=2)
    ex.solver = _ScriptedSolver([(False, False), (True, False)])

    (episode_id, steps, final_obs, success, infeasible, attempts,
     urls_seen) = ex._solve_with_retries(_Browser(), "task", difficulty=1, tag="LOCAL")

    assert success is True and infeasible is False
    assert attempts == 2
    assert episode_id == "ep_0001"          # id of the LAST attempt
    assert ex.episode == 2                  # both attempts recorded
    assert os.path.isdir(os.path.join(ex.out_dir, "episodes", "ep_0000"))
    assert os.path.isdir(os.path.join(ex.out_dir, "episodes", "ep_0001"))
    assert {"http://x/attempt1", "http://x/attempt2"} <= urls_seen


def test_infeasible_is_never_retried():
    ex = _explorer(retries=2)
    ex.solver = _ScriptedSolver([(False, True), (True, False)])

    (episode_id, steps, final_obs, success, infeasible, attempts,
     urls_seen) = ex._solve_with_retries(_Browser(), "task", difficulty=1, tag="LOCAL")

    assert infeasible is True and success is False
    assert attempts == 1
    assert ex.solver.calls == 1


def test_zero_retries_is_single_attempt():
    ex = _explorer(retries=0)
    ex.solver = _ScriptedSolver([(False, False), (True, False)])

    (episode_id, steps, final_obs, success, infeasible, attempts,
     urls_seen) = ex._solve_with_retries(_Browser(), "task", difficulty=1, tag="LOCAL")

    assert success is False
    assert attempts == 1


def test_retries_exhausted_reports_last_failure():
    ex = _explorer(retries=2)
    ex.solver = _ScriptedSolver([(False, False)])

    (episode_id, steps, final_obs, success, infeasible, attempts,
     urls_seen) = ex._solve_with_retries(_Browser(), "task", difficulty=1, tag="LOCAL")

    assert success is False and infeasible is False
    assert attempts == 3                    # 1 + task_retries
    assert ex.episode == 3


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_task_retries.py -q`
Expected: FAIL — `TypeError: WebArenaExplorer.__init__() got an unexpected keyword argument 'task_retries'`

- [ ] **Step 3: Implement runtime changes**

In `hsge/webarena/runtime.py`:

3a. `__init__` — add `task_retries: int = 0` to the signature (after
`max_hrefs_per_page: int = 100`) and store it next to the other run knobs:

```python
        self.task_retries = task_retries
```

3b. `_record` — add the `infeasible` kwarg and persist it in the outcome:

```python
    def _record(self, goal, steps, obs_texts, obs_screenshots, success, difficulty, tag,
                infeasible: bool = False):
        ep = os.path.join(self.out_dir, "episodes", f"ep_{self.episode:04d}")
        os.makedirs(os.path.join(ep, "page_state"), exist_ok=True)
        meta = {"kind": "low_level_trajectory", "goal": goal,
                "outcome": {"success": bool(success), "reward": 1.0 if success else 0.0,
                             "response": "", "infeasible": bool(infeasible)},
                "metadata": {"difficulty": difficulty, "tags": [tag]}, "step_count": len(steps)}
```

(the rest of `_record` is unchanged).

3c. Add the retry helper (place it right after `_record`):

```python
    # ---- one task, up to 1 + task_retries attempts --------------------------
    def _solve_with_retries(self, browser, task, difficulty, tag, goal_predicate=None):
        """Run the Solver on one task, retrying failures up to task_retries
        times. Every attempt is recorded as its own episode (SFT data and
        logs stay honest). Infeasible attempts are terminal -- retrying a
        task the model just declared impossible wastes budget. Returns
        (episode_id, steps, final_obs, success, infeasible, attempts,
        urls_seen) for the LAST attempt, with urls_seen accumulated across
        all attempts so the frontier keeps every reached URL.
        """
        attempts = 0
        urls_seen: set[str] = set()
        while True:
            attempts += 1
            episode_id = f"ep_{self.episode:04d}"
            browser.reset()
            (steps, obs_texts, obs_screenshots, final_obs, success,
             infeasible) = self.solver.solve(browser, task, goal_predicate=goal_predicate)
            self._record(task, steps, obs_texts, obs_screenshots, success,
                         difficulty=difficulty, tag=tag, infeasible=infeasible)
            urls_seen.update(st.url for st in steps)
            urls_seen.add(final_obs.get("url", ""))
            if success or infeasible or attempts > self.task_retries:
                return episode_id, steps, final_obs, success, infeasible, attempts, urls_seen
```

3d. `run()` — `task_stats` init gains the `infeasible` bucket:

```python
        task_stats = {"LOCAL": {"success": 0, "fail": 0, "infeasible": 0},
                      "GOAL": {"success": 0, "fail": 0, "infeasible": 0}}
```

3e. Replace the local-task block (from `for task in self.explorer.propose(...)` through the `print(f"    local: ...")` line) with:

```python
                for task in self.explorer.propose(obs, screenshot_b64=node_screenshot_b64):
                    (episode_id, steps, final_obs, success, infeasible, attempts,
                     urls_seen) = self._solve_with_retries(browser, task, difficulty=1, tag="LOCAL")
                    bucket = "success" if success else ("infeasible" if infeasible else "fail")
                    task_stats["LOCAL"][bucket] += 1
                    node_rec["tasks"].append({"episode": episode_id, "tag": "LOCAL", "task": task,
                                               "success": success, "infeasible": infeasible,
                                               "attempts": attempts, "steps": len(steps)})
                    self._log("task_result", node_index=node_index, episode=episode_id, tag="LOCAL",
                               task=task, success=success, infeasible=infeasible,
                               attempts=attempts, steps=len(steps))
                    if success:
                        # only skills that recur enough to be admitted become operators
                        admitted = self.discovery.on_trajectory(steps, site=root_url, task=task)
                        for sid in admitted:
                            card = self._card_by_id(sid)
                            if card:
                                print(f"    [skill] admitted {card.skill_id} '{card.name}' "
                                      f"(members={len(card.member_ids)})")
                                self._log("skill_admitted", skill_id=card.skill_id, name=card.name,
                                           members=len(card.member_ids))
                            self._promote_skill_to_operator(sid)
                    seen_urls |= urls_seen
                    print(f"    local: {task[:50]!r} success={success}"
                          + (" infeasible" if infeasible else "")
                          + (f" attempts={attempts}" if attempts > 1 else "")
                          + f" steps={len(steps)}")
```

(the old standalone `browser.reset()` and `episode_id = f"ep_{...}"` lines disappear — the helper owns both now.)

3f. Replace the goal-task block body (inside `if gt:`) with:

```python
                if gt:
                    (episode_id, steps, final_obs, success, infeasible, attempts,
                     urls_seen) = self._solve_with_retries(
                        browser, gt["goal"], difficulty=gt["difficulty"], tag="GOAL",
                        goal_predicate=self.terminal_goal)
                    bucket = "success" if success else ("infeasible" if infeasible else "fail")
                    task_stats["GOAL"][bucket] += 1
                    node_rec["tasks"].append({"episode": episode_id, "tag": "GOAL", "task": gt["goal"],
                                               "success": success, "infeasible": infeasible,
                                               "attempts": attempts, "steps": len(steps)})
                    self._log("task_result", node_index=node_index, episode=episode_id, tag="GOAL",
                               task=gt["goal"], success=success, infeasible=infeasible,
                               attempts=attempts, steps=len(steps), chain=gt["chain"])
                    seen_urls |= urls_seen
                    print(f"    GOAL chain={gt['chain']} verified={success} steps={len(steps)}")
```

3g. The final `print(f"  tasks: LOCAL success=...")` in `run()` — append the infeasible counts:

```python
        print(f"  tasks: LOCAL success={task_stats['LOCAL']['success']} "
              f"fail={task_stats['LOCAL']['fail']} "
              f"infeasible={task_stats['LOCAL']['infeasible']}  "
              f"GOAL success={task_stats['GOAL']['success']} "
              f"fail={task_stats['GOAL']['fail']} "
              f"infeasible={task_stats['GOAL']['infeasible']}")
```

- [ ] **Step 4: Wire `task_retries` through `run_webarena.py` and `config.yaml`**

In `run_webarena.py`:
- DEFAULTS `run` dict: add `"task_retries": 0,` after `"maturity": 2,`.
- argparse, after `--maturity`:

```python
    ap.add_argument("--task-retries", type=int, default=None,
                    help="retry a failed task up to N more times (default 0; "
                         "infeasible tasks are never retried)")
```

- `main()`: add `task_retries = _pick(args.task_retries, run["task_retries"])` beside the other `_pick` lines, and pass `task_retries=task_retries,` in the `WebArenaExplorer(...)` call.

In `config.yaml`, after the `maturity: 2` line:

```yaml
  task_retries: 2            # retry a failed task up to N more times (0 = off;
                             # tasks the model reports infeasible are never retried)
```

- [ ] **Step 5: Run the tests and the dry run**

Run: `python -m pytest hsge/tests/ -q` — Expected: all pass (4 new in test_task_retries).
If `test_run_timing.py` / `test_frontier_mining.py` assert exact shapes of
`nodes.json` task entries or `task_stats`, update those assertions
deliberately (the new `infeasible`/`attempts` keys are additive).
Run: `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2` — Expected: completes; final "tasks:" line shows the new `infeasible=` fields.
Run: `python3 -c "import json; print(json.load(open('/tmp/wa_dry/episodes/ep_0000/episode_meta.json'))['outcome'])"` — Expected: dict containing `'infeasible': False`.

- [ ] **Step 6: Update docs + memory changelog**

- `.claude/rules/architecture.md`, in the `agents.py` bullet: after the sentence about the hard stop (`_MAX_REPEATS`, default 4) ending the episode, append:

```
  When an episode ends exhausted (hard stop or max_steps) on a non-predicate
  task, the Solver makes one text-only "wrap-up" call -- history is shown
  with per-action outcomes (`-> now at <url>` / `-> no change`) -- that may
  only answer send_msg_to_user (declared done -> success) or
  report_infeasible; anything else is discarded. report_infeasible is a
  first-class outcome (allowed in ACTIONS_DOC, never executed in the
  browser, counted in its own `infeasible` bucket, never fed to Discovery,
  never retried).
```

- Same file, in the `runtime.py` bullet: after the sentence about dumping artifacts, append:

```
  `run.task_retries` (default 0, CLI `--task-retries`) retries a failed task
  up to N more times via `_solve_with_retries`; every attempt is recorded as
  its own episode, `nodes.json`/`task_result` events carry
  `attempts`/`infeasible`, and task_stats counts each task once by final
  outcome (success / fail / infeasible).
```

- `docs/superpowers/specs/2026-07-14-solver-success-rate-design.md`: change the Status line to `**Status:** implemented (see docs/superpowers/plans/2026-07-14-solver-success-rate.md)`.
- `.claude/memory/changelog.md`: get the timestamp with `date "+%Y-%m-%d %H:%M"`, then add one entry under the `## 2026-07-14` heading (newest first) summarizing: Solver wrap-up call + outcome-annotated history + report_infeasible outcome + NAV prompt rule + config-gated task retries; name the files touched.

- [ ] **Step 7: Commit**

```bash
git add hsge/webarena/runtime.py run_webarena.py config.yaml \
        hsge/tests/test_task_retries.py .claude/rules/architecture.md \
        .claude/memory/changelog.md \
        docs/superpowers/specs/2026-07-14-solver-success-rate-design.md
git commit -m "Runtime: infeasible accounting + config-gated task retries

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Note: `config.yaml` has a pre-existing uncommitted user edit (deepseek model
names). Stage it anyway — the user's edit and the new key both belong in this
commit; do NOT revert the model-name lines.
