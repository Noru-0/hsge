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
from ..curriculum import generate_curriculum
from ..transfer import TransferResult
from ..schema import Step
from ..segmentation import segment_trajectory
from .agents import PageExplorer, Solver
from .frontier_filter import (
    extract_templates,
    filter_frontier,
    template_priority,
    _sample_diverse,
)
from .predicates import predicates_from, reached


def _name_from_goal(goal: str) -> str:
    g = goal.lower()
    for k, n in [("search", "search"), ("cart", "add_to_cart"), ("checkout", "checkout"),
                 ("payment", "enter_payment"), ("order", "place_order"), ("product", "open_product")]:
        if k in g:
            return n
    return re.sub(r"\W+", "_", g.strip())[:24] or "op"


class WebArenaExplorer:
    def __init__(self, browser_factory, embedder, out_dir: str,
                 allow_pattern: str, max_depth: int = 6, max_nodes: int = 20,
                 max_steps: int = 20, terminal_goal: str = "order_confirmed",
                 llm=None, explorer_llm=None, solver_llm=None,
                 resume: bool = False,
                 denylist_patterns: list[str] | None = None):
        self.browser_factory = browser_factory
        self.out_dir = out_dir
        self.allow = re.compile(allow_pattern)
        self.max_depth, self.max_nodes, self.terminal_goal = max_depth, max_nodes, terminal_goal
        # support both old single-llm API and new separate explorer/solver llms
        _explorer_llm = explorer_llm or llm
        _solver_llm = solver_llm or llm
        if not _explorer_llm or not _solver_llm:
            raise ValueError("Must provide llm= or both explorer_llm= and solver_llm=")
        self.explorer = PageExplorer(_explorer_llm)
        self.solver = Solver(_solver_llm, max_steps=max_steps)
        self.opgraph = OperatorGraph()
        # HSGE discovery; verification here is by terminal outcome (see _record), so
        # the library's own gate is relaxed (maturity=1) and we admit from successes.
        self.library = SkillLibrary(_explorer_llm, embedder, verify_contexts_fn=lambda: [],
                                    maturity=3, verify_k=2)
        self.graph = HierarchicalGraph()
        self.discovery = Discovery(self.library, self.graph)
        self.episode = 0
        # Skill admission callback: log + save to JSON
        self._skills_log: list[dict] = []
        self._curriculum_log: list[dict] = []
        self._transfer_log: list[dict] = []
        self.library._on_admit = self._on_skill_admitted
        os.makedirs(os.path.join(out_dir, "episodes"), exist_ok=True)
        # Frontier filter: max URLs to keep per node after template clustering
        self._frontier_max = getattr(self, '_frontier_max', None) or 200
        # Global template quota: track how many URLs per template have been queued
        self._template_quota: dict[str, int] = {}
        self._template_max = 10        # max URLs per template across ALL nodes
        # Denylist: URLs matching any of these regex patterns are silently dropped.
        # Default: block /logout paths (they destroy session, causing downstream failures).
        self._denylist = [re.compile(p) for p in (denylist_patterns or [])]
        self._denylist.append(re.compile(r'/logout'))

        # Log file (must open BEFORE _replay_episodes so _on_skill_admitted can write)
        log_mode = "a" if resume else "w"
        self._log_file = open(os.path.join(out_dir, "run.log"), log_mode, encoding="utf-8")
        # Frontier snapshot file
        f_mode = "a" if resume else "w"
        self._frontier_file = open(os.path.join(out_dir, "frontier.jsonl"), f_mode, encoding="utf-8")

        self._ckpt = self._load_checkpoint() if resume else None
        if self._ckpt:
            self._resume_from_checkpoint(self._ckpt)
            self._log_file.write(f"\n{'='*60}\n[resume] continuing from node {self._nodes_done + 1}\n\n")
            self._log_file.flush()
            self._replay_episodes()

    def _build_skill_hints(self, page_url: str = "", task: str = "") -> str:
        """Build a prompt hint string from admitted skills in the library.

        Returns empty string if no skills are available yet.
        """
        skills = self.library.all_skills()
        if not skills:
            return ""
        # Retrieve skills most relevant to the current task or page
        query = task or page_url or "web task"
        relevant = self.library.retrieve(query, top_k=5)
        if not relevant:
            return ""
        names = [s.name for s in relevant]
        lines = ["AVAILABLE SKILLS (already learned, may help with this task):"]
        for s in relevant:
            lines.append(f"  - {s.name}: {s.description}")
            if s.action_template:
                lines.append(f"    action: {s.action_template}")
        return "\n".join(lines)

    def _filter_links(self, links: list[str], already_queued: set[str]) -> list[str]:
        """Filter links using template clustering with global quota.

        Unlike the standalone filter_frontier which only looks at the current
        batch, this method maintains a *global* view: each URL template is
        allowed at most ``_template_max`` URLs across all nodes combined.
        This prevents the frontier from accumulating many similar URLs over
        multiple nodes.
        """
        if not links:
            return []

        # Deduplicate while preserving order (page has multiple <a> to same URL)
        links = list(dict.fromkeys(links))

        # Build template → URLs mapping for this batch
        batch_templates = extract_templates(links)
        kept: list[str] = []

        # Sort templates by priority (highest first)
        sorted_templates = sorted(
            batch_templates.items(),
            key=lambda kv: template_priority(kv[0], len(kv[1])),
            reverse=True,
        )

        budget = self._frontier_max
        for tmpl, urls in sorted_templates:
            if budget <= 0:
                break
            # Global quota: how many of this template have we already kept?
            already_kept = self._template_quota.get(tmpl, 0)
            remaining = self._template_max - already_kept
            if remaining <= 0:
                continue

            # Pick up to `remaining` URLs that aren't already queued
            candidates = [u for u in urls if u not in already_queued]
            if not candidates:
                continue

            # Diverse sample from candidates
            items = [{'url': u, 'depth': 0} for u in candidates]
            sampled = _sample_diverse(items, min(remaining, budget))
            sampled_urls = [it['url'] for it in sampled]

            kept.extend(sampled_urls)
            self._template_quota[tmpl] = already_kept + len(sampled_urls)
            budget -= len(sampled_urls)

        if kept:
            msg = (f"  [filter] {len(links)} links → {len(kept)} "
                   f"(global quotas: {len(self._template_quota)} templates)")
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()

        return kept

    def _on_skill_admitted(self, card):
        """Called by SkillLibrary when a new skill is verified and admitted."""
        info = {
            "skill_id": card.skill_id,
            "name": card.name,
            "description": card.description,
            "precondition": card.precondition,
            "success_predicate": card.success_predicate,
            "action_template": card.action_template,
            "slots": [{"name": s.name, "slot_type": s.slot_type} for s in card.slots],
            "cluster_id": card.cluster_id,
            "n_members": card.stats.n_members,
        }
        self._skills_log.append(info)
        msg = f"  >>> SKILL admitted: {card.name}  ({card.description[:60]})"
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()
        # Write skills.json immediately so data survives even if run is interrupted
        skills_path = os.path.join(self.out_dir, "skills.json")
        json.dump(self._skills_log, open(skills_path, "w", encoding="utf-8"), indent=2)

    # ---- hierarchical graph export -------------------------------------------
    def _write_graph(self):
        """Export the full hierarchical graph to graph.json.

        Captures all four layers:
          - low-level: states (URLs) + trajectory edges
          - high-level: skill nodes + state↔skill edges + skill→skill composition edges
        """
        skills_serialized = {}
        for sid, card in self.graph.skills.items():
            skills_serialized[sid] = {
                "skill_id": card.skill_id,
                "name": card.name,
                "description": card.description,
                "precondition": card.precondition,
                "success_predicate": card.success_predicate,
                "action_template": card.action_template,
                "cluster_id": card.cluster_id,
                "n_members": card.stats.n_members,
                "sites_seen": sorted(card.stats.sites_seen),
            }
        graph_out = {
            "low_level": {
                "n_states": len(self.graph.states),
                "states": sorted(self.graph.states),
                "trajectory_edges": {u: sorted(vs) for u, vs in self.graph.trajectory_edges.items()},
            },
            "high_level": {
                "n_skills": len(self.graph.skills),
                "skills": skills_serialized,
                "state_to_skill": {s: sorted(sk) for s, sk in self.graph.state_to_skill.items()},
                "skill_to_state": {s: sorted(st) for s, st in self.graph.skill_to_state.items()},
                "skill_to_skill": {s: sorted(ss) for s, ss in self.graph.skill_to_skill.items()},
            },
        }
        path = os.path.join(self.out_dir, "graph.json")
        json.dump(graph_out, open(path, "w", encoding="utf-8"), indent=2)
        n_states = len(self.graph.states)
        n_skills = len(self.graph.skills)
        n_comp = sum(len(v) for v in self.graph.skill_to_skill.values())
        msg = (f"  [graph] {n_states} states, {n_skills} skills, "
               f"{n_comp} composition edges → {path}")
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()

    # ---- curriculum generation from the hierarchical graph ------------------
    def _write_curriculum(self):
        """Generate curriculum from the hierarchical graph and persist to file.

        Called periodically during the run and at the end. Curriculum tasks
        are ordered easy→hard by skill-chain length and can be used for
        curriculum-ordered fine-tuning of the agent.
        """
        if not self.graph.skills:
            return
        tasks = generate_curriculum(self.graph, max_len=3, site="webarena")
        self._curriculum_log = [
            {
                "instruction": t.instruction,
                "skill_chain": t.skill_chain,
                "skill_names": [self.graph.skills[s].name if s in self.graph.skills else s
                                for s in t.skill_chain],
                "difficulty": t.difficulty,
                "site": t.site,
            }
            for t in tasks
        ]
        path = os.path.join(self.out_dir, "curriculum.json")
        json.dump(self._curriculum_log, open(path, "w", encoding="utf-8"), indent=2)
        n_skills = len(self.graph.skills)
        msg = (f"  [curriculum] {len(tasks)} tasks from {n_skills} skills "
               f"→ {path}")
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()

    # ---- transfer retrieval (cross-domain skill transfer) -------------------
    def transfer_eval(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve skills from the library for a target query.

        This is the retrieval half of cross-domain transfer: given a query
        describing a task on a new site, retrieve the most relevant previously-
        learned skills. The results show which skills would be candidates for
        grounding on the target site.

        Full verification (ground_and_execute) requires a browser on the target
        site; use run_webarena.py with a second --root-url to measure actual
        transfer success rates across sites.
        """
        cards = self.library.retrieve(query, top_k=top_k)
        results = []
        for card in cards:
            results.append({
                "skill_id": card.skill_id,
                "name": card.name,
                "description": card.description,
                "action_template": card.action_template,
                "precondition": card.precondition,
                "success_predicate": card.success_predicate,
                "sites_seen": sorted(card.stats.sites_seen),
                "n_members": card.stats.n_members,
                "n_verify_success": card.stats.n_verify_success,
            })
        entry = {
            "query": query,
            "top_k": top_k,
            "n_retrieved": len(results),
            "skills": results,
        }
        self._transfer_log.append(entry)
        path = os.path.join(self.out_dir, "transfer.json")
        json.dump(self._transfer_log, open(path, "w", encoding="utf-8"), indent=2)
        msg = (f"  [transfer] query={query!r} → {len(results)}/{top_k} skills "
               f"retrieved → {path}")
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()
        return results

    # ---- persistence in a build_sft_dataset-compatible run-dir layout --------
    def _record(self, goal, steps, obs_texts, success, difficulty, tag,
                screenshots: list | None = None):
        ep = os.path.join(self.out_dir, "episodes", f"ep_{self.episode:04d}")
        os.makedirs(os.path.join(ep, "page_state"), exist_ok=True)
        meta = {"kind": "low_level_trajectory", "goal": goal,
                "outcome": {"success": bool(success), "reward": 1.0 if success else 0.0, "response": ""},
                "metadata": {"difficulty": difficulty, "tags": [tag]}, "step_count": len(steps)}
        json.dump(meta, open(os.path.join(ep, "episode_meta.json"), "w"), indent=2)
        with open(os.path.join(ep, "episode.jsonl"), "w") as f:
            for k, st in enumerate(steps):
                axp = f"page_state/step_{k:03d}_axtree.txt"
                obs_text = obs_texts[k] if k < len(obs_texts) else ""
                open(os.path.join(ep, axp), "w", encoding="utf-8").write(obs_text)
                # Save screenshot in separate screenshots/ folder
                ssp = None
                if screenshots and k < len(screenshots) and screenshots[k]:
                    os.makedirs(os.path.join(ep, "screenshots"), exist_ok=True)
                    ssp = f"screenshots/step_{k:03d}.png"
                    with open(os.path.join(ep, ssp), "wb") as sf:
                        sf.write(screenshots[k])
                observation = {"axtree_txt": {"path": axp}}
                if ssp:
                    observation["screenshot_png"] = {"path": ssp}
                rec = {"record_type": "step", "index": k,
                       "action": json.dumps({"thought": st.obs_summary, "action": st.action}),
                       "parsed_action": st.action, "thought": st.obs_summary,
                       "observation": observation}
                f.write(json.dumps(rec) + "\n")
        self.episode += 1

    # ---- operator mining from a successful trajectory ------------------------
    def _mine_operator(self, goal, steps, obs_texts, final_obs):
        if not steps or not hasattr(steps[0], 'url'):
            return
        start_url = getattr(steps[0], 'url', '')
        if not start_url:
            return
        start = predicates_from(start_url, obs_texts[0] if obs_texts else "")
        end = predicates_from(final_obs.get("url", ""), final_obs.get("axtree", ""))
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

    # ---- checkpoint ------------------------------------------------------
    @property
    def _checkpoint_path(self) -> str:
        return os.path.join(self.out_dir, "checkpoint.json")

    @property
    def _nodes_done(self) -> int:
        """Count how many nodes have been completed so far (from frontier.jsonl)."""
        n = 0
        fj = os.path.join(self.out_dir, "frontier.jsonl")
        if os.path.isfile(fj):
            with open(fj, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        n += 1
        return n

    def save_checkpoint(self, frontier, visited, queued):
        """Persist explorer state so the run can be resumed after interruption."""
        ckpt = {
            "frontier": [[u, d] for u, d in frontier],
            "visited": sorted(visited),
            "queued": sorted(queued),
            "nodes_processed": self._nodes_done,
            "episode": self.episode,
            "template_quota": self._template_quota,
        }
        with open(self._checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(ckpt, f, indent=2)

    def _load_checkpoint(self) -> dict | None:
        """Load a previously saved checkpoint, or None if not found."""
        if not os.path.isfile(self._checkpoint_path):
            return None
        with open(self._checkpoint_path, encoding="utf-8") as f:
            ckpt = json.load(f)
        print(f"[resume] Loaded checkpoint: {ckpt['nodes_processed']} nodes done, "
              f"{len(ckpt['frontier'])} URLs in frontier, "
              f"{ckpt['episode']} episodes recorded")
        return ckpt

    def _resume_from_checkpoint(self, ckpt: dict) -> None:
        """Restore in-memory state from a checkpoint dict."""
        self.episode = ckpt.get("episode", 0)
        self._template_quota = ckpt.get("template_quota", {})
        # Restore skills_log from existing skills.json
        sp = os.path.join(self.out_dir, "skills.json")
        if os.path.isfile(sp):
            with open(sp, encoding="utf-8") as f:
                self._skills_log = json.load(f)
        # Restore curriculum_log
        cp = os.path.join(self.out_dir, "curriculum.json")
        if os.path.isfile(cp):
            with open(cp, encoding="utf-8") as f:
                self._curriculum_log = json.load(f)
        # Restore transfer_log
        tp = os.path.join(self.out_dir, "transfer.json")
        if os.path.isfile(tp):
            with open(tp, encoding="utf-8") as f:
                self._transfer_log = json.load(f)

    def _replay_episodes(self) -> None:
        """Replay all existing episodes through discovery to rebuild the skill
        library, operator graph, and hierarchical graph.

        This is called on resume so that previously learned skills are available
        for skill hints and transfer without re-exploring those pages.
        """
        ep_dir = os.path.join(self.out_dir, "episodes")
        if not os.path.isdir(ep_dir):
            return
        episodes = sorted(
            [d for d in os.listdir(ep_dir) if d.startswith("ep_")],
            key=lambda x: int(x.split("_")[1]),
        )
        if not episodes:
            return
        print(f"[resume] Replaying {len(episodes)} existing episodes to rebuild library...")
        rebuilt = 0
        for ep_name in episodes:
            ep_path = os.path.join(ep_dir, ep_name)
            meta_path = os.path.join(ep_path, "episode_meta.json")
            traj_path = os.path.join(ep_path, "episode.jsonl")
            if not os.path.isfile(meta_path) or not os.path.isfile(traj_path):
                continue
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            if not meta.get("outcome", {}).get("success"):
                continue
            goal = meta.get("goal", "")
            # Reconstruct steps from episode.jsonl
            steps: list[Step] = []
            obs_texts: list[str] = []
            with open(traj_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    action = rec.get("parsed_action", "")
                    url = ""
                    obs_text = ""
                    obs = rec.get("observation", {})
                    if isinstance(obs, dict):
                        ax_path = obs.get("axtree_txt", {}).get("path", "")
                        if ax_path:
                            ax_full = os.path.join(ep_path, ax_path)
                            if os.path.isfile(ax_full):
                                with open(ax_full, encoding="utf-8") as af:
                                    obs_text = af.read()
                                # Infer URL from the observation (look for URL pattern)
                                url_match = re.search(r'URL:\s*(\S+)', obs_text)
                                if url_match:
                                    url = url_match.group(1)
                    steps.append(Step(action=action, url=url, obs_summary=rec.get("thought", "")[:100]))
                    obs_texts.append(obs_text)
            if not steps:
                continue
            # Mine operator from successful trajectory
            final_obs = {"url": steps[-1].url if steps else "",
                         "axtree": obs_texts[-1] if obs_texts else ""}
            self._mine_operator(goal, steps, obs_texts, final_obs)
            # Feed through HSGE discovery
            self.discovery.on_trajectory(steps, site="webarena", task=goal)
            rebuilt += 1
        print(f"[resume] Rebuilt library from {rebuilt}/{len(episodes)} successful episodes "
              f"→ {len(self.library.all_skills())} skills, {len(self.opgraph.ops)} operators")

    # ---- the loop ------------------------------------------------------------
    def run(self, root_url: str):
        # Normalize URLs: strip trailing slash, query string, and fragment.
        def _norm(u: str) -> str:
            from urllib.parse import urlparse, urlunparse
            p = urlparse(u)
            return urlunparse((p.scheme, p.netloc, p.path.rstrip('/'), '', '', ''))

        # Use checkpoint loaded in __init__ (if any)
        if self._ckpt:
            root_url = _norm(root_url)
            frontier: list[tuple[str, int]] = [tuple(p) for p in self._ckpt["frontier"]]
            visited: set[str] = set(self._ckpt["visited"])
            queued: set[str] = set(self._ckpt["queued"])
        else:
            root_url = _norm(root_url)
            frontier: list[tuple[str, int]] = [(root_url, 0)]
            visited: set[str] = set()
            queued: set[str] = {root_url}
        nodes_processed = self._nodes_done
        while frontier and nodes_processed < self.max_nodes:
            url, depth = frontier.pop(0)
            if url in visited or depth > self.max_depth:
                continue
            visited.add(url)
            nodes_processed += 1
            try:
                browser = self.browser_factory(url)
                obs = browser.reset()
            except Exception as e:
                msg = f"[node {nodes_processed} depth={depth}] SKIP {url}  (load error: {e})"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
                continue
            actual_url = _norm(obs['url'])

            # Skip if redirected to an already-visited page (e.g. wishlist → login)
            # Don't skip if actual_url == popped url (first visit to this page)
            if actual_url in visited and actual_url != url:
                msg = f"[node {nodes_processed} depth={depth}] SKIP {url} → redirect to already-visited {actual_url}"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
                browser.close()
                continue

            msg = f"[node {nodes_processed} depth={depth}] {actual_url}"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()

            # 1) local exploration (with skill hints when available)
            skill_hints = self._build_skill_hints(page_url=actual_url)
            for task in self.explorer.propose(obs, skill_hints=skill_hints):
                reset_obs = browser.reset()
                if not reset_obs.get("url"):
                    msg_skip = f"    local: {task[:50]!r} SKIP (reset failed)"
                    print(msg_skip)
                    if self._log_file:
                        self._log_file.write(msg_skip + "\n")
                        self._log_file.flush()
                    continue
                task_hints = self._build_skill_hints(task=task)
                steps, obs_texts, final_obs, success, screenshots = self.solver.solve(
                    browser, task, skill_hints=task_hints)
                self._record(task, steps, obs_texts, success, difficulty=1, tag="LOCAL",
                             screenshots=screenshots)
                if success:
                    self._mine_operator(task, steps, obs_texts, final_obs)
                    self.discovery.on_trajectory(steps, site=root_url, task=task)
                msg2 = f"    local: {task[:50]!r} success={success}"
                print(msg2)
                if self._log_file:
                    self._log_file.write(msg2 + "\n")
                    self._log_file.flush()

            # 2) goal-conditioned composed task (once a plan to the goal exists)
            gt = self._goal_task()
            if gt:
                reset_obs = browser.reset()
                if not reset_obs.get("url"):
                    msg_skip = f"    GOAL SKIP (reset failed)"
                    print(msg_skip)
                    if self._log_file:
                        self._log_file.write(msg_skip + "\n")
                        self._log_file.flush()
                else:
                    task_hints = self._build_skill_hints(task=gt["goal"])
                    steps, obs_texts, final_obs, success, screenshots = self.solver.solve(
                        browser, gt["goal"], goal_predicate=self.terminal_goal,
                        skill_hints=task_hints)
                    self._record(gt["goal"], steps, obs_texts, success,
                                 difficulty=gt["difficulty"], tag="GOAL",
                                 screenshots=screenshots)
                    msg3 = f"    GOAL chain={gt['chain']} verified={success}"
                    print(msg3)
                    if self._log_file:
                        self._log_file.write(msg3 + "\n")
                        self._log_file.flush()

            # 3) expand frontier with allowed child links (filtered, global quota)
            raw_links = [_norm(link) for link in browser.links()]
            # Filter: must pass allowlist, not already queued, and not on denylist
            eligible = [l for l in raw_links
                        if self.allow.search(l)
                        and l not in queued
                        and not any(d.search(l) for d in self._denylist)]
            for link in self._filter_links(eligible, queued):
                queued.add(link)
                frontier.append((link, depth + 1))
            browser.close()

            # Dump frontier snapshot after each node
            self._frontier_file.write(json.dumps({
                "node": nodes_processed,
                "depth": depth,
                "url": actual_url,
                "frontier_size": len(frontier),
                "frontier": [{"url": u, "depth": d} for u, d in frontier],
            }) + "\n")
            self._frontier_file.flush()

            # Save checkpoint for resume support
            self.save_checkpoint(frontier, visited, queued)

            # Periodic graph + curriculum snapshots (every 5 nodes)
            if nodes_processed % 5 == 0:
                self._write_graph()
                self._write_curriculum()

        # Export skills log
        if self._skills_log:
            skills_path = os.path.join(self.out_dir, "skills.json")
            json.dump(self._skills_log, open(skills_path, "w", encoding="utf-8"), indent=2)
            print(f"\nskills exported to {skills_path}")

        # Final graph + curriculum export
        self._write_graph()
        self._write_curriculum()

        # Transfer retrieval: which skills are most relevant for common queries?
        for q in ["search for a product", "add item to cart and checkout",
                   "log in with credentials"]:
            self.transfer_eval(q, top_k=5)

        print(f"\ndone: {nodes_processed} nodes, {self.episode} episodes, "
              f"{len(self.library.all_skills())} skills, {len(self.opgraph.ops)} operators")
        print(f"trajectories under {self.out_dir}/episodes  "
              f"(feed to build_sft_dataset.py)")

        # Final checkpoint save
        self.save_checkpoint(frontier, visited, queued)
