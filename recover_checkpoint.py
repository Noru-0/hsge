"""Recover checkpoint from existing episodes after accidental overwrite.

Reads all episode_meta.json files to extract visited URLs and rebuild
a checkpoint.json so exploration can resume without re-visiting pages.

Usage:
    python recover_checkpoint.py outputs/wa_run
"""
import json
import os
import sys

def recover(out_dir: str):
    ep_dir = os.path.join(out_dir, "episodes")
    if not os.path.isdir(ep_dir):
        print(f"[ERROR] No episodes dir: {ep_dir}")
        return

    visited: set[str] = set()
    episode_count = 0

    for name in sorted(os.listdir(ep_dir)):
        if not name.startswith("ep_"):
            continue
        ep_path = os.path.join(ep_dir, name)
        meta_path = os.path.join(ep_path, "episode_meta.json")
        if not os.path.isfile(meta_path):
            continue
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        # Extract URL from the episode steps
        traj_path = os.path.join(ep_path, "episode.jsonl")
        if os.path.isfile(traj_path):
            with open(traj_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    obs = rec.get("observation", {})
                    if isinstance(obs, dict):
                        ax_path = obs.get("axtree_txt", {}).get("path", "")
                        if ax_path:
                            ax_full = os.path.join(ep_path, ax_path)
                            if os.path.isfile(ax_full):
                                with open(ax_full, encoding="utf-8") as af:
                                    text = af.read()
                                import re
                                m = re.search(r'URL:\s*(\S+)', text)
                                if m:
                                    url = m.group(1).rstrip('/')
                                    visited.add(url)

        episode_count += 1

    # Also extract visited URLs from any existing frontier.jsonl nodes
    fj = os.path.join(out_dir, "frontier.jsonl")
    if os.path.isfile(fj):
        with open(fj, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    visited.add(rec["url"].rstrip('/'))
                except (json.JSONDecodeError, KeyError):
                    pass

    # Build frontier from root URL, excluding visited
    root_url = "http://192.168.1.31:7770"
    # Try to read root from existing checkpoint or guess from episodes
    ckpt_path = os.path.join(out_dir, "checkpoint.json")
    old_root = root_url
    if os.path.isfile(ckpt_path):
        with open(ckpt_path, encoding="utf-8") as f:
            old_ckpt = json.load(f)

    # Build checkpoint
    checkpoint = {
        "frontier": [[root_url, 0]],      # restart from root; filter will skip visited
        "visited": sorted(visited),
        "queued": sorted(visited),        # mark visited URLs as queued to avoid re-adding
        "nodes_processed": 0,              # will be updated by _nodes_done from frontier.jsonl
        "episode": episode_count,
        "template_quota": {},              # lost, but will rebuild as exploration proceeds
    }

    with open(ckpt_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)

    print(f"[recover] Found {episode_count} episodes, {len(visited)} unique URLs visited")
    print(f"[recover] Checkpoint saved to {ckpt_path}")
    print(f"[recover] Now run with --resume to continue:")
    print(f"  python run_webarena.py ... --out {out_dir} --resume")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "outputs/wa_run"
    recover(out)
