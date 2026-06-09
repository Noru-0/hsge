"""flat-graph exploration baseline (flat graph), reconstructed on the same mock infra.

flat-graph exploration frames collection as graph search where nodes are unique URLs and
edges are trajectories between them, and stores successful task-solving
trajectories as a flat dataset. It has *no* skill abstraction, *no* verification
gate, *no* hierarchy, and *no* cross-site reuse -- a new website is explored from
scratch. This class implements exactly that, so we can diff artifacts against
HSGE on identical input.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .env import WebEnv
from .schema import Step


@dataclass
class FlatGraph:
    states: set[str] = field(default_factory=set)              # unique URLs (nodes)
    edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add_edge(self, u: str, v: str) -> None:
        self.states.update([u, v])
        self.edges[u].add(v)

    @property
    def n_edges(self) -> int:
        return sum(len(v) for v in self.edges.values())


class FlatExploreBaseline:
    def __init__(self):
        self.graph = FlatGraph()
        self.dataset: list[dict] = []          # flat list of task-solving trajectories
        self.explored_sites: set[str] = set()

    def collect(self, steps: list[Step], site: str, task: str) -> None:
        """Add URL nodes + trajectory edges; append the raw trajectory to the dataset."""
        for s in steps:
            self.graph.states.add(s.url)
        for a, b in zip(steps, steps[1:]):
            if a.url != b.url:
                self.graph.add_edge(a.url, b.url)
        self.dataset.append({"site": site, "task": task, "steps": steps})
        self.explored_sites.add(site)

    # flat-graph exploration has no transferable unit. To "cover" a sub-goal on a NEW site it
    # must run a fresh exploration episode that collects a trajectory there.
    def cover_new_site(self, target_env: WebEnv, subgoals: list[str]) -> dict:
        episodes = 0
        for _ in subgoals:
            episodes += 1                       # must explore + solve from scratch
        return {"site": target_env.site, "transfer": "n/a (no reusable skills)",
                "new_exploration_episodes": episodes,
                "reused_units": 0}
