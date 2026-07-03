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
