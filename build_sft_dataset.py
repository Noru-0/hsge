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
import glob
import json
import os

from hsge.webarena.agents import PageExplorer, SOLVER_SYS, step_outcome

SYSTEM = SOLVER_SYS

_HISTORY_WINDOW = 6  # matches Solver.solve's history[-6:] window exactly
_TAG_RE = PageExplorer._TAG_RE  # reuse the same "[INFO]/[NAV]/[MOD] " stripper


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


def _strip_tag(goal: str) -> str:
    """Drop a leading [INFO]/[NAV]/[MOD] classification tag from a goal string.
    Those tags come from PageExplorer's task proposals (see agents.py); a real
    WebArena eval goal never carries one, so leaving it in would teach the
    model to expect a prefix that won't be there at inference time."""
    return _TAG_RE.sub("", goal or "").strip()


def _is_error_step(thought: str) -> bool:
    """A step whose recorded thought carries the '[action error: ...]' suffix
    Solver.solve appends when browser.act() raised (see agents.py::Solver.solve)
    -- the *next* LLM call saw the error and picked a different action, so this
    exact action was never added to Solver.solve's own `history`/`outcomes`
    either. It must not become an imitation target (it's the mistake, not the
    recovery) or appear in a later step's history."""
    return "[action error:" in (thought or "")


def _include_episode(success: bool, infeasible: bool, judge_verified: bool | None,
                     require_judge: bool) -> bool:
    """Whether one episode's steps should be turned into SFT examples.
    Infeasible episodes are always eligible (report_infeasible is a real
    target regardless of judging). A plain success is eligible unless
    --require-judge is set, in which case it needs judge_verified is True --
    an episode never judged (judge_verified is None) is dropped, not
    silently trusted, so --require-judge fails safe."""
    if infeasible:
        return True
    if not success:
        return False
    if require_judge:
        return judge_verified is True
    return True


def episode_to_examples(goal: str, steps: list[dict], episode_dir: str,
                        difficulty: int, trajectory_id: str) -> list[dict]:
    goal = _strip_tag(goal)
    axtrees = [_read_axtree(episode_dir, step) for step in steps]
    urls = [step.get("url", "") for step in steps]
    thoughts = [step.get("thought_v2") or step.get("thought", "") for step in steps]
    total_steps = len(steps)

    history: list[str] = []   # outcome-annotated "- action -> outcome" lines
    examples = []
    for k, step in enumerate(steps):
        target_action = step.get("parsed_action") or ""
        if not target_action:
            continue
        thought = thoughts[k]
        if _is_error_step(step.get("thought", "")):
            continue
        assistant = json.dumps({"thought": thought, "action": target_action})
        hist_block = "\n".join(history[-_HISTORY_WINDOW:]) or "(none)"
        obs_block = axtrees[k] if axtrees[k] else "[accessibility tree omitted]"
        user = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n{hist_block}\n\n"
                f"URL: {urls[k]}\n\nPAGE:\n{obs_block}")
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
                {"role": "assistant", "content": assistant},
            ],
            "trajectory_id": trajectory_id,
            "step_index": step.get("index", k),
            "total_steps": total_steps,
            "difficulty": difficulty,
            "axtree_loaded": bool(axtrees[k]),
        })
        is_terminal = (target_action.startswith("send_msg_to_user")
                      or target_action.startswith("report_infeasible"))
        if not is_terminal and k + 1 < len(steps):
            outcome = step_outcome(urls[k], axtrees[k], urls[k + 1], axtrees[k + 1])
            history.append(f"- {target_action} -> {outcome}")
    return examples


def load_episodes(path: str):
    """Yield (goal, steps, episode_dir, trajectory_id, difficulty, success,
    infeasible, judge_verified) tuples. judge_verified is None if the
    episode has never been through judge_episodes.py."""
    if os.path.isfile(path) and path.endswith(".json"):
        d = json.load(open(path))
        em = d.get("episode_meta", d)
        ti = d.get("task_info", {})
        steps = d.get("steps") or []
        outcome = em.get("outcome", {})
        trajectory_id = os.path.splitext(os.path.basename(path))[0]
        yield (em.get("goal", ""), steps, os.path.dirname(path), trajectory_id,
              _difficulty(ti, em), outcome.get("success", False),
              outcome.get("infeasible", False), outcome.get("judge_verified"))
        return
    for meta_path in glob.glob(os.path.join(path, "**", "episode_meta.json"), recursive=True):
        ep_dir = os.path.dirname(meta_path)
        em = json.load(open(meta_path))
        jl = os.path.join(ep_dir, "episode.jsonl")
        steps = [json.loads(l) for l in open(jl)] if os.path.exists(jl) else []
        ti_path = os.path.join(ep_dir, "..", "..", "task_info.json")
        ti = json.load(open(ti_path)) if os.path.exists(ti_path) else {}
        outcome = em.get("outcome", {})
        trajectory_id = os.path.basename(ep_dir)
        yield (em.get("goal", ""), steps, ep_dir, trajectory_id, _difficulty(ti, em),
              outcome.get("success", False), outcome.get("infeasible", False),
              outcome.get("judge_verified"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="run directory or single episode json")
    ap.add_argument("out", nargs="?", default="train.jsonl")
    ap.add_argument("--require-judge", action="store_true",
                    help="only keep declared-success episodes whose "
                         "outcome.judge_verified is true (run judge_episodes.py "
                         "first); never-judged success episodes are dropped, "
                         "not silently trusted")
    args = ap.parse_args()

    all_examples, n_ep, n_kept, n_infeasible_kept, n_unjudged_dropped = [], 0, 0, 0, 0
    for (goal, steps, ep_dir, trajectory_id, diff, success, infeasible,
        judge_verified) in load_episodes(args.src):
        n_ep += 1
        if args.require_judge and success and not infeasible and judge_verified is None:
            n_unjudged_dropped += 1
        if not _include_episode(success, infeasible, judge_verified, args.require_judge):
            continue
        n_kept += 1
        n_infeasible_kept += int(infeasible)
        all_examples += episode_to_examples(goal, steps, ep_dir, diff, trajectory_id)

    all_examples.sort(key=lambda e: e["difficulty"])   # curriculum: easy -> hard
    with open(args.out, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")

    by_diff = {}
    for e in all_examples:
        by_diff[e["difficulty"]] = by_diff.get(e["difficulty"], 0) + 1
    loaded = sum(e["axtree_loaded"] for e in all_examples)
    print(f"episodes seen        : {n_ep}")
    print(f"successful (kept)    : {n_kept}")
    print(f"  of which infeasible : {n_infeasible_kept}  (teaches report_infeasible)")
    if args.require_judge:
        print(f"unjudged success episodes dropped: {n_unjudged_dropped} "
              f"(run judge_episodes.py first to include them)")
    print(f"SFT examples written : {len(all_examples)} -> {args.out}")
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
