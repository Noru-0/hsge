#!/usr/bin/env python3
"""List all successful tasks from a run folder with node, episode, and task info.

Usage:
    python list_successful_tasks.py outputs/wa_run_19
    python list_successful_tasks.py outputs/wa_run_20 --out report.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def parse_run_log(run_dir: str) -> list[dict]:
    """Parse run.log to extract task results with node context."""
    log_path = os.path.join(run_dir, "run.log")
    if not os.path.isfile(log_path):
        print(f"ERROR: run.log not found in {run_dir}", file=sys.stderr)
        sys.exit(1)

    results: list[dict] = []
    current_node: int | None = None
    current_depth: int | None = None
    current_url: str = ""

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            # Detect node header: [node N depth=D] URL
            node_match = re.match(
                r"\[node (\d+) depth=(\d+)\]\s+(https?://\S+)", line
            )
            if node_match:
                current_node = int(node_match.group(1))
                current_depth = int(node_match.group(2))
                current_url = node_match.group(3)
                continue

            # Detect task result: "    local: ... success=True/False"
            task_match = re.match(
                r"\s{4}local:\s+\"(.+?)\"\s+success=(True|False)", line
            )
            if task_match and current_node is not None:
                task_goal = task_match.group(1)
                success = task_match.group(2) == "True"
                results.append({
                    "node": current_node,
                    "depth": current_depth,
                    "url": current_url,
                    "task": task_goal,
                    "success": success,
                })

    return results


def main():
    ap = argparse.ArgumentParser(
        description="List successful tasks from an HSGE run folder."
    )
    ap.add_argument("run_dir", help="Path to the run output folder (e.g. outputs/wa_run_19)")
    ap.add_argument("--out", "-o", default=None,
                    help="Output JSON file path (default: <run_dir>/successful_tasks.json)")
    ap.add_argument("--all", action="store_true", dest="include_all",
                    help="Include failed tasks too")
    args = ap.parse_args()

    results = parse_run_log(args.run_dir)

    # Match tasks with episode metadata
    episodes_dir = os.path.join(args.run_dir, "episodes")
    task_to_ep: dict[str, int] = {}

    def _normalize(s: str) -> str:
        """Normalize task strings for matching: resolve all unicode escapes."""
        # Handle \\xNN and \\uNNNN (from run.log — literal backslashes in text)
        # and \xNN, \uNNNN (from json-loaded meta — actual escape sequences)
        # The regex matches 1-2 backslashes followed by x/u + hex digits
        s = re.sub(
            r"\\+([xu][0-9a-fA-F]{2,4})",
            lambda m: chr(int(m.group(1)[1:], 16)),
            s,
        )
        s = s.replace("\xa0", " ")
        s = re.sub(r"\s+", " ", s).strip()
        return s

    if os.path.isdir(episodes_dir):
        for ep_name in sorted(os.listdir(episodes_dir)):
            ep_path = os.path.join(episodes_dir, ep_name)
            meta_path = os.path.join(ep_path, "episode_meta.json")
            if not os.path.isfile(meta_path):
                continue
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                continue
            goal = _normalize(meta.get("goal", ""))
            ep_num = int(ep_name.split("_")[-1])
            task_to_ep[goal] = ep_num

    # Enrich results with episode numbers
    for r in results:
        r["episode"] = task_to_ep.get(_normalize(r["task"]), None)

    # Filter
    if not args.include_all:
        results = [r for r in results if r["success"]]

    # Output
    out_path = args.out or os.path.join(args.run_dir, "successful_tasks.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    n_total = len(results)
    n_success = sum(1 for r in results if r["success"])
    n_fail = n_total - n_success
    print(f"Exported {n_success} successful + {n_fail} failed = {n_total} tasks → {out_path}")


if __name__ == "__main__":
    main()
