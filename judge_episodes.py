"""Judge pass: catch false-positive `success` episodes before they enter SFT
training data.

For a non-predicate task (LOCAL, and most GOAL tasks without a terminal
predicate), "success" in episode_meta.json only means the Solver itself
called send_msg_to_user without an error (see hsge/webarena/agents.py::
Solver.solve) -- the agent is grading its own homework. A strong judge model
re-checks each declared-success episode against its own final state and
appends outcome.judge_verified / outcome.judge_reason to episode_meta.json
IN PLACE (additive, never destructive -- outcome.success is left untouched
so the raw collection record stays intact). build_sft_dataset.py's
--require-judge flag then requires judge_verified in addition to success.

Usage:
    python judge_episodes.py outputs/wa_run_09
    python judge_episodes.py outputs/wa_run_09 --config config.yaml --limit 50
"""
from __future__ import annotations

import argparse
import glob
import json
import os

from build_sft_dataset import _read_axtree
from run_webarena import _effective_llm_config, _load_config, _load_dotenv

_SYS = (
    "You are a strict grader of a web agent's completed task. You are given "
    "the GOAL the agent was told to accomplish, the actions it took before "
    "declaring the task done, and the FINAL page (URL + accessibility tree) "
    "where it declared done. Decide whether the goal was genuinely achieved "
    "by the final state -- not whether the agent SAID it was done. Common "
    "false positives: the agent gave up and declared done anyway; it "
    "answered an INFO question with a guess not actually shown on the final "
    "page; it navigated to the wrong page. "
    'Return JSON {"verdict": "PASS"|"FAIL", "reason": "<one sentence>"}.'
)

_AXTREE_CAP = 4000


def _judge_prompt(goal: str, history: list[str], final_url: str, final_axtree: str) -> str:
    payload = {
        "goal": goal,
        "actions_taken": history,
        "final_url": final_url,
        "final_page": (final_axtree or "")[:_AXTREE_CAP],
    }
    return f"<payload>{json.dumps(payload)}</payload>"


def judge_episode(llm, ep_dir: str) -> dict:
    """Return {"judge_verified": bool, "judge_reason": str} for one episode."""
    steps = []
    for line in open(os.path.join(ep_dir, "episode.jsonl"), encoding="utf-8"):
        rec = json.loads(line)
        if rec.get("record_type") == "step":
            steps.append(rec)
    if not steps:
        return {"judge_verified": False, "judge_reason": "no steps recorded"}
    meta = json.load(open(os.path.join(ep_dir, "episode_meta.json"), encoding="utf-8"))
    goal = meta.get("goal", "")
    history = [rec.get("parsed_action", "") for rec in steps[:-1]]
    final = steps[-1]
    final_axtree = _read_axtree(ep_dir, final)
    out = llm.complete_json(_SYS, _judge_prompt(goal, history, final.get("url", ""), final_axtree))
    verdict = str(out.get("verdict", "")).strip().upper()
    return {"judge_verified": verdict == "PASS",
            "judge_reason": str(out.get("reason", ""))[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--limit", type=int, default=10**9)
    args = ap.parse_args()

    _load_dotenv()
    ns = argparse.Namespace(provider=None, model=None, base_url=None)
    cfg = _effective_llm_config(ns, _load_config(args.config)["llm"], "episode_judge")
    from hsge.backends import OpenAILLM
    print(f"[llm:episode_judge] provider={cfg['provider']} model={cfg['model']}")
    llm = OpenAILLM(model=cfg["model"], base_url=cfg["base_url"],
                    api_key=cfg["api_key"], temperature=cfg["temperature"])

    episodes_dir = os.path.join(args.run_dir, "episodes")
    checked, verified = 0, 0
    for ep_dir in sorted(glob.glob(os.path.join(episodes_dir, "ep_*")))[: args.limit]:
        meta_path = os.path.join(ep_dir, "episode_meta.json")
        meta = json.load(open(meta_path, encoding="utf-8"))
        if not meta.get("outcome", {}).get("success"):
            continue
        checked += 1
        result = judge_episode(llm, ep_dir)
        meta["outcome"]["judge_verified"] = result["judge_verified"]
        meta["outcome"]["judge_reason"] = result["judge_reason"]
        json.dump(meta, open(meta_path, "w", encoding="utf-8"), indent=2)
        verified += int(result["judge_verified"])
        print(f"  {os.path.basename(ep_dir)}: "
              f"{'PASS' if result['judge_verified'] else 'FAIL'} -- {result['judge_reason']}")
    print(f"\njudged {checked} declared-success episodes, {verified} verified "
          f"({checked - verified} false positives caught)")


if __name__ == "__main__":
    main()
