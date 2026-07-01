"""WebArena exploration runtime for HSGE.

Frontier loop over URLs. At each page: propose local tasks (PageExplorer) and a
goal-conditioned composed task (planner over operators); solve each with the
Solver; feed HSGE Discovery; persist trajectories in a run-dir layout that
build_sft_dataset.py can read directly.

Operators are derived from *verified/mature skills* (not raw trajectories): once a
skill recurs enough to be admitted by the library, an LLM induces its NL
preconditions/effects, which are canonicalized by an embedding registry into
stable ids. The planner's precondition/effect set logic then composes a purchase
chain on real pages. Goal verification stays deterministic via reached().
"""
from __future__ import annotations

import json
import os
import re

from ..discovery import Discovery
from ..graph import HierarchicalGraph
from ..library import SkillLibrary
from ..operator_induction import induce_operator
from ..operators import Operator, OperatorGraph, plan
from ..predicate_registry import PredicateRegistry
from ..segmentation import segment_trajectory
from .agents import PageExplorer, Solver
from .predicates import reached


def _slug(name: str) -> str:
    return re.sub(r"\W+", "_", (name or "").strip().lower())[:24] or "op"


class WebArenaExplorer:
    def __init__(self, browser_factory, llm, embedder, out_dir: str,
                 allow_pattern: str, deny_pattern: str | None = None, max_depth: int = 6,
                 max_nodes: int = 20, max_steps: int = 15,
                 terminal_goal: str = "order_confirmed",
                 maturity: int = 2, predicate_sim: float = 0.6):
        self.browser_factory = browser_factory
        self.llm = llm
        self.out_dir = out_dir
        self.allow = re.compile(allow_pattern)
        self.deny = re.compile(deny_pattern) if deny_pattern else None
        self.max_depth, self.max_nodes, self.terminal_goal = max_depth, max_nodes, terminal_goal
        self.explorer = PageExplorer(llm)
        self.solver = Solver(llm, max_steps=max_steps)
        self.opgraph = OperatorGraph()
        # HSGE discovery; verification is by terminal outcome (see _record / reached),
        # so the library's own held-out gate is off (verify_k=0). `maturity` is the
        # real bar: a skill must recur that many times before it becomes an operator.
        self.library = SkillLibrary(llm, embedder, verify_contexts_fn=lambda: [],
                                    maturity=maturity, verify_k=0)
        # Planning predicates are LLM-authored NL, canonicalized by embedding here
        # instead of a hardcoded vocabulary; operators reference these canonical ids.
        self.registry = PredicateRegistry(embedder, sim_threshold=predicate_sim)
        self.graph = HierarchicalGraph()
        self.discovery = Discovery(self.library, self.graph)
        self.episode = 0
        os.makedirs(os.path.join(out_dir, "episodes"), exist_ok=True)

    # ---- persistence in a build_sft_dataset-compatible run-dir layout --------
    def _record(self, goal, steps, obs_texts, success, difficulty, tag):
        ep = os.path.join(self.out_dir, "episodes", f"ep_{self.episode:04d}")
        os.makedirs(os.path.join(ep, "page_state"), exist_ok=True)
        meta = {"kind": "low_level_trajectory", "goal": goal,
                "outcome": {"success": bool(success), "reward": 1.0 if success else 0.0, "response": ""},
                "metadata": {"difficulty": difficulty, "tags": [tag]}, "step_count": len(steps)}
        json.dump(meta, open(os.path.join(ep, "episode_meta.json"), "w"), indent=2)
        with open(os.path.join(ep, "episode.jsonl"), "w") as f:
            for k, st in enumerate(steps):
                axp = f"page_state/step_{k:03d}_axtree.txt"
                open(os.path.join(ep, axp), "w").write(obs_texts[k] if k < len(obs_texts) else "")
                rec = {"record_type": "step", "index": k,
                       "action": json.dumps({"thought": st.obs_summary, "action": st.action}),
                       "parsed_action": st.action, "thought": st.obs_summary,
                       "observation": {"axtree_txt": {"path": axp}}}
                f.write(json.dumps(rec) + "\n")
        self.episode += 1

    # ---- promote a verified/mature skill into a planning operator ------------
    def _promote_skill_to_operator(self, skill_id: str):
        """Turn one admitted SkillCard into an Operator.

        Preconditions/effects are LLM-induced NL predicates (from the card + the
        page state before/after a few members ran), canonicalized by the embedding
        registry so the planner's set logic still applies. A skill is terminal iff
        one of its members actually ends at the terminal goal state (ground truth
        via reached), OR the inducer flagged it terminal.
        """
        card = next((c for c in self.library.skills.values() if c.skill_id == skill_id), None)
        if card is None:
            return
        members = [self.library.subtrajs.get(mid) for mid in card.member_ids[:2]]
        members = [m for m in members if m and m.steps]
        boundary = [(m.steps[0].axtree, m.steps[-1].axtree) for m in members]
        induced = induce_operator(self.llm, card, boundary)
        pre = frozenset(self.registry.canonical(p) for p in induced["preconditions"])
        eff = frozenset(self.registry.canonical(e) for e in induced["effects"])
        if not eff:
            return
        reached_terminal = any(
            reached(self.terminal_goal, m.steps[-1].url, m.steps[-1].axtree) for m in members)
        self.opgraph.add(Operator(_slug(card.name), pre, eff,
                                  terminal=induced["terminal"] or reached_terminal))

    def _goal_task(self):
        # goal_predicates holds canonical ids contributed by terminal operators;
        # plan toward the first one that is reachable from the empty initial state.
        for goal in sorted(self.opgraph.goal_predicates):
            chain = plan(self.opgraph, frozenset(), goal)
            if chain:
                return {"goal": "Purchase an item: complete the full checkout to order confirmation.",
                        "difficulty": len(chain), "chain": chain}
        return None

    # ---- the loop ------------------------------------------------------------
    def run(self, root_url: str):
        frontier, visited = [root_url], set()
        while frontier and len(visited) < self.max_nodes:
            url = frontier.pop(0)
            if url in visited:
                continue
            visited.add(url)
            browser = self.browser_factory(url)
            obs = browser.reset()
            print(f"[node {len(visited)}] {obs['url']}")

            # 1) local exploration
            for task in self.explorer.propose(obs):
                browser.reset()
                steps, obs_texts, final_obs, success = self.solver.solve(browser, task)
                self._record(task, steps, obs_texts, success, difficulty=1, tag="LOCAL")
                if success:
                    # only skills that recur enough to be admitted become operators
                    admitted = self.discovery.on_trajectory(steps, site=root_url, task=task)
                    for sid in admitted:
                        self._promote_skill_to_operator(sid)
                print(f"    local: {task[:50]!r} success={success}")

            # 2) goal-conditioned composed task (once a plan to the goal exists)
            gt = self._goal_task()
            if gt:
                browser.reset()
                steps, obs_texts, final_obs, success = self.solver.solve(
                    browser, gt["goal"], goal_predicate=self.terminal_goal)
                self._record(gt["goal"], steps, obs_texts, success,
                             difficulty=gt["difficulty"], tag="GOAL")
                print(f"    GOAL chain={gt['chain']} verified={success}")

            # 3) expand frontier with allowed child links (denylist wins over allow)
            for link in browser.links():
                if (self.allow.search(link) and link not in visited
                        and not (self.deny and self.deny.search(link))):
                    frontier.append(link)
            browser.close()

        print(f"\ndone: {len(visited)} nodes, {self.episode} episodes, "
              f"{len(self.library.all_skills())} skills, {len(self.opgraph.ops)} operators")
        print(f"trajectories under {self.out_dir}/episodes  "
              f"(feed to build_sft_dataset.py)")
