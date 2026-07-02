# Conventions

- The public API is re-exported from `hsge/__init__.py`; prefer importing from
  `hsge` (e.g. `from hsge import Discovery, SkillLibrary`) over deep module paths.
- The mock pipeline is deterministic — tests and demos assert exact skill counts and
  composition edges (see `hsge/tests/test_clustering.py`). Keep it that way.
- `requirements.txt` lists real-backend deps (sentence-transformers, openai, browsergym,
  pyyaml, python-dotenv, requests) under a "swap-in" section; only `numpy` is required
  for the mock pipeline.
- Secrets (API keys, account passwords, `WA_*` site URLs) go in a git-ignored `.env`,
  never in `config.yaml` or committed files. Non-secret run parameters (site,
  max_nodes/steps, maturity, LLM provider/model, ...) go in the committed
  `config.yaml`. CLI flags override `config.yaml`, which overrides built-in defaults.
- Auto-commit (local only, no push) when a task/feature is finished and verified —
  no need to ask before each commit. A "finished" unit is a coherent change
  (bug fix, feature, doc/rule update, etc.) that's been checked, not a
  mid-task/partial edit. Never push without explicit request each time.
- All code and documentation (comments, docstrings, commit messages, docs/*.md,
  README, etc.) must be written in English.
