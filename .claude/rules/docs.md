# Docs

Deeper references live in `docs/` — `02_architecture.md` (module map + data flow),
`03_running_locally.md` (per-script output), `04_webarena_runbook.md` (hosting
WebArena), `06_training.md` (collect→SFT→fine-tune loop), `09_run_on_webarena.md`
(the standalone runtime — **stale**: predates the skill-derived-operator,
config.yaml, vision/auth work, see `10_webarena_real_wiring_session.md` and
`11_vision_auth_hardening_session.md`),
`10_webarena_real_wiring_session.md` (session report: real WebArena wiring,
skill-derived operators, config.yaml/.env split, frontier/prompt fixes),
`11_vision_auth_hardening_session.md` (session report: node content-dedup +
persisted run artifacts/logging, GPT-4o vision + Set-of-Marks, OpenAILLM
retry/backoff, WebArena login/auth with cached sessions, and four real-run
bugs found and fixed — non-string tasks, `None` message content, answer-leaking
`[INFO]` tasks, frontier-stall from task truncation order).
