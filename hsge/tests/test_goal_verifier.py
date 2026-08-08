"""Inline GOAL verifier flips a self-declared success to fail when the final
page does not satisfy the goal (reuses the judge_episodes grader prompt).
Run: PYTHONPATH=. python -m pytest hsge/tests/test_goal_verifier.py -q
"""
import json
import os
import tempfile
from unittest import mock

from hsge.llm import HashingEmbedder, MockLLM
from hsge.schema import Step
from hsge.webarena.runtime import WebArenaExplorer


class _Judge:
    def __init__(self, verdict):
        self.verdict = verdict

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"verdict": self.verdict, "reason": "r"}


def _ex(judge, **kw):
    ex = WebArenaExplorer(browser_factory=lambda u: None, llm=MockLLM(),
                          embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
                          allow_pattern=".*", terminal_goal=None, verify_goals=True, **kw)
    ex.judge_llm = judge
    return ex


def test_verify_episode_pass_and_fail():
    steps = [Step(action="click('1')", url="http://x/1", axtree="a"),
             Step(action="send_msg_to_user('done')", url="http://x/2", axtree="b")]
    obs = {"url": "http://x/2", "axtree": "b"}
    assert _ex(_Judge("PASS"))._verify_episode("goal", steps, obs)[0] is True
    assert _ex(_Judge("FAIL"))._verify_episode("goal", steps, obs)[0] is False


def test_record_writes_judge_fields():
    ex = _ex(_Judge("FAIL"))
    steps = [Step(action="send_msg_to_user('done')", url="http://x", axtree="b")]
    ex._record("goal", steps, ["b"], [None], success=True, difficulty=2, tag="GOAL",
               judge_verified=False, judge_reason="gave up")
    meta = json.load(open(os.path.join(ex.out_dir, "episodes", "ep_0000",
                                       "episode_meta.json"), encoding="utf-8"))
    assert meta["outcome"]["judge_verified"] is False
    assert meta["outcome"]["judge_reason"] == "gave up"


def test_solve_with_retries_demotes_unverified_goal_success():
    ex = _ex(_Judge("FAIL"))
    steps = [Step(action="send_msg_to_user('done')", url="http://x", axtree="b")]
    with mock.patch.object(
            ex.solver, "solve",
            return_value=(steps, ["b"], [None], {"url": "http://x", "axtree": "b"}, True, False, "")):
        _, _, _, success, infeasible, *_ = ex._solve_with_retries(
            mock.MagicMock(), "goal", difficulty=2, tag="GOAL",
            goal_predicate=None, verify_fn=ex._verify_episode)
    assert success is False


def test_verify_skipped_when_goal_predicate_present():
    # a deterministic reached() result is already trustworthy -> never re-judge it
    ex = _ex(_Judge("FAIL"))
    steps = [Step(action="send_msg_to_user('done')", url="http://x", axtree="b")]
    with mock.patch.object(
            ex.solver, "solve",
            return_value=(steps, ["b"], [None], {"url": "http://x", "axtree": "b"}, True, False, "")):
        _, _, _, success, *_ = ex._solve_with_retries(
            mock.MagicMock(), "goal", difficulty=2, tag="GOAL",
            goal_predicate="order_confirmed", verify_fn=ex._verify_episode)
    assert success is True   # not demoted -- verifier not consulted
