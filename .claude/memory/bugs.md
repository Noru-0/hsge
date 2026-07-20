# Bugs

Known bugs found in this project — open ones at the top, fixed ones below.
Entry format:

```
### <short title>
- **Status**: open | fixed (YYYY-MM-DD HH:MM)
- **Found**: YYYY-MM-DD, where/how it was noticed
- **Where**: file(s):line(s)
- **Symptom**: what goes wrong
- **Cause**: root cause (once known)
- **Fix**: what was changed (commit hash if committed)
```

## Open

### Predicate canonicalization never unifies synonyms, so the operator graph stays edgeless and no semantic task is ever generated
- **Status**: open
- **Found**: 2026-07-20, while gathering Appendix C statistics for the thesis.
  Verified directly against `outputs/`: **0 of 1745 episodes** across all 12
  runs carry a `GOAL` tag, every `summary.json` shows
  `GOAL: {success: 0, fail: 0}`, and all 370 examples in
  `training/train_12.jsonl` come from low-level tasks.
- **Where**: `hsge/predicate_registry.py` + `run.predicate_sim` (0.6) in
  `config.yaml`; downstream effect in `hsge/operators.py::OperatorGraph.all_chains`
  and `hsge/webarena/runtime.py::_goal_tasks()`.
- **Symptom**: the operator graph is effectively edgeless, so
  `all_chains(min_len=2)` returns nothing and no composed GOAL task is ever
  attempted on a live site. The largest run (`wa_run_07`, 128 nodes, 13
  operators) has **exactly one** effect→precondition edge, and it only formed
  when the 13th and last operator was induced, after the run had been stopped.
- **Cause**: not a coding defect — embedding-only canonicalization cannot
  separate synonyms from near-neighbours at any single threshold. Measured on
  `wa_run_09`: a true synonym pair scored 0.570 while a false pair scored
  0.606, straddling the 0.6 threshold from both sides. Each operator therefore
  gets a private predicate vocabulary and nothing chains. The mechanism itself
  is implemented and passes the deterministic mock tests
  (`test_operators.py`, `test_goal_task.py`).
- **Fix**: not started. Must be fixed **before** the planned re-run, otherwise
  the new run reproduces the same 0-goal-task outcome. Vocabulary-aware
  induction (reusing the registry's existing labels verbatim at authoring
  time) already exists and is the lever to lean on; consider also an LLM
  adjudication step for borderline cosine scores instead of a hard threshold.
- **Thesis impact**: three places currently overstate this — the O2 rows in
  `Chapter1`/`Chapter6` and a sentence in `Chapter5` §5.1 claiming operator
  chaining "executed against a real website". Appendix C.3 already reports the
  0 honestly, so the book is internally inconsistent until either the re-run
  succeeds or those three are reworded. See `Thesis_report/memory/07-dan-y-chi-tiet.md`.

## Fixed

### A single flaky/slow frontier URL crashes the whole exploration run
- **Status**: fixed (2026-07-14 18:41)
- **Found**: 2026-07-14, real gitlab exploration run — a mined `.../tree/main`
  page exceeded Playwright's navigation timeout (`Page.goto: Timeout 10000ms
  exceeded`), and the entire multi-hour run terminated with an uncaught
  traceback instead of skipping that one node.
- **Where**: `hsge/webarena/runtime.py::WebArenaExplorer.run()` — the
  per-node `browser = self.browser_factory(url); obs = browser.reset()`
  call had no exception handling of its own; only the whole-loop `try/except`
  around the entire `while` existed, which logs the failure as `run_error`
  and then **re-raises**.
- **Symptom**: any single URL whose browser construction or navigation
  raised (timeout, unreachable, browser-launch failure, ...) killed the
  entire run, discarding the rest of the frontier even though the run had
  already discovered nodes/skills worth continuing past.
- **Cause**: no node-level exception boundary around browser creation/reset,
  unlike every other node-processing step (duplicate-content skip, action
  errors inside `Solver.solve`) which already degrade gracefully instead of
  crashing.
- **Fix**: wrapped `browser_factory(url)` + `browser.reset()` in a
  try/except that logs a new `node_error` event, appends a `nodes_log`
  entry (`nodes.json`, `"error": <message>`), best-effort closes the
  partially-constructed browser, increments a `node_errors` counter
  (subtracted from `nodes_visited` everywhere it's reported, including the
  final print line and `summary.json`), and `continue`s to the next
  frontier item instead of propagating. The whole-loop `try/except` still
  exists and still re-raises for genuinely unexpected exceptions elsewhere
  in node processing (e.g. a bug in Discovery/skill promotion) — only
  browser-load failures are now treated as recoverable per-node events.
  Regression tests: `hsge/tests/test_node_error_resilience.py` (reset()
  failure and browser-construction failure, both mid-run and not crashing
  the loop, `summary.json` status stays `"done"`). Updated
  `hsge/tests/test_run_timing.py::test_run_logs_run_error_and_reraises`
  to inject its failure via the LLM call (`PageExplorer.propose()`) instead
  of `browser_factory`, since the latter is no longer an unhandled-exception
  path — the test's "still crashes on a genuinely unexpected exception"
  contract is unchanged, only its trigger point moved.

### Same crash, second call site: `_solve_with_retries` also calls unguarded `browser.reset()`
- **Status**: fixed (2026-07-14 18:50)
- **Found**: 2026-07-14, real gitlab exploration run, same session as the bug
  above -- the previous fix only guarded `run()`'s node-visit `reset()` (the
  *first* reset when a node is entered); `_solve_with_retries` calls
  `browser.reset()` again before *every task* at that node (to return to a
  clean page), and that second call site was still unguarded.
- **Where**: `hsge/webarena/runtime.py::WebArenaExplorer._solve_with_retries`
  (line ~156).
- **Symptom**: identical crash (`playwright._impl._errors.TimeoutError:
  Page.goto: Timeout 10000ms exceeded`), this time thrown from inside
  `_solve_with_retries` after the node's own initial page load had already
  succeeded -- a second/later navigation between tasks at the same node
  still took down the whole run.
- **Cause:** audited every `WebArenaBrowser` method call in `runtime.py`
  (`close`/`screenshot_b64`/`links`/`page_hrefs` are all already
  internally fail-soft in `browser.py` -- they catch and return a safe
  default) and found `reset()` is the *only* method with no internal
  exception handling of its own, since a real network/timeout failure
  there has no safe default observation to fall back to. It had two call
  sites in `runtime.py`; only one was guarded by the previous fix.
- **Fix**: wrapped `_solve_with_retries`'s `browser.reset()` in the same
  try/except pattern: on failure, logs `task_reset_error`, treats it like
  a solve failure (bounded by `task_retries`, no bogus 0-step episode
  recorded since `self.solver.solve()` never even ran), and returns a
  clean `(None, [], {}, False, False, attempts, urls_seen)` once retries
  are exhausted instead of propagating. Regression tests added to
  `hsge/tests/test_task_retries.py`: reset failing every attempt (bounded,
  no episode recorded, solver never called) and reset recovering after one
  failure (task completes normally once the browser comes back). Full
  suite: 113 passed.

_(Bugs fixed before this log existed are documented in `docs/11_vision_auth_hardening_session.md`, `docs/12_real_run_bug_fixes_session.md`, and `docs/13_run02_reddit_exploration_log.md`.)_
