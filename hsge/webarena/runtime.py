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

import hashlib
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
                 maturity: int = 2, predicate_sim: float = 0.6, read_only: bool = False,
                 agent_llms: dict[str, object] | None = None):
        agent_llms = agent_llms or {}

        def role(name: str):
            return agent_llms.get(name, llm)

        self.browser_factory = browser_factory
        # Legacy alias: callers that supply one LLM still get the old behaviour.
        self.llm = llm
        self.operator_llm = role("operator_inducer")
        self.out_dir = out_dir
        self.allow = re.compile(allow_pattern)
        self.deny = re.compile(deny_pattern) if deny_pattern else None
        self.max_depth, self.max_nodes, self.terminal_goal = max_depth, max_nodes, terminal_goal
        self.explorer = PageExplorer(role("page_explorer"), read_only=read_only)
        self.solver = Solver(role("solver"), max_steps=max_steps)
        self.opgraph = OperatorGraph()
        # HSGE discovery; verification is by terminal outcome (see _record / reached),
        # so the library's own held-out gate is off (verify_k=0). `maturity` is the
        # real bar: a skill must recur that many times before it becomes an operator.
        self.library = SkillLibrary(
            role("skill_abstractor"), embedder, verify_contexts_fn=lambda: [],
            maturity=maturity, verify_k=0,
            abstraction_llm=role("skill_abstractor"),
            verification_llm=role("skill_verifier"),
        )
        # Planning predicates are LLM-authored NL, canonicalized by embedding here
        # instead of a hardcoded vocabulary; operators reference these canonical ids.
        self.registry = PredicateRegistry(embedder, sim_threshold=predicate_sim)
        self.graph = HierarchicalGraph()
        self.discovery = Discovery(
            self.library, self.graph,
            segmentation_llm=role("trajectory_segmenter"),
        )
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

    def _card_by_id(self, skill_id: str):
        return next((c for c in self.library.skills.values() if c.skill_id == skill_id), None)

    # ---- promote a verified/mature skill into a planning operator ------------
    def _promote_skill_to_operator(self, skill_id: str):
        """Turn one admitted SkillCard into an Operator.

        Preconditions/effects are LLM-induced NL predicates (from the card + the
        page state before/after a few members ran), canonicalized by the embedding
        registry so the planner's set logic still applies. A skill is terminal iff
        one of its members actually ends at the terminal goal state (ground truth
        via reached), OR the inducer flagged it terminal.
        """
        card = self._card_by_id(skill_id)
        if card is None:
            return
        members = [self.library.subtrajs.get(mid) for mid in card.member_ids[:2]]
        members = [m for m in members if m and m.steps]
        if not members:
            print(f"[operator] skill {skill_id} has no usable member steps; "
                  "inducing without page context")
        boundary = [(m.steps[0].axtree, m.steps[-1].axtree) for m in members]
        induced = induce_operator(self.operator_llm, card, boundary)
        pre = frozenset(self.registry.canonical(p) for p in induced["preconditions"])
        eff = frozenset(self.registry.canonical(e) for e in induced["effects"])
        if not eff:
            return
        # terminal only when a real terminal goal is configured and a member reached it
        reached_terminal = bool(self.terminal_goal) and any(
            reached(self.terminal_goal, m.steps[-1].url, m.steps[-1].axtree) for m in members)
        op = Operator(_slug(card.name), pre, eff, terminal=induced["terminal"] or reached_terminal)
        self.opgraph.add(op)
        print(f"    [operator] {op.name}  pre={sorted(op.preconditions)}  "
              f"eff={sorted(op.effects)}  terminal={op.terminal}")

    def _goal_task(self):
        # No terminal predicate configured (e.g. a non-shopping site) -> exploration-only.
        if not self.terminal_goal:
            return None
        # goal_predicates holds canonical ids contributed by terminal operators;
        # plan toward the first one that is reachable from the empty initial state.
        for goal in sorted(self.opgraph.goal_predicates):
            chain = plan(self.opgraph, frozenset(), goal)
            if chain:
                return {"goal": "Purchase an item: complete the full checkout to order confirmation.",
                        "difficulty": len(chain), "chain": chain}
        return None

    def _admit_url(self, link: str, visited: set) -> bool:
        return bool(link and self.allow.search(link) and link not in visited
                    and not (self.deny and self.deny.search(link)))

    # ---- persist the discovered skill library / operator graph / run stats ---
    def _dump_artifacts(self, task_stats: dict, nodes_visited: int, duplicate_nodes: int):
        """Write what was actually learned to disk (not just stdout).

        Without this, a completed run's skills/operators only ever existed in
        memory and in the one-line summary print -- unrecoverable once the
        process exits.
        """
        skills = [card.to_dict() for card in self.library.all_skills()]
        json.dump(skills, open(os.path.join(self.out_dir, "skills.json"), "w"), indent=2)

        operators = [{"name": op.name, "preconditions": sorted(op.preconditions),
                      "effects": sorted(op.effects), "terminal": op.terminal}
                     for op in self.opgraph.ops.values()]
        json.dump(operators, open(os.path.join(self.out_dir, "operators.json"), "w"), indent=2)

        graph = {
            "states": sorted(self.graph.states),
            "trajectory_edges": {u: sorted(vs) for u, vs in self.graph.trajectory_edges.items()},
            "state_to_skill": {k: sorted(v) for k, v in self.graph.state_to_skill.items()},
            "skill_to_state": {k: sorted(v) for k, v in self.graph.skill_to_state.items()},
            "skill_to_skill": {k: sorted(v) for k, v in self.graph.skill_to_skill.items()},
        }
        json.dump(graph, open(os.path.join(self.out_dir, "graph.json"), "w"), indent=2)

        summary = {
            "nodes_visited": nodes_visited,
            "duplicate_nodes_skipped": duplicate_nodes,
            "episodes": self.episode,
            "tasks": task_stats,
            "skills_discovered": len(skills),
            "operators_induced": len(operators),
        }
        json.dump(summary, open(os.path.join(self.out_dir, "summary.json"), "w"), indent=2)

    # ---- the loop ------------------------------------------------------------
    def run(self, root_url: str):
        frontier, visited = [(root_url, 0)], set()
        seen_content: set[str] = set()   # sha256 of a node's initial axtree
        duplicate_nodes = 0
        task_stats = {"LOCAL": {"success": 0, "fail": 0}, "GOAL": {"success": 0, "fail": 0}}
        if not self.terminal_goal:
            print("[goal] no terminal predicate for this run -> exploration-only "
                  "(skills/operators still discovered; goal composition disabled).")
        while frontier and len(visited) < self.max_nodes:
            url, depth = frontier.pop(0)
            if url in visited:
                continue
            visited.add(url)
            browser = self.browser_factory(url)
            obs = browser.reset()

            # Two different URLs can render the same content (redirects, aliases,
            # already-authenticated login pages, ...). Skip re-exploring content
            # we've already proposed/solved tasks for -- it wastes a full batch of
            # explorer+solver LLM calls for zero new discovery.
            content_hash = hashlib.sha256(obs["axtree"].encode("utf-8")).hexdigest()
            if content_hash in seen_content:
                duplicate_nodes += 1
                print(f"[node {len(visited)}/{self.max_nodes}] {obs['url']} "
                      f"-- duplicate content of a visited page, skipping")
                browser.close()
                continue
            seen_content.add(content_hash)

            print(f"[node {len(visited)}/{self.max_nodes}] {obs['url']} "
                  f"(depth={depth}, frontier={len(frontier)})")
            # URLs actually loaded while solving become frontier candidates (the agent
            # navigates during tasks); open tabs are added too. Page hrefs are not in
            # the flattened axtree, so this visited-during-solving signal is what grows
            # the frontier -- same approach as go-browse's open_pages_urls tracking.
            seen_urls = set()

            # 1) local exploration
            for task in self.explorer.propose(obs):
                browser.reset()
                steps, obs_texts, final_obs, success = self.solver.solve(browser, task)
                self._record(task, steps, obs_texts, success, difficulty=1, tag="LOCAL")
                task_stats["LOCAL"]["success" if success else "fail"] += 1
                if success:
                    # only skills that recur enough to be admitted become operators
                    admitted = self.discovery.on_trajectory(steps, site=root_url, task=task)
                    for sid in admitted:
                        card = self._card_by_id(sid)
                        if card:
                            print(f"    [skill] admitted {card.skill_id} '{card.name}' "
                                  f"(members={len(card.member_ids)})")
                        self._promote_skill_to_operator(sid)
                seen_urls.update(st.url for st in steps)
                seen_urls.add(final_obs.get("url", ""))
                print(f"    local: {task[:50]!r} success={success} steps={len(steps)}")

            # 2) goal-conditioned composed task (once a plan to the goal exists)
            gt = self._goal_task()
            if gt:
                browser.reset()
                steps, obs_texts, final_obs, success = self.solver.solve(
                    browser, gt["goal"], goal_predicate=self.terminal_goal)
                self._record(gt["goal"], steps, obs_texts, success,
                             difficulty=gt["difficulty"], tag="GOAL")
                task_stats["GOAL"]["success" if success else "fail"] += 1
                seen_urls.update(st.url for st in steps)
                print(f"    GOAL chain={gt['chain']} verified={success} steps={len(steps)}")

            # 3) expand frontier (bounded by max_depth) with pages seen while solving
            if depth < self.max_depth:
                seen_urls.update(browser.links())
                new_links = [link for link in sorted(seen_urls)
                             if self._admit_url(link, visited)]
                frontier.extend((link, depth + 1) for link in new_links)
                if new_links:
                    print(f"    frontier: +{len(new_links)} new url(s)")
            browser.close()

        nodes_visited = len(visited) - duplicate_nodes
        self._dump_artifacts(task_stats, nodes_visited, duplicate_nodes)

        print(f"\ndone: {nodes_visited} nodes ({duplicate_nodes} duplicate skipped), "
              f"{self.episode} episodes, "
              f"{len(self.library.all_skills())} skills, {len(self.opgraph.ops)} operators")
        print(f"  tasks: LOCAL success={task_stats['LOCAL']['success']} "
              f"fail={task_stats['LOCAL']['fail']}  "
              f"GOAL success={task_stats['GOAL']['success']} fail={task_stats['GOAL']['fail']}")
        print(f"trajectories under {self.out_dir}/episodes  "
              f"(feed to build_sft_dataset.py)")
        print(f"skills/operators/graph/summary under {self.out_dir}")
