"""Goal-conditioned curriculum generation over verified skill operators."""
from __future__ import annotations

from collections.abc import Iterable

from .graph import HierarchicalGraph
from .operators import OperatorGraph, plan
from .schema import Task


def _display_name(name: str) -> str:
    name = (name or "skill").strip()
    if "_" in name and name.lower() == name:
        return name.replace("_", " ")
    return name


def _operator_graph(graph: HierarchicalGraph | OperatorGraph) -> OperatorGraph:
    if isinstance(graph, OperatorGraph):
        return graph
    return graph.operator_graph


def _instruction(opgraph: OperatorGraph, chain: list[str], goal: str) -> str:
    names = [_display_name(opgraph.ops[skill_id].name) for skill_id in chain]
    actions = ", then ".join(f"'{name}'" for name in names)
    return f"Complete {actions} to reach the verified condition '{goal}'."


def generate_curriculum(
    graph: HierarchicalGraph | OperatorGraph,
    max_len: int | None = None,
    site: str = "",
    initial_predicates: Iterable[str] | None = None,
    goal_predicates: Iterable[str] | None = None,
) -> list[Task]:
    """Plan one shortest task for every requested reachable goal predicate.

    ``max_len`` remains as a compatibility filter for existing callers.  A
    value of ``None`` (the default) keeps long-horizon plans intact.
    """
    opgraph = _operator_graph(graph)
    initial = frozenset(initial_predicates or ())
    goals = set(goal_predicates or ())
    if goal_predicates is None:
        goals = {
            effect
            for operator in opgraph.ops.values()
            for effect in operator.effects
        }

    tasks: list[Task] = []
    for goal in sorted(goals):
        chain = plan(opgraph, initial, goal)
        # A goal already true in the initial state is not a task, and an
        # unreachable goal must never produce an atom or co-occurrence chain.
        if not chain:
            continue
        if max_len is not None and len(chain) > max_len:
            continue
        tasks.append(Task(
            instruction=_instruction(opgraph, chain, goal),
            skill_chain=chain,
            difficulty=len(chain),
            site=site,
            goal_predicate=goal,
            terminal=goal in opgraph.goal_predicates,
        ))

    tasks.sort(key=lambda task: (
        task.difficulty,
        task.goal_predicate,
        tuple(task.skill_chain),
    ))
    return tasks


def generate_curriculum_from_operators(
    opgraph: OperatorGraph,
    max_len: int | None = None,
    site: str = "",
    initial_predicates: Iterable[str] | None = None,
    goal_predicates: Iterable[str] | None = None,
) -> list[Task]:
    """Backward-compatible entrypoint for callers holding an OperatorGraph."""
    return generate_curriculum(
        opgraph,
        max_len=max_len,
        site=site,
        initial_predicates=initial_predicates,
        goal_predicates=goal_predicates,
    )
