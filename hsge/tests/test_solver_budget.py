"""Solver.solve accepts a per-call max_steps override (used to give GOAL tasks a
larger budget than LOCAL). Run: PYTHONPATH=. python -m pytest hsge/tests/test_solver_budget.py -q
"""
from hsge.webarena.agents import Solver


class _Browser:
    terminated = False

    def __init__(self):
        self.n = 0
        self.url = "http://x/0"

    def observation(self):
        return {"url": self.url, "axtree": f"page {self.n}"}

    def act(self, action):
        self.n += 1
        self.url = f"http://x/{self.n}"
        return self.observation()

    def screenshot_b64(self, som=True):
        return None


class _NeverDoneLLM:
    """Always returns a non-terminal action, so the episode runs to the budget."""
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"thought": "go", "action": "click('1')"}


def test_solve_max_steps_override_extends_budget():
    llm = _NeverDoneLLM()
    solver = Solver(llm, max_steps=3)

    steps_default, *_ = solver.solve(_Browser(), "goal")
    steps_override, *_ = solver.solve(_Browser(), "goal", max_steps=7)

    # a non-terminal episode runs exactly one action per step until the budget
    assert len(steps_default) == 3
    assert len(steps_override) == 7
