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

### `goal_task_selected` logs an empty `goal`
- **Status**: open
- **Found**: 2026-08-08, same audit — all 16 `goal_task_selected` events in
  `run_log.jsonl` carry `"goal": ""`.
- **Where**: `hsge/webarena/runtime.py`, `goal_task_selected` event emission.
- **Symptom**: GOAL selection cannot be traced from the log alone; the goal has to
  be recovered by joining against `episodes/*/episode_meta.json`.
- **Fix**: not yet applied.

### Predicate canonicalization never unifies synonyms, so the operator graph stays edgeless and no semantic task is ever generated
- **Status**: open, but **downgraded 2026-08-08 — the symptom is no longer zero.**
  `outputs/wa_eval_reddit` (158 nodes, 887 episodes) induced 4 operators whose
  predicate sets finally intersect: `p5 "a post listing page is shown"` is an
  effect of `attempt_to_find_comment_` AND a precondition of
  `apply_featured_filter` -> **1 edge**, 1 depth-chain, and GOAL
  **2 success / 4 fail / 1 infeasible** (first non-zero GOAL on a live site).
  The three thesis overstatements can now be reworded against real evidence,
  though "1 edge out of 4 operators" is still weak and 3/7 skills were rejected
  as tautological. Grounding stays shaky: `effect_confirmed` was 0.0 for
  `navigate_to_wiki`, 0.5 for two others, 1.0 for only one.
  Earlier status: the synonym-canonicalization fix **implemented +
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

### `infeasible` conflates "impossible" with "out of steps", and a state-changing task can succeed without changing anything
- **Status**: fixed (2026-08-08 17:09)
- **Found**: 2026-08-08, auditing `outputs/wa_eval_shopping_admin` (222 episodes).
  27 of 56 infeasible episodes have `step_count` exactly at the budget (16);
  `[MOD] Send an email confirmation for order #000000299` is a one-step success
  whose only action is `send_msg_to_user('done: The order confirmation email was
  already sent.')`.
- **Where**: `hsge/webarena/agents.py::Solver.solve` (wrap-up block + the
  non-predicate success rule), `hsge/webarena/runtime.py::_record`,
  `build_sft_dataset.py::_include_episode`.
- **Symptom**: (a) the wrap-up call fires *because* a guard or the budget stopped
  the episode and is told so; whatever it then declares is a rationalization, not
  a conclusion. Those `report_infeasible` episodes were kept as SFT targets,
  teaching the model to give up. (b) a MOD/COMPOSITE task the model declared done
  counted as a success even when no action ever touched the page.
- **Cause**: `stop_reason` was computed (2026-08-08 04:31) only to make the
  wrap-up *prompt* honest; it was never returned or persisted, so no consumer
  could tell a wrap-up verdict from a self-decided one. And the non-predicate
  success rule was purely "the last action is send_msg_to_user", with no evidence
  requirement for tasks whose whole point is to change the site.
- **Fix**: `Solver.solve` returns a 7th value `stop_reason` (`""` = self-decided,
  else `budget`/`stuck`/`novelty`); `_record` writes `outcome.stop_reason`;
  `_include_episode` accepts an infeasible episode only when it is empty
  (pre-existing episodes lack the key and default to self-decided, since nothing
  can distinguish them retroactively). A `[MOD]`/`[COMPOSITE]` goal additionally
  requires one executed action that changed url or axtree. Measured on the real
  run the second gate demotes 1 of 33 MOD/COMPOSITE successes -- the rest of the
  inflation came from failing actions that silently no-op'd, which the
  `ActionError` fix above addresses instead. Tests:
  `hsge/tests/test_honest_outcomes.py`. Suite 241 -> 249.

### `WebArenaBrowser.act` never sees a failed action — BrowserGym swallows it into `last_action_error`
- **Status**: fixed (2026-08-08 17:12)
- **Found**: 2026-08-08, auditing `outputs/wa_eval_shopping_admin` (222 episodes).
  **Zero** episodes out of 222 contain the `[action error:` marker, even though
  70/1683 steps (4.2%) call `fill()`/`click()` with a field *label* instead of a
  bid (`fill('[global] Price * $', '19.99')`, `fill('[store view] Product Name *',
  ...)`, `fill('123 New Street', '789 New Ave')`).
- **Where**: `hsge/webarena/browser.py::WebArenaBrowser.act` (line ~104);
  consumers `hsge/webarena/agents.py:569-572` (`except Exception` /
  `last_error`) and `build_sft_dataset.py` (its `[action error:` filter).
- **Symptom**: an action that fails in the browser is reported to the Solver as a
  normal successful step. The Solver's error-recovery feedback
  (`LAST ACTION ERROR: ...` in the prompt) is dead code — `last_error` is always
  `""`. `build_sft_dataset.py`'s `[action error:` exclusion never fires, so
  **failed actions are exported as correct SFT targets**. 18/222 episodes contain
  at least one invalid bid and 6 of those are marked `success`.
- **Cause**: `browsergym.core.env.BrowserEnv.step` catches the action exception
  itself (`self.last_action_error = f"{type(e).__name__}: {e}"`, env.py:405-407)
  and returns it as the `last_action_error` observation key. It never raises, so
  HSGE's `try/except Exception` around `browser.act()` can never trigger.
- **Fix**: `hsge/webarena/browser.py` — new `ActionError`; `act()` reads
  `obs["last_action_error"]` and raises it (after updating `_last_obs`/
  `terminated`, so a caller that catches stays consistent). `Solver`'s existing
  `except Exception` now fires, so `last_error` populates the `LAST ACTION ERROR`
  prompt block and `[action error:` lands in `obs_summary` as designed. Tests:
  `hsge/tests/test_action_error_and_thought_fidelity.py`.

### Persisted `thought` is truncated at 100 characters, mid-word
- **Status**: fixed (2026-08-08 17:12)
- **Found**: 2026-08-08, same audit — 694/1683 steps (41.2%) have a `thought`
  sitting exactly at the 100-char ceiling, cut mid-word ("...as indicated by the
  message on th").
- **Where**: `hsge/webarena/agents.py:557` (`Step(..., obs_summary=thought[:100])`),
  persisted by `hsge/webarena/runtime.py:301-302` as both `action.thought` and
  the top-level `thought` field.
- **Symptom**: `thought` is the SFT training target's reasoning; 41% of examples
  train the model to emit a sentence that stops mid-word. Also degrades
  `reannotate_thoughts.py`'s input and segmentation's `obs_summary` signal.
- **Cause**: `obs_summary` was originally a short display summary; it later became
  the persisted training target without the truncation being revisited.
- **Fix**: `hsge/webarena/agents.py` — `Step(..., obs_summary=thought)` (both the
  main loop and the wrap-up step). The 100-char cap moved to the only consumer
  that needs it, `hsge/segmentation.py:99` (`st.obs_summary[:100]`), so that
  prompt's size is unchanged.

### `outcome.response` is always empty — INFO answers are never captured
- **Status**: fixed (2026-08-08 17:12)
- **Found**: 2026-08-08, same audit — 0/222 episodes have a non-empty
  `outcome.response`, although 44 successes are single-step
  `send_msg_to_user('done: Lifetime Sales value is $194.40')`.
- **Where**: `hsge/webarena/runtime.py` episode-meta assembly.
- **Symptom**: the answer text an INFO task produced only exists inside the raw
  `parsed_action` string. `judge_episodes.py` cannot check the answer against the
  page without re-parsing, and no eval can score INFO correctness.
- **Fix**: new `hsge/webarena/agents.py::terminal_message(action)` (ast-parses the
  argument of a terminal `send_msg_to_user`/`report_infeasible`, `""` otherwise);
  `runtime.py::_record` fills `outcome.response` from the last step. Derived at
  the record site rather than threaded through `Solver.solve`'s return tuple, so
  every call site benefits.

### Wrap-up prompt claims "action budget is exhausted" after a guard stop, so report_infeasible records a false reason
- **Status**: fixed (2026-08-08 04:31)
- **Found**: 2026-08-08, evaluating `outputs/wa_eval_shopping_admin` — episodes that ran only 5-6 steps recorded `report_infeasible('action budget exhausted, cannot uncheck the checkbox')` while `max_steps=15` and `goal_max_steps=25`.
- **Where**: `hsge/webarena/agents.py::Solver.solve` wrap-up prompt.
- **Symptom**: the recorded infeasible reason is wrong whenever the same-target stuck guard (`_MAX_REPEATS`) or the novelty guard (`_NOVELTY_MAX`) ended the episode — which is most short infeasible episodes. Pollutes failure analysis (can't separate "ran out of steps" from "got stuck") AND the SFT data, since infeasible episodes are kept as training targets: the model is taught to plead budget exhaustion when that is not what happened.
- **Cause**: the prompt hardcoded one sentence for every exit path; the model faithfully repeats whatever the prompt asserts.
- **Fix**: `stop_reason` (`budget`/`stuck`/`novelty`) is tracked at each exit and rendered from `Solver._STOP_REASONS`; the prompt also now asks for "the REAL obstacle, not the fact that you stopped". Tests in `test_stop_reason_and_capability_retire.py`.

### Seed capabilities are retried up to the repeat cap even when every attempt fails
- **Status**: fixed (2026-08-08 04:31)
- **Found**: 2026-08-08, same run — "Review recent orders and update the status of an order to 'Shipped'" ran 3 times (ep_0009/0015/0026), all infeasible, consuming 3 of the run's GOAL slots.
- **Where**: `hsge/webarena/runtime.py::_goal_task` — introduced by the 2026-08-08 03:08 `seed_capability_repeats` fix.
- **Symptom**: a capability beyond the solver's ability spends its whole repeat budget on identical failures.
- **Cause**: `_capability_attempts` counted attempts but never looked at outcomes.
- **Fix**: `_capability_failures` retires a capability after `_CAPABILITY_MAX_FAILS = 2` *consecutive* failures (a success resets it). Seed tasks now carry their `capability` name so the GOAL result loop can score them; the counter is checkpointed for `--resume`.

### Five data-quality defects found by auditing the wa_eval_reddit run (frontier flooding, GOAL starvation, INFO flood, unrunnable SkillCards, vacuous `verified`)
- **Status**: fixed (2026-08-08 03:08) — all five; each has a regression test in `hsge/tests/test_run_quality_fixes.py`.
- **Found**: 2026-08-08, auditing `outputs/wa_eval_reddit` (158 nodes, 887 episodes) before building an SFT dataset from it.
- **Where**: `hsge/webarena/runtime.py` (frontier pop-time cap, `_goal_task`), `hsge/webarena/agents.py::PageExplorer` (tag caps), `hsge/abstraction.py::_SYS`, `hsge/verification.py::verify_skill`, `build_sft_dataset.py`.
- **Symptoms, measured**:
  1. **Frontier flooding** — 58/158 nodes were `/f/AskReddit/*/*/*/*`; two forums accounted for 47% of the whole run, despite `per_template_cap: 3`.
  2. **GOAL starvation** — 7 GOAL tasks total (6 seed + 1 depth chain) across 158 nodes, none after node ~3.
  3. **INFO flood** — INFO was 272/560 (49%) of successful episodes, and 237 of those had ZERO browser actions (only `send_msg_to_user`). 44% of all successes were answer-only; 60% had <= 1 real action.
  4. **Unrunnable SkillCards** — `click({sel})` (unquoted), `fill('{{text}}', '')` (arguments swapped), `press('{{btn}}')` (one arg where two are needed), CSS-selector slot examples (`#notification-bell`) for a bid-only action space.
  5. **Vacuous `verified`** — every skill in `skills.json` was `"verified": true` next to `"n_verify_attempts": 0`.
- **Causes**: (1) the cap was written `if tier == 1 and ...`, exempting tier-0 — which is also the highest-priority tier, so solving one task inside a thread pushed every comment URL it touched ahead of the entire frontier. (2) `_attempted_capabilities` was a set of bare capability names, blocking a capability for the rest of the run after one attempt. (3) `_INFO_RESERVE` only bounds INFO inside the `len(parsed) > max_tasks` overflow branch, so a page proposing <= max_tasks tasks was never truncated at all. (4) the abstraction prompt passed only bare action verbs and never described the action space. (5) `successes >= k` is vacuously true at `k=0`, which is what the WebArena runtime passes (it verifies by terminal episode outcome instead).
- **Fixes**: (1) `reached_template_cap` (default 8) applied to tier 0 by the same lazy pop-time check — still looser than the mined cap, since reaching a page while solving is evidence it matters. (2) capabilities keyed `(name, url_template)` plus a `seed_capability_repeats` global cap (default 3). (3) unconditional `_INFO_CAP = 2`, mirroring the existing `_NAV_CAP`. (4) `_SYS` documents each action's exact arity and that elements are addressed by BID, never CSS/XPath; payload gained `example_actions` (members' literal action strings). (5) admission decision unchanged, but `.verified` now additionally requires `n_verify_attempts > 0`. Also `build_sft_dataset.py --min-actions N` (default 0, old behavior) to drop answer-only episodes.
- **Note**: `--min-actions 1` on the real reddit data drops 249 episodes (34%) but only 6.6% of examples (3767 -> 3518) — the dropped episodes were one step each, so the trade is heavily favourable.
- **Related, still open**: an LLM exception during a task still kills the whole run (see the API-timeout entry below).

### Every GOAL task stalls ~12 minutes then can kill the run (60s API timeout x the SDK's hidden retries, vs a reasoning goal-solver)
- **Status**: fixed (2026-08-07 17:22)
- **Found**: 2026-08-07, first 4-domain eval collection run — `outputs/wa_eval_shopping` produced 3 LOCAL episodes then froze with no file activity for 13 min, printing only `[OpenAILLM] retry 1/3` and `2/3 after APITimeoutError`. The reddit run in parallel was fine (13 episodes, 0 retries) — it had not reached a GOAL task yet.
- **Where**: `hsge/backends.py::OpenAILLM.__init__` (`_REQUEST_TIMEOUT_S`, missing `max_retries`).
- **Symptom**: the first GOAL task of a run hangs ~12 min, then raises `APITimeoutError`. That exception is not caught per-task (only browser errors get `node_error` + skip), so it propagates to the whole-loop handler, writes `run_error`, and re-raises — killing a long unattended run.
- **Cause**: `_REQUEST_TIMEOUT_S = 60.0` is below what `solver_goal: gpt-5.6-terra` needs — a non-streaming reasoning call over a 6000-char axtree + screenshot routinely takes longer. Compounding it, `OpenAI()` was constructed without `max_retries`, so the SDK's default 2 internal retries tripled each of `_create_with_retry`'s 4 attempts: 4 x 3 x 60s ~ 12 min of silent blocking. `sample <pid>` confirmed the stack (`_ssl__SSLSocket_read -> PySSL_select -> poll`), and `/v1/models` confirmed `gpt-5.6-terra` is present on the account — slowness, not a bad model id.
- **Fix**: `_REQUEST_TIMEOUT_S` 60 -> 180s, and `max_retries=0` on the client so this class's own logged, transient-only backoff loop is the single retry policy (worst case 4 x 180s, and every wait is now logged instead of hidden inside the SDK).
- **Note (still open, separate)**: an LLM exception during a task still kills the whole run rather than failing just that task. `--resume` recovers, but a per-task guard like the existing `node_error` one would be more robust for long unattended runs.

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
