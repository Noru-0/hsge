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
    python build_sft_dataset.py <run_dir_or_episode.json> [out.jsonl]

Accepts either a run directory (walks node_*/tasks/*/positive_trajs/*/) or a single
combined episode json (like sample_trajectory.json).
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


def load_episodes(path: str):
    """Yield (goal, steps, episode_dir, difficulty, success) tuples."""
    if os.path.isfile(path) and path.endswith(".json"):
        d = json.load(open(path))
        em = d.get("episode_meta", d)
        ti = d.get("task_info", {})
        steps = d.get("steps") or []
        success = em.get("outcome", {}).get("success", False)
        yield em.get("goal", ""), steps, os.path.dirname(path), _difficulty(ti, em), success
        return
    # run directory: each episode is a dir with episode_meta.json + episode.jsonl
    for meta_path in glob.glob(os.path.join(path, "**", "episode_meta.json"), recursive=True):
        ep_dir = os.path.dirname(meta_path)
        em = json.load(open(meta_path))
        jl = os.path.join(ep_dir, "episode.jsonl")
        steps = [json.loads(l) for l in open(jl)] if os.path.exists(jl) else []
        ti_path = os.path.join(ep_dir, "..", "..", "task_info.json")
        ti = json.load(open(ti_path)) if os.path.exists(ti_path) else {}
        success = em.get("outcome", {}).get("success", False)
        yield em.get("goal", ""), steps, ep_dir, _difficulty(ti, em), success


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "train.jsonl"

    all_examples, n_ep, n_kept = [], 0, 0
    for goal, steps, ep_dir, diff, success in load_episodes(src):
        n_ep += 1
        if not success:                              # only train on successes
            continue
        n_kept += 1
        all_examples += episode_to_examples(goal, steps, ep_dir, diff)

    all_examples.sort(key=lambda e: e["difficulty"])   # curriculum: easy -> hard
    with open(out, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")

    by_diff = {}
    for e in all_examples:
        by_diff[e["difficulty"]] = by_diff.get(e["difficulty"], 0) + 1
    loaded = sum(e["axtree_loaded"] for e in all_examples)
    print(f"episodes seen        : {n_ep}")
    print(f"successful (kept)    : {n_kept}")
    print(f"SFT examples written : {len(all_examples)} -> {out}")
    print(f"examples by difficulty: {dict(sorted(by_diff.items()))}")
    print(f"with real AXTree text : {loaded}/{len(all_examples)} "
          f"(rest need the run dir's page_state/*.txt files)")
    if all_examples:
        print("\n--- example[0] (truncated) ---")
        ex = all_examples[0]
        print("system   :", ex["messages"][0]["content"][:90], "...")
        print("user     :", ex["messages"][1]["content"][:120].replace("\n", " "), "...")
        print("assistant:", ex["messages"][2]["content"][:120], "...")


if __name__ == "__main__":
    main()
