"""Online discovery loop — the seam into flat-graph exploration.

flat-graph exploration already produces successful trajectories during structured exploration.
You call `Discovery.on_trajectory(...)` from inside that loop (right after a task
is solved). It segments, feeds the skill library, and wires admitted skills into
the hierarchical graph, including composition edges inferred from co-occurrence
within the same parent trajectory.
"""
from __future__ import annotations

from .graph import HierarchicalGraph
from .library import SkillLibrary
from .schema import Step
from .segmentation import segment_trajectory


class Discovery:
    def __init__(self, library: SkillLibrary, graph: HierarchicalGraph):
        self.library = library
        self.graph = graph

    def on_trajectory(
        self,
        steps: list[Step],
        site: str,
        task: str,
        subgoal_hints: list[str] | None = None,
    ) -> list[str]:
        """Process one finished trajectory. Returns newly admitted skill_ids."""
        # 1. update low-level graph with the URL path actually traversed
        for a, b in zip(steps, steps[1:]):
            if a.url != b.url:
                self.graph.add_trajectory_edge(a.url, b.url)

        # 2. segment + feed the library
        subs = segment_trajectory(self.library.llm, steps, site, task, subgoal_hints)
        admitted, just_admitted_in_order = [], []
        for sub in subs:
            sid = self.library.observe(sub)
            if sid:
                admitted.append(sid)

        # 3. wire admitted skills into the hierarchical graph using their
        #    sub-trajectory boundary URLs as init/effect states
        for sub, sid in self._segment_skill_pairs(subs):
            if sid is None:
                continue
            cid = self._cid_of(sid)
            card = self.library.skills.get(cid)
            init = [sub.steps[0].url] if sub.steps else []
            effect = [sub.steps[-1].url] if sub.steps else []
            if card:
                self.graph.add_skill(card, init_states=init, effect_states=effect)
                just_admitted_in_order.append(sid)

        # 4. composition edges: consecutive admitted skills in one trajectory
        for a, b in zip(just_admitted_in_order, just_admitted_in_order[1:]):
            self.graph.link_skills(a, b)

        return admitted

    # helpers -------------------------------------------------------------- #
    def _segment_skill_pairs(self, subs):
        pairs = []
        for sub in subs:
            sid = None
            for cid, card in self.library.skills.items():
                if sub.sub_id in card.member_ids:
                    sid = card.skill_id
                    break
            pairs.append((sub, sid))
        return pairs

    def _cid_of(self, skill_id: str) -> int:
        for cid, card in self.library.skills.items():
            if card.skill_id == skill_id:
                return cid
        return -1
