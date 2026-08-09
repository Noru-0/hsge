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
from urllib.parse import urlparse

from hsge.webarena.agents import (PageExplorer, SOLVER_SYS, build_solver_prompt,
                                  step_outcome)
from hsge.webarena.urls import relativize_goto

SYSTEM = SOLVER_SYS

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


def _last_action_error(thought: str) -> str:
    """The error text Solver.solve appended to a failed step's thought as
    ` [action error: <msg>]` (agents.py:607). The live Solver puts that message
    in the NEXT prompt's `LAST ACTION ERROR:` block, so the offline builder has
    to recover it to reproduce the prompt the recovery action was chosen from."""
    marker = "[action error:"
    i = (thought or "").find(marker)
    if i < 0:
        return ""
    return thought[i + len(marker):].rstrip().rstrip("]").strip()


def _is_off_origin_goto(action: str, url: str) -> bool:
    """A `goto` whose host differs from the page the agent is on.

    WebArena is a set of self-hosted clones; navigating to the public site the
    clone imitates ends the episode immediately with reward 0. Collection let
    one such action through -- goto('https://www.reddit.com/r/AskReddit/') on a
    Postmill instance -- and the fine-tuned model reproduced the pattern in 10
    of 57 reddit eval episodes. A same-host goto is legitimate (deep-linking a
    known URL) and stays."""
    a = (action or "").strip()
    if not a.startswith("goto("):
        return False
    target = a[len("goto("):-1].strip().strip("'\"")
    host = urlparse(target).netloc
    return bool(host) and host != urlparse(url or "").netloc


def _is_error_step(thought: str) -> bool:
    """A step whose recorded thought carries the '[action error: ...]' suffix
    Solver.solve appends when browser.act() raised (see agents.py::Solver.solve)
    -- the *next* LLM call saw the error and picked a different action, so this
    exact action was never added to Solver.solve's own `history`/`outcomes`
    either. It must not become an imitation target (it's the mistake, not the
    recovery) or appear in a later step's history."""
    return "[action error:" in (thought or "")


def _include_episode(success: bool, infeasible: bool, judge_verified: bool | None,
                     require_judge: bool, stop_reason: str = "") -> bool:
    """Whether one episode's steps should be turned into SFT examples.
    An infeasible episode is eligible only if the agent decided that WHILE
    solving (stop_reason ""); a non-empty stop_reason means a guard stopped the
    episode and the wrap-up call produced the report_infeasible after being told
    it had stopped -- that is a rationalization, not a conclusion, and training
    on it teaches the model to give up. 27 of the 56 infeasible episodes in the
    shopping_admin run ended at exactly the step budget this way. Episodes
    recorded before stop_reason existed have no key and are treated as
    self-decided, since nothing can distinguish them retroactively.
    A plain success is eligible unless --require-judge is set, in which case it
    needs judge_verified is True -- an episode never judged (judge_verified is
    None) is dropped, not silently trusted, so --require-judge fails safe.

    --require-judge holds infeasible episodes to that SAME bar. It used not to:
    the infeasible branch short-circuited above the judge check, and since
    judge_episodes.py only ever judges declared-SUCCESS episodes, every kept
    infeasible episode was unverified by construction -- exactly the silent
    trust the flag promises not to extend. Measured on the four collection runs
    behind train_all.jsonl, that admitted 136 give-ups (868 examples, 23% of the
    dataset), concentrated on the hard task class: 75 of 191 COMPOSITE
    trajectories (39%) ended in report_infeasible, over reasons that were
    collection-time artifacts rather than impossibility ("Too many failed login
    attempts", "askscience forum not found" on a site that has one). The model
    trained on it reported infeasible on 22 of 57 reddit eval tasks (39%,
    matching that rate), 15 of them self-decided, including three separate
    "change my bio" tasks whose edit link was verified present."""
    if infeasible:
        if stop_reason:
            return False
        return judge_verified is True if require_judge else True
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
    last_error = ""           # mirrors Solver.solve's `last_error` across steps
    for k, step in enumerate(steps):
        target_action = step.get("parsed_action") or ""
        if not target_action:
            continue
        thought = thoughts[k]
        if _is_error_step(step.get("thought", "")):
            # Not a target (it's the mistake), but the error it produced is what
            # the live Solver showed the NEXT call -- carry it forward.
            last_error = _last_action_error(step.get("thought", ""))
            continue
        step_error, last_error = last_error, ""
        if _is_off_origin_goto(target_action, urls[k]):
            # Leaves the site and ends the episode at reward 0; never imitate it.
            # It stays in `history` below, because it really did execute.
            history.append(f"- {relativize_goto(target_action, urls[k])} -> "
                          + step_outcome(urls[k], axtrees[k],
                                        urls[k + 1] if k + 1 < len(steps) else urls[k],
                                        axtrees[k + 1] if k + 1 < len(steps) else axtrees[k]))
            continue
        assistant = json.dumps({"thought": thought,
                                "action": relativize_goto(target_action, urls[k])})
        user = build_solver_prompt(goal, history, step_error, urls[k],
                                    axtrees[k] or "[accessibility tree omitted]")
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
            history.append(f"- {relativize_goto(target_action, urls[k])} -> {outcome}")
    return examples


_TERMINAL_PREFIXES = ("send_msg_to_user", "report_infeasible")


def _n_browser_actions(steps: list[dict]) -> int:
    """How many steps actually acted on the page.

    send_msg_to_user / report_infeasible end an episode without touching it, so an
    episode made only of those taught the model to answer, never to act. On a real
    158-node reddit run 244 of 560 successful episodes (44%) were exactly that --
    an INFO question the solver answered straight off the landing page.
    """
    return sum(1 for s in steps
               if (s.get("parsed_action") or "").strip()
               and not (s.get("parsed_action") or "").strip().startswith(_TERMINAL_PREFIXES))


def load_episodes(path: str):
    """Yield (goal, steps, episode_dir, trajectory_id, difficulty, success,
    infeasible, judge_verified, stop_reason) tuples. judge_verified is None if
    the episode has never been through judge_episodes.py; stop_reason is "" for
    an episode that ended on a terminal action of its own (and for every episode
    recorded before the field existed)."""
    if os.path.isfile(path) and path.endswith(".json"):
        d = json.load(open(path, encoding="utf-8"))
        em = d.get("episode_meta", d)
        ti = d.get("task_info", {})
        steps = d.get("steps") or []
        outcome = em.get("outcome", {})
        trajectory_id = os.path.splitext(os.path.basename(path))[0]
        yield (em.get("goal", ""), steps, os.path.dirname(path), trajectory_id,
              _difficulty(ti, em), outcome.get("success", False),
              outcome.get("infeasible", False), outcome.get("judge_verified"),
              outcome.get("stop_reason", ""))
        return
    for meta_path in glob.glob(os.path.join(path, "**", "episode_meta.json"), recursive=True):
        ep_dir = os.path.dirname(meta_path)
        em = json.load(open(meta_path, encoding="utf-8"))
        jl = os.path.join(ep_dir, "episode.jsonl")
        steps = [json.loads(l) for l in open(jl, encoding="utf-8")] if os.path.exists(jl) else []
        ti_path = os.path.join(ep_dir, "..", "..", "task_info.json")
        ti = json.load(open(ti_path, encoding="utf-8")) if os.path.exists(ti_path) else {}
        outcome = em.get("outcome", {})
        trajectory_id = os.path.basename(ep_dir)
        yield (em.get("goal", ""), steps, ep_dir, trajectory_id, _difficulty(ti, em),
              outcome.get("success", False), outcome.get("infeasible", False),
              outcome.get("judge_verified"), outcome.get("stop_reason", ""))


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
    ap.add_argument("--min-actions", type=int, default=0, metavar="N",
                    help="drop episodes with fewer than N steps that actually act on "
                         "the page (send_msg_to_user/report_infeasible do not count). "
                         "0 = keep everything (default). Use 1 to exclude "
                         "answer-only INFO episodes, which were 44%% of the "
                         "successes in a real reddit run. report_infeasible "
                         "episodes are exempt -- refusing IS their target.")
    args = ap.parse_args()

    all_examples, n_ep, n_kept, n_infeasible_kept, n_unjudged_dropped = [], 0, 0, 0, 0
    n_too_few_actions = n_wrapup_infeasible_dropped = 0
    for (goal, steps, ep_dir, trajectory_id, diff, success, infeasible,
        judge_verified, stop_reason) in load_episodes(args.src):
        n_ep += 1
        if infeasible and stop_reason:
            n_wrapup_infeasible_dropped += 1
        if args.require_judge and success and not infeasible and judge_verified is None:
            n_unjudged_dropped += 1
        if not _include_episode(success, infeasible, judge_verified,
                                args.require_judge, stop_reason):
            continue
        if (args.min_actions and not infeasible
                and _n_browser_actions(steps) < args.min_actions):
            n_too_few_actions += 1
            continue
        n_kept += 1
        n_infeasible_kept += int(infeasible)
        all_examples += episode_to_examples(goal, steps, ep_dir, diff, trajectory_id)

    all_examples.sort(key=lambda e: e["difficulty"])   # curriculum: easy -> hard
    with open(args.out, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")

    by_diff = {}
    for e in all_examples:
        by_diff[e["difficulty"]] = by_diff.get(e["difficulty"], 0) + 1
    loaded = sum(e["axtree_loaded"] for e in all_examples)
    thought_v2_count = sum(1 for e in all_examples
                           if "State:" in json.loads(e["messages"][2]["content"])["thought"])
    subgoal_count = sum(1 for e in all_examples
                        if "Subgoal:" in json.loads(e["messages"][2]["content"])["thought"])
    print(f"episodes seen        : {n_ep}")
    print(f"successful (kept)    : {n_kept}")
    print(f"  of which infeasible : {n_infeasible_kept}  (teaches report_infeasible)")
    if n_wrapup_infeasible_dropped:
        print(f"dropped, wrap-up infeasible: {n_wrapup_infeasible_dropped} "
              f"(a guard stopped the episode and the wrap-up rationalized it)")
    if args.require_judge:
        print(f"unjudged success episodes dropped: {n_unjudged_dropped} "
              f"(run judge_episodes.py first to include them)")
    if args.min_actions:
        print(f"dropped, < {args.min_actions} real action(s): {n_too_few_actions} "
              f"(answer-only episodes, no page interaction)")
    print(f"SFT examples written : {len(all_examples)} -> {args.out}")
    print(f"examples by difficulty: {dict(sorted(by_diff.items()))}")
    print(f"with real AXTree text : {loaded}/{len(all_examples)} "
          f"(rest need the run dir's page_state/*.txt files)")
    print(f"re-annotated thoughts : {thought_v2_count}/{len(all_examples)} "
          f"(run reannotate_thoughts.py first to raise this)")
    print(f"with subgoal in target: {subgoal_count}/{len(all_examples)}")
    if all_examples:
        print("\n--- example[0] (truncated) ---")
        ex = all_examples[0]
        print("system   :", ex["messages"][0]["content"][:90], "...")
        print("user     :", ex["messages"][1]["content"][:120].replace("\n", " "), "...")
        print("assistant:", ex["messages"][2]["content"][:120], "...")


if __name__ == "__main__":
    main()
