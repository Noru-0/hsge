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
- **Status**: open — the synonym-canonicalization fix **implemented +
  unit-tested (2026-07-22)** did NOT resolve the symptom. Two fresh live runs
  (wa_run_13_shopping, wa_run_14_reddit, 77/79 nodes, ~290 episodes each) still
  show **GOAL 0/0/0**. Re-analysis (2026-07-22) shows the root cause is a
  **three-stage loss cascade**, of which synonym-merging is only stage 3 and
  not the binding constraint. Stays open until a run produces non-zero GOAL.
- **Re-diagnosis (2026-07-22, runs 13/14)**: the cascade, measured directly:
  (1) **single-hop tasks** — `EXPLORER_SYS` asks for tasks doable on THIS page,
  so 104/221 (reddit) and 118/230 (shopping) success episodes are literally
  1 action (median 2 steps); atomic tasks → atomic skills.
  (2) **anti-tautology gate kills ~half the skills** — 4/7 (reddit), 3/5
  (shopping) admitted skills are rejected `operator_rejected reason=tautological`
  because an atomic skill's effect is phrased ≈ its precondition
  (`uncheck_checkbox`: pre "a checkbox exists" / eff "the checkbox is checked"
  → `eff-pre=∅`). So only 3/2 operators survive.
  (3) **effect/precondition vocabulary disjunction** — the survivors' effects
  are all page-state ("the wiki page is displayed") while preconditions are all
  element-presence ("a menu toggle is present"); `effects ∩ preconditions = ∅`
  in BOTH runs → 0 edges (operators.py:44 `A→B iff effects(A)&preconds(B)`)
  → `all_chains(min_len=2)` empty → 0 GOAL. Synonym canonicalization can't help
  here because eff/pre are different predicate *types*, not synonyms.
  Note canonicalization DOES work at the precondition level (reddit `p0` reused
  across two operators). Grounding `effect_accuracy` is often 0.5 (shaky
  predicate quality). Chosen fixes: **A** (multi-step task proposals, attacks
  stage 1 & 2) + **B** (align induced preconditions to page-state vocabulary,
  attacks stage 3).
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
- **Fix**: LLM adjudication in the borderline band (2026-07-22, unit-tested;
  see changelog). `PredicateRegistry` now takes an optional `llm` +
  `adjudication_band` (default 0.15): cosine decides the confident tails
  (`>= sim_threshold+band` merge, `< sim_threshold-band` new id) and
  `predicates_equivalent()` settles only the ambiguous middle where a single
  cutoff provably fails. `OnlineClusterer` gained `nearest`/`add_to`/`spawn`
  to let the registry interpose that decision; `partial_fit` composes them
  (unchanged). `runtime.py` wires `operator_llm` in; `llm=None` keeps the old
  deterministic single-threshold path for the mock pipeline. This also repairs
  the upstream vocabulary-aware induction that already existed: once two
  synonyms collapse, the id's count grows, it enters `vocabulary()`'s frequent
  set, and the inducer starts reusing it verbatim (virtuous cycle). **Still
  needs a real-run to confirm goal tasks actually appear** — do not reword the
  three thesis overstatements below until that run succeeds.
- **Thesis impact**: three places currently overstate this — the O2 rows in
  `Chapter1`/`Chapter6` and a sentence in `Chapter5` §5.1 claiming operator
  chaining "executed against a real website". Appendix C.3 already reports the
  0 honestly, so the book is internally inconsistent until either the re-run
  succeeds or those three are reworded. See `Thesis_report/memory/07-dan-y-chi-tiet.md`.

## Fixed

### Real run crashes on GPT-5.x/o-series models that reject a custom temperature
- **Status**: fixed (2026-07-31 23:10)
- **Found**: 2026-07-31, first real run with `solver_goal: gpt-5.6-terra` — `openai.BadRequestError 400: "Unsupported value: 'temperature' does not support 0.0 with this model. Only the default (1) value is supported."` (`run_webarena.py` → `Solver.solve` → `OpenAILLM.complete_json`).
- **Where**: `hsge/backends.py::OpenAILLM.complete_json` / `_create_with_retry` (always sent `temperature`).
- **Symptom**: any GPT-5.x / o-series model 400s when given a non-default temperature (the whole run aborts), because `config.yaml` set `solver_goal.temperature: 0.0`.
- **Cause**: those models only accept the default temperature (1); the backend unconditionally passed the configured value.
- **Fix**: `OpenAILLM` now (a) catches the temperature-specific 400, drops the param, retries, and sets `self._omit_temperature` so later calls skip it (`_is_unsupported_temperature`); and (b) `complete_json` omits `temperature` once flagged. Also set `config.yaml` `solver_goal.temperature: 1` to avoid the first wasted 400. Tests in `hsge/tests/test_backends_temperature.py`.

### C2 subgoal-advance signal is hijacked into send_msg_to_user, ending the episode at subgoal 1
- **Status**: fixed (2026-07-31 19:58, commit 685a93b)
- **Found**: 2026-07-31, run v3 (`outputs/wa_seed_shopping_v3`) GOAL dropped to 0 success / 4 fail / 2 infeasible (v2 was 2/0/4); 3/6 GOAL episodes ended after 2-3 steps.
- **Where**: `hsge/webarena/agents.py::Solver.solve` subgoal-mode advance.
- **Symptom**: gpt-4o-mini emitted the advance as a **terminal** `send_msg_to_user('subgoal_done...')` instead of the JSON field, so `solve` ended the episode after subgoal 1; the B1 verifier correctly FAILed it ("navigated to Electronics but did not add to cart"). The 2 easy nav/read goals that PASSED in v2 were the ones killed.
- **Cause**: the `subgoal_done` JSON field is unreliable with gpt-4o-mini, which conflates "advance subgoal" with the send_msg terminal action.
- **Fix**: a `send_msg_to_user` (or a `subgoal_done` field) on a NON-last subgoal now ADVANCES instead of terminating; only the last subgoal may end the episode. Regression test `test_send_msg_on_nonlast_subgoal_advances_not_terminates`.

### C3 stuck/novelty guards miss same-target churn that only wiggles the axtree
- **Status**: fixed (2026-07-31 19:58, commit 685a93b)
- **Found**: 2026-07-31, run v3: `click('247')` ×9, `click('1790')` ×8 burned ~10-19 steps.
- **Where**: `hsge/webarena/agents.py::Solver.solve` (`progressed` fed to `_stuck_streak`).
- **Symptom**: hammering one control never tripped the same-target stuck guard, because each click wiggled the axtree (dropdown/toggle) and the guard's "progress" = url-OR-axtree change reset the streak.
- **Cause**: keying progress on axtree changes too; a slightly-mutating page defeats it.
- **Fix**: the same-target stuck guard now keys "progress" on **URL change only** — a legit multi-step flow uses different targets (so the same-target guard never groups it) or changes the URL, so this is safe. Regression test `test_stuck_guard_fires_on_same_target_when_url_does_not_change`. (The different-target-no-new-page case is still handled by the exact-obs novelty guard; a slightly-mutating different-target churn remains a minor known gap.)

### Frontier re-explores the same landed page under different URL strings (URL dedup keyed the pre-navigation frontier string, not the page actually loaded)
- **Status**: fixed (2026-07-22 13:59)
- **Found**: 2026-07-22, auditing whether already-explored URLs (esp. root) get re-explored.
- **Where**: `hsge/webarena/runtime.py::run()` — `visited`/`queued` dedup on the
  frontier `url` (pre-navigation mined/reached string) and `_admit_url`, while the
  node is logged and content-compared by `obs["url"]` (the POST-navigation landed
  URL). `_url_template` normalization was used only for the tier-1 per-template cap.
- **Symptom**: the same logical page fully re-explored (new explorer+solver LLM
  batch, not skipped) when reached via a different frontier string. Confirmed on
  run 13: `checkout/cart/#payment` explored **twice** (depths 3 and 4);
  `electronics.html` **18×** / `sports-outdoors.html` **11×** across `?cat=`/`?price=`
  variants. Root was at latent risk (its front page is the most dynamic, so the
  content-hash backstop is least reliable there).
- **Cause**: URL identity for dedup was the pre-navigation frontier key, but many
  distinct keys resolve to the same page after navigation (`#fragment`,
  trailing-slash/case, redirects, login redirects). The only backstop was
  `seen_content` (sha256 of the initial axtree), which fails whenever the page
  content differs even slightly between visits (dynamic content). Two compounding
  gaps: (a) no normalization of the dedup key; (b) no dedup on the actual landed
  `obs["url"]`, so a redirect/alias to an already-visited page slipped through
  whenever the content-hash also differed.
- **Fix**: added `WebArenaExplorer._norm_url` (strips `#fragment`, lowercases
  scheme+host, drops a non-root trailing `/`, KEEPS the query since `?cat=1`≠`?cat=2`)
  and keyed `visited`/`queued`/`_admit_url` by it (part 1). Added a `visited_landed`
  set of normalized POST-navigation urls, checked alongside the content-hash in the
  duplicate-skip block, so a redirect/alias to an already-loaded page is skipped even
  when its content changed (part 2). `visited_landed` is checkpointed/restored (kept
  out of `_LOOP_KEYS`; `load_checkpoint` defaults it via `.get` for back-compat with
  older checkpoints). Regression tests in `hsge/tests/test_frontier_mining.py`:
  `_norm_url` canonicalization, `_admit_url` rejecting a fragment/slash variant of a
  visited url, and an end-to-end redirect browser proving the second route to a
  canonical page is skipped (RED before the fix). Full suite 157 -> 160 passed.
  **Not fixed (separate design question):** query-string / tier-0 proliferation
  (`electronics.html`×18) — different `?cat=` pages are genuinely different content,
  so whether to cap them is a coverage-vs-cost decision left open.

### Windows run crashes writing an axtree with non-cp1252 characters (UnicodeEncodeError)
- **Status**: fixed (2026-07-22 09:10)
- **Found**: 2026-07-22, a real run on a Windows machine (`D:\...\hsge`,
  conda env, cp1252 locale) crashed at node 3 with
  `UnicodeEncodeError: 'charmap' codec can't encode character '↓'`
  (a `↓` down-arrow in the page's accessibility tree).
- **Where**: `hsge/webarena/runtime.py::_record` line ~213 (the axtree
  `page_state/step_*.txt` write) plus every other text-mode `open()` in the
  pipeline (episode/artifact writes in `runtime.py`, and the readers in
  `build_sft_dataset.py` / `judge_episodes.py` / `reannotate_thoughts.py` /
  `replay_segmentation.py`, plus `browser.py` headers and `run_webarena.py`
  config load).
- **Symptom**: on Windows the run dies mid-node when any visited page's axtree
  contains a character outside cp1252 (arrows, bullets, box-drawing, emoji —
  all common in real sites). Invisible on macOS/Linux, whose default text
  encoding is UTF-8.
- **Cause**: `open(path, "w")` / `open(path)` in text mode with no `encoding=`
  uses the platform default codec, which is cp1252 on a typical Windows
  install. The axtree files hold **raw** page text (not JSON-escaped), so a
  non-cp1252 glyph is unencodable. The `json.dump` artifact files did *not*
  crash (default `ensure_ascii=True` escapes non-ASCII to `\uXXXX`), but their
  reads would still mis-decode on Windows, so those were hardened too.
- **Fix**: added `encoding="utf-8"` to every text-mode `open()` across the
  runtime and the four SFT-pipeline scripts (writes and reads), so files are
  always UTF-8 regardless of platform locale. Regression test
  `hsge/tests/test_encoding.py::test_record_writes_axtree_with_non_cp1252_chars`
  patches `builtins.open` to simulate the Windows cp1252 default and asserts
  `_record` writes a `↓`-containing axtree without crashing (RED cross-platform
  before the fix). Full suite 152 passed.

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
