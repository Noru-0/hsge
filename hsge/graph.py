"""Two-level graph with URL exploration below and planning operators above.

    state -> skill   : skill is applicable from this state (initiation set)
    skill -> state   : landing/effect state after the skill
    skill -> skill   : A's effects establish a precondition required by B

URL transitions never create high-level composition edges.  Planning and
curriculum operate only on the verified SkillCard operator view.
"""
from __future__ import annotations

from collections import defaultdict

from .operators import Operator, OperatorGraph
from .schema import SkillCard


class HierarchicalGraph:
    def __init__(self):
        # low level (inherited flat-graph exploration structure)
        self.states: set[str] = set()                      # URLs
        self.trajectory_edges: dict[str, set[str]] = defaultdict(set)  # url -> urls
        # high level
        self.skills: dict[str, SkillCard] = {}             # skill_id -> card
        self.state_to_skill: dict[str, set[str]] = defaultdict(set)
        self.skill_to_state: dict[str, set[str]] = defaultdict(set)
        self.operator_graph = OperatorGraph()

    @property
    def opgraph(self) -> OperatorGraph:
        """The canonical high-level planning view."""
        return self.operator_graph

    @property
    def skill_to_skill(self) -> dict[str, set[str]]:
        """A read-only-by-construction view derived from operator semantics."""
        derived: dict[str, set[str]] = defaultdict(set)
        for source, target in self.operator_graph.edges():
            derived[source].add(target)
        return derived

    # --- low level -------------------------------------------------------- #
    def add_state(self, url: str) -> None:
        self.states.add(url)

    def add_trajectory_edge(self, u: str, v: str) -> None:
        self.states.update([u, v])
        self.trajectory_edges[u].add(v)

    # --- high level ------------------------------------------------------- #
    def add_skill(self, card: SkillCard, init_states: list[str],
                  effect_states: list[str]) -> None:
        op = Operator.from_skill(card)
        self.skills[card.skill_id] = card
        for s in init_states:
            self.add_state(s)
            self.state_to_skill[s].add(card.skill_id)
        for s in effect_states:
            self.add_state(s)
            self.skill_to_state[card.skill_id].add(s)
        self.operator_graph.add(op)

    def link_skills(self, a_id: str, b_id: str) -> None:
        """Validate a derived composition edge for compatibility callers."""
        if (a_id, b_id) not in set(self.operator_graph.edges()):
            raise ValueError(
                "skill composition requires effect/precondition matching"
            )

    def rebuild_composition_edges(self) -> dict[str, set[str]]:
        """Return the derived view; retained for compatibility with old callers."""
        return self.skill_to_skill

    def _init_states_for(self, skill_id: str) -> set[str]:
        return {state for state, skills in self.state_to_skill.items() if skill_id in skills}

    def applicable_skills(self, state: str) -> list[str]:
        return sorted(self.state_to_skill.get(state, set()))

    def successors(self, skill_id: str) -> list[str]:
        """Skills whose preconditions match an effect of ``skill_id``."""
        return sorted(self.skill_to_skill.get(skill_id, set()))
