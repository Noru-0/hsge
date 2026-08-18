#!/usr/bin/env python3
"""Build the full merged dataset: training_data/ + training_data_continue_v1/'s
increment (reddit + shopping_admin, wa_run_21/22), WITHOUT the replay rows.

The replay rows in training_data_continue_v1/ are resampled directly from
training_data/ (verified: every replay trajectory_id is an exact match --
191/191 train, 9/9 val), so including them here would double-count those
trajectories. This script keeps training_data/ untouched and does not
overwrite training_data_continue_v1/ -- it only reads both and writes a new,
separate merged pair.

Usage:
    python scripts/build_merged_dataset.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / "training_data"
INCREMENT = ROOT / "training_data_continue_v1"
OUT = ROOT / "training_data_merged_v1"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def main() -> None:
    OUT.mkdir(exist_ok=True)

    old_train = load_jsonl(OLD / "train.jsonl")
    old_val = load_jsonl(OLD / "val.jsonl")
    inc_train = load_jsonl(INCREMENT / "train.jsonl")
    inc_val = load_jsonl(INCREMENT / "val.jsonl")

    inc_train_new = [r for r in inc_train if not r["run"].startswith("replay_")]
    inc_val_new = [r for r in inc_val if not r["run"].startswith("replay_")]

    # old_train/val have no "site"/"run" columns of their own beyond "site"
    # (see training_data/train.jsonl schema); tag "run" for provenance so a
    # reader can tell old vs increment rows apart without re-deriving it.
    for r in old_train:
        r.setdefault("run", "wa_run_20_" + r["site"])
    for r in old_val:
        r.setdefault("run", "wa_run_20_" + r["site"])

    train = old_train + inc_train_new
    val = old_val + inc_val_new
    train.sort(key=lambda r: r["difficulty"])
    val.sort(key=lambda r: r["difficulty"])

    write_jsonl(OUT / "train.jsonl", train)
    write_jsonl(OUT / "val.jsonl", val)

    print(f"old train:       {len(old_train)}")
    print(f"increment train: {len(inc_train_new)} (replay excluded: {len(inc_train) - len(inc_train_new)})")
    print(f"TOTAL train:     {len(train)}  -> {OUT / 'train.jsonl'}")
    print()
    print(f"old val:         {len(old_val)}")
    print(f"increment val:   {len(inc_val_new)} (replay excluded: {len(inc_val) - len(inc_val_new)})")
    print(f"TOTAL val:       {len(val)}  -> {OUT / 'val.jsonl'}")


if __name__ == "__main__":
    main()
