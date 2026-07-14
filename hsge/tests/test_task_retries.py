"""_solve_with_retries: retry failed tasks up to task_retries times, record
every attempt as its own episode, never retry infeasible, accumulate URLs
across attempts.

Run:  python -m pytest hsge/tests/test_task_retries.py -q
 (or) PYTHONPATH=. python hsge/tests/test_task_retries.py
"""
import os
import tempfile

from hsge.llm import HashingEmbedder, MockLLM
from hsge.schema import Step
from hsge.webarena.runtime import WebArenaExplorer


class _ScriptedSolver:
    """Yields scripted (success, infeasible) outcomes, one per attempt."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def solve(self, browser, task, goal_predicate=None):
        success, infeasible = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        action = ("send_msg_to_user('done')" if success
                  else "report_infeasible('nope')" if infeasible
                  else "click('1')")
        url = f"http://x/attempt{self.calls}"
        steps = [Step(action=action, url=url, obs_summary="", axtree="ax")]
        return steps, ["ax"], [None], {"url": url, "axtree": "ax"}, success, infeasible


class _Browser:
    def reset(self):
        return {"url": "http://x/", "axtree": "ax"}


def _explorer(retries):
    ex = WebArenaExplorer(
        browser_factory=lambda url: None, llm=MockLLM(),
        embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
        allow_pattern=".*", task_retries=retries)
    return ex


def test_fail_then_success_retries_and_records_every_attempt():
    ex = _explorer(retries=2)
    ex.solver = _ScriptedSolver([(False, False), (True, False)])

    (episode_id, steps, final_obs, success, infeasible, attempts,
     urls_seen) = ex._solve_with_retries(_Browser(), "task", difficulty=1, tag="LOCAL")

    assert success is True and infeasible is False
    assert attempts == 2
    assert episode_id == "ep_0001"          # id of the LAST attempt
    assert ex.episode == 2                  # both attempts recorded
    assert os.path.isdir(os.path.join(ex.out_dir, "episodes", "ep_0000"))
    assert os.path.isdir(os.path.join(ex.out_dir, "episodes", "ep_0001"))
    assert {"http://x/attempt1", "http://x/attempt2"} <= urls_seen


def test_infeasible_is_never_retried():
    ex = _explorer(retries=2)
    ex.solver = _ScriptedSolver([(False, True), (True, False)])

    (episode_id, steps, final_obs, success, infeasible, attempts,
     urls_seen) = ex._solve_with_retries(_Browser(), "task", difficulty=1, tag="LOCAL")

    assert infeasible is True and success is False
    assert attempts == 1
    assert ex.solver.calls == 1


def test_zero_retries_is_single_attempt():
    ex = _explorer(retries=0)
    ex.solver = _ScriptedSolver([(False, False), (True, False)])

    (episode_id, steps, final_obs, success, infeasible, attempts,
     urls_seen) = ex._solve_with_retries(_Browser(), "task", difficulty=1, tag="LOCAL")

    assert success is False
    assert attempts == 1


def test_retries_exhausted_reports_last_failure():
    ex = _explorer(retries=2)
    ex.solver = _ScriptedSolver([(False, False)])

    (episode_id, steps, final_obs, success, infeasible, attempts,
     urls_seen) = ex._solve_with_retries(_Browser(), "task", difficulty=1, tag="LOCAL")

    assert success is False and infeasible is False
    assert attempts == 3                    # 1 + task_retries
    assert ex.episode == 3


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
