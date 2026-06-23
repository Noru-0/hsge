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

import argparse
from collections import Counter
import glob
import json
import os

from hsge.webarena.action_validation import (
    action_family,
    answer_has_evidence,
    extract_action_from_target,
    repair_thought,
    task_family,
    validate_hsge_action,
)

def _system_prompt(allow_goto: bool) -> str:
    actions = (
        "click('bid'), fill('bid','text'), type('bid','text','1_or_0'), "
        "press('key'), scroll('down'|'up'), hover('bid')"
    )
    if allow_goto:
        actions += ", goto('url')"
    actions += ", or send_msg_to_user('text')"
    return (
        "You are a web agent. At each step you receive the task goal, the current page "
        "accessibility tree, and your recent actions. Respond with a JSON object "
        '{"thought": <reasoning>, "action": <one HSGE action>} where action is one '
        f"of {actions}. Use numeric bids from the current accessibility tree. "
        "Do not bypass visible UI with direct URLs unless goto is explicitly allowed."
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


def _new_report() -> dict:
    return {
        "episodes_seen": 0,
        "episodes_kept": 0,
        "episodes_dropped_empty": 0,
        "steps_seen": 0,
        "steps_kept": 0,
        "steps_dropped": 0,
        "thoughts_repaired": 0,
        "axtree_missing": 0,
        "drop_reasons": Counter(),
        "action_family": Counter(),
        "task_family": Counter(),
        "successful_task_family": Counter(),
    }


def _json_target(thought: str, action: str) -> str:
    return json.dumps({"thought": thought, "action": action}, ensure_ascii=False)


def _validate_step(goal: str, step: dict, episode_dir: str,
                   recent_obs: list[str], actions: list[str],
                   repair: bool, allow_goto: bool,
                   report: dict) -> tuple[str, str, str] | None:
    """Return (target_json, parsed_action, axtree) when trainable."""
    report["steps_seen"] += 1
    target = step.get("action")
    if not target:
        report["steps_dropped"] += 1
        report["drop_reasons"]["missing_target"] += 1
        return None
    try:
        thought, action = extract_action_from_target(target)
    except Exception:
        report["steps_dropped"] += 1
        report["drop_reasons"]["invalid_assistant_json"] += 1
        return None

    axtree = _read_axtree(episode_dir, step)
    if not axtree:
        report["axtree_missing"] += 1
    validation = validate_hsge_action(action, axtree, allow_goto=allow_goto)
    if not validation.ok:
        report["steps_dropped"] += 1
        report["drop_reasons"][validation.reason] += 1
        return None

    if validation.parsed and validation.parsed.name == "send_msg_to_user":
        answer = validation.parsed.args[0] if validation.parsed.args else ""
        if not answer_has_evidence(goal, answer, recent_obs + [axtree], actions + [action]):
            report["steps_dropped"] += 1
            report["drop_reasons"]["send_msg_to_user_without_visible_evidence"] += 1
            return None

    if repair:
        thought, did_repair = repair_thought(thought, action, axtree)
        if did_repair:
            report["thoughts_repaired"] += 1

    report["steps_kept"] += 1
    report["action_family"][action_family(action)] += 1
    return _json_target(thought, action), action, axtree


def episode_to_examples(goal: str, steps: list[dict], episode_dir: str,
                        difficulty: int, repair: bool = True,
                        allow_goto: bool = False,
                        report: dict | None = None) -> list[dict]:
    if report is None:
        report = _new_report()
    examples, history = [], []
    recent_obs: list[str] = []
    actions: list[str] = []
    for step in steps:
        valid = _validate_step(
            goal, step, episode_dir, recent_obs, actions, repair, allow_goto, report
        )
        if not valid:
            continue
        target, parsed_action, axtree = valid
        obs_block = axtree if axtree else "[accessibility tree omitted]"
        hist = "\n".join(f"- {h}" for h in history[-5:]) or "(none yet)"
        user = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n{hist}\n\n"
                f"CURRENT PAGE (accessibility tree):\n{obs_block}")
        examples.append({
            "messages": [
                {"role": "system", "content": _system_prompt(allow_goto)},
                {"role": "user", "content": user},
                {"role": "assistant", "content": target},
            ],
            "difficulty": difficulty,
            "axtree_loaded": bool(axtree),
            "task_family": task_family(goal),
            "action_family": action_family(parsed_action),
        })
        history.append(parsed_action)
        actions.append(parsed_action)
        recent_obs.append(axtree)
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", help="Run directory or episode JSON")
    parser.add_argument("out", nargs="?", default="train.jsonl")
    parser.add_argument("--validate-only", action="store_true",
                        help="Validate and report without writing train data")
    parser.add_argument("--repair-thoughts", action="store_true", default=True,
                        help="Rewrite weak thoughts with grounded deterministic text (default)")
    parser.add_argument("--no-repair-thoughts", action="store_false",
                        dest="repair_thoughts",
                        help="Keep raw thoughts instead of grounding weak thoughts")
    parser.add_argument("--report", default=None,
                        help="Optional JSON report path")
    parser.add_argument("--allow-goto-training", action="store_true",
                        help="Keep goto(url) examples. Default drops them to avoid UI-bypass training.")
    args = parser.parse_args()

    all_examples, n_ep, n_kept = [], 0, 0
    report = _new_report()
    for goal, steps, ep_dir, diff, success in load_episodes(args.src):
        n_ep += 1
        report["episodes_seen"] += 1
        if not success:                              # only train on successes
            continue
        n_kept += 1
        report["task_family"][task_family(goal)] += 1
        examples = episode_to_examples(
            goal, steps, ep_dir, diff, args.repair_thoughts,
            args.allow_goto_training, report
        )
        if examples:
            report["episodes_kept"] += 1
            report["successful_task_family"][task_family(goal)] += 1
            all_examples += examples
        else:
            report["episodes_dropped_empty"] += 1

    all_examples.sort(key=lambda e: e["difficulty"])   # curriculum: easy -> hard
    if not args.validate_only:
        with open(args.out, "w") as f:
            for ex in all_examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    by_diff = {}
    for e in all_examples:
        by_diff[e["difficulty"]] = by_diff.get(e["difficulty"], 0) + 1
    loaded = sum(e["axtree_loaded"] for e in all_examples)
    serializable_report = {
        k: (dict(v) if isinstance(v, Counter) else v)
        for k, v in report.items()
    }
    serializable_report["examples_written"] = 0 if args.validate_only else len(all_examples)
    serializable_report["examples_valid"] = len(all_examples)
    serializable_report["examples_by_difficulty"] = dict(sorted(by_diff.items()))
    serializable_report["axtree_loaded"] = loaded
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(serializable_report, f, indent=2, sort_keys=True)
    print(f"episodes seen        : {n_ep}")
    print(f"successful (kept)    : {n_kept}")
    print(f"episodes after filter: {report['episodes_kept']} "
          f"(dropped empty: {report['episodes_dropped_empty']})")
    if args.validate_only:
        print(f"SFT examples valid   : {len(all_examples)} (validate-only)")
    else:
        print(f"SFT examples written : {len(all_examples)} -> {args.out}")
    print(f"examples by difficulty: {dict(sorted(by_diff.items()))}")
    print(f"action families      : {dict(report['action_family'])}")
    print(f"task families        : {dict(report['successful_task_family'])}")
    print(f"dropped steps        : {report['steps_dropped']} {dict(report['drop_reasons'])}")
    print(f"thoughts repaired    : {report['thoughts_repaired']}")
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
