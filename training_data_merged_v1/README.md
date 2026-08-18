# `training_data_merged_v1/` — full dataset: training_data/ + the reddit/shopping_admin increment

Built by `scripts/build_merged_dataset.py` (deterministic, no sampling). This is
`training_data/` (what `checkpoint-536` was trained on) **plus**
`training_data_continue_v1/`'s increment (reddit + shopping_admin from
`wa_run_21`/`wa_run_22`), **with the increment's replay rows excluded** — those
rows are resampled directly from `training_data/` itself (verified: every
replay `trajectory_id` is an exact match, 191/191 train + 9/9 val), so keeping
them here would double-count those trajectories.

Neither source directory is modified by this build — `training_data/` and
`training_data_continue_v1/` are read-only inputs.

## Composition

| component | train | val |
|---|---|---|
| `training_data/` (all 4 domains, `wa_run_20_*`) | 4,288 | 266 |
| increment (reddit + shopping_admin, `wa_run_21`/`22`, replay excluded) | 4,266 | 187 |
| **TOTAL** | **8,554** | **453** |

| site | train (old + new = total) | val (old + new = total) |
|---|---|---|
| reddit | 1,279 + 1,856 = **3,135** | 71 + 100 = **171** |
| shopping_admin | 1,175 + 2,410 = **3,585** | 87 + 87 = **174** |
| shopping | 979 + 0 = 979 (unchanged) | 52 + 0 = 52 (unchanged) |
| gitlab | 855 + 0 = 855 (unchanged) | 56 + 0 = 56 (unchanged) |

reddit and shopping_admin roughly double/triple in size; shopping and gitlab
are untouched since no new data was collected for them this round.

## When to use this vs. `training_data_continue_v1/`

- `training_data_continue_v1/` — the **increment only** (+ a small 15% replay
  slice), meant to **continue-finetune** an existing checkpoint (e.g.
  `checkpoint-536`) that already learned from `training_data/`.
- `training_data_merged_v1/` (this directory) — the **full union**, meant for
  a **from-scratch** LoRA run over all four domains at once, if that's ever
  preferred over continuing an existing checkpoint.

## Format

Same schema as `training_data/` and `training_data_v2/`: `messages`,
`trajectory_id`, `step_index`, `total_steps`, `difficulty`, `axtree_loaded`,
`site`, `run`. `training_data/`'s rows didn't originally carry a `run` column;
this build tags them `wa_run_20_<site>` for provenance. Sorted by `difficulty`
ascending (curriculum convention).

## Rebuilding

```bash
python scripts/build_merged_dataset.py
```
