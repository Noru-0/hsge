"""Build an SFT dataset from HSGE trajectory artifacts.

HSGE collects trajectories; this script turns the SUCCESSFUL (and, post-upgrade,
terminal-VERIFIED) ones into supervised fine-tuning examples that mirror the
the solver action-planner prompt, so the fine-tuned model drops straight back
into the same agent.

Each step becomes one chat example:
    system    : action-space + output-format instructions (matches your solver)
    user      : goal + current observation (AXTree) + recent action history
    assistant : the step's action  (the {"thought":..., "action":...} the solver emits)

Curriculum: every example carries a `difficulty` (task chain length; 1 for local
tasks). Emit train.jsonl sorted easy->hard, or sample by difficulty during training.

Usage:
    python build_sft_dataset.py <run_dir_or_episode.json> [out.jsonl] [--include-local]

By default only verified GEN episodes (phase-2, eval-spec-passing) are kept;
--include-local additionally admits self-reported LOCAL/GOAL successes.
"""
from __future__ import annotations

import glob
import json
import os
import sys

SYSTEM = (
    "You are a web agent. At each step you receive the task goal, the current page "
    "accessibility tree, and your recent actions. Respond with a JSON object "
    '{"thought": <reasoning>, "action": <one BrowserGym action>} where action is one '
    "of click('bid'), fill('bid','text'), select_option('bid','opt'), "
    "goto('url'), or send_msg_to_user('text')."
)


def _read_axtree(episode_dir: str, step: dict) -> str:
    """Best-effort load of the step's accessibility-tree text from disk."""
    obs = step.get("observation")
    if not isinstance(obs, dict):
        return ""
    for key in ("axtree_visible_only_txt", "axtree_txt"):
        node = obs.get(key)
        if isinstance(node, dict) and node.get("path"):
            p = node["path"] if os.path.isabs(node["path"]) else os.path.join(episode_dir, node["path"])
            if os.path.exists(p):
                return open(p, encoding="utf-8", errors="ignore").read()
    return ""        # not available (e.g. standalone json without page_state files)


def _difficulty(task_info: dict, episode_meta: dict) -> int:
    # GOAL/composed tasks carry an explicit difficulty; local tasks default to 1.
    for src in (task_info, episode_meta, episode_meta.get("metadata", {})):
        if isinstance(src, dict) and isinstance(src.get("difficulty"), int):
            return src["difficulty"]
    return 1


def episode_to_examples(goal: str, steps: list[dict], episode_dir: str,
                        difficulty: int) -> list[dict]:
    examples, history = [], []
    for step in steps:
        target = step.get("action")                 # already the JSON the solver emits
        if not target:
            continue
        axtree = _read_axtree(episode_dir, step)
        obs_block = axtree if axtree else "[accessibility tree omitted]"
        hist = "\n".join(f"- {h}" for h in history[-5:]) or "(none yet)"
        user = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n{hist}\n\n"
                f"CURRENT PAGE (accessibility tree):\n{obs_block}")
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
                {"role": "assistant", "content": target},
            ],
            "difficulty": difficulty,
            "axtree_loaded": bool(axtree),
        })
        history.append(step.get("parsed_action") or target)
    return examples


def _keep(meta: dict, include_local: bool) -> bool:
    """Default gate: only GEN episodes that PASSED their eval spec (verified).
    Self-reported LOCAL/GOAL successes are opt-in via --include-local."""
    tags = (meta.get("metadata") or {}).get("tags") or []
    if "GEN" in tags:
        return bool(meta.get("verified"))
    return include_local and bool((meta.get("outcome") or {}).get("success"))


def load_episodes(path: str):
    """Yield (goal, steps, episode_dir, difficulty, meta) tuples."""
    if os.path.isfile(path) and path.endswith(".json"):
        d = json.load(open(path))
        em = d.get("episode_meta", d)
        ti = d.get("task_info", {})
        steps = d.get("steps") or []
        yield em.get("goal", ""), steps, os.path.dirname(path), _difficulty(ti, em), em
        return
    for meta_path in glob.glob(os.path.join(path, "**", "episode_meta.json"), recursive=True):
        ep_dir = os.path.dirname(meta_path)
        em = json.load(open(meta_path))
        jl = os.path.join(ep_dir, "episode.jsonl")
        steps = [json.loads(l) for l in open(jl)] if os.path.exists(jl) else []
        ti_path = os.path.join(ep_dir, "..", "..", "task_info.json")
        ti = json.load(open(ti_path)) if os.path.exists(ti_path) else {}
        yield em.get("goal", ""), steps, ep_dir, _difficulty(ti, em), em


def build(src: str, out: str, include_local: bool = False) -> dict:
    all_examples, n_ep, n_kept = [], 0, 0
    for goal, steps, ep_dir, diff, meta in load_episodes(src):
        n_ep += 1
        if not _keep(meta, include_local):
            continue
        n_kept += 1
        all_examples += episode_to_examples(goal, steps, ep_dir, diff)
    all_examples.sort(key=lambda e: e["difficulty"])   # curriculum: easy -> hard
    with open(out, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")
    return {"episodes_seen": n_ep, "kept": n_kept, "examples": len(all_examples)}


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="run dir or single episode json")
    ap.add_argument("out", nargs="?", default="train.jsonl")
    ap.add_argument("--include-local", action="store_true",
                    help="also include self-reported LOCAL/GOAL successes "
                         "(default: verified GEN episodes only)")
    args = ap.parse_args()
    stats = build(args.src, args.out, include_local=args.include_local)
    print(f"episodes seen        : {stats['episodes_seen']}")
    print(f"kept (verified/gated): {stats['kept']}")
    print(f"SFT examples written : {stats['examples']} -> {args.out}")


if __name__ == "__main__":
    main()
