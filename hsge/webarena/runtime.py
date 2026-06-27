"""WebArena exploration runtime for HSGE.

Frontier loop over URLs. At each page: propose local tasks (PageExplorer) and a
goal-conditioned composed task (planner over mined operators); solve each with the
Solver; mine operators from successful trajectories; feed HSGE Discovery; persist
trajectories in a run-dir layout that build_sft_dataset.py can read directly.

Operators are mined from predicate deltas (start-state predicates -> end-state
predicates), which is what lets the planner compose a purchase chain on real pages.
"""
from __future__ import annotations

import json
import os
import re

from ..discovery import Discovery
from ..graph import HierarchicalGraph
from ..library import SkillLibrary
from ..operators import Operator, OperatorGraph, plan
from ..segmentation import segment_trajectory
from .agents import PageExplorer, Solver
from .predicates import predicates_from, reached


def _name_from_goal(goal: str) -> str:
    g = goal.lower()
    for k, n in [("search", "search"), ("cart", "add_to_cart"), ("checkout", "checkout"),
                 ("payment", "enter_payment"), ("order", "place_order"), ("product", "open_product")]:
        if k in g:
            return n
    return re.sub(r"\W+", "_", g.strip())[:24] or "op"


class WebArenaExplorer:
    def __init__(self, browser_factory, llm, embedder, out_dir: str,
                 allow_pattern: str, max_depth: int = 6, max_nodes: int = 20,
                 max_steps: int = 15, terminal_goal: str = "order_confirmed"):
        self.browser_factory = browser_factory
        self.out_dir = out_dir
        self.allow = re.compile(allow_pattern)
        self.max_depth, self.max_nodes, self.terminal_goal = max_depth, max_nodes, terminal_goal
        self.explorer = PageExplorer(llm)
        self.solver = Solver(llm, max_steps=max_steps)
        self.opgraph = OperatorGraph()
        # HSGE discovery; verification here is by terminal outcome (see _record), so
        # the library's own gate is relaxed (maturity=1) and we admit from successes.
        self.library = SkillLibrary(llm, embedder, verify_contexts_fn=lambda: [],
                                    maturity=1, verify_k=0)
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

    # ---- operator mining from a successful trajectory ------------------------
    def _mine_operator(self, goal, steps, obs_texts, final_obs):
        if not steps:
            return
        start = predicates_from(steps[0].url, obs_texts[0] if obs_texts else "")
        end = predicates_from(final_obs["url"], final_obs["axtree"])
        eff = end - start
        if not eff:
            return
        name = _name_from_goal(goal)
        terminal = self.terminal_goal in eff
        self.opgraph.add(Operator(name, frozenset(start), frozenset(eff), terminal=terminal))

    def _goal_task(self):
        chain = plan(self.opgraph, frozenset(), self.terminal_goal)
        if not chain:
            return None
        return {"goal": "Purchase an item: complete the full checkout to order confirmation.",
                "difficulty": len(chain), "chain": chain}

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
                    self._mine_operator(task, steps, obs_texts, final_obs)
                    self.discovery.on_trajectory(steps, site=root_url, task=task)
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

            # 3) expand frontier with allowed child links
            for link in browser.links():
                if self.allow.search(link) and link not in visited:
                    frontier.append(link)
            browser.close()

        print(f"\ndone: {len(visited)} nodes, {self.episode} episodes, "
              f"{len(self.library.all_skills())} skills, {len(self.opgraph.ops)} operators")
        print(f"trajectories under {self.out_dir}/episodes  "
              f"(feed to build_sft_dataset.py)")
