# 03 — Running Locally

All scripts use deterministic mock backends — no keys, GPU, or browser. Run them
from the project root (the directory containing `hsge/`).

```bash
pip install numpy
```

## Exploration loop

```bash
python explore.py
```
Phase 1 expands a frontier over a mock store, discovering a skill at each page
transition and building the high-level edges. Phase 2 proposes a goal-conditioned
composed task, executes the full chain, and verifies it at the order-confirmation
page (reward 1.0 → kept for training). Mirrors a real loop: Phase 1 ≈
PageExplorer + `Discovery.on_trajectory`, Phase 2 ≈ GoalTaskProposer + Solver +
TerminalStateEvaluator.

## Shopping domain, end-to-end

```bash
python demo_shopping.py
```
Builds a mock store, derives the skill graph, plans a purchase, executes it
page-by-page, and prints the terminal verification + the easy→hard curriculum.

## Discovery + transfer (login/search domain)

```bash
python demo.py
```
Streams trajectories from three mock sites, discovers and verifies two skills,
builds the hierarchical graph, and transfers them to a held-out site.

## Planning / curriculum only

```bash
python demo_purchase.py
```
Shows the operator/precondition model forcing the purchase chain, with no execution.

## Baseline comparisons

```bash
python compare.py            # Flat baseline vs HSGE
python compare_three_way.py  # Flat baseline vs AWM vs HSGE
```

## Build a training dataset

```bash
# Go-Browse style: JSON output + narrative thought
python build_sft_dataset.py path/to/run_dir_or_episode.json train.jsonl \
  --action-format webarena_json

# Multi-turn: one sample per trajectory
python build_sft_dataset.py path/to/run_dir_or_episode.json train.jsonl \
  --action-format webarena_json --multiturn
```
Converts successful trajectories into curriculum-ordered chat-format SFT examples.

## Tests

```bash
PYTHONPATH=. python hsge/tests/test_clustering.py
```

## Troubleshooting

- `ModuleNotFoundError: No module named 'hsge'` → you're inside the package folder.
  Run from its parent (the directory that *contains* `hsge/`), or use
  `PYTHONPATH=. python <script>.py`.
