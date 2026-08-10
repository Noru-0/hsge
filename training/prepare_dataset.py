#!/usr/bin/env python3
"""Split an HSGE SFT jsonl into LLaMA-Factory train/val files.

Writes `train.jsonl` / `val.jsonl` containing only the `messages` field, and a
`dataset_info.json` registering both under the names the training yaml uses.

The registered names are `hsge_<name>_train` / `hsge_<name>_val`; `--name`
must match the `dataset:` / `eval_dataset:` keys in the training yaml, so two
sites can be prepared side by side into separate `--out-dir`s.

**The split is by (site, goal), not by trajectory.** Grouping by
`trajectory_id` keeps a trajectory's steps together but is not enough:
`run.unprefixed_sampling` records every solved task twice -- once LOCAL from
its own node, once UNPREFIXED from the site root -- so one goal owns two
trajectories, and a trajectory-level split puts one in train and its twin in
val. Measured on `training_data/` (built from the four `wa_run_20_*` runs),
that leaked 29 of 56 val trajectories (50% of val examples): the model had
already trained on the same goal, same site, same destination page, which made
`eval_loss` optimistic and the epoch-2-vs-3 checkpoint choice unreliable. The
goal text is read back out of the prompt (`# Goal` block) so this works on any
exported jsonl without needing the original `episodes/` on disk.

Redundant repeats are dropped by default. A goal with exactly one difficulty-1
and one difficulty-2 trajectory is the intended LOCAL/UNPREFIXED pair and is
kept in full (the unprefixed twin is the longer, more valuable trajectory --
mean 6.0 vs 3.4 steps in that same data). Anything beyond that -- two
trajectories of the SAME difficulty for one goal, which is the seed-capability
GOAL generator re-proposing a goal at another node -- keeps only the longest
and drops the rest. Pass `--keep-repeats` to disable.

Usage:
    python training/prepare_dataset.py [training/train_12.jsonl] [--out-dir training/data]
    python training/prepare_dataset.py train_reddit.jsonl --name reddit \
        --out-dir training/data/reddit
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

_GOAL_RE = re.compile(r"# Goal\n(.*?)\n\n# Current Page", re.S)


def task_key(rows: list[dict]) -> tuple[str, str]:
    """Identity of the task a trajectory solves: (site, goal text).

    The goal is recovered from the user prompt rather than a top-level field,
    since exported examples carry no `goal` column. `site` is part of the key
    because `merge_datasets.py` combines domains and two sites can legitimately
    be given the same task wording.

    Falls back to the trajectory id when the prompt predates the `# Goal`
    format (`training/train_12.jsonl` and the other pre-2026-08 exports used
    `GOAL: ...`). Without the fallback every such trajectory would key to the
    same empty goal and land in one giant group.
    """
    first = min(rows, key=lambda r: r.get("step_index", 0))
    user = next(m["content"] for m in first["messages"] if m["role"] == "user")
    m = _GOAL_RE.search(user)
    if not m:
        return (first.get("site", ""), first["trajectory_id"])
    return (first.get("site", ""), m.group(1).strip())


def drop_redundant(trajs: dict[str, list[dict]]) -> tuple[set[str], list[tuple]]:
    """Ids to drop, plus one (site, goal, difficulty, kept, dropped) row per
    group that lost something -- so the caller can report exactly what went."""
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for tid, rows in trajs.items():
        groups[task_key(rows)].append(tid)

    dropped: set[str] = set()
    report: list[tuple] = []
    for (site, goal), tids in groups.items():
        by_diff: dict[int, list[str]] = defaultdict(list)
        for tid in tids:
            by_diff[trajs[tid][0].get("difficulty", 1)].append(tid)
        for diff, same in by_diff.items():
            if len(same) == 1:
                continue
            # keep the longest trajectory; trajectory_id breaks ties so the
            # choice is stable across runs
            same.sort(key=lambda t: (-len(trajs[t]), t))
            dropped.update(same[1:])
            report.append((site, goal, diff, same[0], same[1:]))
    return dropped, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", nargs="?", default="training/train_12.jsonl")
    ap.add_argument("--out-dir", default="training/data")
    ap.add_argument("--name", default="gitlab",
                    help="dataset key suffix: registers hsge_<name>_{train,val}")
    ap.add_argument("--val-fraction", type=float, default=0.05,
                    help="target fraction of *examples* (not trajectories) held out")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--keep-repeats", action="store_true",
                    help="keep same-goal same-difficulty duplicate trajectories "
                         "(dropped by default; LOCAL/UNPREFIXED pairs are never touched)")
    ap.add_argument("--keep-all-fields", action="store_true",
                    help="write every column (site/difficulty/trajectory_id/...) instead "
                         "of just `messages`, for auditable intermediate splits")
    args = ap.parse_args()

    rows = [json.loads(line) for line in open(args.src, encoding="utf-8")]
    trajs: dict[str, list[dict]] = {}
    for r in rows:
        trajs.setdefault(r["trajectory_id"], []).append(r)
    n_traj_in = len(trajs)

    if not args.keep_repeats:
        dropped, report = drop_redundant(trajs)
        for site, goal, diff, kept, gone in sorted(report):
            print(f"  drop {len(gone)} repeat(s) of [{site} d{diff}] {goal[:70]!r} "
                  f"(kept {kept}, {len(trajs[kept])} steps)")
        n_ex_dropped = sum(len(trajs[t]) for t in dropped)
        for tid in dropped:
            del trajs[tid]
        rows = [r for r in rows if r["trajectory_id"] in trajs]
        print(f"redundant repeats: dropped {len(dropped)} trajectories / "
              f"{n_ex_dropped} examples")

    # Split whole tasks, never whole trajectories -- see module docstring.
    tasks: dict[tuple[str, str], list[str]] = defaultdict(list)
    for tid, tr in trajs.items():
        tasks[task_key(tr)].append(tid)

    # Hold out `--val-fraction` of each site's examples separately. One shuffled
    # pass over all tasks lets whichever site owns the longest trajectories fill
    # the quota: on the four wa_run_20_* domains that gave a val set of shopping
    # 117 / reddit 83 / gitlab 28 / shopping_admin 16 examples off a train set
    # that is balanced within 10 points, so eval_loss mostly tracked shopping.
    by_site: dict[str, list[tuple[str, str]]] = defaultdict(list)
    n_ex_site: dict[str, int] = defaultdict(int)
    for k, tids in tasks.items():
        by_site[k[0]].append(k)
        n_ex_site[k[0]] += sum(len(trajs[t]) for t in tids)

    rng = random.Random(args.seed)
    val_ids: set[str] = set()
    for site in sorted(by_site):
        keys = sorted(by_site[site])
        rng.shuffle(keys)
        target = round(n_ex_site[site] * args.val_fraction)
        n_val = 0
        for k in keys:
            if n_val >= target:
                break
            val_ids.update(tasks[k])
            n_val += sum(len(trajs[t]) for t in tasks[k])

    train = [r for r in rows if r["trajectory_id"] not in val_ids]
    val = [r for r in rows if r["trajectory_id"] in val_ids]

    train_goals = {task_key(trajs[t]) for t in trajs if t not in val_ids}
    leaked = {task_key(trajs[t]) for t in val_ids} & train_goals
    assert not leaked, f"{len(leaked)} val goals also appear in train"

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, part in (("train.jsonl", train), ("val.jsonl", val)):
        with open(out / name, "w", encoding="utf-8") as f:
            for r in part:
                row = r if args.keep_all_fields else {"messages": r["messages"]}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # openai-messages mapping for LLaMA-Factory's sharegpt loader
    tags = {"role_tag": "role", "content_tag": "content",
            "user_tag": "user", "assistant_tag": "assistant", "system_tag": "system"}
    info = {
        f"hsge_{args.name}_train": {"file_name": "train.jsonl", "formatting": "sharegpt",
                                    "columns": {"messages": "messages"}, "tags": tags},
        f"hsge_{args.name}_val": {"file_name": "val.jsonl", "formatting": "sharegpt",
                                  "columns": {"messages": "messages"}, "tags": tags},
    }
    (out / "dataset_info.json").write_text(json.dumps(info, indent=2) + "\n")

    lens = [sum(len(m["content"]) for m in r["messages"]) for r in rows]
    n_val_tasks = sum(1 for tids in tasks.values() if tids[0] in val_ids)
    print(f"examples: {len(rows)} ({len(trajs)} of {n_traj_in} trajectories, "
          f"{len(tasks)} distinct tasks) -> train {len(train)} / val {len(val)} "
          f"({len(val_ids)} trajectories / {n_val_tasks} tasks held out, "
          f"0 goals shared with train)")
    print(f"example chars: min {min(lens)} / median {int(statistics.median(lens))} "
          f"/ max {max(lens)}  (~{max(lens) // 3} tokens max; cutoff_len 4096 is safe)")
    print(f"wrote {out}/train.jsonl, {out}/val.jsonl, {out}/dataset_info.json")


if __name__ == "__main__":
    main()
