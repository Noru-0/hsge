"""The hierarchical graph: the flat explorer's flat URL graph (low level) augmented with
skill nodes (high level) and three edge types:

    state -> skill   : skill is applicable from this state (initiation set)
    skill -> state   : landing/effect state after the skill
    skill -> skill   : composition edge (skill B frequently follows skill A)

Planning/curriculum then operates on the high-level subgraph.
"""
from __future__ import annotations

from collections import defaultdict

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
        self.skill_to_skill: dict[str, set[str]] = defaultdict(set)

    # --- low level -------------------------------------------------------- #
    def add_state(self, url: str) -> None:
        self.states.add(url)

    def add_trajectory_edge(self, u: str, v: str) -> None:
        self.states.update([u, v])
        self.trajectory_edges[u].add(v)

    # --- high level ------------------------------------------------------- #
    def add_skill(self, card: SkillCard, init_states: list[str],
                  effect_states: list[str]) -> None:
        self.skills[card.skill_id] = card
        for s in init_states:
            self.add_state(s)
            self.state_to_skill[s].add(card.skill_id)
        for s in effect_states:
            self.add_state(s)
            self.skill_to_state[card.skill_id].add(s)

    def link_skills(self, a_id: str, b_id: str) -> None:
        """Record that skill b commonly follows skill a (composition edge)."""
        self.skill_to_skill[a_id].add(b_id)

    def applicable_skills(self, state: str) -> list[str]:
        return sorted(self.state_to_skill.get(state, set()))

    def successors(self, skill_id: str) -> list[str]:
        """Skills composable after `skill_id` (via shared landing/init states or
        explicit composition edges)."""
        succ = set(self.skill_to_skill.get(skill_id, set()))
        for land in self.skill_to_state.get(skill_id, set()):
            succ |= self.state_to_skill.get(land, set())
        succ.discard(skill_id)
        return sorted(succ)
