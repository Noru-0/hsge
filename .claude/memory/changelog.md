# Changelog

Every finished, verified change gets one entry. Newest first.
Entry format: `- **HH:MM** — \`file(s)\` — what changed (and why, if not obvious).`
Get the timestamp with `date "+%Y-%m-%d %H:%M"` — never guess it.

## 2026-07-14

- **00:39** — `.claude/memory/changelog.md`, `.claude/memory/bugs.md`, `.claude/rules/memory.md`, `.claude/CLAUDE.md` — Added the project-memory system: a timestamped changelog and a bug log under `.claude/memory/`, a rule requiring Claude Code to read both at session start and update them after every finished change, and a link to that rule from CLAUDE.md.
- **00:34** — `README.md` — Rewrote stale README: added "Real WebArena run" section (config.yaml/.env split, per-role LLMs + vision, two-tier frontier with href mining, cached login/auth, per-node artifact persistence), added docs 10–13 to the docs table, marked `09_run_on_webarena.md` stale, clarified mock-vs-real in intro/Quickstart. Commit `3fd47bb`.
