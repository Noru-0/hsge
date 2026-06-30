from types import SimpleNamespace

import pytest

from hsge.curriculum import (
    generate_curriculum,
    generate_curriculum_from_operators,
)
from hsge.graph import HierarchicalGraph
from hsge.operators import Operator, OperatorGraph, plan
from hsge.schema import SkillCard
from hsge.webarena.runtime import WebArenaExplorer


def _card(
    skill_id: str,
    preconditions=(),
    effects=(),
    *,
    terminal: bool = False,
) -> SkillCard:
    return SkillCard(
        name=skill_id,
        description=f"Execute {skill_id}",
        slots=[],
        action_template=["click('1')"],
        precondition="required state is present",
        success_predicate="effect is present",
        cluster_id=skill_id,
        verified=True,
        skill_id=skill_id,
        planning_preconditions=set(preconditions),
        planning_effects=set(effects),
        planning_ready=bool(effects),
        predicate_schema_version="test-v1",
        terminal=terminal,
    )


def test_url_adjacency_never_creates_skill_composition():
    graph = HierarchicalGraph()
    graph.add_skill(_card("make_x", effects={"x"}), ["/start"], ["/shared"])
    graph.add_skill(
        _card("needs_y", preconditions={"y"}, effects={"z"}),
        ["/shared"],
        ["/end"],
    )

    assert graph.successors("make_x") == []
    assert graph.operator_graph.edges() == []
    assert plan(graph.operator_graph, frozenset(), "z") is None


def test_execution_only_skill_is_rejected_from_operator_graph():
    card = _card("execution_only", effects={"observed"})
    card.planning_ready = False
    card.planning_rejection_reason = "planning_effects_unverified"

    with pytest.raises(ValueError, match="non-planner-ready"):
        Operator.from_skill(card)
    with pytest.raises(ValueError, match="planner-ready"):
        HierarchicalGraph().add_skill(card, [], [])


def test_composition_edges_are_exactly_effect_precondition_matches():
    graph = HierarchicalGraph()
    graph.add_skill(_card("make_x", effects={"x"}), [], [])
    graph.add_skill(
        _card("needs_x_and_y", preconditions={"x", "y"}, effects={"z"}),
        [],
        [],
    )
    graph.add_skill(_card("needs_q", preconditions={"q"}, effects={"r"}), [], [])

    assert graph.operator_graph.edges() == [("make_x", "needs_x_and_y")]
    assert graph.successors("make_x") == ["needs_x_and_y"]


def test_planner_handles_multi_preconditions_initial_goal_and_shortest_path():
    graph = OperatorGraph()
    for op in (
        Operator("make_a", frozenset(), frozenset({"a"})),
        Operator("make_b", frozenset(), frozenset({"b"})),
        Operator("finish", frozenset({"a", "b"}), frozenset({"goal"})),
        Operator("slow_1", frozenset(), frozenset({"s1"})),
        Operator("slow_2", frozenset({"s1"}), frozenset({"s2"})),
        Operator("slow_3", frozenset({"s2"}), frozenset({"goal"})),
    ):
        graph.add(op)

    assert plan(graph, frozenset({"goal"}), "goal") == []
    assert plan(graph, frozenset(), "missing") is None
    assert plan(graph, frozenset(), "goal") == ["make_a", "make_b", "finish"]


def test_curriculum_plans_all_reachable_goals_and_keeps_long_terminal_chain():
    graph = HierarchicalGraph()
    previous = None
    expected_chain = []
    for index in range(1, 8):
        skill_id = f"step_{index}"
        expected_chain.append(skill_id)
        graph.add_skill(
            _card(
                skill_id,
                preconditions=() if previous is None else {previous},
                effects={f"p{index}"},
                terminal=index == 7,
            ),
            [],
            [],
        )
        previous = f"p{index}"
    graph.add_skill(
        _card("unreachable", preconditions={"never"}, effects={"blocked"}),
        [],
        [],
    )

    tasks = generate_curriculum(graph)
    by_goal = {task.goal_predicate: task for task in tasks}

    assert "blocked" not in by_goal
    assert list(by_goal) == [f"p{index}" for index in range(1, 8)]
    assert by_goal["p7"].skill_chain == expected_chain
    assert by_goal["p7"].difficulty == 7
    assert by_goal["p7"].terminal
    assert "p7" in by_goal["p7"].instruction
    assert [
        (task.difficulty, task.goal_predicate, task.skill_chain)
        for task in tasks
    ] == sorted(
        (task.difficulty, task.goal_predicate, task.skill_chain)
        for task in tasks
    )
    alias_tasks = generate_curriculum_from_operators(graph.operator_graph)
    assert [
        (task.goal_predicate, task.skill_chain, task.terminal)
        for task in alias_tasks
    ] == [
        (task.goal_predicate, task.skill_chain, task.terminal)
        for task in tasks
    ]
    assert all(task.task_id.startswith("curriculum_") for task in tasks)
    assert [task.task_id for task in tasks] == [
        task.task_id for task in generate_curriculum(graph)
    ]


def test_curriculum_respects_initial_predicates_and_optional_depth_filter():
    graph = OperatorGraph()
    graph.add(Operator("open", frozenset({"ready"}), frozenset({"opened"})))
    graph.add(Operator("finish", frozenset({"opened"}), frozenset({"done"})))

    tasks = generate_curriculum(
        graph,
        max_len=1,
        initial_predicates={"ready"},
    )

    assert [(task.goal_predicate, task.skill_chain) for task in tasks] == [
        ("opened", ["open"]),
    ]


def test_replacing_operator_removes_stale_terminal_goal():
    graph = OperatorGraph()
    graph.add(Operator(
        "finish", frozenset(), frozenset({"old_goal"}),
        terminal=True, skill_id="skill_finish",
    ))
    graph.add(Operator(
        "finish", frozenset(), frozenset({"new_effect"}),
        terminal=False, skill_id="skill_finish",
    ))

    assert graph.goal_predicates == set()


def test_restore_ignores_legacy_composition_edges():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.graph = HierarchicalGraph()
    explorer.graph.add_skill(_card("make_x", effects={"x"}), [], [])
    explorer.graph.add_skill(
        _card("needs_y", preconditions={"y"}, effects={"z"}), [], []
    )

    explorer._restore_hierarchical_graph({
        "state_to_skill": {},
        "skill_to_state": {},
        "skill_to_skill": {"make_x": ["needs_y"]},
    })

    assert explorer.graph.skill_to_skill == {}


def test_runtime_curriculum_export_includes_goal_metadata(tmp_path):
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.graph = HierarchicalGraph()
    explorer.opgraph = explorer.graph.operator_graph
    card = _card(
        "finish", preconditions={"ready"}, effects={"done"}, terminal=True
    )
    explorer._register_skill_operator(card)
    explorer.library = SimpleNamespace(all_skills=lambda: list(explorer.graph.skills.values()))
    explorer._curriculum_initial_predicates = {"ready"}
    explorer._curriculum_log = []
    explorer._log_file = None
    explorer.out_dir = str(tmp_path)

    explorer._write_curriculum()

    assert explorer.graph.skills["finish"] is card
    assert explorer.opgraph is explorer.graph.operator_graph
    assert explorer._curriculum_log[0]["goal_predicate"] == "done"
    assert explorer._curriculum_log[0]["terminal"] is True
    assert explorer._curriculum_log[0]["task_origin"] == "curriculum"
    assert explorer._curriculum_log[0]["task_id"].startswith("curriculum_")
