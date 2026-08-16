#!/usr/bin/env python3
"""Quarantine episodes that wandered off the target WebArena site.

Root cause: run_webarena.py's old default `allow` pattern derivation
(`root_url.rsplit("/", 1)[0]`) failed to restrict the frontier to the site's
own host whenever WA_<SITE> in .env was a bare host with no path (every site
except shopping_admin's .../admin) -- see .claude/memory/bugs.md ("Default
`allow` pattern lets the frontier escape onto real external sites", fixed
2026-08-17). Runs collected before that fix may contain episodes whose steps
touched a real external site (news sites, ncbi.nlm.nih.gov, gitlab.com, ...).

This script does NOT delete anything: it moves each contaminated episode
directory from `<run_dir>/episodes/` to `<run_dir>/episodes_offdomain/`
(sibling, easy to inspect or restore), leaving `episodes/` safe to feed
straight into build_sft_dataset.py.

An episode is contaminated if ANY step's recorded `url` has a different host
than the expected one (not just the node it was launched from -- an episode
can wander off-domain mid-trajectory by clicking an external link, which is
exactly how these off-domain nodes entered the frontier in the first place).

Usage:
    python scripts/filter_offdomain_episodes.py <run_dir> [--expected-host HOST] [--apply]

Without --apply, only reports what WOULD move (dry run). Pass --apply to
actually move the directories.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from urllib.parse import urlsplit


def episode_hosts(ep_dir: str) -> set[str]:
    hosts = set()
    jsonl_path = os.path.join(ep_dir, "episode.jsonl")
    if not os.path.exists(jsonl_path):
        return hosts
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = rec.get("url", "")
            if url:
                hosts.add(urlsplit(url).netloc)
    return hosts


def infer_expected_host(run_dir: str) -> str:
    nodes_path = os.path.join(run_dir, "nodes.json")
    nodes = json.load(open(nodes_path, encoding="utf-8"))
    for n in nodes:
        if not n.get("duplicate") and n.get("url"):
            return urlsplit(n["url"]).netloc
    raise ValueError(f"could not infer expected host from {nodes_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--expected-host", default=None,
                     help="target site's host; inferred from nodes.json[0] if omitted")
    ap.add_argument("--apply", action="store_true",
                     help="actually move contaminated episodes (default: dry run, report only)")
    args = ap.parse_args()

    expected = args.expected_host or infer_expected_host(args.run_dir)
    print(f"[filter] run_dir={args.run_dir} expected_host={expected!r} "
          f"({'APPLYING' if args.apply else 'DRY RUN'})")

    episodes_dir = os.path.join(args.run_dir, "episodes")
    quarantine_dir = os.path.join(args.run_dir, "episodes_offdomain")
    ep_ids = sorted(d for d in os.listdir(episodes_dir)
                     if d.startswith("ep_") and os.path.isdir(os.path.join(episodes_dir, d)))

    contaminated = []
    for ep_id in ep_ids:
        ep_dir = os.path.join(episodes_dir, ep_id)
        hosts = episode_hosts(ep_dir)
        off_hosts = hosts - {expected}
        if off_hosts:
            contaminated.append((ep_id, off_hosts))

    print(f"[filter] {len(contaminated)}/{len(ep_ids)} episodes touched a host "
          f"other than {expected!r}")
    for ep_id, off_hosts in contaminated[:20]:
        print(f"    {ep_id}: {sorted(off_hosts)}")
    if len(contaminated) > 20:
        print(f"    ... and {len(contaminated) - 20} more")

    if not args.apply:
        print("[filter] dry run only -- pass --apply to move these into "
              f"{quarantine_dir}")
        return

    os.makedirs(quarantine_dir, exist_ok=True)
    moved = 0
    for ep_id, _ in contaminated:
        src = os.path.join(episodes_dir, ep_id)
        dst = os.path.join(quarantine_dir, ep_id)
        if os.path.exists(dst):
            print(f"    [skip] {dst} already exists, not overwriting")
            continue
        shutil.move(src, dst)
        moved += 1
    print(f"[filter] moved {moved} contaminated episode dirs to {quarantine_dir}")
    print(f"[filter] {len(ep_ids) - moved} clean episodes remain in {episodes_dir}")


if __name__ == "__main__":
    main()
