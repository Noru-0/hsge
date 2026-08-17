# `training_data_continue_v1/` — increment dataset for continue-finetuning checkpoint-536

Built by `scripts/build_continue_finetune_dataset.py` (seed 42, deterministic).
**Not** a from-scratch training set and **not** the full `training_data_v2/`
4-domain merge — this is the increment meant to warm-start from
`checkpoint-536` (`training/qwen35_9b_lora_continue_v1.yaml`).

## Why this scope

`checkpoint-536` was trained only on the four `wa_run_20_*` runs
(`training_data/`, confirmed against `datasets/README.md`). Everything
collected afterward in `wa_run_21_*`/`wa_run_22_*` for **reddit** and
**shopping_admin** is genuinely new — checkpoint-536 never saw it — so
continue-finetuning on it (rather than retraining from base) is a reasonable
incremental update. `shopping` and `gitlab` were not re-collected this round,
so they contribute no new data here.

## Composition

| component | rows (train) | rows (val) | source |
|---|---|---|---|
| increment: reddit (wa_run_21) | 796 | — | `training_data_v2/train_wa_run_21_reddit.jsonl` |
| increment: reddit (wa_run_22) | 1,060 | — | `training_data_v2/train_wa_run_22_reddit.jsonl` |
| increment: shopping_admin (wa_run_21) | 1,333 | — | `training_data_v2/train_wa_run_21_shopping_admin.jsonl` |
| increment: shopping_admin (wa_run_22) | 1,077 | — | `training_data_v2/train_wa_run_22_shopping_admin.jsonl` |
| **increment total** | **4,266** | **187** | `training_data_v2/val.jsonl` filtered to these 4 runs |
| replay: shopping | 380 | 24 | random whole trajectories from `training_data/train.jsonl`/`val.jsonl` (site==shopping) |
| replay: gitlab | 380 | 23 | random whole trajectories from `training_data/train.jsonl`/`val.jsonl` (site==gitlab) |
| **replay total** | **760** | **47** | ~15% of the final set, evenly split |
| **TOTAL** | **5,026** | **234** | `train.jsonl` / `val.jsonl` |

## Why the replay slice

A continue-finetune pass that only sees reddit/shopping_admin examples risks
catastrophic forgetting on shopping/gitlab, which checkpoint-536 already
learned but this increment never exercises. The replay slice (~15%, sampled
by **whole trajectory** — never a partial one — with `random.seed(42)`) is
there purely to preserve those two domains' skills, not to improve them.
**After training, evaluate all four domains, not just reddit/shopping_admin**,
to confirm the replay slice actually held.

## Format

Same schema as `training_data/` and `training_data_v2/`: one JSON object per
step with `messages`, `trajectory_id`, `step_index`, `total_steps`,
`difficulty`, `axtree_loaded`, `site`, `run`. Sorted by `difficulty` ascending
(curriculum convention, stable — a trajectory's own steps stay adjacent).
Replay rows carry `run: "replay_<site>_v20"` to distinguish them from the
increment at a glance.

The LLaMA-Factory-ready, `messages`-only copy (what the training config
actually reads) is staged at `training/data/continue_v1/` (gitignored,
written by the same script below).

## Rebuilding

```bash
python scripts/build_continue_finetune_dataset.py
```
