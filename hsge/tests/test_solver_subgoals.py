"""Solver subgoal mode: pursue an ordered subgoal list one at a time, advancing
on the model's subgoal_done signal or a per-subgoal step cap.
Run: PYTHONPATH=. python -m pytest hsge/tests/test_solver_subgoals.py -q
"""
from hsge.webarena.agents import Solver


class _Browser:
    terminated = False

    def __init__(self):
        self.n = 0

    def observation(self):
        return {"url": f"http://x/{self.n}", "axtree": f"p{self.n}"}

    def act(self, a):
        self.n += 1
        return self.observation()

    def screenshot_b64(self, som=True):
        return None


class _ScriptLLM:
    """subgoal_done for subgoal 1, then finish on subgoal 2."""
    def __init__(self):
        self.calls = 0
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        self.calls += 1
        if self.calls == 1:
            return {"thought": "did A", "action": "click('1')", "subgoal_done": True}
        return {"thought": "done", "action": "send_msg_to_user('done')"}


def test_subgoal_mode_shows_current_subgoal_and_advances():
    llm = _ScriptLLM()
    steps, _, _, _, success, _, _ = Solver(llm, max_steps=10).solve(
        _Browser(), "overall goal", subgoals=["do A", "do B"])
    assert "CURRENT SUBGOAL (1/2): do A" in llm.prompts[0]
    assert any("CURRENT SUBGOAL (2/2): do B" in p for p in llm.prompts)
    assert success is True


class _CapturingDone:
    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        return {"thought": "done", "action": "send_msg_to_user('done')"}


def test_no_subgoals_leaves_prompt_unchanged():
    llm = _CapturingDone()
    _, _, _, _, success, _, _ = Solver(llm, max_steps=5).solve(_Browser(), "g")
    assert success is True
    assert "CURRENT SUBGOAL" not in llm.prompts[0]


class _NeverDone:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"thought": "work", "action": "click('1')"}


class _HijackLLM:
    """Reproduces run v3: gpt-4o-mini emits the advance as a TERMINAL action
    send_msg_to_user('subgoal_done...') instead of the JSON field, which used to
    end the episode at subgoal 1."""
    def __init__(self):
        self.calls = 0
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        self.calls += 1
        if self.calls == 1:
            return {"thought": "sub1 done",
                    "action": "send_msg_to_user('subgoal_done: page open')"}
        return {"thought": "finish", "action": "send_msg_to_user('done')"}


def test_send_msg_on_nonlast_subgoal_advances_not_terminates():
    llm = _HijackLLM()
    steps, _, _, _, success, _, _ = Solver(llm, max_steps=10).solve(
        _Browser(), "goal", subgoals=["do A", "do B"])
    # must NOT end at subgoal 1: it reached the 2/2 subgoal and only then finished
    assert any("CURRENT SUBGOAL (2/2): do B" in p for p in llm.prompts)
    assert success is True


def test_per_subgoal_cap_auto_advances():
    # never signals subgoal_done -> the cap advances through subgoals; the last
    # subgoal then runs until the outer budget, so we see the final subgoal shown.
    llm_prompts = []

    class _Rec(_NeverDone):
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            llm_prompts.append(prompt)
            return super().complete_json(system, prompt, image_b64, image_detail)

    Solver(_Rec(), max_steps=Solver._SUBGOAL_CAP + 3).solve(
        _Browser(), "g", subgoals=["A", "B"])
    assert any("CURRENT SUBGOAL (2/2): B" in p for p in llm_prompts)
