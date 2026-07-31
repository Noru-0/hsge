"""GoalPlanner decomposes a multi-step GOAL into an ordered subgoal list.
Run: PYTHONPATH=. python -m pytest hsge/tests/test_goal_planner.py -q
"""
from hsge.webarena.agents import PLANNER_SYS, GoalPlanner


class _Stub:
    def __init__(self, out):
        self._out = out
        self.calls = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls.append(prompt)
        return self._out


def test_planner_prompt_prefix_and_no_mock_tokens():
    assert PLANNER_SYS.startswith("DECOMPOSE")
    for tok in ("SEGMENT", "ABSTRACT", "GROUND"):
        assert tok not in PLANNER_SYS


def test_plan_returns_ordered_subgoals():
    llm = _Stub({"subgoals": ["Open the Electronics category",
                              "Select the first in-stock product",
                              "Add it to the cart"]})
    subs = GoalPlanner(llm).plan("add first electronics item to cart",
                                 {"url": "http://x/", "axtree": "cats"})
    assert subs == ["Open the Electronics category",
                    "Select the first in-stock product", "Add it to the cart"]
    assert "http://x/" in llm.calls[0]


def test_plan_drops_blank_and_nonstring_entries():
    llm = _Stub({"subgoals": ["do A", "", 42, "  do B  "]})
    assert GoalPlanner(llm).plan("g", {"url": "", "axtree": ""}) == ["do A", "do B"]


def test_plan_returns_empty_on_garbage():
    assert GoalPlanner(_Stub({"nope": 1})).plan("g", {"url": "", "axtree": ""}) == []
