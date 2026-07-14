#!/usr/bin/env python3
"""Split an HSGE SFT jsonl into LLaMA-Factory train/val files.

Splits by trajectory (a trajectory's steps never straddle the split), writes
`train.jsonl` / `val.jsonl` containing only the `messages` field, and a
`dataset_info.json` registering both under the names the training yaml uses.

Usage:
    python training/prepare_dataset.py [training/train_12.jsonl] [--out-dir training/data]
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", nargs="?", default="training/train_12.jsonl")
    ap.add_argument("--out-dir", default="training/data")
    ap.add_argument("--val-fraction", type=float, default=0.05,
                    help="target fraction of *examples* (not trajectories) held out")
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    rows = [json.loads(line) for line in open(args.src)]
    trajs: dict[str, list[dict]] = {}
    for r in rows:
        trajs.setdefault(r["trajectory_id"], []).append(r)

    ids = sorted(trajs)
    random.Random(args.seed).shuffle(ids)
    target = round(len(rows) * args.val_fraction)
    val_ids: set[str] = set()
    n_val = 0
    for tid in ids:
        if n_val >= target:
            break
        val_ids.add(tid)
        n_val += len(trajs[tid])

    train = [r for r in rows if r["trajectory_id"] not in val_ids]
    val = [r for r in rows if r["trajectory_id"] in val_ids]

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, part in (("train.jsonl", train), ("val.jsonl", val)):
        with open(out / name, "w") as f:
            for r in part:
                f.write(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n")

    # openai-messages mapping for LLaMA-Factory's sharegpt loader
    tags = {"role_tag": "role", "content_tag": "content",
            "user_tag": "user", "assistant_tag": "assistant", "system_tag": "system"}
    info = {
        "hsge_gitlab_train": {"file_name": "train.jsonl", "formatting": "sharegpt",
                              "columns": {"messages": "messages"}, "tags": tags},
        "hsge_gitlab_val": {"file_name": "val.jsonl", "formatting": "sharegpt",
                            "columns": {"messages": "messages"}, "tags": tags},
    }
    (out / "dataset_info.json").write_text(json.dumps(info, indent=2) + "\n")

    lens = [sum(len(m["content"]) for m in r["messages"]) for r in rows]
    print(f"examples: {len(rows)} ({len(trajs)} trajectories) -> "
          f"train {len(train)} / val {len(val)} ({len(val_ids)} trajectories held out)")
    print(f"example chars: min {min(lens)} / median {int(statistics.median(lens))} "
          f"/ max {max(lens)}  (~{max(lens) // 3} tokens max; cutoff_len 4096 is safe)")
    print(f"wrote {out}/train.jsonl, {out}/val.jsonl, {out}/dataset_info.json")


if __name__ == "__main__":
    main()
