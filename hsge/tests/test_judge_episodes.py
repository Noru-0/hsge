"""judge_episodes.py: catch false-positive declared-success episodes by
asking a judge LLM to re-check the final state against the goal, appending
outcome.judge_verified / outcome.judge_reason to episode_meta.json in place.

Run:  python -m pytest hsge/tests/test_judge_episodes.py -q
 (or) PYTHONPATH=. python hsge/tests/test_judge_episodes.py
"""
import json
import os
import tempfile

from judge_episodes import judge_episode


def _write_episode(success, goal, final_url, final_axtree):
    ep_dir = tempfile.mkdtemp()
    os.makedirs(os.path.join(ep_dir, "page_state"), exist_ok=True)
    meta = {"kind": "low_level_trajectory", "goal": goal,
            "outcome": {"success": success, "reward": 1.0 if success else 0.0,
                        "response": "", "infeasible": False},
            "metadata": {"difficulty": 1, "tags": ["LOCAL"]}, "step_count": 1}
    json.dump(meta, open(os.path.join(ep_dir, "episode_meta.json"), "w"))
    rel = "page_state/step_000_axtree.txt"
    open(os.path.join(ep_dir, rel), "w").write(final_axtree)
    rec = {"record_type": "step", "index": 0, "url": final_url,
           "action": json.dumps({"thought": "done", "action": "send_msg_to_user('done')"}),
           "parsed_action": "send_msg_to_user('done')", "thought": "done",
           "observation": {"axtree_txt": {"path": rel}}}
    with open(os.path.join(ep_dir, "episode.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    return ep_dir


class _StubLLM:
    def __init__(self, verdict, reason):
        self.verdict, self.reason = verdict, reason
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        return {"verdict": self.verdict, "reason": self.reason}


def test_judge_passes_a_genuinely_completed_goal():
    ep_dir = _write_episode(True, "go to the wiki page", "http://x/wiki",
                            "[7] heading 'Wiki'")
    llm = _StubLLM("PASS", "the URL and page both confirm the wiki page")

    result = judge_episode(llm, ep_dir)

    assert result["judge_verified"] is True
    assert "wiki" in result["judge_reason"]


def test_judge_catches_a_false_positive():
    ep_dir = _write_episode(True, "find the number of notifications",
                            "http://x/", "[1] link 'Notifications'")
    llm = _StubLLM("FAIL", "the notification count is not shown anywhere on this page")

    result = judge_episode(llm, ep_dir)

    assert result["judge_verified"] is False


def test_judge_prompt_includes_goal_and_final_url():
    ep_dir = _write_episode(True, "go to the wiki page", "http://x/wiki", "ax")
    llm = _StubLLM("PASS", "ok")

    judge_episode(llm, ep_dir)

    assert "go to the wiki page" in llm.prompts[0]
    assert "http://x/wiki" in llm.prompts[0]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
