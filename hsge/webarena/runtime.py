"""WebArena exploration runtime for HSGE.

Frontier loop over URLs. At each page: propose local tasks (PageExplorer) and,
when configured, a goal-conditioned composed task over mined operators. Solve each
task with the Solver, mine operators from successful trajectories, feed HSGE
Discovery, and persist trajectories in a run-dir layout that build_sft_dataset.py
can read directly.

Operators are mined from predicate deltas (start-state predicates -> end-state
predicates), which lets the planner compose longer tasks without domain-specific
rules.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field

from .action_validation import action_family, repair_thought, task_family, validate_hsge_action
from ..discovery import Discovery
from ..graph import HierarchicalGraph
from ..library import SkillLibrary
from ..operators import Operator, OperatorGraph, plan
from ..curriculum import generate_curriculum
from ..transfer import TransferResult
from ..schema import Step
from ..segmentation import segment_trajectory
from .agents import PageExplorer, Solver
from .predicates import predicates_from, reached
from .verification_context import make_verify_contexts_fn
from .scoring import FrontierScorer, LookaheadPredictor
from urllib.parse import urlparse, urlunparse


@dataclass
class RunMetrics:
    """Track run statistics for monitoring."""
    nodes_visited: int = 0
    nodes_processed: int = 0
    nodes_error: int = 0
    tasks_proposed: int = 0
    tasks_solved: int = 0
    tasks_failed: int = 0
    tasks_error: int = 0
    skills_discovered: int = 0
    skills_verified: int = 0
    skill_families_verified: int = 0
    skill_family_counts: dict[str, int] = field(default_factory=dict)
    skill_diversity_target: int = 4
    skill_diversity_met: bool = False
    segments_created: int = 0
    clusters_matured: int = 0
    abstractions_rejected_by_reason: dict[str, int] = field(default_factory=dict)
    verification_rejected_by_reason: dict[str, int] = field(default_factory=dict)
    bootstrap_skills_verified: int = 0
    checkout_tasks_attempted: int = 0
    checkout_tasks_solved: int = 0
    composed_goal_tasks_attempted: int = 0
    operators_mined: int = 0
    goal_tasks_attempted: int = 0
    goal_tasks_solved: int = 0
    total_llm_calls: int = 0
    total_llm_tokens: int = 0
    start_time: float = 0.0
    errors: int = 0

    def summary(self) -> str:
        import time
        elapsed = time.time() - self.start_time
        return (
            f"\n{'='*50}"
            f"\n  Run Summary ({elapsed:.0f}s)"
            f"\n  Nodes visited: {self.nodes_visited}"
            f"\n  Nodes processed: {self.nodes_processed}, node errors: {self.nodes_error}"
            f"\n  Tasks: {self.tasks_solved}/{self.tasks_proposed} solved"
            f"\n  Task failures: {self.tasks_failed}, task backend errors: {self.tasks_error}"
            f"\n  Skills: {self.skills_discovered} discovered, {self.skills_verified} verified"
            f"\n  Skill families: {self.skill_families_verified}/{self.skill_diversity_target}"
            f"\n  Segments: {self.segments_created}, clusters matured: {self.clusters_matured}"
            f"\n  Operators: {self.operators_mined}"
            f"\n  Goal tasks: {self.goal_tasks_solved}/{self.goal_tasks_attempted}"
            f"\n  LLM calls: {self.total_llm_calls}, tokens: {self.total_llm_tokens}"
            f"\n  Errors: {self.errors}"
            f"\n{'='*50}"
        )


def _name_from_goal(goal: str) -> str:
    g = re.sub(r"\s+", " ", (goal or "").lower()).strip()
    if re.search(r"checkout|payment|shipping|billing|place order|proceed to checkout|review order|order summary", g):
        return "advance_transaction_flow"
    if re.search(r"wish\s*list|wishlist|cart|compare|reorder|add to compare", g):
        return "activate_state_change_control" if re.search(r"add|click|open|remove|change|reorder", g) else "inspect_state_collection"
    if re.search(r"\bsearch\b|\bfind\b", g):
        return "submit_search_query"
    if re.search(r"\bsort\b|\bfilter\b|\bnarrow\b|\brefine\b", g):
        return "inspect_sort_filter"
    if re.search(r"review|feedback|rating|comment", g):
        return "inspect_feedback_indicator"
    if re.search(r"account|profile|settings|address|preference", g):
        return "inspect_account_options"
    if re.search(r"hover|submenu|menu", g):
        return "inspect_menu_options"
    if re.search(r"product|details?", g):
        return "open_visible_detail"

    g = re.sub(r"'[^']+'|\"[^\"]+\"", "item", g)
    words = [
        w for w in re.findall(r"[a-z0-9]+", g)
        if w not in {"the", "a", "an", "visible", "button", "link", "control", "for", "to", "and", "item"}
    ]
    return "_".join(words[:4]) or "op"


def skill_family(name: str) -> str:
    """Map learned skill names to generic reusable affordance families."""
    n = re.sub(r"\s+", "_", (name or "").lower())
    if re.search(r"search|query|find", n):
        return "search_submission"
    if re.search(r"open_visible_(item|detail)|click_visible_detail|detail", n):
        return "open_visible_item"
    if re.search(r"feedback|review|rating|comment", n):
        return "inspect_feedback"
    if re.search(r"menu|hover|submenu", n):
        return "inspect_menu"
    if re.search(r"filter|sort|facet|refine", n):
        return "inspect_filter_sort"
    if re.search(r"activate|state_change|save|submit|apply|confirm", n):
        return "activate_state_change"
    if re.search(r"read|inspect|visible_detail|lookup", n):
        return "read_visible_detail"
    if re.search(r"fill|field|input|textbox", n):
        return "fill_visible_field"
    return "other"


def desired_skill_family_for_task(goal: str) -> str:
    fam = task_family(goal)
    if fam == "search":
        return "search_submission"
    if fam == "feedback_analysis":
        return "inspect_feedback"
    if fam == "state_change":
        return "activate_state_change"
    if fam == "analysis":
        return "read_visible_detail"
    if fam in {"records_status", "profile_settings", "other"}:
        g = (goal or "").lower()
        if re.search(r"sort|filter|facet|refine", g):
            return "inspect_filter_sort"
        if re.search(r"hover|menu|submenu|expand", g):
            return "inspect_menu"
        if re.search(r"field|form|textbox|input", g):
            return "fill_visible_field"
        if re.search(r"open|view|detail|link|item|record|article|issue|product", g):
            return "open_visible_item"
        return "read_visible_detail"
    return "other"


class WebArenaExplorer:
    def __init__(self, browser_factory, embedder, out_dir: str,
                 allow_pattern: str, max_depth: int = 6, max_nodes: int = 20,
                 max_steps: int = 20, terminal_goal: str | None = None,
                 goal_instruction: str | None = None,
                 llm=None, explorer_llm=None, solver_llm=None,
                 resume: bool = False,
                 denylist_patterns: list[str] | None = None,
                 full_reset_url: str | None = None,
                 checkout_mode: str = "safe",
                 auto_terminal_goals: bool = True,
                 place_order_allowed: bool = False):
        self.browser_factory = browser_factory
        self.out_dir = out_dir
        self.allow = re.compile(allow_pattern)
        self.max_depth, self.max_nodes = max_depth, max_nodes
        self.terminal_goal = terminal_goal
        self.goal_instruction = goal_instruction
        self.checkout_mode = checkout_mode
        self.auto_terminal_goals = auto_terminal_goals
        self.place_order_allowed = place_order_allowed
        # support both old single-llm API and new separate explorer/solver llms
        _explorer_llm = explorer_llm or llm
        _solver_llm = solver_llm or llm
        if not _explorer_llm or not _solver_llm:
            raise ValueError("Must provide llm= or both explorer_llm= and solver_llm=")
        self.explorer = PageExplorer(
            _explorer_llm,
            checkout_mode=checkout_mode,
            place_order_allowed=place_order_allowed,
        )
        self.solver = Solver(_solver_llm, max_steps=max_steps)
        self.opgraph = OperatorGraph()
        # HSGE discovery with verification gate: skills are verified by replaying
        # on contexts built from successful episodes (different pages/sites).
        self.library = SkillLibrary(
            _explorer_llm, embedder,
            verify_contexts_fn=make_verify_contexts_fn(out_dir, browser_factory),
            maturity=3, verify_k=2,
        )
        self.graph = HierarchicalGraph()
        self.discovery = Discovery(self.library, self.graph)
        self.episode = 0
        # Callback-discovered URLs with prefix traces (for frontier expansion)
        # Stores: {normalized_url: {"prefix_steps": [...], "source_url": str}}
        self._discovered_urls: dict[str, dict] = {}
        # Skill admission callback: log + save to JSON
        self._skills_log: list[dict] = []
        self._curriculum_log: list[dict] = []
        self._transfer_log: list[dict] = []
        self.library._on_admit = self._on_skill_admitted
        self.solver._skill_library = self.library  # for tool execution
        self._skill_diagnostics: list[dict] = []
        os.makedirs(os.path.join(out_dir, "episodes"), exist_ok=True)
        # Denylist: URLs matching any of these regex patterns are silently dropped.
        # Default: block /logout paths (they destroy session, causing downstream failures).
        self._denylist = [re.compile(p) for p in (denylist_patterns or [])]
        self._denylist.append(re.compile(r'/logout'))

        # Full reset URL: POST request to reset server state before each node.
        self.full_reset_url = full_reset_url

        # Frontier scorer (UVD) replaces FIFO queue for node selection
        # Matches Go-Browse's FrontierScorer with LookaheadPredictor
        # Read account credentials from environment for solver prompts
        self._account_info = self._build_account_info()
        # Lookahead predictor: dùng model rẻ (deepseek-chat) để propose task candidates
        # cho các URL trong frontier, phục vụ tính Uncertainty (U)
        try:
            from ..backends import OpenAILLM
            _lookahead_api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
            _lookahead_base_url = os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
            _lookahead_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
            if _lookahead_api_key:
                _lookahead_llm = OpenAILLM(model=_lookahead_model, api_key=_lookahead_api_key, base_url=_lookahead_base_url)
            else:
                _lookahead_llm = None
        except Exception:
            _lookahead_llm = None
        self._lookahead_predictor = LookaheadPredictor(llm=_lookahead_llm, num_candidates=5)
        self._frontier_scorer = FrontierScorer(
            alpha=1.0, beta=1.0, theta=1.0, epsilon=1e-5,
        )
        # Track per-URL stats for the scorer
        self._url_successes: dict[str, int] = {}       # url -> successful trajectories
        self._url_attempts: dict[str, int] = {}         # url -> total trajectories

        # Run metrics for monitoring
        self.metrics = RunMetrics()
        self.metrics.start_time = time.time()
        self._coverage = {
            "task_family": Counter(),
            "action_family": Counter(),
            "successful_task_family": Counter(),
            "failed_task_family": Counter(),
            "successful_action_family": Counter(),
            "invalid_or_empty_episodes": 0,
        }
        self._task_attempt_counts: Counter[str] = Counter()
        self._task_success_counts: Counter[str] = Counter()
        self._task_failure_counts: Counter[str] = Counter()
        self._task_error_counts: Counter[str] = Counter()
        self._task_family_failure_counts: Counter[str] = Counter()
        self._skill_family_counts: Counter[str] = Counter()
        self._skill_diversity_target = 4

        # Log file (must open BEFORE _replay_episodes so _on_skill_admitted can write)
        log_mode = "a" if resume else "w"
        self._log_file = open(os.path.join(out_dir, "run.log"), log_mode, encoding="utf-8")
        self.library._on_diagnostic = self._on_skill_diagnostic
        # Frontier snapshot file
        f_mode = "a" if resume else "w"
        self._frontier_file = open(os.path.join(out_dir, "frontier.jsonl"), f_mode, encoding="utf-8")

        self._ckpt = self._load_checkpoint() if resume else None
        if self._ckpt:
            self._resume_from_checkpoint(self._ckpt)
            self._log_file.write(f"\n{'='*60}\n[resume] continuing from node {self._nodes_done + 1}\n\n")
            self._log_file.flush()
            self._replay_episodes()

    @staticmethod
    def _build_account_info() -> str:
        """Read account credentials from environment and format for solver prompts.

        Reads WA_ACCOUNT_*_USERNAME / WA_ACCOUNT_*_PASSWORD env vars.
        Returns a formatted string, or empty string if no credentials found.
        """
        accounts = []
        for site in ("SHOPPING", "SHOPPING_ADMIN", "REDDIT", "GITLAB"):
            user = os.environ.get(f"WA_ACCOUNT_{site}_USERNAME")
            pwd = os.environ.get(f"WA_ACCOUNT_{site}_PASSWORD")
            if user and pwd:
                accounts.append(f"  {site}: username={user}, password={pwd}")
        if not accounts:
            return ""
        return (
            "You are logged in with the following account credentials. "
            "Use them when the site asks for login, or when filling forms "
            "that require account information (e.g. email, password, address).\n"
            + "\n".join(accounts)
        )

    def _reset_env(self) -> None:
        """Reset server state before exploring a new node.

        Sends a POST request to `full_reset_url` (if configured) to clear
        session and other server-side state. This ensures each node starts with a
        clean environment and prevents stale state from one attempt affecting the
        next.

        Based on Go-Browse's full_reset_url mechanism.
        """
        if not self.full_reset_url:
            return
        try:
            import requests
            resp = requests.post(self.full_reset_url, timeout=15)
            if resp.ok:
                msg = f"  [reset] Full env reset OK: {self.full_reset_url}"
            else:
                msg = f"  [reset] Full env reset returned {resp.status_code}: {self.full_reset_url}"
        except ImportError:
            msg = "  [reset] requests library not available, skipping reset"
        except Exception as e:
            msg = f"  [reset] Failed: {self.full_reset_url} ({e})"
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()

    def _build_skill_hints(self, page_url: str = "", task: str = "") -> str:
        """Build a prompt hint string from admitted skills in the library.

        Returns empty string if no skills are available yet.
        Provides guidance on how to adapt skills to the current page.
        """
        skills = self.library.all_skills()
        if not skills:
            return ""
        # Retrieve skills most relevant to the current task or page
        query = task or page_url or "web task"
        relevant = self.library.retrieve(query, top_k=5)
        if not relevant:
            return ""
        lines = [
            "You have previously learned the following skills. "
            "You MAY use them as reference for action patterns, but you MUST "
            "adapt selectors/values to the current page's actual element IDs.",
            ""
        ]
        for s in relevant:
            lines.append(f"Skill: {s.name}")
            lines.append(f"  Description: {s.description}")
            lines.append(f"  When: {s.precondition}")
            if s.action_template:
                tmpl = s.action_template if isinstance(s.action_template, str) else "; ".join(s.action_template)
                lines.append(f"  Action pattern: {tmpl}")
            lines.append(f"  Success when: {s.success_predicate}")
            lines.append("")
        return "\n".join(lines)

    def _build_tools(self, page_url: str = "", task: str = "") -> list[dict]:
        """Convert admitted skills to OpenAI/DeepSeek tool definitions.

        Each skill becomes a 'function' tool that the LLM can call.
        The LLM calls the tool with slot bindings, and the runtime
        executes the action template with those bindings.

        Returns empty list if no skills are available.
        """
        skills = self.library.all_skills()
        if not skills:
            return []
        query = task or page_url or "web task"
        relevant = self.library.retrieve(query, top_k=5)
        if not relevant:
            return []

        tools = []
        for s in relevant:
            properties = {}
            required_params = []
            for slot in s.slots:
                properties[slot.name] = {
                    "type": "string",
                    "description": slot.description or f"{slot.slot_type}: {slot.name}",
                }
                if slot.slot_type == "value":
                    required_params.append(slot.name)

            # Build description with precondition and success info
            desc_parts = [s.description]
            if s.precondition:
                desc_parts.append(f"Precondition: {s.precondition}")
            if s.success_predicate:
                desc_parts.append(f"Success when: {s.success_predicate}")

            tools.append({
                "type": "function",
                "function": {
                    "name": re.sub(r'[^a-zA-Z0-9_-]', '_', s.name)[:64],
                    "description": ". ".join(desc_parts),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required_params,
                    },
                },
            })
        return tools

    def _on_step_completed(self, action: str, url_before: str, url_after: str,
                            traj_steps: list) -> None:
        """Callback after each agent step — detects URL transitions in real-time.

        When the browser navigates to a new URL during task execution, we capture
        the transition with the full prefix trace (steps taken so far). This is
        more reliable than DOM query after task completion because:
          - The URL is confirmed reachable (browser just navigated there)
          - The page state is still fresh
          - We have the exact path taken to reach it

        Discovered URLs are stored in self._discovered_urls for later frontier
        expansion. They are preferred over DOM-queried links because they come
        with verified prefix traces.
        """
        def _norm(u: str) -> str:
            p = urlparse(u)
            return urlunparse((p.scheme, p.netloc, p.path.rstrip('/'), '', '', ''))

        if not url_after or not url_before:
            return

        norm_before = _norm(url_before)
        norm_after = _norm(url_after)

        # Only capture actual navigations (URL changes)
        if norm_after == norm_before:
            return

        # Only capture same-origin URLs
        try:
            if urlparse(norm_before).netloc != urlparse(norm_after).netloc:
                return
        except Exception:
            return

        # Only capture if not already queued/visited
        if norm_after in self._discovered_urls:
            return

        # Save the discovered URL with its prefix trace
        # Store the actual Step objects for replay, plus serializable form for checkpoint
        self._discovered_urls[norm_after] = {
            "prefix_steps": list(traj_steps),  # actual Step objects for replay
            "source_url": norm_before,
            "action": action,
        }

    def _on_skill_admitted(self, card):
        """Called by SkillLibrary when a new skill is verified and admitted."""
        self.metrics.skills_verified += 1
        if getattr(card.stats, "bootstrap_verified", False):
            self.metrics.bootstrap_skills_verified += 1
        self._refresh_skill_diversity_metrics()
        info = {
            "skill_id": card.skill_id,
            "name": card.name,
            "family": skill_family(card.name),
            "description": card.description,
            "precondition": card.precondition,
            "success_predicate": card.success_predicate,
            "action_template": card.action_template,
            "slots": [{"name": s.name, "slot_type": s.slot_type} for s in card.slots],
            "cluster_id": card.cluster_id,
            "n_members": card.stats.n_members,
            "bootstrap_verified": bool(getattr(card.stats, "bootstrap_verified", False)),
            "execution_plan": getattr(card, 'execution_plan', []),
            "alternative_templates": getattr(card, 'alternative_templates', []),
        }
        self._skills_log.append(info)
        msg = f"  >>> SKILL admitted: {card.name}  ({card.description[:60]})"
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            if not self.metrics.skill_diversity_met:
                missing = sorted(self._missing_skill_families())
                self._log_file.write(
                    "  [skills] diversity target unmet: "
                    f"{self.metrics.skill_families_verified}/"
                    f"{self.metrics.skill_diversity_target}; "
                    f"missing={missing}\n"
                )
            self._log_file.flush()
        # Write skills.json immediately so data survives even if run is interrupted
        skills_path = os.path.join(self.out_dir, "skills.json")
        json.dump(self._skills_log, open(skills_path, "w", encoding="utf-8"), indent=2)

    def _on_skill_diagnostic(self, event: dict) -> None:
        """Persist discovery/abstraction/verification diagnostics."""
        event = dict(event)
        event["episode"] = self.episode
        self._skill_diagnostics.append(event)
        kind = event.get("event", "")
        if kind == "segments_created":
            self.metrics.segments_created += int(event.get("segments", 0) or 0)
        elif kind == "cluster_matured":
            self.metrics.clusters_matured += 1
        elif kind == "abstraction_rejected":
            reason = event.get("reason", "unknown")
            self.metrics.abstractions_rejected_by_reason[reason] = (
                self.metrics.abstractions_rejected_by_reason.get(reason, 0) + 1
            )
        elif kind == "verification_rejected":
            reason = event.get("reason", "unknown")
            self.metrics.verification_rejected_by_reason[reason] = (
                self.metrics.verification_rejected_by_reason.get(reason, 0) + 1
            )
        if kind in {
            "segments_created", "cluster_matured", "abstraction_rejected",
            "skill_abstracted", "verification_rejected", "skill_admitted",
        }:
            msg = "  [skill_diag] " + json.dumps(event, sort_keys=True)[:1000]
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
        path = os.path.join(self.out_dir, "skill_diagnostics.json")
        json.dump(self._skill_diagnostics, open(path, "w", encoding="utf-8"), indent=2)

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
        """Generate curriculum from the hierarchical graph (DFS composition).

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
                "skill_names": [self.graph.skills[s].name for s in t.skill_chain if s in self.graph.skills],
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
    def transfer_eval(self, query: str, top_k: int = 5,
                      target_url: str | None = None) -> list[dict]:
        """Retrieve skills from the library for a target query.

        This is the retrieval half of cross-domain transfer: given a query
        describing a task on a new site, retrieve the most relevant previously-
        learned skills. The results show which skills would be candidates for
        grounding on the target site.

        If `target_url` is provided AND a browser_factory is available, performs
        full browser-based transfer with adaptation (transfer_and_adapt).
        Otherwise, falls back to retrieval-only mode.
        """
        if target_url and hasattr(self, 'browser_factory'):
            from ..transfer import transfer_and_adapt
            result = transfer_and_adapt(
                library=self.library,
                llm=self.solver.llm,
                browser_factory=self.browser_factory,
                target_url=target_url,
                query=query,
                top_k=top_k,
            )
            entry = {
                "query": query,
                "top_k": top_k,
                "mode": "browser_adapt",
                "n_retrieved": result.attempted,
                "n_transferred": result.succeeded,
                "n_adapted": len(result.adapted_skill_ids),
                "transferred_skill_ids": result.transferred_skill_ids,
                "adapted_skill_ids": result.adapted_skill_ids,
                "transfer_rate": result.transfer_rate,
            }
            self._transfer_log.append(entry)
            path = os.path.join(self.out_dir, "transfer.json")
            json.dump(self._transfer_log, open(path, "w", encoding="utf-8"), indent=2)
            msg = (f"  [transfer] query={query!r} → {result.succeeded}/{result.attempted} "
                   f"transferred, {len(result.adapted_skill_ids)} adapted → {path}")
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            return [{"skill_id": sid} for sid in result.transferred_skill_ids + result.adapted_skill_ids]

        # Fallback: retrieval-only mode
        cards = self.library.retrieve(query, top_k=top_k)
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
            repaired_steps: list[Step] = []
            for k, st in enumerate(steps):
                axp = f"page_state/step_{k:03d}_axtree.txt"
                obs_text = obs_texts[k] if k < len(obs_texts) else ""
                open(os.path.join(ep, axp), "w", encoding="utf-8").write(obs_text)
                thought, _ = repair_thought(st.obs_summary, st.action, obs_text)
                repaired_step = Step(
                    action=st.action,
                    url=st.url,
                    obs_summary=thought,
                    dom_signature=st.dom_signature,
                    misc=st.misc,
                )
                repaired_steps.append(repaired_step)
                # Save screenshot in separate screenshots/ folder
                ssp = None
                if screenshots and k < len(screenshots) and screenshots[k]:
                    os.makedirs(os.path.join(ep, "screenshots"), exist_ok=True)
                    ssp = f"screenshots/step_{k:03d}.png"
                    with open(os.path.join(ep, ssp), "wb") as sf:
                        sf.write(screenshots[k])
                observation = {"axtree_txt": {"path": axp}, "url": st.url}
                if ssp:
                    observation["screenshot_png"] = {"path": ssp}
                rec = {"record_type": "step", "index": k,
                       "action": json.dumps({"thought": thought, "action": st.action}),
                       "parsed_action": st.action, "thought": thought,
                       "observation": observation}
                # last_action: chứa thought và action của step trước (để SFT có context)
                if k > 0:
                    prev_st = repaired_steps[k - 1]
                    rec["last_action"] = json.dumps({"thought": prev_st.obs_summary, "action": prev_st.action})
                if st.misc:
                    rec["misc"] = st.misc
                f.write(json.dumps(rec) + "\n")
        self._update_coverage(goal, steps, success)
        self._write_coverage()
        self.episode += 1

    def _update_coverage(self, goal: str, steps: list[Step], success: bool) -> None:
        fam = task_family(goal)
        self._coverage["task_family"][fam] += 1
        if success:
            self._coverage["successful_task_family"][fam] += 1
        else:
            self._coverage["failed_task_family"][fam] += 1
        if not steps:
            self._coverage["invalid_or_empty_episodes"] += 1
            return
        for st in steps:
            af = action_family(st.action)
            self._coverage["action_family"][af] += 1
            if success:
                self._coverage["successful_action_family"][af] += 1

    def _write_coverage(self) -> None:
        path = os.path.join(self.out_dir, "coverage.json")
        data = {
            k: (dict(v) if isinstance(v, Counter) else v)
            for k, v in self._coverage.items()
        }
        json.dump(data, open(path, "w", encoding="utf-8"), indent=2, sort_keys=True)

    def _rank_tasks_for_coverage(self, tasks: list[str]) -> list[str]:
        """Prefer task families that successful training data under-covers."""
        successful = self._coverage["successful_task_family"]
        failed_family = self._task_family_failure_counts
        missing_skill_families = self._missing_skill_families()
        filtered = [t for t in tasks if self._should_attempt_task(t)]
        return sorted(
            filtered,
            key=lambda t: (
                desired_skill_family_for_task(t) not in missing_skill_families,
                failed_family[task_family(t)] >= 4 and successful[task_family(t)] == 0,
                successful[task_family(t)],
                failed_family[task_family(t)],
                self._task_attempt_counts[self._task_key(t)],
                task_family(t),
                t.lower(),
            ),
        )

    def _missing_skill_families(self) -> set[str]:
        desired = {
            "search_submission",
            "open_visible_item",
            "inspect_feedback",
            "inspect_menu",
            "inspect_filter_sort",
            "activate_state_change",
            "read_visible_detail",
            "fill_visible_field",
        }
        return {fam for fam in desired if self._skill_family_counts.get(fam, 0) == 0}

    def _refresh_skill_diversity_metrics(self) -> None:
        counts = Counter(skill_family(s.name) for s in self.library.all_skills())
        self._skill_family_counts = counts
        present = {fam for fam, count in counts.items() if count > 0 and fam != "other"}
        self.metrics.skill_family_counts = dict(sorted(counts.items()))
        self.metrics.skill_families_verified = len(present)
        self.metrics.skill_diversity_target = self._skill_diversity_target
        self.metrics.skill_diversity_met = len(present) >= self._skill_diversity_target

    def _should_attempt_task(self, task: str) -> bool:
        key = self._task_key(task)
        if self._task_success_counts[key] >= 1:
            return False
        if self._task_attempt_counts[key] >= 2:
            return False
        if self._task_failure_counts[key] >= 2:
            return False
        fam = task_family(task)
        if self._task_family_failure_counts[fam] >= 4 and self._coverage["successful_task_family"][fam] == 0:
            return False
        return True

    @staticmethod
    def _task_key(task: str) -> str:
        return re.sub(r"\s+", " ", (task or "").lower()).strip()

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
        terminal = bool(self.terminal_goal and self.terminal_goal in eff)
        op = Operator(name, frozenset(start), frozenset(eff), terminal=terminal)
        self.opgraph.add(op)
        # Sync to HierarchicalGraph for export compatibility
        self._sync_to_hierarchical_graph(op)

    def _sync_to_hierarchical_graph(self, op: Operator) -> None:
        """Sync one operator to HierarchicalGraph for export compatibility.

        Creates a virtual SkillCard from the operator and wires state→skill
        and skill→state edges based on preconditions/effects. Also derives
        skill→skill composition edges from effect/precondition matching
        across all operators (replaces co-occurrence edges).
        """
        from ..schema import SkillCard, ParamSlot, SkillStats

        # Create a virtual SkillCard for this operator
        skill_id = f"op_{op.name}"
        card = SkillCard(
            name=op.name,
            description=f"Operator: {op.name}",
            slots=[],
            action_template="",
            precondition=" | ".join(sorted(op.preconditions)) if op.preconditions else "(none)",
            success_predicate=" | ".join(sorted(op.effects)) if op.effects else "(none)",
            cluster_id=skill_id,
            stats=SkillStats(n_members=1),
        )
        card.skill_id = skill_id
        self.graph.skills[skill_id] = card

        # Edge from precondition states to skill
        for state in op.preconditions:
            self.graph.state_to_skill[state].add(skill_id)

        # Edge from skill to effect states
        for state in op.effects:
            self.graph.skill_to_state[skill_id].add(state)

        # Composition edges from effect/precondition matching across ALL operators
        # A -> B iff some effect of A satisfies some precondition of B
        for other_name, other_op in self.opgraph.ops.items():
            other_id = f"op_{other_name}"
            if other_id == skill_id:
                continue
            # Ensure other operator has a card in the graph
            if other_id not in self.graph.skills:
                other_card = SkillCard(
                    name=other_name,
                    description=f"Operator: {other_name}",
                    slots=[],
                    action_template="",
                    precondition=" | ".join(sorted(other_op.preconditions)) if other_op.preconditions else "(none)",
                    success_predicate=" | ".join(sorted(other_op.effects)) if other_op.effects else "(none)",
                    cluster_id=other_id,
                )
                other_card.skill_id = other_id
                self.graph.skills[other_id] = other_card

            # op -> other_op if op's effects satisfy some of other_op's preconditions
            if op.effects & other_op.preconditions:
                self.graph.skill_to_skill[skill_id].add(other_id)
            # other_op -> op if other_op's effects satisfy some of op's preconditions
            if other_op.effects & op.preconditions:
                self.graph.skill_to_skill[other_id].add(skill_id)

    def _goal_task(self, initial_predicates: set[str] | None = None):
        initial = frozenset(initial_predicates or set())
        goal = self.terminal_goal
        instruction = self.goal_instruction
        if not goal and self.auto_terminal_goals:
            goal, instruction = self._auto_transaction_goal(initial)
        if not goal:
            return None
        chain = plan(self.opgraph, initial, goal)
        if not chain:
            return None
        instruction = instruction or f"Achieve the terminal condition: {goal}."
        return {"goal": instruction,
                "difficulty": len(chain), "chain": chain, "terminal_goal": goal}

    def _auto_transaction_goal(self, initial: frozenset[str]) -> tuple[str | None, str | None]:
        if not self._transactional_state_available(initial):
            return None, None
        candidates = [
            ("has_confirmation_cue", "Safely advance the transaction flow until a confirmation cue is visible, without placing a final order."),
            ("path:checkout", "Safely reach the checkout flow and report the next required step."),
            ("has_progress_control", "Advance the visible transaction flow one step and report the next required action."),
        ]
        for goal, instruction in candidates:
            chain = plan(self.opgraph, initial, goal)
            if chain:
                return goal, instruction
        return None, None

    def _transactional_state_available(self, initial: frozenset[str]) -> bool:
        joined = " ".join(initial)
        if re.search(r"path:(cart|checkout)|has_progress_control", joined):
            return True
        for op in self.opgraph.ops.values():
            text = " ".join([op.name, *op.preconditions, *op.effects])
            if re.search(r"cart|checkout|payment|shipping|billing|confirmation|progress", text):
                return True
        return False

    @staticmethod
    def _is_checkout_task(task: str) -> bool:
        return bool(re.search(
            r"\b(cart|checkout|payment|shipping|billing|order summary|review order|"
            r"place order|proceed to checkout|reorder|purchase)\b",
            task or "",
            re.IGNORECASE,
        ))

    def _checkout_safety_hint(self, task: str) -> str:
        if not self._is_checkout_task(task):
            return ""
        if self.checkout_mode == "discover-only":
            return (
                "Checkout safety: inspect and report checkout/order-flow fields only. "
                "Do not submit forms, change quantities, select payment, or place an order."
            )
        if self.checkout_mode == "safe" and not self.place_order_allowed:
            return (
                "Checkout safety: you may navigate cart/checkout/address/shipping/payment/review steps, "
                "but do not click a final irreversible Place Order/Pay Now/Complete Order control. "
                "If that final control is reached, report it instead."
            )
        if not self.place_order_allowed:
            return "Checkout safety: do not place a final order unless explicitly allowed."
        return ""

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
        """Persist explorer state so the run can be resumed after interruption.

        Now saves FULL state including:
          - Frontier/visited/queued (previous)
          - OperatorGraph (new) — all mined operators with preconditions/effects
          - HierarchicalGraph structure (new) — states, edges, skill mappings
          - Discovery clusterer state (new) — centroids for online clustering
          - Episode counter + template quota (previous)
          - Frontier scorer state (previous)
        """
        # Serialize operator graph
        operator_graph = {}
        for name, op in self.opgraph.ops.items():
            operator_graph[name] = {
                "preconditions": sorted(op.preconditions),
                "effects": sorted(op.effects),
                "terminal": op.terminal,
            }

        # Serialize hierarchical graph (skill-level only; states can be large)
        hierarchical_graph = {
            "state_to_skill": {s: sorted(sk) for s, sk in self.graph.state_to_skill.items()},
            "skill_to_state": {s: sorted(st) for s, st in self.graph.skill_to_state.items()},
            "skill_to_skill": {s: sorted(ss) for s, ss in self.graph.skill_to_skill.items()},
        }

        # Serialize clusterer state (centroids)
        clusterer_state = self._serialize_clusterer()

        ckpt = {
            "version": 2,
            "frontier": [[u, d] for u, d in frontier],
            "visited": sorted(visited),
            "queued": sorted(queued),
            "nodes_processed": self._nodes_done,
            "episode": self.episode,
            "discovered_urls": {
                url: {
                    "source_url": info["source_url"],
                    "action": info.get("action", ""),
                    "prefix_steps": [
                        {"action": s.action, "url": s.url, "obs_summary": s.obs_summary}
                        for s in info.get("prefix_steps", [])
                    ],
                }
                for url, info in self._discovered_urls.items()
            },
            "frontier_scorer": self._frontier_scorer.to_dict(),
            "url_attempts": dict(self._url_attempts),
            "url_successes": dict(self._url_successes),
            # NEW: full state for resume without replay
            "operator_graph": operator_graph,
            "hierarchical_graph": hierarchical_graph,
            "clusterer": clusterer_state,
        }
        with open(self._checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(ckpt, f, indent=2)

    def _serialize_clusterer(self) -> dict:
        """Serialize the online clusterer state (centroids + cluster members)."""
        try:
            clusters = {}
            for cid, cluster in self.library.clusterer.clusters.items():
                clusters[str(cid)] = {
                    "centroid": cluster.centroid.tolist() if hasattr(cluster.centroid, 'tolist') else list(cluster.centroid),
                    "members": self.library.cluster_to_members.get(cid, []),
                }
            return {
                "clusters": clusters,
                "sim_threshold": getattr(self.library.clusterer, 'sim_threshold', 0.6),
            }
        except Exception as e:
            print(f"  [checkpoint] WARNING: clusterer serialization failed: {e}")
            return {}

    def _deserialize_clusterer(self, state: dict) -> None:
        """Restore clusterer state from a serialized dict."""
        if not state:
            return
        import numpy as np
        try:
            sim_threshold = state.get("sim_threshold", 0.6)
            self.library.clusterer.sim_threshold = sim_threshold
            clusters = state.get("clusters", {})
            for cid_str, cdata in clusters.items():
                cid = int(cid_str)
                centroid = np.array(cdata.get("centroid", []), dtype=np.float32)
                members = cdata.get("members", [])
                # Restore cluster in clusterer
                from ..clustering import _Cluster
                self.library.clusterer.clusters[cid] = _Cluster(centroid=centroid, members=set(members))
                # Restore cluster_to_members mapping
                self.library.cluster_to_members[cid] = list(members)
                # Restore subtrajs references (empty placeholders; actual data from episodes)
                for mid in members:
                    if mid not in self.library.subtrajs:
                        self.library.subtrajs[mid] = None  # placeholder
        except Exception as e:
            print(f"  [checkpoint] WARNING: clusterer deserialization failed: {e}")

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
        """Restore in-memory state from a checkpoint dict.

        Handles both v1 (partial) and v2 (full) checkpoint formats.
        v2 includes operator_graph, hierarchical_graph, and clusterer state
        so that replay_episodes is NOT needed.
        """
        self.episode = ckpt.get("episode", 0)
        # Restore callback-discovered URLs with prefix traces
        self._discovered_urls = {}
        for url, info in ckpt.get("discovered_urls", {}).items():
            prefix_steps_data = info.get("prefix_steps", [])
            prefix_steps = [
                Step(action=s.get("action", ""), url=s.get("url", ""),
                     obs_summary=s.get("obs_summary", ""))
                for s in prefix_steps_data
            ]
            self._discovered_urls[url] = {
                "prefix_steps": prefix_steps,
                "source_url": info.get("source_url", ""),
                "action": info.get("action", ""),
            }
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

        # Restore frontier scorer state
        scorer_state = ckpt.get("frontier_scorer")
        if scorer_state:
            self._frontier_scorer = FrontierScorer.from_dict(scorer_state)
        self._url_attempts = ckpt.get("url_attempts", {})
        self._url_successes = ckpt.get("url_successes", {})

        # --- v2: Restore full state (no replay needed) ---
        version = ckpt.get("version", 1)
        if version >= 2:
            self._restore_operator_graph(ckpt.get("operator_graph", {}))
            self._restore_hierarchical_graph(ckpt.get("hierarchical_graph", {}))
            self._deserialize_clusterer(ckpt.get("clusterer", {}))
            # Mark that full state was restored (skip replay)
            self._full_state_restored = True
        else:
            self._full_state_restored = False

    def _restore_operator_graph(self, op_graph_data: dict) -> None:
        """Restore operator graph from serialized state."""
        if not op_graph_data:
            return
        for name, op_data in op_graph_data.items():
            op = Operator(
                name=name,
                preconditions=frozenset(op_data.get("preconditions", [])),
                effects=frozenset(op_data.get("effects", [])),
                terminal=op_data.get("terminal", False),
            )
            self.opgraph.add(op)
            # Sync to HierarchicalGraph for export compatibility
            self._sync_to_hierarchical_graph(op)

    def _restore_hierarchical_graph(self, hg_data: dict) -> None:
        """Restore hierarchical graph edges from serialized state.

        Skill cards are rebuilt from operator graph (if available) or
        from skills.json. Edge structures are restored directly.
        """
        if not hg_data:
            return
        # Restore state_to_skill edges
        for state, skill_ids in hg_data.get("state_to_skill", {}).items():
            self.graph.state_to_skill[state] = set(skill_ids)
            self.graph.add_state(state)
        # Restore skill_to_state edges
        for skill_id, states in hg_data.get("skill_to_state", {}).items():
            self.graph.skill_to_state[skill_id] = set(states)
            for s in states:
                self.graph.add_state(s)
        # Restore skill_to_skill edges
        for skill_id, successors in hg_data.get("skill_to_skill", {}).items():
            self.graph.skill_to_skill[skill_id] = set(successors)

    def _navigate_via_prefix(self, browser, target_url: str) -> dict | None:
        """Navigate to target_url by replaying prefix steps from source page.

        Instead of doing browser.goto(target_url) directly (which can break
        state), this replays the actual click/fill actions that were recorded
        when the URL was first discovered. This preserves login and session state.

        Returns the observation dict at the target URL, or None if navigation
        fails (fall back to direct goto).
        """
        info = self._discovered_urls.get(target_url)
        self._last_prefix_replay_status = {
            "attempted": False,
            "ok": False,
            "reason": "no_prefix",
            "arrived_url": "",
            "expected_url": target_url,
            "stateful": False,
            "used_direct_goto": False,
        }
        if not info:
            return None

        prefix_steps = info.get("prefix_steps", [])
        source_url = info.get("source_url", "")
        stateful_prefix = self._prefix_contains_state_change(prefix_steps)
        self._last_prefix_replay_status.update({
            "attempted": True,
            "reason": "started",
            "stateful": stateful_prefix,
        })

        if not prefix_steps or not source_url:
            self._last_prefix_replay_status["reason"] = "missing_prefix_steps_or_source"
            return None

        msg = f"      [prefix] Replaying {len(prefix_steps)} steps from {source_url[:60]}..."
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()

        # Navigate to the source URL first (this is a direct goto, but it's
        # the starting point of the prefix — the prefix itself is natural clicks)
        try:
            browser.act(f"goto('{source_url}')")
        except Exception as e:
            self._last_prefix_replay_status["reason"] = f"goto_source_failed:{e}"
            msg = f"      [prefix] goto source FAILED: {e}"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            return None

        # Replay each step in the prefix
        for i, step in enumerate(prefix_steps):
            action = step.action if isinstance(step, Step) else step.get("action", "")
            action = (action or "").strip()
            if not action:
                continue
            if action.startswith("goto(") or action.startswith("send_msg"):
                self._last_prefix_replay_status["reason"] = f"non_replayable_action:{action[:40]}"
                msg = f"      [prefix] step {i} rejected: non-replayable action {action[:50]}"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
                return None
            current_obs = browser.observation()
            validation = validate_hsge_action(
                action, current_obs.get("axtree", ""), allow_goto=False
            )
            if not validation.ok:
                self._last_prefix_replay_status["reason"] = f"stale_action:{validation.reason}"
                msg = f"      [prefix] step {i} stale: {validation.reason}"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
                return None
            if validation.target_line and self._text_suggests_state_change(validation.target_line):
                stateful_prefix = True
                self._last_prefix_replay_status["stateful"] = True
            try:
                browser.act(action)
            except Exception as e:
                self._last_prefix_replay_status["reason"] = f"step_failed:{e}"
                msg = f"      [prefix] step {i} FAILED: {action[:50]} ({e})"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
                return None

        # Verify we arrived at the target
        obs = browser.observation()
        def _norm(u): return urlunparse((urlparse(u).scheme, urlparse(u).netloc, urlparse(u).path.rstrip('/'), '', '', ''))
        arrived = _norm(obs.get("url", ""))
        self._last_prefix_replay_status["arrived_url"] = arrived

        if arrived == target_url:
            self._last_prefix_replay_status.update({"ok": True, "reason": "arrived"})
            msg = f"      [prefix] ✅ Arrived at {target_url[:60]}"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            return obs
        else:
            self._last_prefix_replay_status["reason"] = "url_mismatch"
            msg = f"      [prefix] ⚠️  Expected {target_url[:60]}, got {arrived[:60]}"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            return None

    @staticmethod
    def _text_suggests_state_change(text: str) -> bool:
        return bool(re.search(
            r"\b(add|remove|delete|cancel|archive|deactivate|disable|submit|send|"
            r"publish|post|save|apply|confirm|book|reserve|subscribe|checkout|"
            r"purchase|payment|pay|refund|return|reorder|compare|wishlist|cart|"
            r"continue|next|complete|finish)\b",
            text or "",
            re.IGNORECASE,
        ))

    @classmethod
    def _prefix_contains_state_change(cls, prefix_steps: list) -> bool:
        for step in prefix_steps:
            action = step.action if isinstance(step, Step) else step.get("action", "")
            summary = step.obs_summary if isinstance(step, Step) else step.get("obs_summary", "")
            if cls._text_suggests_state_change(f"{action} {summary}"):
                return True
        return False

    def _reset_browser_to_node(self, browser, url: str, actual_url: str) -> dict:
        """Return browser to the node state before each local task.

        Correctness first: if the node was reached through a prefix trace, replay
        that trace again instead of relying on BrowserGym reset, which may go
        back to the original start URL and lose query/stateful navigation.
        """
        def _norm(u: str) -> str:
            p = urlparse(u)
            return urlunparse((p.scheme, p.netloc, p.path.rstrip('/'), '', '', ''))

        if url in self._discovered_urls:
            obs = self._navigate_via_prefix(browser, url)
            return obs or {"url": "", "axtree": ""}

        obs = browser.reset()
        if obs.get("url") and _norm(obs.get("url", "")) != actual_url:
            try:
                browser.act(f"goto('{actual_url}')")
                obs = browser.observation()
            except Exception:
                return {"url": "", "axtree": ""}
        return obs

    def _process_node(self, url, depth, root_url, frontier, visited, queued, node_num):
        """Process one node with full error isolation.

        Each node: reset env → create browser → navigate (via prefix or direct) →
        explore local tasks → attempt goal task → expand frontier.

        Navigation prefers prefix trace replay over direct browser.goto()
        to preserve session state (Go-Browse style).
        """
        def _norm(u: str) -> str:
            p = urlparse(u)
            return urlunparse((p.scheme, p.netloc, p.path.rstrip('/'), '', '', ''))

        # KHÔNG gọi _reset_env() ở đây — nó xóa session trên server,
        # làm cho storage_state cookie (PHPSESSID) trở nên vô dụng.
        # Mỗi node đã dùng browser context mới (state sạch), và
        # storage_state cung cấp session login sẵn.

        # Create browser with timeout protection
        browser = None
        try:
            # Try prefix-based navigation first (replay natural clicks)
            browser = self.browser_factory(url)
            obs = browser.reset()

            # If we have a prefix trace for this URL, use it instead of direct goto
            if obs.get("url") and url in self._discovered_urls:
                prefix_obs = self._navigate_via_prefix(browser, url)
                if prefix_obs is not None:
                    obs = prefix_obs
                else:
                    status = getattr(self, "_last_prefix_replay_status", {})
                    if status.get("stateful"):
                        msg = (
                            f"      [prefix] SKIP stale stateful prefix for {url[:60]} "
                            f"(reason={status.get('reason')}, arrived={status.get('arrived_url')})"
                        )
                        print(msg)
                        if self._log_file:
                            self._log_file.write(msg + "\n")
                            self._log_file.flush()
                        try:
                            browser.close()
                        except Exception:
                            pass
                        return None
                    # Prefix failed — fall back to fresh browser
                    msg = f"      [prefix] Fallback to direct goto for {url[:60]}"
                    print(msg)
                    if self._log_file:
                        self._log_file.write(msg + "\n")
                        self._log_file.flush()
                    status["used_direct_goto"] = True
                    try:
                        browser.close()
                    except Exception:
                        pass
                    browser = self.browser_factory(url)
                    obs = browser.reset()
        except Exception as e:
            msg = f"[node {node_num} depth={depth}] SKIP {url}  (load error: {e})"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            return None

        if not obs.get("url"):
            msg = f"[node {node_num} depth={depth}] SKIP {url}  (empty observation after reset)"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            try:
                browser.close()
            except Exception:
                pass
            return None

        actual_url = _norm(obs['url'])

        # Lưu axtree vào cache (nếu chưa có từ lần fetch trước)
        if actual_url not in self._axtree_cache:
            self._axtree_cache[actual_url] = obs.get("axtree", "")

        # Skip if redirected to an already-visited page (e.g. wishlist → login)
        if actual_url in visited and actual_url != url:
            msg = f"[node {node_num} depth={depth}] SKIP {url} → redirect to already-visited {actual_url}"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            try:
                browser.close()
            except Exception:
                pass
            return None

        msg = f"[node {node_num} depth={depth}] {actual_url}"
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()

        # Track episode range cho node này
        _ep_start = self.episode

        # Root node: detect domain type, common tasks và common actions
        if depth == 0:
            self.explorer.detect_domain(obs)
            # Lưu domain info ra file
            domain_info = {
                "domain_type": self.explorer.domain_type,
                "common_tasks": self.explorer.common_tasks,
                "common_actions": self.explorer.common_actions,
            }
            domain_path = os.path.join(self.out_dir, "domain.json")
            json.dump(domain_info, open(domain_path, "w", encoding="utf-8"), indent=2)
            msg_domain = f"  [domain] Saved to {domain_path}"
            print(msg_domain)
            if self._log_file:
                self._log_file.write(msg_domain + "\n")
                self._log_file.flush()

        # Track whether any task succeeded on this node (for UVD scorer)
        _any_success = False

        # 1) local exploration (with skill hints when available)
        skill_hints = self._build_skill_hints(page_url=actual_url)
        _node_task_records = []  # track task outcomes for this node
        raw_proposed_tasks = self.explorer.propose(obs, skill_hints=skill_hints)
        proposed_tasks = self._rank_tasks_for_coverage(raw_proposed_tasks)
        skipped_repeats = len(raw_proposed_tasks) - len(proposed_tasks)
        if skipped_repeats:
            msg_repeat = f"  [tasks] Skipped {skipped_repeats} repeated/saturated proposal(s)"
            print(msg_repeat)
            if self._log_file:
                self._log_file.write(msg_repeat + "\n")
                self._log_file.flush()
        for task in proposed_tasks:
            self.metrics.tasks_proposed += 1
            is_checkout_task = self._is_checkout_task(task)
            if is_checkout_task:
                self.metrics.checkout_tasks_attempted += 1
            task_record = {
                "goal": task,
                "family": task_family(task),
                "status": "attempted",
                "episode_id": None,
            }
            _node_task_records.append(task_record)
            task_key = self._task_key(task)
            self._task_attempt_counts[task_key] += 1
            try:
                reset_obs = self._reset_browser_to_node(browser, url, actual_url)
                if not reset_obs.get("url"):
                    task_record["status"] = "skipped"
                    msg_skip = f"    local: {task!r} SKIP (reset failed)"
                    print(msg_skip)
                    if self._log_file:
                        self._log_file.write(msg_skip + "\n")
                        self._log_file.flush()
                    continue
                task_hints = self._build_skill_hints(task=task)
                safe_hint = self._checkout_safety_hint(task)
                if safe_hint:
                    task_hints = safe_hint + "\n\n" + task_hints if task_hints else safe_hint
                # Append account credentials to solver prompt
                if self._account_info:
                    task_hints = self._account_info + "\n\n" + task_hints if task_hints else self._account_info
                task_tools = self._build_tools(task=task)
                steps, obs_texts, final_obs, success, screenshots = self.solver.solve(
                    browser, task, skill_hints=task_hints, tools=task_tools,
                    step_callback=self._on_step_completed)
                ep_id = self.episode
                self._record(task, steps, obs_texts, success, difficulty=1, tag="LOCAL",
                             screenshots=screenshots)
                task_record["episode_id"] = ep_id
                if success:
                    task_record["status"] = "solved"
                    if is_checkout_task:
                        self.metrics.checkout_tasks_solved += 1
                    self._task_success_counts[task_key] += 1
                    _any_success = True
                    self.metrics.tasks_solved += 1
                    self._mine_operator(task, steps, obs_texts, final_obs)
                    self.discovery.on_trajectory(steps, site=root_url, task=task)
                else:
                    task_record["status"] = "failed"
                    self.metrics.tasks_failed += 1
                    self._task_failure_counts[task_key] += 1
                    self._task_family_failure_counts[task_family(task)] += 1
                msg2 = f"    local: {task!r} success={success}"
                print(msg2)
                if self._log_file:
                    self._log_file.write(msg2 + "\n")
                    self._log_file.flush()
            except Exception as e:
                task_record["status"] = "error"
                self.metrics.errors += 1
                self.metrics.tasks_error += 1
                self._task_error_counts[task_key] += 1
                msg_err = f"    local: {task!r} ERROR: {e}"
                print(msg_err)
                if self._log_file:
                    self._log_file.write(msg_err + "\n")
                    self._log_file.flush()
                continue

        # 2) goal-conditioned composed task (once a plan to the goal exists)
        gt = self._goal_task(predicates_from(actual_url, obs.get("axtree", "")))
        if gt:
            self.metrics.goal_tasks_attempted += 1
            self.metrics.composed_goal_tasks_attempted += 1
            goal_record = {
                "goal": gt["goal"],
                "family": task_family(gt["goal"]),
                "status": "attempted",
                "episode_id": None,
            }
            _node_task_records.append(goal_record)
            try:
                reset_obs = self._reset_browser_to_node(browser, url, actual_url)
                if not reset_obs.get("url"):
                    goal_record["status"] = "skipped"
                    msg_skip = f"    GOAL SKIP (reset failed)"
                    print(msg_skip)
                    if self._log_file:
                        self._log_file.write(msg_skip + "\n")
                        self._log_file.flush()
                else:
                    task_hints = self._build_skill_hints(task=gt["goal"])
                    safe_hint = self._checkout_safety_hint(gt["goal"])
                    if safe_hint:
                        task_hints = safe_hint + "\n\n" + task_hints if task_hints else safe_hint
                    if self._account_info:
                        task_hints = self._account_info + "\n\n" + task_hints if task_hints else self._account_info
                    task_tools = self._build_tools(task=gt["goal"])
                    steps, obs_texts, final_obs, success, screenshots = self.solver.solve(
                        browser, gt["goal"], goal_predicate=self.terminal_goal,
                        skill_hints=task_hints, tools=task_tools,
                        step_callback=self._on_step_completed)
                    ep_id = self.episode
                    self._record(gt["goal"], steps, obs_texts, success,
                                 difficulty=gt["difficulty"], tag="GOAL",
                                 screenshots=screenshots)
                    goal_record["episode_id"] = ep_id
                    if success:
                        goal_record["status"] = "solved"
                        _any_success = True
                        self.metrics.goal_tasks_solved += 1
                    else:
                        goal_record["status"] = "failed"
                        self.metrics.tasks_failed += 1
                    msg3 = f"    GOAL chain={gt['chain']} verified={success}"
                    print(msg3)
                    if self._log_file:
                        self._log_file.write(msg3 + "\n")
                        self._log_file.flush()
            except Exception as e:
                goal_record["status"] = "error"
                self.metrics.errors += 1
                self.metrics.tasks_error += 1
                msg_err = f"    GOAL ERROR: {e}"
                print(msg_err)
                if self._log_file:
                    self._log_file.write(msg_err + "\n")
                    self._log_file.flush()

        # Record exploration outcome for UVD scorer (Go-Browse style)
        self._url_attempts[actual_url] = self._url_attempts.get(actual_url, 0) + 1
        if _any_success:
            self._url_successes[actual_url] = self._url_successes.get(actual_url, 0) + 1
        total = self._url_attempts.get(actual_url, 0)
        succ = self._url_successes.get(actual_url, 0)
        self._frontier_scorer.record_exploration(
            actual_url, success=_any_success, parent_url=url,
            total_trajs=total, successful_trajs=succ,
        )

        # 3) expand frontier — CHỈ từ callback-discovered URLs (phát hiện trong lúc solve task)
        #     Không còn query DOM <a href> hay filter_frontier nữa.
        #     URL chỉ được thêm vào frontier khi agent thực sự đi đến URL đó.
        _node_children = []
        _node_lookahead = []
        try:
            new_urls = []
            for discovered_url, info in list(self._discovered_urls.items()):
                if (discovered_url not in queued
                    and discovered_url not in visited
                    and discovered_url not in {url, actual_url}
                    and self.allow.search(discovered_url)
                    and not any(d.search(discovered_url) for d in self._denylist)):
                    new_urls.append(discovered_url)
            # Prefix được giữ lại trong _discovered_urls cho đến khi dùng thành công

            for link in new_urls:
                _node_children.append(link)
                queued.add(link)
                frontier.append((link, depth + 1))
                self._frontier_scorer.set_parent(link, actual_url)
                # Lookahead: dùng axtree từ cache (đã fetch trong _fetch_axtree_for_frontier)
                # Nếu chưa có, dùng axtree của node hiện tại làm proxy
                cached = self._axtree_cache.get(link)
                axtree_for_lookahead = cached or self._axtree_cache.get(actual_url, obs.get("axtree", ""))
                try:
                    lookahead = self._lookahead_predictor.propose(
                        axtree_for_lookahead[:3500]
                    )
                    self._frontier_scorer.set_lookahead(link, lookahead)
                    _node_lookahead = lookahead
                except Exception:
                    pass
            if new_urls:
                msg = f"  [frontier] +{len(new_urls)} URLs from callback discovery"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
        except Exception as e:
            self.metrics.errors += 1
            msg_err = f"    frontier expansion ERROR: {e}"
            print(msg_err)
            if self._log_file:
                self._log_file.write(msg_err + "\n")
                self._log_file.flush()
        finally:
            try:
                browser.close()
            except Exception:
                pass

        # Dump frontier snapshot after each node (Go-Browse style with full scores)
        frontier_snapshot = []
        for u, d in frontier:
            breakdown = self._frontier_scorer.breakdown(u, visited)
            frontier_snapshot.append({
                "url": u,
                "depth": d,
                "score": round(breakdown["score"], 4),
                "U": round(breakdown["U"], 4),
                "V": round(breakdown["V"], 4),
                "V_sr": round(breakdown["V_sr"], 4),
                "V_sr_source": breakdown["V_sr_source"],
                "V_n": breakdown["V_n"],
                "V_n_source": breakdown["V_n_source"],
            })
        # Sort by score descending for the snapshot
        frontier_snapshot.sort(key=lambda x: -x["score"])
        self._frontier_file.write(json.dumps({
            "node": node_num,
            "depth": depth,
            "url": actual_url,
            "frontier_size": len(frontier),
            "frontier": frontier_snapshot,
        }) + "\n")
        self._frontier_file.flush()

        # Save per-node info to nodes/node_{N}/node_info.json
        total_trajs = self._url_attempts.get(actual_url, 0)
        successful_trajs = self._url_successes.get(actual_url, 0)
        # selected_child_count = số child đã được chọn từ node này (V_n)
        selected_child_count = self._frontier_scorer._selected_child_count.get(actual_url, 0)
        node_breakdown = self._frontier_scorer.breakdown(actual_url, visited)
        node_score = node_breakdown.get("score", 0.0)
        _ep_end = self.episode
        # Lấy lookahead của chính node này (đã được fetch từ _fetch_axtree_for_frontier)
        node_lookahead = self._frontier_scorer._lookahead.get(actual_url, _node_lookahead)
        self._save_node_info(
            node_num=node_num,
            url=actual_url,
            depth=depth,
            children=_node_children,
            visited=True,
            total_trajs=total_trajs,
            successful_trajs=successful_trajs,
            selected_child_count=selected_child_count,
            frontier_score=node_score,
            frontier_breakdown=node_breakdown,
            lookahead_candidates=node_lookahead,
            parent_url=url,
            tasks=_node_task_records,
            episode_range=[_ep_start, _ep_end],
        )
        return actual_url

    def _replay_episodes(self) -> None:
        """Replay all existing episodes through discovery to rebuild the skill
        library, operator graph, and hierarchical graph.

        This is called on resume so that previously learned skills are available
        for skill hints and transfer without re-exploring those pages.

        If full state was restored from a v2 checkpoint, replay is skipped
        (operator graph, hierarchical graph, and clusterer are already restored).
        """
        if getattr(self, '_full_state_restored', False):
            n_skills = len(self.library.all_skills())
            n_ops = len(self.opgraph.ops)
            print(f"[resume] Full state restored from v2 checkpoint: "
                  f"{n_skills} skills, {n_ops} operators (skipping replay)")
            return

        ep_dir = os.path.join(self.out_dir, "episodes")
        if not os.path.isdir(ep_dir):
            return
        episodes = sorted(
            [d for d in os.listdir(ep_dir) if d.startswith("ep_")],
            key=lambda x: int(x.split("_")[1]),
        )
        if not episodes:
            return
        # Clear callback-discovered URLs from checkpoint — they are stale
        # and will be re-discovered during new exploration.
        self._discovered_urls.clear()
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
                    steps.append(Step(action=action, url=url, obs_summary=rec.get("thought", "")))
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

    # ---- per-node info persistence (Go-Browse style) -------------------------
    def _save_node_info(self, node_num: int, url: str, depth: int,
                         children: list[str], visited: bool,
                         total_trajs: int, successful_trajs: int,
                         selected_child_count: int,
                         frontier_score: float, frontier_breakdown: dict,
                         lookahead_candidates: list[dict],
                         parent_url: str | None = None,
                         tasks: list[dict | str] | None = None,
                         episode_range: list[int] | None = None) -> None:
        """Save detailed per-node metadata to nodes/node_{N}/node_info.json.

        Matches Go-Browse's node_info.json schema so analysis tools can
        process both formats uniformly.
        """
        nodes_dir = os.path.join(self.out_dir, "nodes", f"node_{node_num}")
        os.makedirs(nodes_dir, exist_ok=True)
        sr = (successful_trajs / total_trajs) if total_trajs > 0 else 0.0
        task_records = self._normalize_node_task_records(tasks or [])
        tasks_attempted = sum(1 for t in task_records if t.get("status") != "skipped")
        tasks_solved = sum(1 for t in task_records if t.get("status") == "solved")
        tasks_failed = sum(1 for t in task_records if t.get("status") == "failed")
        tasks_error = sum(1 for t in task_records if t.get("status") == "error")
        tasks_skipped = sum(1 for t in task_records if t.get("status") == "skipped")
        task_success_rate = (tasks_solved / tasks_attempted) if tasks_attempted > 0 else 0.0
        info = {
            "url": url,
            "description": "",
            "children": children,
            "visited": visited,
            "misc": {
                "depth": depth,
                "parent_url": parent_url,
            },
            "exploration_count": total_trajs,
            "success_rate": round(sr, 6),
            "node_success_rate": round(sr, 6),
            "task_success_rate": round(task_success_rate, 6),
            "tasks_attempted": tasks_attempted,
            "tasks_solved": tasks_solved,
            "tasks_failed": tasks_failed,
            "tasks_error": tasks_error,
            "tasks_skipped": tasks_skipped,
            "total_trajs": total_trajs,
            "successful_trajs": successful_trajs,
            "selected_child_count": selected_child_count,
            "frontier_score": round(frontier_score, 6),
            "frontier_breakdown": frontier_breakdown,
            "lookahead_candidates": lookahead_candidates,
            "parent_url": parent_url,
            "depth": depth,
            "tasks": task_records,
            "episode_range": episode_range or [],
        }
        path = os.path.join(nodes_dir, "node_info.json")
        json.dump(info, open(path, "w", encoding="utf-8"), indent=4)

    @staticmethod
    def _normalize_node_task_records(tasks: list[dict | str]) -> list[dict]:
        out: list[dict] = []
        for item in tasks:
            if isinstance(item, dict):
                goal = item.get("goal", "")
                status = item.get("status", "attempted")
                out.append({
                    "goal": goal,
                    "family": item.get("family") or task_family(goal),
                    "status": status,
                    "episode_id": item.get("episode_id"),
                })
            else:
                goal = str(item)
                out.append({
                    "goal": goal,
                    "family": task_family(goal),
                    "status": "attempted",
                    "episode_id": None,
                })
        return out

    # ---- frontier axtree fetching for lookahead ------------------------------
    def _fetch_axtree_for_frontier(self, frontier: list[tuple[str, int]]) -> None:
        """Duyệt từng URL trong frontier, fetch axtree và propose lookahead.

        Với mỗi URL chưa có lookahead, tạo browser tạm, goto URL, lấy axtree,
        propose lookahead candidates, rồi close browser.
        Lưu axtree vào cache để dùng lại khi explore node đó.
        """
        for url, depth in frontier:
            if depth == 0:
                continue  # root node không cần lookahead
            if self._frontier_scorer._lookahead.get(url):
                continue  # đã có lookahead rồi
            if url in self._axtree_cache:
                # Đã fetch rồi, dùng cache để propose lookahead
                try:
                    lookahead = self._lookahead_predictor.propose(
                        self._axtree_cache[url][:3500]
                    )
                    self._frontier_scorer.set_lookahead(url, lookahead)
                except Exception:
                    pass
                continue

            # Fetch axtree thật bằng browser
            browser = None
            try:
                browser = self.browser_factory(url)
                obs = browser.reset()
                if obs.get("url") and obs.get("axtree"):
                    axtree = obs["axtree"]
                    self._axtree_cache[url] = axtree
                    lookahead = self._lookahead_predictor.propose(axtree[:3500])
                    self._frontier_scorer.set_lookahead(url, lookahead)
                    msg = f"  [lookahead] Fetched axtree for {url[:80]}... ({len(axtree)} chars)"
                    print(msg)
                    if self._log_file:
                        self._log_file.write(msg + "\n")
                        self._log_file.flush()
            except Exception as e:
                msg = f"  [lookahead] SKIP {url[:60]} (fetch error: {e})"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
            finally:
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass

    # ---- the loop ------------------------------------------------------------
    def run(self, root_url: str):
        # Normalize URLs: strip trailing slash, query string, and fragment.
        def _norm(u: str) -> str:
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
        # Lưu axtree đã fetch cho từng URL (tránh fetch lại khi explore)
        self._axtree_cache: dict[str, str] = {}
        while frontier and nodes_processed < self.max_nodes:
            # Fetch axtree cho các URL trong frontier chưa có lookahead
            self._fetch_axtree_for_frontier(frontier)

            # Use UVD scorer to select the best node from frontier
            scored = self._frontier_scorer.score_all(frontier, visited)
            if not scored:
                break
            # Log full frontier ranking (Go-Browse style)
            frontier_log = []
            for rank, (s, u, d) in enumerate(scored):
                breakdown = self._frontier_scorer.breakdown(u, visited)
                frontier_log.append({
                    "rank": rank + 1,
                    "url": u,
                    "depth": d,
                    "score": round(s, 4),
                    "U": round(breakdown["U"], 4),
                    "V": round(breakdown["V"], 4),
                    "V_sr": round(breakdown["V_sr"], 4),
                    "V_sr_source": breakdown["V_sr_source"],
                    "V_n": breakdown["V_n"],
                    "V_n_source": breakdown["V_n_source"],
                })
            # Print top-5 to console
            print(f"  [frontier] ranking ({len(scored)} nodes):")
            for entry in frontier_log[:5]:
                print(f"    #{entry['rank']} score={entry['score']:.3f} "
                      f"U={entry['U']:.3f} V={entry['V']:.3f} "
                      f"depth={entry['depth']} {entry['url'][:80]}")
            if len(scored) > 5:
                print(f"    ... and {len(scored) - 5} more")

            # Remove the selected node from frontier
            _score, url, depth = scored[0]
            frontier = [(u, d) for u, d in frontier if u != url]
            if url in visited or depth > self.max_depth:
                continue
            node_num = nodes_processed + 1

            # Ghi nhận parent đã chọn 1 child (cho V_n)
            parent_url = self._frontier_scorer._parent_url.get(url)

            # Error-isolated node processing: any failure in one node
            # is caught, logged, and skipped — the run continues.
            try:
                processed_url = self._process_node(
                    url, depth, root_url,
                    frontier, visited, queued, node_num,
                )
            except Exception as e:
                self.metrics.errors += 1
                self.metrics.nodes_error += 1
                msg = f"[node {node_num} depth={depth}] ERROR: {e}"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
                # Save emergency checkpoint and continue
                self.save_checkpoint(frontier, visited, queued)
                continue

            if not processed_url:
                self.save_checkpoint(frontier, visited, queued)
                continue

            visited.add(url)
            visited.add(processed_url)
            nodes_processed += 1
            self.metrics.nodes_visited += 1
            self.metrics.nodes_processed = nodes_processed
            if parent_url:
                self._frontier_scorer.record_child_selection(parent_url)

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

        # Update metrics with final counts
        self.metrics.nodes_processed = nodes_processed
        self.metrics.skills_discovered = len(self.library.all_skills())
        self.metrics.skills_verified = len([s for s in self.library.all_skills() if s.verified])
        self._refresh_skill_diversity_metrics()
        self.metrics.operators_mined = len(self.opgraph.ops)

        print(f"\ndone: {nodes_processed} nodes, {self.episode} episodes, "
              f"{len(self.library.all_skills())} skills, {len(self.opgraph.ops)} operators")
        print(f"trajectories under {self.out_dir}/episodes  "
              f"(feed to build_sft_dataset.py)")

        # Print metrics summary
        print(self.metrics.summary())

        # Save metrics to file
        metrics_path = os.path.join(self.out_dir, "metrics.json")
        import dataclasses
        json.dump(dataclasses.asdict(self.metrics),
                  open(metrics_path, "w", encoding="utf-8"), indent=2)
        print(f"metrics exported to {metrics_path}")

        # Final checkpoint save
        self.save_checkpoint(frontier, visited, queued)
