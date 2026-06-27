"""AWM (Agent Workflow Memory) baseline, reconstructed on the same mock infra.

AWM induces reusable workflows from successful trajectories and reuses them as
in-context memory, including some cross-website generalization. Crucially, that
means AWM is NOT zero on abstraction or reuse -- it is the baseline that actually
competes with HSGE. The differences are narrower and must be stated
honestly:

  AWM has:    workflow induction from successes; retrieval/reuse; cross-site reuse.
  AWM lacks:  an execution-VERIFICATION gate (it trusts inductions from successes),
              a PLANNED hierarchical graph (workflows are flat memory, not nodes
              with precondition/effect edges), and an explicit difficulty-graded
              COMPOSITION curriculum.

This mock reflects exactly those haves/lacks so the three-way diff is fair.
"""
from __future__ import annotations

from hsge import HashingEmbedder, MockLLM, Step
from hsge.flat_baseline import FlatGraph
from hsge.segmentation import segment_trajectory


class AWMBaseline:
    def __init__(self, embedder: HashingEmbedder | None = None):
        self.graph = FlatGraph()                 # same flat URL graph as flat-graph exploration
        self.dataset: list[dict] = []
        self.workflows: dict[str, dict] = {}     # subgoal -> induced workflow (NO pre/eff, NO verification)
        self.embedder = embedder or HashingEmbedder()
        self.llm = MockLLM()

    def collect(self, steps: list[Step], site: str, task: str,
                subgoal_hints: list[str] | None = None) -> None:
        # flat graph + raw dataset, exactly like flat-graph exploration
        for s in steps:
            self.graph.states.add(s.url)
        for a, b in zip(steps, steps[1:]):
            if a.url != b.url:
                self.graph.add_edge(a.url, b.url)
        self.dataset.append({"site": site, "task": task, "steps": steps})

        # induce workflows from the SUCCESS (no verification, no clustering gate):
        # any recurring sub-goal becomes a reusable workflow stored as memory.
        for sub in segment_trajectory(self.llm, steps, site, task, subgoal_hints):
            wf = self.workflows.setdefault(sub.subgoal, {
                "subgoal": sub.subgoal,
                "action_signature": sub.action_signature(),
                "verified": False,                 # AWM never execution-verifies
                "induced_from": [],
            })
            if site not in wf["induced_from"]:
                wf["induced_from"].append(site)

    def reuse_on_new_site(self, queries: list[str]) -> dict:
        """AWM retrieves induced workflows as in-context memory for the new site.

        This IS reuse (AWM's strength) -- but it is UNVERIFIED: there is no gate
        that checks the workflow actually executes on the new site, so AWM also
        carries over workflows that may misfire and cannot tell good from bad.
        """
        return {
            "reused_unverified": len(self.workflows),
            "verified": "n/a (no verification gate)",
            "new_exploration_episodes": 0,        # reuse, like HSGE, so this is fair
        }

    @property
    def n_workflows(self) -> int:
        return len(self.workflows)
