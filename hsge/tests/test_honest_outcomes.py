"""Regression tests for the two P1 label-honesty defects found by auditing the
shopping_admin run (outputs/wa_eval_shopping_admin, 222 episodes):

  1. `infeasible` conflated "this cannot be done" with "I ran out of steps".
     27 of 56 infeasible episodes stopped at exactly the step budget, then the
     wrap-up call -- which is explicitly told the episode has stopped -- chose
     report_infeasible. build_sft_dataset.py kept every one of them as a valid
     target, teaching the model to give up.
  2. A state-changing task could be a success without anything changing:
     "[MOD] Send an email confirmation for order #000000299" was declared done
     in one step, zero browser actions, on the grounds it "was already sent".
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from build_sft_dataset import _include_episode
from hsge.schema import Step
from hsge.webarena.agents import Solver


class _FrozenBrowser:
    """Every action lands on the same page -- nothing ever changes."""

    def observation(self):
        return {"url": "http://x", "axtree": "[1] link 'a'"}

    def screenshot_b64(self, som=False):
        return None

    def act(self, action):
        return self.observation()


class _MovingBrowser:
    def __init__(self):
        self.n = 0

    def observation(self):
        return {"url": f"http://x/{self.n}", "axtree": f"[1] link 'a' {self.n}"}

    def screenshot_b64(self, som=False):
        return None

    def act(self, action):
        self.n += 1
        return self.observation()


# ---- 1. a wrap-up verdict is flagged, not passed off as the agent's own -----

class _NeverFinishesLLM:
    """Keeps acting until a guard stops the episode, then the wrap-up call
    (recognizable by its closing instruction) reports infeasible."""

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        if "Answer with one of those two actions only." in prompt:
            return {"thought": "out of options",
                    "action": "report_infeasible('the button does nothing')"}
        return {"thought": "keep trying", "action": f"click('{len(prompt) % 7}')"}


class _DeclaresInfeasibleLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"thought": "this site has no such feature",
                "action": "report_infeasible('Advanced Reporting needs a SaaS account')"}


def test_wrapup_infeasible_carries_the_guard_that_stopped_the_episode():
    steps, _, _, _, success, infeasible, stop_reason = Solver(
        _NeverFinishesLLM(), max_steps=6).solve(_FrozenBrowser(), "do the thing")

    assert infeasible is True
    assert stop_reason in ("budget", "stuck", "novelty")   # a guard ended it


def test_self_declared_infeasible_has_no_stop_reason():
    steps, _, _, _, success, infeasible, stop_reason = Solver(
        _DeclaresInfeasibleLLM(), max_steps=6).solve(_MovingBrowser(), "do the thing")

    assert infeasible is True
    assert stop_reason == ""     # the agent concluded this on its own, step 1


def test_only_a_self_declared_infeasible_is_an_sft_target():
    assert _include_episode(False, True, None, False, stop_reason="") is True
    assert _include_episode(False, True, None, False, stop_reason="budget") is False
    assert _include_episode(False, True, None, False, stop_reason="stuck") is False
    # episodes recorded before the field existed default to self-decided
    assert _include_episode(False, True, None, False) is True


def test_record_persists_the_stop_reason(tmp_path):
    from hsge.webarena.runtime import WebArenaExplorer

    ex = WebArenaExplorer.__new__(WebArenaExplorer)
    ex.out_dir = str(tmp_path)
    ex.episode = 0
    steps = [Step(action="report_infeasible('gave up')", url="http://x",
                  obs_summary="", axtree="[1] a")]
    ex._record("[MOD] do it", steps, ["[1] a"], [None], False, 1, "LOCAL",
               infeasible=True, stop_reason="budget")

    meta = json.load(open(tmp_path / "episodes" / "ep_0000" / "episode_meta.json"))
    assert meta["outcome"]["stop_reason"] == "budget"


# ---- 2. a state-changing task needs the page to have actually changed -------

class _DeclaresDoneImmediatelyLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"thought": "it was already sent",
                "action": "send_msg_to_user('done: already sent')"}


class _ActsThenDeclaresDoneLLM:
    def __init__(self):
        self.calls = 0

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls += 1
        if self.calls == 1:
            return {"thought": "save it", "action": "click('7')"}
        return {"thought": "saved", "action": "send_msg_to_user('done: saved')"}


def test_mod_task_declared_done_with_no_page_change_is_not_a_success():
    _, _, _, _, success, _, _ = Solver(_DeclaresDoneImmediatelyLLM()).solve(
        _FrozenBrowser(), "[MOD] Send an email confirmation for order #000000299")
    assert success is False


def test_composite_task_that_never_changed_the_page_is_not_a_success():
    """Zero executed actions at all -- the frozen browser is never even touched."""
    _, _, _, _, success, _, _ = Solver(_DeclaresDoneImmediatelyLLM()).solve(
        _FrozenBrowser(), "[COMPOSITE] Update the last name and save the order address")
    assert success is False


def test_mod_task_that_did_change_the_page_stays_a_success():
    _, _, _, _, success, _, _ = Solver(_ActsThenDeclaresDoneLLM()).solve(
        _MovingBrowser(), "[MOD] Update the price and save")
    assert success is True


def test_info_task_declared_done_with_no_page_change_is_still_a_success():
    """The gate is for state-changing tasks only: answering a question off the
    landing page is exactly what an INFO task should look like."""
    _, _, _, _, success, _, _ = Solver(_DeclaresDoneImmediatelyLLM()).solve(
        _FrozenBrowser(), "[INFO] Find the lifetime sales value")
    assert success is True
