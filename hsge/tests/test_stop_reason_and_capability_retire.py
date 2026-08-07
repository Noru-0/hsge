"""Two defects found in the first shopping_admin run (outputs/wa_eval_shopping_admin).

1. The wrap-up prompt hardcoded "Your action budget is exhausted", but it also
   runs when a GUARD stopped the episode after a handful of steps. The model
   repeated the claim, so episodes that stopped at 5-6 steps recorded
   `report_infeasible('action budget exhausted, ...')` -- a false reason in both
   the analysis record and the SFT target.
2. seed_capability_repeats retried a capability the solver cannot do: "update
   the status of an order to 'Shipped'" ran all 3 allowed times, all infeasible.

Run: PYTHONPATH=. python -m pytest hsge/tests/test_stop_reason_and_capability_retire.py -q
"""
import tempfile

from hsge.webarena.agents import Solver
from hsge.webarena.runtime import WebArenaExplorer


# ------------------------------------------------------------ 1. stop reason
class _FrozenBrowser:
    terminated = False

    def observation(self):
        return {"url": "http://x/same", "axtree": "same page"}

    def act(self, a):
        return self.observation()

    def screenshot_b64(self, som=True):
        return None


class _RecordingLLM:
    """Always the SAME target, never terminal -> trips the same-target guard."""

    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        return {"thought": "again", "action": "click('7')"}


class _ExhaustLLM:
    """Progresses every step, never terminal -> runs the budget out honestly."""

    def __init__(self):
        self.prompts = []
        self.n = 0

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        self.n += 1
        return {"thought": "go", "action": f"click('{self.n}')"}


class _MovingBrowser:
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


def test_wrapup_does_not_claim_budget_exhausted_after_a_guard_stop():
    llm = _RecordingLLM()
    solver = Solver(llm, max_steps=40)
    steps, *_ = solver.solve(_FrozenBrowser(), "goal")

    assert len(steps) < 40, "the stuck guard should have stopped this early"
    wrapup = llm.prompts[-1]
    assert "budget is exhausted" not in wrapup, wrapup[-320:]
    assert "stopped early" in wrapup


def test_wrapup_still_says_budget_exhausted_when_the_budget_really_ran_out():
    llm = _ExhaustLLM()
    solver = Solver(llm, max_steps=3)
    solver.solve(_MovingBrowser(), "goal")

    assert "Your action budget is exhausted." in llm.prompts[-1]


def test_wrapup_asks_for_the_real_obstacle():
    llm = _RecordingLLM()
    Solver(llm, max_steps=40).solve(_FrozenBrowser(), "goal")
    assert "REAL obstacle" in llm.prompts[-1]


# ------------------------------------------------- 2. capability retirement
def _explorer(**kw):
    return WebArenaExplorer(
        browser_factory=lambda url: None, llm=None, embedder=None,
        out_dir=tempfile.mkdtemp(), allow_pattern=".*",
        use_site_seed=True, goal_chains_per_node=1, seed_capability_repeats=5, **kw)


def _seed(ex, n=2):
    ex.site_seed = {"description": "", "capabilities": [
        {"name": f"cap{i}", "goal": f"do thing {i}"} for i in range(n)]}
    return ex


def test_capability_retired_after_consecutive_failures():
    ex = _seed(_explorer(), n=1)
    pages = ["alpha", "beta", "gamma", "delta"]
    offered = []
    for page in pages:
        got = ex._goal_task(f"http://h/{page}")
        offered.append(len(got))
        for t in got:                       # every attempt fails
            ex._capability_failures[t["capability"]] += 1
    assert offered == [1, 1, 0, 0], (
        f"expected retirement after {WebArenaExplorer._CAPABILITY_MAX_FAILS} "
        f"consecutive failures, got {offered}")


def test_success_resets_the_failure_count():
    ex = _seed(_explorer(), n=1)
    ex._goal_task("http://h/alpha")
    ex._capability_failures["cap0"] += 1     # one failure
    ex._capability_failures["cap0"] = 0      # then a success resets it
    assert len(ex._goal_task("http://h/beta")) == 1


def test_seed_tasks_carry_their_capability_name():
    ex = _seed(_explorer(), n=1)
    task = ex._goal_task("http://h/alpha")[0]
    assert task["capability"] == "cap0", "the result loop needs this to score failures"
