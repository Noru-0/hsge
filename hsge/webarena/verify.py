"""Shared grader prompt for the offline judge (judge_episodes.py) and the live
inline GOAL verifier (runtime.py).

A leaf module -- it imports nothing from run_webarena/build_sft_dataset -- so
runtime.py can use it without the import cycle
runtime -> judge_episodes -> run_webarena -> runtime.
"""
import json

JUDGE_SYS = (
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


def judge_prompt(goal, history, final_url, final_axtree) -> str:
    payload = {
        "goal": goal,
        "actions_taken": history,
        "final_url": final_url,
        "final_page": (final_axtree or "")[:_AXTREE_CAP],
    }
    return f"<payload>{json.dumps(payload)}</payload>"
