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

import base64
import hashlib
import heapq
import itertools
import json
import os
import re
import time
from collections import Counter
from datetime import datetime
from urllib.parse import urlsplit

from ..discovery import Discovery
from ..graph import HierarchicalGraph
from ..library import SkillLibrary
from ..operator_induction import induce_operator, verify_operator_grounding
from ..operators import Operator, OperatorGraph, plan
from ..predicate_registry import PredicateRegistry
from ..segmentation import segment_trajectory
from .agents import PageExplorer, Solver
from .predicates import reached


def _slug(name: str) -> str:
    return re.sub(r"\W+", "_", (name or "").strip().lower())[:24] or "op"


def _now() -> tuple[float, str]:
    """(epoch seconds, ISO 8601 string) pair -- used everywhere timing is recorded,
    so run_log.jsonl/nodes.json/summary.json all stay in the same two formats."""
    return time.time(), datetime.now().isoformat()


class WebArenaExplorer:
    def __init__(self, browser_factory, llm, embedder, out_dir: str,
                 allow_pattern: str, deny_pattern: str | None = None, max_depth: int = 6,
                 max_nodes: int = 20, max_steps: int = 15, max_tasks: int = 4,
                 terminal_goal: str = "order_confirmed",
                 maturity: int = 2, predicate_sim: float = 0.6, seg_axtree_sim: float = 0.6,
                 read_only: bool = False,
                 mine_hrefs: bool = True, per_template_cap: int = 3,
                 max_hrefs_per_page: int = 100, task_retries: int = 0,
                 agent_llms: dict[str, object] | None = None,
                 agent_vision: dict[str, dict] | None = None):
        agent_llms = agent_llms or {}
        agent_vision = agent_vision or {}

        def role(name: str):
            return agent_llms.get(name, llm)

        def vision_cfg(name: str) -> dict:
            return agent_vision.get(name, {"vision": False, "som": True, "image_detail": "low"})

        self.browser_factory = browser_factory
        # Legacy alias: callers that supply one LLM still get the old behaviour.
        self.llm = llm
        self.operator_llm = role("operator_inducer")
        self.out_dir = out_dir
        self.allow = re.compile(allow_pattern)
        self.deny = re.compile(deny_pattern) if deny_pattern else None
        self.max_depth, self.max_nodes, self.terminal_goal = max_depth, max_nodes, terminal_goal
        self.mine_hrefs = mine_hrefs
        self.per_template_cap = per_template_cap
        self.max_hrefs_per_page = max_hrefs_per_page
        self.task_retries = task_retries
        pe_vision, sv_vision = vision_cfg("page_explorer"), vision_cfg("solver")
        self.explorer = PageExplorer(role("page_explorer"), max_tasks=max_tasks, read_only=read_only,
                                     vision=pe_vision["vision"], som=pe_vision["som"],
                                     image_detail=pe_vision["image_detail"])
        self.solver = Solver(role("solver"), max_steps=max_steps,
                             vision=sv_vision["vision"], som=sv_vision["som"],
                             image_detail=sv_vision["image_detail"])
        self.opgraph = OperatorGraph()
        # name -> {"precondition_accuracy": {pid: float}, "effect_accuracy": {pid:
        # float}, "member_count": int}; observation-only signal, never gates
        # admission or planning (see docs/superpowers/specs/2026-07-06-...).
        self.operator_grounding: dict[str, dict] = {}
        # op name -> {"card_name", "description", "init_url"}: recorded at
        # promotion, consumed by _goal_task to generate chain instructions.
        self._op_meta: dict[str, dict] = {}
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
            axtree_sim=seg_axtree_sim,
        )
        self.episode = 0
        os.makedirs(os.path.join(out_dir, "episodes"), exist_ok=True)

    # ---- persistence in a build_sft_dataset-compatible run-dir layout --------
    def _record(self, goal, steps, obs_texts, obs_screenshots, success, difficulty, tag,
                infeasible: bool = False):
        ep = os.path.join(self.out_dir, "episodes", f"ep_{self.episode:04d}")
        os.makedirs(os.path.join(ep, "page_state"), exist_ok=True)
        meta = {"kind": "low_level_trajectory", "goal": goal,
                "outcome": {"success": bool(success), "reward": 1.0 if success else 0.0,
                             "response": "", "infeasible": bool(infeasible)},
                "metadata": {"difficulty": difficulty, "tags": [tag]}, "step_count": len(steps)}
        json.dump(meta, open(os.path.join(ep, "episode_meta.json"), "w"), indent=2)
        with open(os.path.join(ep, "episode.jsonl"), "w") as f:
            for k, st in enumerate(steps):
                axp = f"page_state/step_{k:03d}_axtree.txt"
                open(os.path.join(ep, axp), "w").write(obs_texts[k] if k < len(obs_texts) else "")
                observation = {"axtree_txt": {"path": axp}}
                shot = obs_screenshots[k] if k < len(obs_screenshots) else None
                if shot:
                    shotp = f"page_state/step_{k:03d}_screenshot.jpg"
                    open(os.path.join(ep, shotp), "wb").write(base64.b64decode(shot))
                    observation["screenshot"] = {"path": shotp}
                rec = {"record_type": "step", "index": k, "url": st.url,
                       "action": json.dumps({"thought": st.obs_summary, "action": st.action}),
                       "parsed_action": st.action, "thought": st.obs_summary,
                       "observation": observation}
                f.write(json.dumps(rec) + "\n")
        self.episode += 1

    # ---- one task, up to 1 + task_retries attempts --------------------------
    def _solve_with_retries(self, browser, task, difficulty, tag, goal_predicate=None):
        """Run the Solver on one task, retrying failures up to task_retries
        times. Every attempt is recorded as its own episode (SFT data and
        logs stay honest). Infeasible attempts are terminal -- retrying a
        task the model just declared impossible wastes budget. Returns
        (episode_id, steps, final_obs, success, infeasible, attempts,
        urls_seen) for the LAST attempt, with urls_seen accumulated across
        all attempts so the frontier keeps every reached URL.
        """
        attempts = 0
        urls_seen: set[str] = set()
        while True:
            attempts += 1
            try:
                browser.reset()
            except Exception as e:
                # A flaky/slow/unreachable page can fail mid-node too, not
                # just on the node's first visit (see the guard in run()) --
                # e.g. a real run hit a Playwright Page.goto timeout here,
                # between two tasks at the same already-successfully-loaded
                # node. Treat it like a solve failure: no steps were ever
                # produced, so nothing is recorded (a bogus 0-step episode
                # would only pollute SFT data); retry within task_retries,
                # then give up cleanly instead of crashing the whole run.
                self._log("task_reset_error", tag=tag, task=task, attempt=attempts,
                           error=str(e), error_type=type(e).__name__)
                print(f"    [{tag.lower()}] browser reset failed (attempt {attempts}): {e}")
                if attempts > self.task_retries:
                    return None, [], {}, False, False, attempts, urls_seen
                continue
            episode_id = f"ep_{self.episode:04d}"
            (steps, obs_texts, obs_screenshots, final_obs, success,
             infeasible) = self.solver.solve(browser, task, goal_predicate=goal_predicate)
            self._record(task, steps, obs_texts, obs_screenshots, success,
                         difficulty=difficulty, tag=tag, infeasible=infeasible)
            urls_seen.update(st.url for st in steps)
            urls_seen.add(final_obs.get("url", ""))
            if success or infeasible or attempts > self.task_retries:
                return episode_id, steps, final_obs, success, infeasible, attempts, urls_seen

    def _card_by_id(self, skill_id: str):
        return next((c for c in self.library.skills.values() if c.skill_id == skill_id), None)

    # ---- structured event log, mirrored to out_dir/run_log.jsonl -------------
    def _log(self, event: str, **fields):
        rec = {"event": event, **fields}
        with open(os.path.join(self.out_dir, "run_log.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")

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
        induced = induce_operator(self.operator_llm, card, boundary,
                                  known_predicates=self.registry.vocabulary())
        pre = frozenset(self.registry.canonical(p) for p in induced["preconditions"])
        eff_all = frozenset(self.registry.canonical(e) for e in induced["effects"])
        # Anti-tautology gate: an "effect" that restates a precondition encodes
        # no state change (typical for INFO skills that read state rather than
        # change it) -- wa_run_09 had 3/4 operators with effects == preconditions,
        # which can never chain toward anything new.
        eff = eff_all - pre
        effects_dropped = sorted(eff_all & pre)
        if not eff:
            reason = "tautological" if eff_all else "no_effects"
            print(f"    [operator] rejected {_slug(card.name)}: {reason}")
            self._log("operator_rejected", skill_id=skill_id, name=_slug(card.name),
                       reason=reason, preconditions=sorted(pre),
                       effects_dropped=effects_dropped)
            return
        # terminal only when a real terminal goal is configured and a member reached it
        reached_terminal = bool(self.terminal_goal) and any(
            reached(self.terminal_goal, m.steps[-1].url, m.steps[-1].axtree) for m in members)
        op = Operator(_slug(card.name), pre, eff, terminal=induced["terminal"] or reached_terminal)
        self.opgraph.add(op)
        self._op_meta[op.name] = {
            "card_name": card.name,
            "description": card.description or card.name,
            "init_url": members[0].steps[0].url if members else "",
        }
        pre_txt = [f"{p}:{self.registry.label(p)}" for p in sorted(op.preconditions)]
        eff_txt = [f"{e}:{self.registry.label(e)}" for e in sorted(op.effects)]
        print(f"    [operator] {op.name}  pre={pre_txt}  eff={eff_txt}  terminal={op.terminal}")
        self._log("operator_induced", name=op.name, skill_id=skill_id,
                   preconditions=sorted(op.preconditions), effects=sorted(op.effects),
                   effects_dropped=effects_dropped, terminal=op.terminal)

        # Grounding check: unlike induce_operator's 2-member sample, this uses
        # every member of the skill to score whether each induced predicate
        # actually holds -- observation-only, never gates admission/planning.
        all_members = [self.library.subtrajs.get(mid) for mid in card.member_ids]
        all_members = [m for m in all_members if m and m.steps]
        all_boundary = [(m.steps[0].axtree, m.steps[-1].axtree) for m in all_members]
        grounding = verify_operator_grounding(
            self.operator_llm, induced["preconditions"], induced["effects"], all_boundary)
        pre_acc = {self.registry.canonical(p): acc
                   for p, acc in grounding["precondition_accuracy"].items()}
        eff_acc = {self.registry.canonical(e): acc
                   for e, acc in grounding["effect_accuracy"].items()}
        self.operator_grounding[op.name] = {
            "precondition_accuracy": pre_acc,
            "effect_accuracy": eff_acc,
            "member_count": grounding["member_count"],
        }
        self._log("operator_grounding_check", name=op.name, skill_id=skill_id,
                   member_count=grounding["member_count"],
                   precondition_accuracy=pre_acc, effect_accuracy=eff_acc)

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

    @staticmethod
    def _url_template(url: str) -> str:
        """Normalize a URL into a "shape" that groups same-kind pages, so the
        per-template cap can bound how many near-identical pages (per-post /
        per-comment / per-user) enter the frontier.

        Drops scheme/query/fragment (keeps host + path). A path segment is
        wildcarded to '*' if it contains a digit (an id-like slug) or follows an
        already-wildcarded one -- so an entity's trailing title slug collapses
        too (e.g. reddit's /comments/<id>/<title>). Type-identifying segments
        (a forum name like 'AskReddit', or 'comments') are kept, so different
        forums stay different templates and all get explored.
        """
        parts = urlsplit(url or "")
        segs, wildcarding = [], False
        for seg in parts.path.split("/"):
            if not seg:
                continue
            if wildcarding or any(ch.isdigit() for ch in seg):
                segs.append("*")
                wildcarding = True
            else:
                segs.append(seg)
        return parts.netloc + "/" + "/".join(segs)

    # ---- persist the discovered skill library / operator graph / run stats ---
    def _dump_artifacts(self, task_stats: dict, nodes_visited: int, duplicate_nodes: int,
                        nodes_log: list, status: str = "running",
                        ended_at_epoch: float | None = None, ended_at_iso: str | None = None,
                        error: str | None = None):
        """Write what was actually learned to disk (not just stdout/run_log.jsonl).

        Called after every node so a run interrupted partway through (Ctrl+C,
        network hiccup, ...) still leaves a consistent, up-to-date snapshot --
        not just the final tally. `status`/`ended_at_*`/`error` are only non-default
        on the two final calls in run() (success or exception); every call during
        the loop leaves them at "running"/None so the on-disk summary always
        reflects the run's current state.
        """
        skills = [card.to_dict() for card in self.library.all_skills()]
        json.dump(skills, open(os.path.join(self.out_dir, "skills.json"), "w"), indent=2)

        operators = []
        for op in self.opgraph.ops.values():
            grounding = self.operator_grounding.get(op.name, {})
            operators.append({
                "name": op.name, "preconditions": sorted(op.preconditions),
                "effects": sorted(op.effects), "terminal": op.terminal,
                "precondition_labels": {p: self.registry.label(p)
                                        for p in sorted(op.preconditions)},
                "effect_labels": {e: self.registry.label(e)
                                  for e in sorted(op.effects)},
                "precondition_confirmed": grounding.get("precondition_accuracy", {}),
                "effect_confirmed": grounding.get("effect_accuracy", {}),
            })
        json.dump(operators, open(os.path.join(self.out_dir, "operators.json"), "w"), indent=2)

        # p0/p1/... are canonical predicate ids (see PredicateRegistry.canonical);
        # this is the id -> original NL text lookup so operators.json is legible.
        predicates = {f"p{cid}": label for cid, label in self.registry.labels.items()}
        json.dump(predicates, open(os.path.join(self.out_dir, "predicates.json"), "w"), indent=2)

        graph = {
            "states": sorted(self.graph.states),
            "trajectory_edges": {u: sorted(vs) for u, vs in self.graph.trajectory_edges.items()},
            "state_to_skill": {k: sorted(v) for k, v in self.graph.state_to_skill.items()},
            "skill_to_state": {k: sorted(v) for k, v in self.graph.skill_to_state.items()},
            "skill_to_skill": {k: sorted(v) for k, v in self.graph.skill_to_skill.items()},
        }
        json.dump(graph, open(os.path.join(self.out_dir, "graph.json"), "w"), indent=2)

        # per-node breakdown: which tasks ran at that node and whether they passed
        json.dump(nodes_log, open(os.path.join(self.out_dir, "nodes.json"), "w"), indent=2)

        summary = {
            "nodes_visited": nodes_visited,
            "duplicate_nodes_skipped": duplicate_nodes,
            "episodes": self.episode,
            "tasks": task_stats,
            "skills_discovered": len(skills),
            "operators_induced": len(operators),
            "status": status,
            "started_at_epoch": self.run_started_epoch,
            "started_at_iso": self.run_started_iso,
            "ended_at_epoch": ended_at_epoch,
            "ended_at_iso": ended_at_iso,
            "duration_sec": (ended_at_epoch - self.run_started_epoch) if ended_at_epoch else None,
            "error": error,
        }
        json.dump(summary, open(os.path.join(self.out_dir, "summary.json"), "w"), indent=2)

    # ---- the loop ------------------------------------------------------------
    def run(self, root_url: str):
        open(os.path.join(self.out_dir, "run_log.jsonl"), "w").close()  # fresh log for this run
        self.run_started_epoch, self.run_started_iso = _now()
        self._log("run_start", started_at_epoch=self.run_started_epoch,
                   started_at_iso=self.run_started_iso)
        # Priority-queue frontier. Entry key: (tier, novelty, depth, seq, url).
        #   tier    -- 0 = URL the agent actually reached, 1 = mined <a href> (tier 0
        #              always explored first).
        #   novelty -- tier-1 only: visited-node count of the URL's template (fewer
        #              first, so unseen templates lead); 0 for tier 0.
        #   depth   -- shallower first (BFS breadth). seq -- FIFO tiebreak.
        seq = itertools.count()
        visited: set = set()
        template_counts: Counter = Counter()   # visited nodes per URL template (tier-1 cap)
        queued: set = set()                     # URLs already pushed (dedup pushes)
        frontier: list = []
        heapq.heappush(frontier, (0, 0, 0, next(seq), root_url))
        queued.add(root_url)

        def _push(tier: int, url: str, depth: int, novelty: int) -> bool:
            if url in queued:
                return False
            queued.add(url)
            heapq.heappush(frontier, (tier, novelty, depth, next(seq), url))
            return True

        seen_content: set[str] = set()   # sha256 of a node's initial axtree
        duplicate_nodes = 0
        node_errors = 0
        task_stats = {"LOCAL": {"success": 0, "fail": 0, "infeasible": 0},
                      "GOAL": {"success": 0, "fail": 0, "infeasible": 0}}
        nodes_log: list[dict] = []   # per-node record: url, tasks tried, pass/fail (-> nodes.json)
        # updated at the top of each iteration; used by the except block below so an
        # exception raised before any node completes still reports a sensible value.
        current_node_index, current_node_url = None, None
        if not self.terminal_goal:
            print("[goal] no terminal predicate for this run -> exploration-only "
                  "(skills/operators still discovered; goal composition disabled).")
        try:
            while frontier and len(visited) < self.max_nodes:
                tier, _novelty, depth, _seq, url = heapq.heappop(frontier)
                if url in visited:
                    continue
                # Lazy per-template cap for mined (tier-1) URLs: the visited count of
                # a template grows during the run, so a URL under cap when pushed can
                # be over cap by the time it pops. Tier-0 (reached) URLs are exempt.
                if tier == 1 and template_counts[self._url_template(url)] >= self.per_template_cap:
                    continue
                visited.add(url)
                template_counts[self._url_template(url)] += 1
                node_index = len(visited)
                current_node_index, current_node_url = node_index, url
                node_start_epoch, node_start_iso = _now()
                browser = None
                try:
                    browser = self.browser_factory(url)
                    obs = browser.reset()
                except Exception as e:
                    # A single flaky/slow/unreachable URL (real example: a live
                    # gitlab tree page whose Page.goto exceeded the navigation
                    # timeout) must not kill a multi-hour exploration run --
                    # skip this node the same way node_duplicate_skip does,
                    # instead of letting the exception reach the outer
                    # try/except below, which logs it as run_error and re-raises.
                    node_duration = time.time() - node_start_epoch
                    print(f"[node {node_index}/{self.max_nodes}] {url} "
                          f"-- failed to load, skipping: {e}")
                    self._log("node_error", index=node_index, url=url, depth=depth,
                               error=str(e), error_type=type(e).__name__,
                               started_at_epoch=node_start_epoch, started_at_iso=node_start_iso)
                    nodes_log.append({"index": node_index, "url": url, "depth": depth,
                                       "duplicate": False, "error": str(e), "tasks": [],
                                       "frontier_added": 0, "screenshot": None,
                                       "started_at_epoch": node_start_epoch,
                                       "started_at_iso": node_start_iso,
                                       "duration_sec": node_duration})
                    self._log("node_done", index=node_index, duration_sec=node_duration)
                    if browser is not None:
                        try:
                            browser.close()
                        except Exception:
                            pass
                    node_errors += 1
                    self._dump_artifacts(task_stats, len(visited) - duplicate_nodes - node_errors,
                                          duplicate_nodes, nodes_log)
                    continue

                # Two different URLs can render the same content (redirects, aliases,
                # already-authenticated login pages, ...). Skip re-exploring content
                # we've already proposed/solved tasks for -- it wastes a full batch of
                # explorer+solver LLM calls for zero new discovery.
                content_hash = hashlib.sha256(obs["axtree"].encode("utf-8")).hexdigest()
                if content_hash in seen_content:
                    duplicate_nodes += 1
                    print(f"[node {node_index}/{self.max_nodes}] {obs['url']} "
                          f"-- duplicate content of a visited page, skipping")
                    node_duration = time.time() - node_start_epoch
                    self._log("node_duplicate_skip", index=node_index, url=obs["url"], depth=depth,
                               started_at_epoch=node_start_epoch, started_at_iso=node_start_iso)
                    nodes_log.append({"index": node_index, "url": obs["url"], "depth": depth,
                                       "duplicate": True, "tasks": [], "frontier_added": 0,
                                       "screenshot": None,
                                       "started_at_epoch": node_start_epoch,
                                       "started_at_iso": node_start_iso,
                                       "duration_sec": node_duration})
                    self._log("node_done", index=node_index, duration_sec=node_duration)
                    browser.close()
                    self._dump_artifacts(task_stats, len(visited) - duplicate_nodes - node_errors,
                                          duplicate_nodes, nodes_log)
                    continue
                seen_content.add(content_hash)

                print(f"[node {node_index}/{self.max_nodes}] {obs['url']} "
                      f"(depth={depth}, frontier={len(frontier)})")
                self._log("node_visit", index=node_index, url=obs["url"], depth=depth,
                           started_at_epoch=node_start_epoch, started_at_iso=node_start_iso)
                node_rec = {"index": node_index, "url": obs["url"], "depth": depth,
                            "duplicate": False, "tasks": [], "frontier_added": 0,
                            "frontier_added_mined": 0, "screenshot": None}

                # one screenshot capture reused both for PageExplorer's vision input and
                # for the on-disk record of what the node looked like.
                node_screenshot_b64 = (browser.screenshot_b64(som=self.explorer.som)
                                        if self.explorer.vision else None)
                if node_screenshot_b64:
                    node_dir = os.path.join(self.out_dir, "node_state")
                    os.makedirs(node_dir, exist_ok=True)
                    shotp = f"node_state/node_{node_index:04d}_screenshot.jpg"
                    open(os.path.join(self.out_dir, shotp), "wb").write(
                        base64.b64decode(node_screenshot_b64))
                    node_rec["screenshot"] = shotp

                # URLs actually loaded while solving become frontier candidates (the agent
                # navigates during tasks); open tabs are added too. Page hrefs are not in
                # the flattened axtree, so this visited-during-solving signal is what grows
                # the frontier -- same approach as go-browse's open_pages_urls tracking.
                seen_urls = set()

                # 1) local exploration
                for task in self.explorer.propose(obs, screenshot_b64=node_screenshot_b64):
                    (episode_id, steps, final_obs, success, infeasible, attempts,
                     urls_seen) = self._solve_with_retries(browser, task, difficulty=1, tag="LOCAL")
                    bucket = "success" if success else ("infeasible" if infeasible else "fail")
                    task_stats["LOCAL"][bucket] += 1
                    node_rec["tasks"].append({"episode": episode_id, "tag": "LOCAL", "task": task,
                                               "success": success, "infeasible": infeasible,
                                               "attempts": attempts, "steps": len(steps)})
                    self._log("task_result", node_index=node_index, episode=episode_id, tag="LOCAL",
                               task=task, success=success, infeasible=infeasible,
                               attempts=attempts, steps=len(steps))
                    if success:
                        # only skills that recur enough to be admitted become operators
                        admitted = self.discovery.on_trajectory(steps, site=root_url, task=task)
                        for sid in admitted:
                            card = self._card_by_id(sid)
                            if card:
                                print(f"    [skill] admitted {card.skill_id} '{card.name}' "
                                      f"(members={len(card.member_ids)})")
                                self._log("skill_admitted", skill_id=card.skill_id, name=card.name,
                                           members=len(card.member_ids))
                            self._promote_skill_to_operator(sid)
                    seen_urls |= urls_seen
                    print(f"    local: {task[:50]!r} success={success}"
                          + (" infeasible" if infeasible else "")
                          + (f" attempts={attempts}" if attempts > 1 else "")
                          + f" steps={len(steps)}")

                # 2) goal-conditioned composed task (once a plan to the goal exists)
                gt = self._goal_task()
                if gt:
                    (episode_id, steps, final_obs, success, infeasible, attempts,
                     urls_seen) = self._solve_with_retries(
                        browser, gt["goal"], difficulty=gt["difficulty"], tag="GOAL",
                        goal_predicate=self.terminal_goal)
                    bucket = "success" if success else ("infeasible" if infeasible else "fail")
                    task_stats["GOAL"][bucket] += 1
                    node_rec["tasks"].append({"episode": episode_id, "tag": "GOAL", "task": gt["goal"],
                                               "success": success, "infeasible": infeasible,
                                               "attempts": attempts, "steps": len(steps)})
                    self._log("task_result", node_index=node_index, episode=episode_id, tag="GOAL",
                               task=gt["goal"], success=success, infeasible=infeasible,
                               attempts=attempts, steps=len(steps), chain=gt["chain"])
                    seen_urls |= urls_seen
                    print(f"    GOAL chain={gt['chain']} verified={success} steps={len(steps)}")

                # 3) expand frontier (bounded by max_depth). Tier 0: URLs the agent
                #    actually reached while solving (+ open tabs) -- admitted directly,
                #    no template dedup. Tier 1: mined <a href> off the page -- gated by
                #    the per-template cap so link-dense pages can't flood the frontier.
                if depth < self.max_depth:
                    seen_urls.update(browser.links())
                    reached_new = [link for link in sorted(seen_urls)
                                   if self._admit_url(link, visited)]
                    for link in reached_new:
                        _push(0, link, depth + 1, 0)
                    mined_new = 0
                    if self.mine_hrefs:
                        for link in browser.page_hrefs(self.max_hrefs_per_page):
                            if not self._admit_url(link, visited):
                                continue
                            tmpl = self._url_template(link)
                            if template_counts[tmpl] >= self.per_template_cap:
                                continue
                            if _push(1, link, depth + 1, template_counts[tmpl]):
                                mined_new += 1
                    node_rec["frontier_added"] = len(reached_new)
                    node_rec["frontier_added_mined"] = mined_new
                    if reached_new or mined_new:
                        print(f"    frontier: +{len(reached_new)} reached, +{mined_new} mined url(s)")
                        self._log("frontier_expand", node_index=node_index,
                                   added=len(reached_new), added_mined=mined_new)
                browser.close()

                node_duration = time.time() - node_start_epoch
                node_rec["started_at_epoch"] = node_start_epoch
                node_rec["started_at_iso"] = node_start_iso
                node_rec["duration_sec"] = node_duration
                nodes_log.append(node_rec)
                self._log("node_done", index=node_index, duration_sec=node_duration)
                nodes_visited = len(visited) - duplicate_nodes - node_errors
                self._dump_artifacts(task_stats, nodes_visited, duplicate_nodes, nodes_log)
        except Exception as e:
            ended_epoch, ended_iso = _now()
            duration_sec = ended_epoch - self.run_started_epoch
            self._log("run_error", started_at_epoch=self.run_started_epoch,
                       started_at_iso=self.run_started_iso,
                       ended_at_epoch=ended_epoch, ended_at_iso=ended_iso,
                       duration_sec=duration_sec, error=str(e), error_type=type(e).__name__,
                       last_node_index=current_node_index, last_node_url=current_node_url)
            nodes_visited = len(visited) - duplicate_nodes - node_errors
            self._dump_artifacts(task_stats, nodes_visited, duplicate_nodes, nodes_log,
                                  status="error", ended_at_epoch=ended_epoch, ended_at_iso=ended_iso,
                                  error=str(e))
            raise

        nodes_visited = len(visited) - duplicate_nodes - node_errors
        print(f"\ndone: {nodes_visited} nodes ({duplicate_nodes} duplicate skipped, "
              f"{node_errors} failed to load), "
              f"{self.episode} episodes, "
              f"{len(self.library.all_skills())} skills, {len(self.opgraph.ops)} operators")
        print(f"  tasks: LOCAL success={task_stats['LOCAL']['success']} "
              f"fail={task_stats['LOCAL']['fail']} "
              f"infeasible={task_stats['LOCAL']['infeasible']}  "
              f"GOAL success={task_stats['GOAL']['success']} "
              f"fail={task_stats['GOAL']['fail']} "
              f"infeasible={task_stats['GOAL']['infeasible']}")
        print(f"trajectories under {self.out_dir}/episodes  "
              f"(feed to build_sft_dataset.py)")
        print(f"per-run log/artifacts (run_log.jsonl, nodes.json, skills.json, "
              f"operators.json, predicates.json, graph.json, summary.json) under {self.out_dir}")
        ended_epoch, ended_iso = _now()
        duration_sec = ended_epoch - self.run_started_epoch
        self._log("run_summary", nodes_visited=nodes_visited, duplicate_nodes_skipped=duplicate_nodes,
                   episodes=self.episode, tasks=task_stats,
                   skills_discovered=len(self.library.all_skills()),
                   operators_induced=len(self.opgraph.ops),
                   started_at_epoch=self.run_started_epoch, started_at_iso=self.run_started_iso,
                   ended_at_epoch=ended_epoch, ended_at_iso=ended_iso, duration_sec=duration_sec)
        self._dump_artifacts(task_stats, nodes_visited, duplicate_nodes, nodes_log,
                              status="done", ended_at_epoch=ended_epoch, ended_at_iso=ended_iso,
                              error=None)
