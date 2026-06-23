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
import re

from hsge.webarena.action_validation import (
    action_family,
    answer_has_evidence,
    extract_action_from_target,
    parse_hsge_action,
    repair_thought,
    task_family,
    validate_hsge_action,
)

ACTION_FORMAT_HSGE_JSON = "hsge_json"
ACTION_FORMAT_WEBARENA_ID = "webarena_id"
ACTION_FORMAT_WEBARENA_JSON = "webarena_json"  # Go-Browse style: JSON + bracket actions
ACTION_FORMATS = (ACTION_FORMAT_HSGE_JSON, ACTION_FORMAT_WEBARENA_ID, ACTION_FORMAT_WEBARENA_JSON)


def _system_prompt(allow_goto: bool, action_format: str = ACTION_FORMAT_HSGE_JSON) -> str:
    if action_format in (ACTION_FORMAT_WEBARENA_ID, ACTION_FORMAT_WEBARENA_JSON):
        actions = (
            "click [id], type [id] [text] [press_enter_after=0_or_1], "
            "press [key], scroll [down|up], hover [id]"
        )
        if allow_goto:
            actions += ", goto [url]"
        actions += ", or stop [answer]"
        if action_format == ACTION_FORMAT_WEBARENA_JSON:
            return (
                "You are a web agent. At each step you receive the task goal, the current page "
                "accessibility tree, and your recent actions. Respond with a JSON object "
                '{"thought": "<step-by-step reasoning connecting goal → page → element → action>", '
                '"action": "<one WebArena action>"} where action is one '
                f"of {actions}. Use numeric ids from the current accessibility tree. "
                "Do not bypass visible UI with direct URLs unless goto is explicitly allowed."
            )
        return (
            "You are a web agent. At each step you receive the task goal, the current page "
            "accessibility tree, and your recent actions. Think briefly, then end your response "
            "with exactly one WebArena id_accessibility_tree action wrapped in triple backticks. "
            f"Use one of {actions}. Use numeric ids from the current accessibility tree. "
            "Do not bypass visible UI with direct URLs unless goto is explicitly allowed."
        )

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


def _has_unsafe_webarena_bracket_text(text: str) -> bool:
    return "]" in text or "\n" in text or "\r" in text or "```" in text


def _validate_webarena_id_action(action: str) -> bool:
    """Mirror WebArena's id_accessibility_tree action grammar conservatively."""
    patterns = (
        r"click \[\d+\]",
        r"hover \[\d+\]",
        r"type \[\d+\] \[[^\]\r\n`]+\] \[[01]\]",
        r"press \[[^\]\r\n`]+\]",
        r"scroll \[(?:up|down)\]",
        r"goto \[[^\]\r\n`]+\]",
        r"stop(?: \[[^\]\r\n`]*\])?",
    )
    return any(re.fullmatch(pattern, action) for pattern in patterns)


def _to_webarena_id_action(action: str) -> tuple[str | None, str | None]:
    """Convert one valid HSGE action to WebArena's bracket action dialect."""
    parsed = parse_hsge_action(action)
    args = parsed.args

    match parsed.name:
        case "click":
            converted = f"click [{args[0]}]"
        case "hover":
            converted = f"hover [{args[0]}]"
        case "fill":
            text = args[1]
            if _has_unsafe_webarena_bracket_text(text):
                return None, "webarena_unsafe_bracket_text"
            converted = f"type [{args[0]}] [{text}] [0]"
        case "type":
            text = args[1]
            if _has_unsafe_webarena_bracket_text(text):
                return None, "webarena_unsafe_bracket_text"
            enter_flag = args[2] if len(args) >= 3 else "1"
            converted = f"type [{args[0]}] [{text}] [{enter_flag}]"
        case "press":
            key = args[0]
            if _has_unsafe_webarena_bracket_text(key):
                return None, "webarena_unsafe_bracket_text"
            converted = f"press [{key}]"
        case "scroll":
            converted = f"scroll [{args[0]}]"
        case "goto":
            url = args[0]
            if _has_unsafe_webarena_bracket_text(url):
                return None, "webarena_unsafe_bracket_text"
            converted = f"goto [{url}]"
        case "send_msg_to_user":
            answer = args[0]
            if _has_unsafe_webarena_bracket_text(answer):
                return None, "webarena_unsafe_bracket_text"
            converted = f"stop [{answer}]" if answer else "stop"
        case _:
            return None, "webarena_unsupported_action"

    if not _validate_webarena_id_action(converted):
        return None, "webarena_invalid_converted_action"
    return converted, None


def _webarena_target(thought: str, action: str) -> str:
    return f"{thought}\n\nIn summary, the next action I will perform is ```{action}```"


def _assistant_target(thought: str, action: str, action_format: str, report: dict) -> tuple[str, str] | None:
    if action_format == ACTION_FORMAT_HSGE_JSON:
        return _json_target(thought, action), action
    if action_format == ACTION_FORMAT_WEBARENA_JSON:
        converted, reason = _to_webarena_id_action(action)
        if not converted:
            report["steps_dropped"] += 1
            report["drop_reasons"][reason or "webarena_conversion_failed"] += 1
            return None
        return _json_target(thought, converted), converted
    if action_format == ACTION_FORMAT_WEBARENA_ID:
        converted, reason = _to_webarena_id_action(action)
        if not converted:
            report["steps_dropped"] += 1
            report["drop_reasons"][reason or "webarena_conversion_failed"] += 1
            return None
        return _webarena_target(thought, converted), converted
    raise ValueError(f"unsupported action format {action_format!r}")


def _validate_step(goal: str, step: dict, episode_dir: str,
                   recent_obs: list[str], actions: list[str],
                   repair: bool, allow_goto: bool,
                   action_format: str,
                   report: dict) -> tuple[str, str, str, str] | None:
    """Return (assistant_target, source_action, exported_action, axtree) when trainable."""
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
        thought, did_repair = repair_thought(thought, action, axtree, goal=goal)
        if did_repair:
            report["thoughts_repaired"] += 1

    assistant_target = _assistant_target(thought, action, action_format, report)
    if not assistant_target:
        return None
    target_text, exported_action = assistant_target

    report["steps_kept"] += 1
    report["action_family"][action_family(action)] += 1
    return target_text, action, exported_action, axtree


def episode_to_examples(goal: str, steps: list[dict], episode_dir: str,
                        difficulty: int, repair: bool = True,
                        allow_goto: bool = False,
                        action_format: str = ACTION_FORMAT_HSGE_JSON,
                        report: dict | None = None) -> list[dict]:
    if report is None:
        report = _new_report()
    if action_format not in ACTION_FORMATS:
        raise ValueError(f"unsupported action format {action_format!r}")
    examples, history = [], []
    recent_obs: list[str] = []
    actions: list[str] = []
    for step in steps:
        valid = _validate_step(
            goal, step, episode_dir, recent_obs, actions, repair, allow_goto,
            action_format, report
        )
        if not valid:
            continue
        target, source_action, exported_action, axtree = valid
        obs_block = axtree if axtree else "[accessibility tree omitted]"
        hist = "\n".join(f"- {h}" for h in history[-5:]) or "(none yet)"
        user = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n{hist}\n\n"
                f"CURRENT PAGE (accessibility tree):\n{obs_block}")
        examples.append({
            "messages": [
                {"role": "system", "content": _system_prompt(allow_goto, action_format)},
                {"role": "user", "content": user},
                {"role": "assistant", "content": target},
            ],
            "difficulty": difficulty,
            "axtree_loaded": bool(axtree),
            "task_family": task_family(goal),
            "action_family": action_family(source_action),
            "action_format": action_format,
        })
        history.append(exported_action)
        actions.append(source_action)
        recent_obs.append(axtree)
    return examples


def episode_to_multiturn_example(goal: str, steps: list[dict], episode_dir: str,
                                  difficulty: int, repair: bool = True,
                                  allow_goto: bool = False,
                                  action_format: str = ACTION_FORMAT_HSGE_JSON,
                                  report: dict | None = None) -> dict | None:
    """Build a SINGLE multi-turn sample from an entire episode trajectory.

    Unlike ``episode_to_examples`` which emits one sample per step, this groups
    all valid steps into one chat conversation so the fine-tuned model learns
    sequential decision-making across the full task.

    Returns a dict with ``messages`` (system + alternating user/assistant turns),
    or None if no valid steps remain after filtering.
    """
    if report is None:
        report = _new_report()
    if action_format not in ACTION_FORMATS:
        raise ValueError(f"unsupported action format {action_format!r}")
    sys_msg = _system_prompt(allow_goto, action_format)
    messages: list[dict] = [{"role": "system", "content": sys_msg}]
    history: list[str] = []
    recent_obs: list[str] = []
    actions: list[str] = []
    kept_steps = 0
    exported_actions: list[str] = []

    for step in steps:
        valid = _validate_step(
            goal, step, episode_dir, recent_obs, actions, repair, allow_goto,
            action_format, report
        )
        if not valid:
            continue
        target, source_action, exported_action, axtree = valid
        obs_block = axtree if axtree else "[accessibility tree omitted]"
        hist = "\n".join(f"- {h}" for h in history[-5:]) or "(none yet)"
        user = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n{hist}\n\n"
                f"CURRENT PAGE (accessibility tree):\n{obs_block}")
        messages.append({"role": "user", "content": user})
        messages.append({"role": "assistant", "content": target})
        history.append(exported_action)
        actions.append(source_action)
        recent_obs.append(axtree)
        exported_actions.append(exported_action)
        kept_steps += 1

    if kept_steps == 0:
        return None

    return {
        "messages": messages,
        "difficulty": difficulty,
        "steps": kept_steps,
        "axtree_loaded": True,  # at least one step loaded
        "task_family": task_family(goal),
        "action_families": list(dict.fromkeys(action_family(a) for a in actions)),
        "action_format": action_format,
    }


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
    parser.add_argument("--action-format", choices=ACTION_FORMATS, default=ACTION_FORMAT_HSGE_JSON,
                        help="Assistant target format: hsge_json for HSGE Solver, webarena_id for upstream WebArena PromptAgent.")
    parser.add_argument("--multiturn", action="store_true",
                        help="Emit one multi-turn sample per episode instead of one sample per step "
                             "(Go-Browse style: full trajectory in a single chat).")
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
        if args.multiturn:
            example = episode_to_multiturn_example(
                goal, steps, ep_dir, diff, args.repair_thoughts,
                args.allow_goto_training, args.action_format, report
            )
            if example:
                report["episodes_kept"] += 1
                report["successful_task_family"][task_family(goal)] += 1
                all_examples.append(example)
            else:
                report["episodes_dropped_empty"] += 1
        else:
            examples = episode_to_examples(
                goal, steps, ep_dir, diff, args.repair_thoughts,
                args.allow_goto_training, args.action_format, report
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
    loaded = sum(e.get("axtree_loaded", False) for e in all_examples)
    total_steps = sum(e.get("steps", 1) for e in all_examples)
    serializable_report = {
        k: (dict(v) if isinstance(v, Counter) else v)
        for k, v in report.items()
    }
    serializable_report["examples_written"] = 0 if args.validate_only else len(all_examples)
    serializable_report["examples_valid"] = len(all_examples)
    serializable_report["action_format"] = args.action_format
    serializable_report["multiturn"] = args.multiturn
    serializable_report["examples_by_difficulty"] = dict(sorted(by_diff.items()))
    serializable_report["axtree_loaded"] = loaded
    serializable_report["total_steps"] = total_steps
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
        mode = "multiturn" if args.multiturn else "single-step"
        print(f"SFT examples written : {len(all_examples)} -> {args.out}  (mode={mode}, total_steps={total_steps})")
    print(f"examples by difficulty: {dict(sorted(by_diff.items()))}")
    print(f"action families      : {dict(report['action_family'])}")
    print(f"task families        : {dict(report['successful_task_family'])}")
    print(f"dropped steps        : {report['steps_dropped']} {dict(report['drop_reasons'])}")
    print(f"thoughts repaired    : {report['thoughts_repaired']}")
    print(f"action format        : {args.action_format}")
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
