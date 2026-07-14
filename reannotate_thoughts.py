"""Re-annotate collected trajectories' per-step `thought` into a richer
`thought_v2`: a terse state assessment, the step's subgoal (from an offline
replay of hsge.segmentation.segment_trajectory -- the same segmentation
Discovery uses live, just run after the fact over persisted steps), a
reflection on the prior action when it made no progress, and -- only on a
task's final step (send_msg_to_user / report_infeasible) -- a completion
check of whether the goal is genuinely satisfied by the final page.

The subgoal/completion-check text is written ONLY into the assistant target
(thought_v2), never into build_sft_dataset.py's user prompt: there is no
retrieval/grounding pipeline at inference time to supply "the current
subgoal" as an input, so putting it there would be a training/serving
mismatch. Here it teaches the model to *produce* subgoal-aware reasoning
instead.

thought_v2 is added next to (never replacing) the original `thought` in
episode.jsonl, so partially-annotated runs stay usable and re-running is
idempotent.

Usage:
    python reannotate_thoughts.py outputs/wa_run_09
    python reannotate_thoughts.py outputs/wa_run_09 --config config.yaml --limit 20
"""
from __future__ import annotations

import argparse
import glob
import json
import os

from build_sft_dataset import _read_axtree
from hsge.segmentation import segment_trajectory
from hsge.webarena.agents import step_outcome
from replay_segmentation import load_steps
from run_webarena import _effective_llm_config, _load_config, _load_dotenv

_SYS = (
    "You REWRITE one step's internal reasoning for a web agent's training "
    "data. You are given the step's GOAL, its SUBGOAL (or, for the final "
    "step of a task, a note that a final decision is being made), the "
    "action PRIOR to this one and its outcome (if any), the current page, "
    "and the action this step took. Produce a terse one-sentence STATE "
    "assessment of what the page currently shows. If the PRIOR action's "
    "outcome shows no progress or an error, write a one-sentence REFLECTION "
    "on why (empty string if the prior action clearly succeeded, or this is "
    "the first step). If this step is the FINAL step of the task (marked "
    "below), also judge in COMPLETION_CHECK whether the goal is actually "
    "satisfied by the current page -- not just whether the agent believes "
    "so (empty string otherwise). "
    'Return JSON {"state": "<one short sentence>", "reflection": "<sentence '
    'or empty string>", "completion_check": "<sentence or empty string>"}.'
)

_AXTREE_CAP = 4000


def _reannotate_prompt(goal: str, subgoal: str, is_final: bool,
                       prior_action: str | None, prior_outcome: str | None,
                       url: str, axtree: str, action: str) -> str:
    payload = {
        "goal": goal,
        "subgoal": subgoal if not is_final else "(final step -- deciding whether to finish)",
        "is_final_step": is_final,
        "prior_action": prior_action,
        "prior_outcome": prior_outcome,
        "url": url,
        "page": (axtree or "")[:_AXTREE_CAP],
        "action_taken": action,
    }
    return f"<payload>{json.dumps(payload)}</payload>"


def _compose_thought(original: str, state: str, reflection: str,
                     subgoal: str | None, is_segment_final: bool,
                     completion_check: str) -> str:
    """Join the re-annotated pieces into one compact string -- SOLVER_SYS's
    output format is {"thought": "<string>", ...}, so this stays a single
    field, not a nested structure. completion_check takes priority over
    subgoal (a step is either mid-subgoal or making the final call, never
    both)."""
    parts = [f"State: {state}."]
    if reflection:
        parts.append(f"Reflection: {reflection}.")
    if completion_check:
        parts.append(f"Completion check: {completion_check}.")
    elif subgoal:
        parts.append(f"Subgoal: {subgoal}.")
        if is_segment_final:
            parts.append("Subgoal complete.")
    parts.append(original.strip())
    return " ".join(p for p in parts if p)


def _segment_labels(llm, steps, site: str, task: str, axtree_sim: float) -> dict:
    """step index -> (subgoal, is_segment_final), from an offline
    segment_trajectory() replay over already-persisted steps."""
    subs = segment_trajectory(llm, steps, site=site, task=task, axtree_sim=axtree_sim)
    labels, idx = {}, 0
    for sub in subs:
        for j in range(len(sub.steps)):
            labels[idx] = (sub.subgoal, j == len(sub.steps) - 1)
            idx += 1
    return labels


def reannotate_episode(reannotate_llm, segment_llm, ep_dir: str, goal: str,
                       axtree_sim: float = 0.6) -> int:
    """Rewrite thought -> thought_v2 for every step in one episode's
    episode.jsonl, in place. Returns the number of steps rewritten."""
    steps = load_steps(ep_dir)
    if not steps:
        return 0
    seg_labels = _segment_labels(segment_llm, steps, site=ep_dir, task=goal,
                                 axtree_sim=axtree_sim)

    lines = [json.loads(l) for l in open(os.path.join(ep_dir, "episode.jsonl"))]
    n = 0
    for k, rec in enumerate(lines):
        if rec.get("record_type") != "step":
            continue
        action = rec.get("parsed_action", "")
        is_terminal = (action.startswith("send_msg_to_user")
                      or action.startswith("report_infeasible"))
        prior_action, prior_outcome = None, None
        if k > 0:
            prior_action = lines[k - 1].get("parsed_action", "")
            prior_outcome = step_outcome(
                lines[k - 1].get("url", ""), _read_axtree(ep_dir, lines[k - 1]),
                rec.get("url", ""), _read_axtree(ep_dir, rec))
        subgoal, is_seg_final = seg_labels.get(k, ("", False))
        prompt = _reannotate_prompt(
            goal, subgoal, is_terminal, prior_action, prior_outcome,
            rec.get("url", ""), _read_axtree(ep_dir, rec), action)
        out = reannotate_llm.complete_json(_SYS, prompt)
        rec["thought_v2"] = _compose_thought(
            original=rec.get("thought", ""),
            state=str(out.get("state", "")).strip(),
            reflection=str(out.get("reflection", "")).strip(),
            subgoal=subgoal if not is_terminal else None,
            is_segment_final=is_seg_final,
            completion_check=str(out.get("completion_check", "")).strip() if is_terminal else "")
        n += 1

    with open(os.path.join(ep_dir, "episode.jsonl"), "w") as f:
        for rec in lines:
            f.write(json.dumps(rec) + "\n")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--limit", type=int, default=10**9)
    ap.add_argument("--axtree-sim", type=float, default=0.6)
    args = ap.parse_args()

    _load_dotenv()
    llm_cfg = _load_config(args.config)["llm"]
    ns = argparse.Namespace(provider=None, model=None, base_url=None)
    from hsge.backends import OpenAILLM

    r_cfg = _effective_llm_config(ns, llm_cfg, "thought_reannotator")
    reannotate_llm = OpenAILLM(model=r_cfg["model"], base_url=r_cfg["base_url"],
                               api_key=r_cfg["api_key"], temperature=r_cfg["temperature"])
    s_cfg = _effective_llm_config(ns, llm_cfg, "trajectory_segmenter")
    segment_llm = OpenAILLM(model=s_cfg["model"], base_url=s_cfg["base_url"],
                            api_key=s_cfg["api_key"], temperature=s_cfg["temperature"])
    print(f"[llm:thought_reannotator] model={r_cfg['model']}  "
          f"[llm:trajectory_segmenter] model={s_cfg['model']}")

    episodes_dir = os.path.join(args.run_dir, "episodes")
    total = 0
    for meta_path in sorted(
            glob.glob(os.path.join(episodes_dir, "ep_*", "episode_meta.json")))[: args.limit]:
        ep_dir = os.path.dirname(meta_path)
        meta = json.load(open(meta_path))
        n = reannotate_episode(reannotate_llm, segment_llm, ep_dir, meta.get("goal", ""),
                               axtree_sim=args.axtree_sim)
        total += n
        print(f"  {os.path.basename(ep_dir)}: {n} steps re-annotated")
    print(f"\nre-annotated {total} steps total")


if __name__ == "__main__":
    main()
