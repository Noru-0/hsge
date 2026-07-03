"""Solver must not silently give up on a step when a vision-attached call
gets refused/empty -- retry once text-only before treating it as a dead end.
"""

from hsge.webarena.agents import Solver


class _FakeBrowser:
    def __init__(self):
        self.acted = []

    def observation(self):
        return {"url": "http://x", "axtree": "[1] link 'next'"}

    def screenshot_b64(self, som=False):
        return "ZmFrZQ=="

    def act(self, action):
        self.acted.append(action)
        return self.observation()


class _RefusesWithImageLLM:
    """Refuses (empty response) only when an image is attached; the
    text-only retry succeeds by declaring the goal done."""

    def __init__(self):
        self.calls = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls.append(image_b64)
        if image_b64:
            return {}
        return {"thought": "done", "action": "send_msg_to_user('done')"}


def test_solver_retries_without_image_when_vision_call_is_refused():
    llm = _RefusesWithImageLLM()
    solver = Solver(llm, vision=True)
    browser = _FakeBrowser()

    steps, obs_texts, obs_screenshots, final_obs, success = solver.solve(browser, "goal")

    assert success is True
    assert len(steps) == 1
    assert steps[0].action == "send_msg_to_user('done')"
    assert llm.calls == ["ZmFrZQ==", None]


class _LoopThenRecoverLLM:
    """Keeps clicking the same bid (as if it already arrived and doesn't
    recognize it) until the solver's repeated-action warning shows up in the
    prompt, then declares done -- simulates the ep_0004-style real-run loop
    where the same action succeeded twice in a row with no error and no
    progress, and the model needed an explicit nudge to stop."""

    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        if "WARNING" in prompt:
            return {"thought": "already there", "action": "send_msg_to_user('done')"}
        return {"thought": "click nav link", "action": "click('39')"}


def test_solver_warns_and_recovers_from_a_repeated_no_progress_action():
    """Regression: a real run showed the solver click the same bid 13-14
    times in a row (the target link keeps re-appearing under a new bid on
    the page it just navigated to) and burn the full max_steps budget on
    every such episode. Once the same action has succeeded twice in a row
    with no error, the solver must warn the model instead of silently
    repeating the prompt unchanged."""
    llm = _LoopThenRecoverLLM()
    solver = Solver(llm, max_steps=15)
    browser = _FakeBrowser()

    steps, obs_texts, obs_screenshots, final_obs, success = solver.solve(browser, "goal")

    assert success is True
    assert len(steps) == 3  # recovered on the 3rd call instead of burning all 15
    assert steps[-1].action == "send_msg_to_user('done')"
    assert any("WARNING" in p for p in llm.prompts)
