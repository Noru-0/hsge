# Conventions

- The public API is re-exported from `hsge/__init__.py`; prefer importing from
  `hsge` (e.g. `from hsge import Discovery, SkillLibrary`) over deep module paths.
- The mock pipeline is deterministic — tests and demos assert exact skill counts and
  composition edges (see `hsge/tests/test_clustering.py`). Keep it that way.
- `requirements.txt` lists real-backend deps (sentence-transformers, anthropic/openai,
  browsergym) as opt-in; they are commented as "swap-in" and not needed for mock runs.
- Auto-commit (local only, no push) when a task/feature is finished and verified —
  no need to ask before each commit. A "finished" unit is a coherent change
  (bug fix, feature, doc/rule update, etc.) that's been checked, not a
  mid-task/partial edit. Never push without explicit request each time.
