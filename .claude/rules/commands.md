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
