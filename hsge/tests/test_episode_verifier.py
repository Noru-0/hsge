"""Inline episode verifier: NO episode is a success on the agent's own word.

Every self-declared success (`send_msg_to_user`, i.e. `goal_predicate is None`)
is re-judged against its final page by the `episode_judge` model, and a FAIL is
demoted to fail -- for LOCAL, UNPREFIXED and GOAL alike. Only a deterministic
`reached()` success is trusted without a judge.

Why every tag and not just GOAL (the original B1 scope): running
judge_episodes.py over outputs/wa_eval_shopping_1 after the fact found **198 of
465 declared successes (43%) were false**, concentrated in the LOCAL/INFO tasks
that were never verified live (149 of 313 INFO successes failed the judge). A
verdict that only lands in the artifacts after an optional offline pass is a
verdict the run itself never acts on: the false successes still fed Discovery,
still seeded the unprefixed pass, and still counted in summary.json.

Run: PYTHONPATH=. python -m pytest hsge/tests/test_episode_verifier.py -q
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
        self.calls = 0

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls += 1
        return {"verdict": self.verdict, "reason": "r"}


def _ex(judge, **kw):
    kw.setdefault("verify_episodes", True)
    ex = WebArenaExplorer(browser_factory=lambda u: None, llm=MockLLM(),
                          embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
                          allow_pattern=".*", terminal_goal=None, **kw)
    ex.judge_llm = judge
    return ex


_DONE = [Step(action="send_msg_to_user('done')", url="http://x", axtree="b")]


def _solve(ex, tag="LOCAL", goal_predicate=None, steps=None):
    steps = _DONE if steps is None else steps
    final = {"url": "http://x", "axtree": "b"}
    with mock.patch.object(ex.solver, "solve",
                           return_value=(steps, ["b"], [None], final, True, False, "")):
        return ex._solve_with_retries(mock.MagicMock(), "goal", difficulty=1, tag=tag,
                                       goal_predicate=goal_predicate)


def test_verify_episode_pass_and_fail():
    steps = [Step(action="click('1')", url="http://x/1", axtree="a"),
             Step(action="send_msg_to_user('done')", url="http://x/2", axtree="b")]
    obs = {"url": "http://x/2", "axtree": "b"}
    assert _ex(_Judge("PASS"))._verify_episode("goal", steps, obs)[0] is True
    assert _ex(_Judge("FAIL"))._verify_episode("goal", steps, obs)[0] is False


def test_record_writes_judge_fields():
    ex = _ex(_Judge("FAIL"))
    ex._record("goal", _DONE, ["b"], [None], success=True, difficulty=2, tag="GOAL",
               judge_verified=False, judge_reason="gave up")
    meta = json.load(open(os.path.join(ex.out_dir, "episodes", "ep_0000",
                                       "episode_meta.json"), encoding="utf-8"))
    assert meta["outcome"]["judge_verified"] is False
    assert meta["outcome"]["judge_reason"] == "gave up"


def test_a_local_success_is_judged_and_demoted():
    """The 43%-false-success case: a LOCAL/INFO task the agent declared done."""
    ex = _ex(_Judge("FAIL"))
    _, _, _, success, *_ = _solve(ex, tag="LOCAL")

    assert success is False
    meta = json.load(open(os.path.join(ex.out_dir, "episodes", "ep_0000",
                                       "episode_meta.json"), encoding="utf-8"))
    assert meta["outcome"]["success"] is False
    assert meta["outcome"]["judge_verified"] is False


def test_a_verified_local_success_survives_and_is_marked():
    ex = _ex(_Judge("PASS"))
    _, _, _, success, *_ = _solve(ex, tag="LOCAL")

    assert success is True
    meta = json.load(open(os.path.join(ex.out_dir, "episodes", "ep_0000",
                                       "episode_meta.json"), encoding="utf-8"))
    assert meta["outcome"]["judge_verified"] is True     # --require-judge can use it


def test_unprefixed_episodes_are_judged_too():
    ex = _ex(_Judge("FAIL"))
    _, _, _, success, *_ = _solve(ex, tag="UNPREFIXED")
    assert success is False


def test_goal_success_is_still_judged():
    ex = _ex(_Judge("FAIL"))
    _, _, _, success, *_ = _solve(ex, tag="GOAL")
    assert success is False


def test_verify_skipped_when_goal_predicate_present():
    # a deterministic reached() result is already trustworthy -> never re-judge it
    judge = _Judge("FAIL")
    ex = _ex(judge)
    _, _, _, success, *_ = _solve(ex, tag="GOAL", goal_predicate="order_confirmed")

    assert success is True          # not demoted
    assert judge.calls == 0         # and not even consulted


def test_no_judge_calls_when_verification_is_disabled():
    judge = _Judge("FAIL")
    ex = _ex(judge, verify_episodes=False)
    _, _, _, success, *_ = _solve(ex, tag="LOCAL")

    assert success is True          # old behaviour: the agent's word is taken
    assert judge.calls == 0


def test_a_demoted_success_never_reaches_discovery():
    """A false success must not become a skill: it used to be segmented,
    clustered and (at maturity) promoted to a planning operator."""
    ex = _ex(_Judge("FAIL"))
    steps = [Step(action="click('1')", url="http://x/1", obs_summary="", axtree="a"),
             Step(action="send_msg_to_user('done')", url="http://x/2", obs_summary="",
                  axtree="b")]
    _, _, _, success, *_ = _solve(ex, tag="LOCAL", steps=steps)

    assert success is False
    assert ex.library.subtrajs == {}     # nothing ingested
