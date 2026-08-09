"""Regression tests for the three P0 data-quality defects found by auditing the
shopping_admin run (outputs/wa_eval_shopping_admin, 222 episodes):

  1. BrowserGym never raises on a failed action -- it returns it as
     obs["last_action_error"] -- so WebArenaBrowser.act reported a failure as a
     normal step. Measured: 0/222 episodes carried the "[action error:" marker
     although 70/1683 steps called fill()/click() with a field label instead of
     a bid, and 6 episodes containing such a step were marked success.
  2. Step.obs_summary was thought[:100], and runtime.py persists it verbatim as
     the SFT target's reasoning. Measured: 694/1683 steps (41.2%) sat exactly at
     the ceiling, cut mid-word.
  3. outcome.response was hardcoded to "". Measured: 0/222 episodes had one,
     although 44 successes ended on send_msg_to_user('done: <the answer>').
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from hsge.schema import Step
from hsge.segmentation import segment_trajectory
from hsge.webarena.agents import Solver, terminal_message


# ---- 1. failed actions must surface ---------------------------------------

class _FailingBrowser:
    """Fails the first action, succeeds afterwards -- mirrors BrowserGym's
    contract once WebArenaBrowser.act re-raises last_action_error."""

    def __init__(self):
        self.acted = []

    def observation(self):
        return {"url": "http://x", "axtree": f"[1] link 'next' {len(self.acted)}"}

    def screenshot_b64(self, som=False):
        return None

    def act(self, action):
        self.acted.append(action)
        if len(self.acted) == 1:
            from hsge.webarena.browser import ActionError
            raise ActionError("ValueError: Could not find element with bid '[global] Price * $'")
        return self.observation()


class _BadBidThenGoodLLM:
    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        if "Could not find element with bid" in prompt:
            return {"thought": "that bid was a label, use the real bid",
                    "action": "send_msg_to_user('done')"}
        return {"thought": "fill the price", "action": "fill('[global] Price * $','19.99')"}


def test_failed_action_is_marked_and_fed_back_to_the_solver():
    llm = _BadBidThenGoodLLM()
    solver = Solver(llm, max_steps=5)
    browser = _FailingBrowser()

    steps, _, _, _, success, infeasible, _ = solver.solve(browser, "set the price")

    # the failed step carries the marker build_sft_dataset.py filters on
    assert "[action error:" in steps[0].obs_summary
    # ...and the error reached the next prompt, so the model could recover
    assert any("# Error Message from Last Action\nValueError: Could not find "
               "element with bid" in p for p in llm.prompts)
    assert success is True


def test_browser_act_raises_on_last_action_error():
    """WebArenaBrowser.act must read BrowserGym's last_action_error key. Built
    without a real browser: only act()'s own body is exercised."""
    from hsge.webarena.browser import ActionError, WebArenaBrowser

    class _StubEnv:
        def __init__(self, err):
            self.err = err

        def step(self, action):
            return ({"url": "http://x", "last_action_error": self.err},
                    0.0, False, False, {})

    browser = WebArenaBrowser.__new__(WebArenaBrowser)   # skip gym.make
    browser.env = _StubEnv("TimeoutError: Timeout 10000ms exceeded.")
    browser._last_obs = None
    browser.terminated = False
    with pytest.raises(ActionError, match="Timeout"):
        browser.act("click('99')")
    # the observation is still updated, so a caller that catches stays consistent
    assert browser._last_obs["url"] == "http://x"

    browser.env = _StubEnv("")
    assert browser.act("click('1')")["url"] == "http://x"


# ---- 2. thoughts are persisted in full ------------------------------------

class _LongThoughtLLM:
    THOUGHT = ("I need to open the order view page first because the address form "
               "is only reachable from there, and only then can I edit the last "
               "name field and press save to persist the change.")

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"thought": self.THOUGHT, "action": "send_msg_to_user('done: ok')"}


class _NoopBrowser:
    def observation(self):
        return {"url": "http://x", "axtree": "[1] link 'next'"}

    def screenshot_b64(self, som=False):
        return None

    def act(self, action):
        return self.observation()


def test_solver_keeps_the_whole_thought():
    llm = _LongThoughtLLM()
    steps, _, _, _, _, _, _ = Solver(llm).solve(_NoopBrowser(), "goal")

    assert len(_LongThoughtLLM.THOUGHT) > 100
    assert steps[0].obs_summary == _LongThoughtLLM.THOUGHT


def test_segmentation_prompt_still_caps_the_thought_at_100_chars():
    """The cap moved to the prompt site rather than disappearing -- the
    segmentation payload must not grow because of the fix above."""
    long = "x" * 500
    steps = [Step(action="click('1')", url="http://a", obs_summary=long, axtree="a"),
             Step(action="click('2')", url="http://b", obs_summary=long, axtree="b")]

    class _CapturingLLM:
        def __init__(self):
            self.prompt = ""

        def complete_json(self, system, prompt, **kw):
            self.prompt = prompt
            return {"segments": []}

    llm = _CapturingLLM()
    segment_trajectory(llm, steps, "site", "task")
    payload = json.loads(llm.prompt.split("<payload>")[1].split("</payload>")[0])
    assert all(len(s["obs"]) <= 100 for s in payload["steps"])


# ---- 3. the terminal message becomes outcome.response ----------------------

@pytest.mark.parametrize("action,expected", [
    ("send_msg_to_user('done: Lifetime Sales value is $194.40')",
     "done: Lifetime Sales value is $194.40"),
    ('send_msg_to_user("done: it\'s $12")', "done: it's $12"),
    ("report_infeasible('Advanced Reporting requires a SaaS account')",
     "Advanced Reporting requires a SaaS account"),
    ("click('679')", ""),
    ("", ""),
])
def test_terminal_message_extracts_the_argument(action, expected):
    assert terminal_message(action) == expected


def test_record_writes_the_answer_into_outcome_response(tmp_path):
    from hsge.webarena.runtime import WebArenaExplorer

    ex = WebArenaExplorer.__new__(WebArenaExplorer)   # no backends needed
    ex.out_dir = str(tmp_path)
    ex.episode = 0
    steps = [Step(action="send_msg_to_user('done: Lifetime Sales value is $194.40')",
                  url="http://x", obs_summary="found it", axtree="[1] text")]
    ex._record("[INFO] Find the lifetime sales value", steps, ["[1] text"], [None],
               True, 1, "LOCAL")

    meta = json.load(open(tmp_path / "episodes" / "ep_0000" / "episode_meta.json"))
    assert meta["outcome"]["response"] == "done: Lifetime Sales value is $194.40"
