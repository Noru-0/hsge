# Commands

Activate the project's conda environment before running anything:

```bash
conda activate go-browse
```

```bash
pip install numpy                              # only hard dependency for the mock pipeline

# Demos / pipeline (all mock, no keys):
python explore.py                              # exploration loop: frontier → discover → compose → verify
python demo.py                                 # discover → cluster → abstract → verify → transfer
python demo_shopping.py                        # end-to-end purchase: plan → execute → terminal-verify
python demo_purchase.py                        # planning + curriculum only
python compare_three_way.py                    # Flat vs AWM vs HSGE on identical input
python compare.py                              # pairwise baseline comparison

# Tests (no pytest required for the standalone form):
PYTHONPATH=. python hsge/tests/test_clustering.py
python -m pytest hsge/tests/ -q                # requires pytest

# WebArena runtime:
python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2   # scripted LLM + fake browser, exercises full wiring
python build_sft_dataset.py <episodes_dir> train.jsonl            # trajectories → curriculum-ordered SFT jsonl
```

Most scripts take no CLI args and just run their scenario; `run_webarena.py` and
`build_sft_dataset.py` are the exceptions (argparse / positional args).

## Real WebArena run

Secrets (API keys, account passwords, `WA_*` site URLs) live in a git-ignored `.env`;
non-secret run params (site, max_nodes/steps/tasks, maturity, LLM provider/model, ...)
live in the committed `config.yaml`. Precedence is **CLI flag > config.yaml > built-in
default**.

```bash
python run_webarena.py                              # everything from config.yaml + .env
python run_webarena.py --site shopping --max-nodes 5 --headed
python run_webarena.py --provider deepseek --model deepseek-chat
python run_webarena.py --max-tasks 8                 # more tasks proposed per node
python run_webarena.py --read-only --max-nodes 2 --max-steps 4   # smoke-test a shared
                                                                   # site without writes
python run_webarena.py --phase all                   # explore + generate/collect in one run
python run_webarena.py --phase generate --out outputs/wa_run_02   # phase 2 on an existing run
python build_sft_dataset.py outputs/wa_run_02 train.jsonl          # verified GEN episodes only
python build_sft_dataset.py outputs/wa_run_02 train.jsonl --include-local
```

`--read-only` is the safe way to smoke-test against a real, shared WebArena instance
(e.g. reddit) — it restricts task proposals to `[INFO]`/`[NAV]`, never `[MOD]`.

**Login**: for the four account-gated sites (reddit/gitlab/shopping/shopping_admin),
`run_webarena.py` logs in once and caches the session under `.auth/<site>_state.json`
(git-ignored — it's a live session credential). Optional `.env` overrides if your
instance's seed accounts differ from the standard benchmark ones:
`WA_<SITE>_USERNAME` / `WA_<SITE>_PASSWORD` (e.g. `WA_REDDIT_USERNAME`).

**Vision** (`page_explorer`/`solver` attaching a screenshot, optionally
Set-of-Marks-annotated, to a vision-capable model) is configured per role in
`config.yaml`'s `llm.agents.<role>` alongside `model`: `vision: true`, `som: true`,
`image_detail: low|high|auto`. Off by default; `config.yaml` turns it on for
`page_explorer` (`gpt-4o`) and `solver` (`gpt-4o-mini`) — this needs a real
`OPENAI_API_KEY` and will incur real API cost.
