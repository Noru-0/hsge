# Docs

Deeper references live in `docs/` — `02_architecture.md` (module map + data flow),
`03_running_locally.md` (per-script output), `04_webarena_runbook.md` (hosting
WebArena), `06_training.md` (collect→SFT→fine-tune loop), `09_run_on_webarena.md`
(the standalone runtime — **stale**: predates the skill-derived-operator,
config.yaml, vision/auth work, see `10_webarena_real_wiring_session.md`,
`11_vision_auth_hardening_session.md`, and `12_real_run_bug_fixes_session.md`),
`10_webarena_real_wiring_session.md` (session report: real WebArena wiring,
skill-derived operators, config.yaml/.env split, frontier/prompt fixes),
`11_vision_auth_hardening_session.md` (session report: node content-dedup +
persisted run artifacts/logging, GPT-4o vision + Set-of-Marks, OpenAILLM
retry/backoff, WebArena login/auth with cached sessions, and four real-run
bugs found and fixed — non-string tasks, `None` message content, answer-leaking
`[INFO]` tasks, frontier-stall from task truncation order),
`12_real_run_bug_fixes_session.md` (session report: task-diversity dedup,
structured INFO/NAV/MOD classification replacing the unreliable `[TAG]`
bracket convention, and a two-iteration Solver stuck-loop fix — a same-action
warning proven insufficient by a real run, escalated to a same-target +
observation-progress hard stop),
`13_run02_reddit_exploration_log.md` (exploration log for a real reddit run:
why it stopped at 57/500 nodes — frontier starvation from the documented
"mines navigated URLs, not `<a href>`s" gap, not a bug — plus a quality
assessment of that run's induced operators using the grounding-check feature,
showing half were tautological or ungrounded), `14_vast_ai_training_eval_tutorial.md`
(step-by-step tutorial: LoRA fine-tuning + WebArena eval on rented vast.ai GPUs —
venv-isolation rationale, template/thinking-mode gotchas, official-benchmark
eval via BrowserGym, and a two-machine parallel-eval technique for safely
running a second eval sweep against a shared live WebArena instance while a
first sweep is still in progress),
`15_seed_refinement_improvement_plan.md` (consolidated improvement roadmap from
Explorer + InfiniteWeb: seed-conditioned bottom-up refinement — a top-down,
seed-derived GOAL curriculum that bypasses the edgeless operator graph to attack
open bug O2, plus per-action task refinement and an inline verifier gate;
7-item priority table + 3-phase rollout, planning only),
`16_phaseBC_verification_refinement_plan.md` (Phase B/C roadmap, reprioritized by
the first real seed run `wa_seed_shopping`: verification first — an inline
Verifier gate + auto verify-predicate — because GOAL success was self-graded and
inflated, then solver competence — GOAL step budget, bottom-up refinement,
anti-wandering, grounding-gated operators; planning only),
`17_phaseC_solver_competence_plan.md` (Phase C design, reprioritized by the
second real run `wa_seed_shopping_v2`: with the B1 verifier + goal_max_steps on,
GOAL = 2 verified / 4 infeasible and ALL infeasibles are multi-step
state-changing goals — so the binding constraint is now solver competence;
tasks C2 subgoal-guided GOAL solving, C3 progress-based anti-wandering, C5
stronger GOAL solver, C4 grounding-gated operators; planning only). See also
`training/README.md` for the terse command reference covering the same pipeline.
