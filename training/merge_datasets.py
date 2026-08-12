#!/usr/bin/env python3
"""Merge several per-domain HSGE SFT jsonls into one, for training a single
cross-domain model (as opposed to per-site LoRAs).

Each source file's `trajectory_id` is only unique WITHIN that file -- HSGE
numbers episodes `ep_0000`, `ep_0001`, ... independently per run, so reddit's
`ep_0005` and shopping's `ep_0005` are unrelated trajectories that happen to
share an id. Concatenating the files as-is would make prepare_dataset.py's
trajectory grouping silently merge them, corrupting both the train/val split
(a "trajectory" straddling two domains) and any step history built from that
group. This script prefixes trajectory_id with the domain name (inferred from
the filename, train_<domain>.jsonl -> <domain>) and stamps a `site` field on
every example for later slicing/debugging, then writes one combined jsonl for
prepare_dataset.py to consume.

Usage:
    python training/merge_datasets.py datasets/train_reddit.jsonl \
        datasets/train_shopping.jsonl datasets/train_shopping_admin.jsonl \
        datasets/train_gitlab.jsonl -o datasets/train_all.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _domain_from_filename(path: str) -> str:
    m = re.match(r"train_(.+)\.jsonl$", Path(path).name)
    if not m:
        raise SystemExit(f"can't infer domain from {path!r}; expected train_<domain>.jsonl "
                          "(pass --names to override)")
    return m.group(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("srcs", nargs="+", help="per-domain train_<domain>.jsonl files")
    ap.add_argument("-o", "--out", default="datasets/train_all.jsonl")
    ap.add_argument("--names", nargs="*", default=None,
                    help="explicit domain name per src, same order (default: inferred "
                         "from each filename's train_<domain>.jsonl pattern)")
    args = ap.parse_args()

    names = args.names or [_domain_from_filename(s) for s in args.srcs]
    if len(names) != len(args.srcs):
        raise SystemExit(f"--names has {len(names)} entries but {len(args.srcs)} srcs given")

    n_total = 0
    per_domain = {}
    with open(args.out, "w", encoding="utf-8") as out:
        for src, domain in zip(args.srcs, names):
            n = 0
            for line in open(src, encoding="utf-8"):
                row = json.loads(line)
                row["trajectory_id"] = f"{domain}_{row['trajectory_id']}"
                row["site"] = domain
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
            per_domain[domain] = n
            n_total += n

    print(f"merged {len(args.srcs)} files -> {n_total} examples -> {args.out}")
    for domain, n in per_domain.items():
        print(f"  {domain}: {n} examples ({n / n_total:.1%})")


if __name__ == "__main__":
    main()
