# Solver success-rate improvements: outcome-annotated history, wrap-up call, infeasible outcome, task retries (design)

**Date:** 2026-07-14
**Status:** approved, awaiting implementation plan
**Context:** wa_run_07 failure analysis (521 tasks, 201 fail = 38.6%):
NAV tasks fail at 73% (116/159) vs INFO at 15%; 61 failed episodes died at
exactly 5 steps (the `_MAX_REPEATS=4` stuck hard-stop) and 35 exhausted all 15
steps; 41 failed episodes ended in `report_infeasible(...)`, an action the
model invented (BrowserGym accepts it) that our `ACTIONS_DOC` never mentions.
Reading failed NAV episodes shows the dominant pattern: the model clicks the
right link, **arrives**, but the same sitewide nav link re-appears under a new
bid on the destination page, so it keeps clicking, never realizes it is done,
and never calls `send_msg_to_user` — which is the only thing that counts as
success for non-predicate tasks (`agents.py::solve`, tail).

## Goal

Convert "achieved but never declared" episodes into successes, stop counting
model-declared-infeasible tasks as Solver failures, and give failed tasks a
config-gated second chance. No change to how predicate-verified (GOAL) success
is decided.

## Design

Four components. 1–3 live in `hsge/webarena/agents.py`; 4 in
`hsge/webarena/runtime.py` + `run_webarena.py` + `config.yaml`.

### Component 1 — outcome-annotated action history + wrap-up call

**History annotation.** `solve()` keeps a parallel `outcomes: list[str]` next
to `history`. After each executed action: `"now at <url>"` when the URL
changed, `"page changed"` when only the axtree changed, `"no change"`
otherwise. The prompt's `RECENT ACTIONS` block renders
`- click('24') -> now at http://…/wiki` instead of the bare action, so the
model can see a navigation already succeeded.

**Wrap-up call.** When the loop ends without a terminal action (hard-stop on
stuck streak, or `max_steps` exhausted) and `goal_predicate is None` (LOCAL
tasks only — GOAL success stays predicate-decided), make ONE extra LLM call:
same system prompt, a prompt stating the budget is exhausted and instructing
the model to either `send_msg_to_user(...)` now if the goal was in fact
achieved, or `report_infeasible('why')` otherwise. Only those two actions are
accepted from this call; anything else is discarded (no browser execution
either way). An accepted action is appended as a `Step`, and the existing
"last action is send_msg → success" rule then applies unchanged. Cost: +1 LLM
call only on otherwise-failing episodes.

### Component 2 — `report_infeasible` as a first-class outcome

- Add to `ACTIONS_DOC`: `report_infeasible('reason')` — allowed ONLY when the
  task cannot be performed on this site/page.
- `solve()` treats it as a terminal action exactly like `send_msg_to_user`
  (break before `browser.act`; never executed).
- `solve()` returns a **6-tuple**: `(steps, obs_texts, obs_screenshots,
  final_obs, success, infeasible)` where `infeasible` is True iff the last
  step's action starts with `report_infeasible`. `success` stays False for
  infeasible episodes.
- Runtime: `task_stats` per tag gains an `"infeasible"` counter (episodes
  counted there are NOT counted as `fail`); episode meta `outcome` gains
  `"infeasible": bool`; `task_result` log events and `nodes.json` task entries
  gain `infeasible`. Infeasible episodes are never fed to Discovery (already
  true today since `success=False`) and are never retried (Component 4).

### Component 3 — NAV-aware prompt line

One rule appended to `SOLVER_SYS`: for "go to page X" goals, once the URL/page
has changed to the destination the goal is DONE — call `send_msg_to_user`
immediately instead of clicking the same link again.

### Component 4 — config-gated task retries

- New config `run.task_retries` (built-in default **0** = off; CLI
  `--task-retries`; precedence CLI > config.yaml > default). `config.yaml`
  sets it to **2** per the user's request.
- `runtime.py` gains `_solve_with_retries(browser, task, goal_predicate=None)`:
  up to `1 + task_retries` attempts; `browser.reset()` before each; stop on
  the first attempt that is `success` OR `infeasible` (retrying a task the
  model just declared impossible wastes budget).
- **Every attempt is recorded as its own episode** (SFT data and logs stay
  honest). `task_stats` counts each task ONCE by final outcome
  (success / infeasible / fail). `nodes.json` task entries and `task_result`
  events gain `"attempts": k`. Applies to both LOCAL and GOAL tasks.

## Interface changes (breaking, internal only)

`Solver.solve` 5-tuple → 6-tuple. Callers: 2 sites in `runtime.py`, 4 tests in
`hsge/tests/test_solver.py`. The two stuck-loop tests also change behavior
deliberately: after the hard-stop the wrap-up call now fires, so
`_StubbornRepeatLLM`-style mocks get one extra `complete_json` call (their
non-terminal answer is discarded → still `success=False`, steps unchanged);
assertions on call counts are updated accordingly.

## Non-goals

- No solver model upgrade, no `max_steps` change (61 of the failures died at
  step 5 from the stuck loop, not from budget).
- No change to GOAL success semantics (`reached()` stays the only truth).
- No retry for infeasible episodes.
- No PageExplorer changes (its task quality is a separate concern; the new
  per-tag infeasible counters are the measurement tool for it).

## Verification

1. `hsge/tests/test_solver.py` — updated 6-tuple unpacking; new tests:
   history lines carry outcome annotations; wrap-up converts an
   achieved-but-undeclared episode into success; wrap-up discards a
   non-terminal wrap-up answer; `report_infeasible` ends the episode with
   `infeasible=True, success=False` and is never passed to `browser.act`.
2. New retry tests (runtime level): fail→success on 2nd attempt yields one
   task counted success with `attempts=2` and two recorded episodes;
   infeasible is not retried; `task_retries=0` reproduces today's behavior.
3. `python -m pytest hsge/tests/ -q` all green;
   `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2` passes.
