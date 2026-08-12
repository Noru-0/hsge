# `datasets/` — SFT training data

Exported from `outputs/wa_run_*/episodes/` by `build_sft_dataset.py`, one JSONL
example per agent step. Kept at the repo root until 2026-08-12; moved here so
the root holds code and config only. Nothing about their content changed.

| file | examples | what it is |
|---|---|---|
| `train_reddit.jsonl` | 1,672 | per-domain export |
| `train_shopping.jsonl` | 773 | per-domain export |
| `train_shopping_admin.jsonl` | 241 | per-domain export |
| `train_gitlab.jsonl` | 1,065 | per-domain export |
| `train_all.jsonl` | 3,751 | the four above merged by `training/merge_datasets.py`; **this is what checkpoint-536 was trained on** |
| `train_all_v3.jsonl` | 2,399 | an earlier merged revision, superseded |
| `train.jsonl` | 425 | an early single-domain export, superseded |
| `sample.jsonl` | 1 | one pretty-printed example, for reading the format by eye |

Not to be confused with:
- `training/data/` — LLaMA-Factory train/val splits, **generated** from these by
  `training/prepare_dataset.py`. Gitignored, regenerable, ~42 MB of duplication.
- `training_data/` — a separate, later export (4,288 examples) that is **not** a
  copy of these; the files differ byte-for-byte. Untracked, provenance unclear.

## Rebuilding

```bash
python training/merge_datasets.py datasets/train_reddit.jsonl \
    datasets/train_shopping.jsonl datasets/train_shopping_admin.jsonl \
    datasets/train_gitlab.jsonl -o datasets/train_all.jsonl

python training/prepare_dataset.py datasets/train_all.jsonl --name all \
    --out-dir training/data/all
```
