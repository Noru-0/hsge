"""Progress-based anti-wandering: an episode that stops reaching NEW pages is
hard-stopped early, even when it churns across DIFFERENT targets (which the
same-target stuck guard misses).
Run: PYTHONPATH=. python -m pytest hsge/tests/test_solver_novelty.py -q
"""
from hsge.webarena.agents import Solver


class _FrozenBrowser:
    """act() never changes the observation -> pure churn."""
    terminated = False

    def observation(self):
        return {"url": "http://x/same", "axtree": "same page"}

    def act(self, a):
        return self.observation()

    def screenshot_b64(self, som=True):
        return None


class _WanderLLM:
    """Different target each step, never terminal -> dodges the same-target guard."""
    def __init__(self):
        self.n = 0

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.n += 1
        return {"thought": "try", "action": f"click('{self.n}')"}


def test_novelty_guard_stops_pure_churn_before_budget():
    solver = Solver(_WanderLLM(), max_steps=50)
    steps, *_rest = solver.solve(_FrozenBrowser(), "goal")
    assert len(steps) <= Solver._NOVELTY_MAX + 2   # stopped well before 50


class _ProgressBrowser:
    """Every act() reaches a genuinely new page -> never stuck."""
    terminated = False

    def __init__(self):
        self.n = 0

    def observation(self):
        return {"url": f"http://x/{self.n}", "axtree": f"page {self.n}"}

    def act(self, a):
        self.n += 1
        return self.observation()

    def screenshot_b64(self, som=True):
        return None


def test_novelty_guard_does_not_stop_a_progressing_episode():
    solver = Solver(_WanderLLM(), max_steps=12)
    steps, *_rest = solver.solve(_ProgressBrowser(), "goal")
    assert len(steps) == 12   # ran the full budget -- novelty guard never fired


class _ChurnBrowser:
    """Same URL, but the axtree wiggles each act (dropdown/toggle). This defeated
    the old stuck guard (url-OR-axtree progress reset the streak every click),
    letting run v3 hammer click('247') x9 without stopping."""
    terminated = False

    def __init__(self):
        self.n = 0

    def observation(self):
        return {"url": "http://x/cart", "axtree": f"cart wiggle {self.n}"}

    def act(self, a):
        self.n += 1
        return self.observation()

    def screenshot_b64(self, som=True):
        return None


class _HammerLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"thought": "click", "action": "click('247')"}


def test_stuck_guard_fires_on_same_target_when_url_does_not_change():
    solver = Solver(_HammerLLM(), max_steps=30)
    steps, *_rest = solver.solve(_ChurnBrowser(), "goal")
    # hammering one target on a page whose URL never changes must stop fast,
    # even though the axtree wiggles each click
    assert len(steps) <= Solver._MAX_REPEATS + 1
