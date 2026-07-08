# SFT prompt fidelity + Solver action-space expansion — design

**Date:** 2026-07-08
**Status:** approved (brainstorm session, comparison against `apurvaga/go-browse-wa`)
**Scope note:** Two changes bundled because they touch the same code path
(`Solver.solve()`'s prompt construction) and were approved together: (A) make
`build_sft_dataset.py` emit the exact prompt the Solver saw at inference time
instead of a hand-rolled duplicate template, (B) teach the Solver 3 actions
the underlying BrowserGym executor already supports but the prompt never
mentions. Deferred: keeping `verified`/reward as a data column and
trajectory-linking ids (`episode_id`/`step_idx`) — not requested this round.

## Context

Comparing HSGE's `build_sft_dataset.py` against the `apurvaga/go-browse-wa`
HuggingFace dataset (164k rows, `step_data.prompt`/`step_data.completion`
columns) surfaced two gaps:

1. **Prompt drift.** `build_sft_dataset.py`'s `SYSTEM` constant and its
   hand-built user message ([build_sft_dataset.py:28-34](../../build_sft_dataset.py),
   `episode_to_examples`) do not match the real prompt `Solver.solve()` sends
   to the LLM ([hsge/webarena/agents.py:252-259](../../hsge/webarena/agents.py)):
   missing `LAST ACTION ERROR: ...`, the same-target `repeat_warning` nudge,
   the `KNOWN PROCEDURES` skill-hints block, the `axtree[:6000]` truncation,
   and using different section labels. A model fine-tuned on this data would
   train on a prompt distribution the deployed Solver never actually shows
   it.
2. **Under-documented action space.** `WebArenaBrowser`'s configured
   `HighLevelActionSet` (`subsets=["chat", "bid", "infeas", "nav"]`,
   [hsge/webarena/browser.py:27-28](../../hsge/webarena/browser.py)) supports
   the same 17 BrowserGym actions go-browse-wa's prompt documents. `agents.py`'s
   `ACTIONS_DOC` only tells the model about 6 of them
   (`click`/`fill`/`select_option`/`goto`/`go_back`/`send_msg_to_user`) — the
   other 11 are executable but never offered. Of those, three close concrete
   gaps already visible in this project: no way for the Solver to signal a
   task is impossible (`report_infeasible` — a standing backlog item), no way
   to submit a form with Enter or use keyboard shortcuts (`press`), no way to
   open hover-only nav menus (`hover`).

Explicit design constraint from this session: **the explore/solve runtime
must not be made to carry the full assembled prompt.** Only small raw
signals it already computes get persisted; final prompt assembly happens in
`build_sft_dataset.py` via a prompt-builder function shared with the live
Solver, so there is exactly one place that knows the prompt's format.

## Why hints/last_error must still be persisted (not dropped)

An earlier version of this design considered building the prompt in
`build_sft_dataset.py` from only `action`/`axtree`/`url` already on disk,
with `hints` and `last_error` reconstructed or omitted. Rejected:

- `hints` (the `KNOWN PROCEDURES` block) is computed once per solve from
  live skill-library retrieval ([hsge/webarena/collect.py:131-134](../../hsge/webarena/collect.py))
  and never persisted. Recomputing it later would use the skill library's
  *current* state, which has moved on since the run — not what the model
  actually saw.
- `last_error` exists today only as a local variable inside `solve()`'s loop.
  The only trace of it on disk is a free-text suffix appended to
  `obs_summary` (`" [action error: ...]"`), which would require fragile
  string-parsing to recover and never captures the exact `str(exception)[:200]`
  reliably.

Both are small strings (not the prompt itself), and both concentrate on
exactly the hardest steps to get right — error recovery and skill-hint
usage — so silently training without them would teach the wrong behavior at
the steps that matter most. They are persisted; the prompt text itself is
still assembled only in `build_sft_dataset.py`.

## Changes

### 1. `hsge/schema.py::Step`

Add two fields, defaults keep every existing `Step(...)` call site valid:

```python
hints: str = ""        # KNOWN PROCEDURES block content shown for this step, if any
last_error: str = ""   # LAST ACTION ERROR text shown for this step, if any
```

(`url` already exists on `Step` but is dropped when persisted — see #3.)

### 2. `hsge/webarena/agents.py`

- **`ACTIONS_DOC`**: rewrite as one short block per action (name, one-line
  description, one example), in the same terse style as the current
  `SOLVER_SYS` examples. Add `press(bid, key_comb)`, `hover(bid)`,
  `report_infeasible(reason)` alongside the existing 6. Do not add the
  remaining 8 BrowserGym actions (`noop`, `scroll`, `dblclick`, `focus`,
  `clear`, `drag_and_drop`, `upload_file`, `go_forward`) — no concrete gap in
  this project motivates them yet, and a shorter action list is easier for a
  small model to pick correctly from.
- **New module-level function** `build_solver_prompt(goal, hints, history,
  progressed, last_error, url, axtree) -> str`: the exact body currently
  inlined at [agents.py:252-259](../../hsge/webarena/agents.py), parameterized.
  Takes the **full** `history`/`progressed` lists (matching indices, same
  contract as `Solver._stuck_streak`) and internally both computes the
  streak/`repeat_warning` from them and slices `history[-6:]` for the
  "RECENT ACTIONS" display, exactly as the current inline code does — callers
  never slice themselves. Internally calls the existing
  `Solver._stuck_streak`/`Solver._action_target` classmethods to derive
  `repeat_warning` — no duplicated streak logic. This is the single source of
  truth for prompt text; `Solver.solve()` and `build_sft_dataset.py` both
  call it.
- **`Solver.solve()`**: replace the inline f-string with a call to
  `build_solver_prompt(...)`. When appending each `Step`, also set
  `hints=hints or ""`, `last_error=last_error`, `url=obs["url"]` (in addition
  to the existing `axtree=obs["axtree"]`).
- **Loop termination**: add `action.startswith("report_infeasible")` to the
  break condition alongside `action.startswith("send_msg_to_user")`. Do
  **not** add it to the `success = True` check at the end of `solve()` — an
  episode that ends in `report_infeasible` stays `success=False` with no
  further code change needed, since that check already only fires on
  `send_msg_to_user`.

### 3. `hsge/webarena/recording.py::record_episode`

Add `"hints": st.hints, "last_error": st.last_error, "url": st.url` to the
per-step `rec` dict written to `episode.jsonl` (currently only
`action`/`parsed_action`/`thought`/`observation` are written; `url` was
silently dropped despite being on `Step` already).

### 4. `build_sft_dataset.py`

- Delete the hand-rolled `SYSTEM` constant and `_read_axtree` (superseded).
- Import `SOLVER_SYS` and `build_solver_prompt` from `hsge.webarena.agents`,
  and `Solver` for the streak classmethods (already used inside
  `build_solver_prompt`, no direct call needed here).
- Rewrite `episode_to_examples`: replay each episode's steps in order,
  incrementally reconstructing `history`/`progressed` exactly as `solve()`
  does — a step's action joins `history`/`progressed` unless the *next*
  step's `last_error` is non-empty (meaning this step's action execution
  failed; `solve()` never appends a failed action to `history` either). For
  each step, call `build_solver_prompt(goal, step.hints, history, progressed,
  step.last_error, step.url, axtree)` (full lists so far, not pre-sliced) to
  get the exact user prompt, pair with `SOLVER_SYS` as the system message
  and the step's `action` as the assistant target.
- A step missing `url` or whose episode predates this change (no
  `hints`/`last_error`/`url` keys at all) is **skipped**, not
  approximated — legacy runs (`wa_run_01`..`wa_run_05`) contribute 0
  examples per episode until re-run; this was chosen explicitly over a
  fallback reconstruction path to avoid resurrecting the exact drift this
  design removes.
- Drop the `axtree_loaded` diagnostic field from emitted examples (no longer
  meaningful — the axtree is embedded in `prompt_user` at the exact
  truncation the Solver used, not separately loaded).

## Data flow

```
Solver.solve() computes goal/hints/history/progressed/last_error/obs
  -> build_solver_prompt(...) -> prompt string (LLM call uses this)
  -> Step(action, url, axtree, hints, last_error)   # small fields only
  -> recording.record_episode() -> episode.jsonl (hints/last_error/url added)

build_sft_dataset.py reads episode.jsonl
  -> replays history/progressed from persisted action/url/axtree/last_error
  -> build_solver_prompt(...)   # same function, same output
  -> {"messages": [system=SOLVER_SYS, user=<exact prompt>, assistant=action]}
```

## Testing

- `hsge/tests/test_solver.py`: `Step.hints`/`Step.last_error` populated
  correctly across a normal step, an errored step, and a step with hints
  passed to `solve()`. New test: a `report_infeasible(...)` action ends the
  episode with `success is False` (mirrors the existing
  `send_msg_to_user` termination tests already in this file).
- New test asserting `build_solver_prompt(...)` called directly with a given
  `(history, progressed)` produces byte-identical output to what
  `Solver.solve()` sent to its `LLM.complete_json` for the same step (reuse
  the existing `_FakeBrowser`/fake-LLM pattern already in `test_solver.py`).
- `hsge/tests/test_build_sft.py`: update `_mk()` to pass `hints`/`last_error`
  on the `Step` so existing tests reflect the new contract. Add a test: a
  `Step` without `hints`/`last_error`/`url` set (simulating a pre-change
  episode) is skipped — `kept` (episode-level) stays 1 but `examples == 0`.
  Add a test: a 2-step episode with a genuine mid-episode action error
  produces a second-step prompt containing `LAST ACTION ERROR:` and a
  `history` that excludes the failed action.
- Sanity check that `ACTIONS_DOC` contains `report_infeasible`, `press`,
  `hover` (string-membership, not full-output assertion).

## Out of scope

Keeping `verified`/reward as a per-example data column instead of an
upfront filter; `episode_id`/`step_idx`/`traj_length` for trajectory
reconstruction; the remaining 8 undocumented BrowserGym actions
(`upload_file`, `drag_and_drop` were considered and deferred — no task in
the current site set requires them yet). Re-running `wa_run_04`/`wa_run_05`
to backfill prompt-fidelity fields is a follow-up, not part of this change.
