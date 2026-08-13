# `datasets/` — SFT training data

Exported from `outputs/wa_run_*/episodes/` by `build_sft_dataset.py`, one JSONL
example per agent step. Kept at the repo root until 2026-08-12; moved here so
the root holds code and config only. Nothing about their content changed.

| file | examples | what it is |
|---|---|---|
| `train_reddit.jsonl` | 1,672 | per-domain export from an earlier collection round, superseded by `training_data/` |
| `train_shopping.jsonl` | 773 | per-domain export from an earlier collection round, superseded by `training_data/` |
| `train_shopping_admin.jsonl` | 241 | per-domain export from an earlier collection round, superseded by `training_data/` |
| `train_gitlab.jsonl` | 1,065 | per-domain export from an earlier collection round, superseded by `training_data/` |
| `train_all.jsonl` | 3,751 | the four above merged by `training/merge_datasets.py`; an earlier round, **not** what checkpoint-536 was trained on (see below) |
| `train_all_v3.jsonl` | 2,399 | an earlier merged revision, superseded |
| `train.jsonl` | 425 | an early single-domain export, superseded |
| `sample.jsonl` | 1 | one pretty-printed example, for reading the format by eye |

**Correction (2026-08-13):** this file previously claimed `train_all.jsonl`
(3,751 examples) was what `checkpoint-536` was trained on. That was wrong —
it described an earlier training round. The dataset that actually produced
the shipped `checkpoint-536` result (20.8% on the 655-task WebArena
benchmark, see the thesis report and `outputs/eval/`) is
`training_data/train.jsonl` + `training_data/val.jsonl` (4,288 + 266 = 4,554
examples, from the four official `wa_run_20_*` collection runs), confirmed
against the thesis's `tab:dataset` table. Everything in this directory
predates that final collection round and is kept for reference/reproducibility
of the earlier per-site experiments, not as the source of the current result.

Not to be confused with:
- `training/data/` — LLaMA-Factory train/val splits, **generated** from a
  dataset like the ones here by `training/prepare_dataset.py`. Gitignored,
  regenerable, ~42 MB of duplication.
- `training_data/` — the final, later export described above. It is **not**
  a copy of the files in this directory; the files differ byte-for-byte, and
  it is the one behind the numbers this repo currently reports.

## Rebuilding

```bash
python training/merge_datasets.py datasets/train_reddit.jsonl \
    datasets/train_shopping.jsonl datasets/train_shopping_admin.jsonl \
    datasets/train_gitlab.jsonl -o datasets/train_all.jsonl

python training/prepare_dataset.py datasets/train_all.jsonl --name all \
    --out-dir training/data/all
```
