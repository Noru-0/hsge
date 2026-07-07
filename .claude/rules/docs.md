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
showing half were tautological or ungrounded), `14_semantic_trajectory_two_phase_session.md`
(session report: the two-phase explore→compose pipeline that fixes `wa_run_02`'s
short, self-reported-success episodes — `NodeDigester`/`SiteKB` with code-side
evidence grounding, `TaskComposer` generating WebArena-style tasks with eval
specs, `GenerationRunner` verifying and gating what enters the SFT dataset —
plus what's still unverified against a real WebArena instance and suggested
next steps).
