"""C5: GOAL/composite tasks may use a stronger, separately-configured solver
model than LOCAL. The `solver_goal` role is optional -- absent -> GOAL uses the
LOCAL solver (no change).
Run: PYTHONPATH=. python -m pytest hsge/tests/test_goal_solver.py -q
"""
import tempfile
from unittest import mock

from hsge.llm import HashingEmbedder, MockLLM
from hsge.webarena.runtime import WebArenaExplorer


class _RoleLLM:
    def __init__(self, name):
        self.name = name

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {}


def _ex(agent_llms=None, **kw):
    return WebArenaExplorer(browser_factory=lambda u: None, llm=MockLLM(),
                            embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
                            allow_pattern=".*", terminal_goal=None,
                            agent_llms=agent_llms, **kw)


def test_goal_solver_defaults_to_local_solver_when_not_configured():
    ex = _ex()
    assert ex.goal_solver is ex.solver


def test_goal_solver_uses_configured_model_when_present():
    goal_llm = _RoleLLM("solver_goal")
    ex = _ex(agent_llms={"solver_goal": goal_llm})
    assert ex.goal_solver is not ex.solver
    assert ex.goal_solver.llm is goal_llm


def test_solve_with_retries_uses_the_given_solver():
    ex = _ex()
    alt = mock.MagicMock()
    alt.solve.return_value = ([], [], [], {"url": ""}, False, False, "")
    with mock.patch.object(ex, "_record"):
        ex._solve_with_retries(mock.MagicMock(), "g", difficulty=2, tag="GOAL", solver=alt)
    assert alt.solve.called
