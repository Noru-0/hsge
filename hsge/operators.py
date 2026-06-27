"""Operator-based skills: the upgrade that makes long-horizon (purchase) tasks
appear instead of page-local atoms.

This is what `graph.py` and `curriculum.py` must become:

  graph.py   ->  skills are OPERATORS with preconditions + effects, and the
                 skill->skill edge is DERIVED from effect/precondition matching
                 (A -> B iff A establishes something B needs), not co-occurrence.
                 Some predicates are TERMINAL (e.g. order_confirmed) = goal states.

  curriculum.py -> instead of enumerating co-occurrence chains, run a PLANNER
                 from the initial state to a sampled goal predicate. The plan IS
                 the task. Targeting the terminal predicate yields the full
                 purchase chain; targeting intermediate predicates yields the
                 easy->hard curriculum.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Operator:
    """A skill expressed as a planning operator."""
    name: str
    preconditions: frozenset[str]      # predicates that must hold to apply it
    effects: frozenset[str]            # predicates it establishes
    terminal: bool = False             # does it reach a goal/transactional state?


class OperatorGraph:
    """The high-level graph, now with precondition/effect semantics."""
    def __init__(self):
        self.ops: dict[str, Operator] = {}
        self.goal_predicates: set[str] = set()

    def add(self, op: Operator) -> None:
        self.ops[op.name] = op
        if op.terminal:
            self.goal_predicates |= op.effects

    # ---- this is the new graph.py edge rule -------------------------------- #
    def edges(self) -> list[tuple[str, str]]:
        """A -> B iff some effect of A satisfies some precondition of B.

        This replaces co-occurrence edges. It is what encodes 'checkout follows
        cart follows product', so traversal can chain toward payment.
        """
        out = []
        for a in self.ops.values():
            for b in self.ops.values():
                if a.name == b.name:
                    continue
                if a.effects & b.preconditions:
                    out.append((a.name, b.name))
        return out

    def successors(self, op_name: str, state: frozenset[str]) -> list[str]:
        eff = self.ops[op_name].effects
        nxt = state | eff
        return [b.name for b in self.ops.values()
                if b.name != op_name and b.preconditions <= nxt
                and not b.preconditions <= state]  # newly enabled by op


def plan(graph: OperatorGraph, initial: frozenset[str], goal: str) -> list[str] | None:
    """Forward BFS over operators: shortest sequence reaching `goal`.

    The returned operator sequence is the long-horizon task. For goal=
    'order_confirmed' the only way to satisfy place_order's precondition chains
    all the way back through checkout -> cart -> product -> search: the purchase
    trajectory is *forced* by the precondition graph.
    """
    if goal in initial:
        return []
    seen = {initial}
    q: deque[tuple[frozenset[str], list[str]]] = deque([(initial, [])])
    while q:
        state, path = q.popleft()
        for op in graph.ops.values():
            if op.preconditions <= state and not (op.effects <= state):
                ns = state | op.effects
                npath = path + [op.name]
                if goal in ns:
                    return npath
                if ns not in seen:
                    seen.add(ns)
                    q.append((ns, npath))
    return None
