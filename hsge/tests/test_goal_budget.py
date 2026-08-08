"""GOAL tasks are solved with goal_max_steps; it defaults to the shared max_steps.
Run: PYTHONPATH=. python -m pytest hsge/tests/test_goal_budget.py -q
"""
import tempfile
from unittest import mock

from hsge.llm import HashingEmbedder, MockLLM
from hsge.webarena.runtime import WebArenaExplorer


def _ex(**kw):
    return WebArenaExplorer(browser_factory=lambda u: None, llm=MockLLM(),
                            embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
                            allow_pattern=".*", terminal_goal=None, **kw)


def test_goal_max_steps_defaults_to_max_steps():
    assert _ex(max_steps=15).goal_max_steps == 15
    assert _ex(max_steps=15, goal_max_steps=25).goal_max_steps == 25


def test_solve_with_retries_forwards_max_steps():
    ex = _ex(max_steps=15, goal_max_steps=25)
    with mock.patch.object(ex.solver, "solve",
                           return_value=([], [], [], {"url": ""}, False, False, "")) as m:
        ex._solve_with_retries(mock.MagicMock(), "g", difficulty=2, tag="GOAL",
                               goal_predicate=None, max_steps=ex.goal_max_steps)
    assert m.call_args.kwargs.get("max_steps") == 25


def test_solve_with_retries_defaults_max_steps_to_none():
    ex = _ex(max_steps=15)
    with mock.patch.object(ex.solver, "solve",
                           return_value=([], [], [], {"url": ""}, False, False, "")) as m:
        ex._solve_with_retries(mock.MagicMock(), "g", difficulty=1, tag="LOCAL")
    assert m.call_args.kwargs.get("max_steps") is None
