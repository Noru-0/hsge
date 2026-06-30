"""WebArena exploration runtime for HSGE.

Frontier loop over URLs. Successful local trajectories feed HSGE Discovery;
verified SkillCards retain observed symbolic preconditions/effects and expose an
Operator view under the same skill_id. The planner uses only those operators to
compose longer goals. The Solver receives the resulting natural-language goal,
never learned skill hints, templates, or tools.
"""
from __future__ import annotations

import json
import os
import re
import time
from fnmatch import fnmatchcase
from collections import Counter
from dataclasses import dataclass, field

from .action_validation import (
    action_family,
    axtree_elements,
    parse_hsge_action,
    repair_thought,
    task_family,
    validate_hsge_action,
)
from ..discovery import Discovery
from ..graph import HierarchicalGraph
from ..library import SkillLibrary
from ..operators import plan
from ..curriculum import generate_curriculum
from ..transfer import TransferResult
from ..schema import ParamSlot, SkillCard, SkillStats, Step
from ..segmentation import segment_trajectory
from .agents import PageExplorer, Solver
from .frontier_filter import filter_frontier
from .observability import ExploreEventLogger
from .predicates import build_predicate_extractor, predicates_from, reached
from .verification_context import make_verify_contexts_fn
from .scoring import FrontierScorer, LookaheadPredictor
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


PREFIX_TRACE_SCHEMA_VERSION = 2
DEFAULT_IGNORED_QUERY_PARAMS = (
    "utm_*", "gclid", "fbclid", "msclkid", "dclid", "_ga", "_gl",
)


def _atomic_json_dump(path: str, value, **kwargs) -> None:
    """Write JSON through a sibling temporary file, then atomically replace."""
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, **kwargs)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _normalize_trace_url(
    url: str,
    ignored_query_params: tuple[str, ...] | list[str] = DEFAULT_IGNORED_QUERY_PARAMS,
) -> str:
    """Return a stable node identity while preserving semantic query state."""
    p = urlparse(url or "")
    ignored = tuple(pattern.lower() for pattern in ignored_query_params)
    query = [
        (key, value)
        for key, value in parse_qsl(p.query, keep_blank_values=True)
        if not any(fnmatchcase(key.lower(), pattern) for pattern in ignored)
    ]
    query.sort()
    return urlunparse((
        p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), '',
        urlencode(query, doseq=True), '',
    ))


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
    solver_navigation_events: int = 0
    solver_unique_urls_discovered: int = 0
    solver_urls_duplicate: int = 0
    solver_urls_cross_origin: int = 0
    solver_urls_already_visited: int = 0
    solver_urls_already_queued: int = 0
    solver_urls_denied: int = 0
    solver_urls_outside_allowlist: int = 0
    solver_urls_frontier_eligible: int = 0
    solver_urls_added_to_frontier: int = 0
    solver_urls_dropped_capacity: int = 0
    dom_urls_considered: int = 0
    dom_urls_added_to_frontier: int = 0
    event_counts: dict[str, int] = field(default_factory=dict)
    execution_skills_verified: int = 0
    planner_ready_skills: int = 0
    effectless_skills: int = 0
    reachable_goals: int = 0
    terminal_tasks: int = 0
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
            f"\n  Skill tiers: {self.execution_skills_verified} execution-verified, "
            f"{self.planner_ready_skills} planner-ready, {self.effectless_skills} effectless"
            f"\n  Skill families: {self.skill_families_verified}/{self.skill_diversity_target}"
            f"\n  Segments: {self.segments_created}, clusters matured: {self.clusters_matured}"
            f"\n  Operators: {self.operators_mined}; reachable goals: "
            f"{self.reachable_goals}, terminal tasks: {self.terminal_tasks}"
            f"\n  Goal tasks: {self.goal_tasks_solved}/{self.goal_tasks_attempted}"
            f"\n  Solver URLs: {self.solver_unique_urls_discovered} unique / "
            f"{self.solver_navigation_events} navigations, "
            f"{self.solver_urls_added_to_frontier} added to frontier"
            f"\n  DOM fallback URLs: {self.dom_urls_added_to_frontier}/"
            f"{self.dom_urls_considered} added"
            f"\n  LLM calls: {self.total_llm_calls}, tokens: {self.total_llm_tokens}"
            f"\n  Errors: {self.errors}"
            f"\n{'='*50}"
        )


@dataclass
class PrefixTraceStep:
    """One replayable action inside a URL-discovery prefix trace."""
    action: str
    source_url: str
    target_url: str
    thought: str = ""
    stateful_hint: bool = False
    target_bid: str = ""
    target_role: str = ""
    target_name: str = ""
    target_fingerprint: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "source_url": self.source_url,
            "target_url": self.target_url,
            "thought": self.thought,
            "stateful_hint": self.stateful_hint,
            "target_bid": self.target_bid,
            "target_role": self.target_role,
            "target_name": self.target_name,
            "target_fingerprint": self.target_fingerprint,
        }


@dataclass
class PrefixTrace:
    """Versioned runtime-local schema for replaying discovered frontier URLs."""
    source_url: str
    target_url: str
    discovered_by_action: str
    steps: list[PrefixTraceStep]
    created_at: float = field(default_factory=time.time)
    schema_version: int = PREFIX_TRACE_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "source_url": self.source_url,
            "target_url": self.target_url,
            "discovered_by_action": self.discovered_by_action,
            "created_at": self.created_at,
            "steps": [s.to_dict() for s in self.steps],
        }


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
                 place_order_allowed: bool = False,
                 max_goal_attempts: int = 3,
                 explorer_max_tasks: int = 12,
                 explorer_profile: str = "training_quality",
                 solver_profile: str = "training_quality",
                 skill_sim_threshold: float = 0.6,
                 skill_maturity: int = 3,
                 skill_verify_k: int = 2,
                 skill_prune_min_rate: float = 0.34,
                 skill_diversity_target: int = 4,
                 frontier_alpha: float = 1.0,
                 frontier_beta: float = 1.0,
                 frontier_epsilon: float = 1e-5,
                 frontier_select_pool: int = 5,
                 frontier_score_band: float = 0.98,
                 frontier_max_size: int | None = None,
                 prefix_retry_limit: int = 2,
                 load_retry_limit: int = 2,
                 task_retry_limit: int = 3,
                 lookahead_candidates: int = 5,
                 lookahead_model: str | None = None,
                 lookahead_base_url: str | None = None,
                 lookahead_timeout_seconds: float = 30.0,
                 lookahead_max_retries: int = 1,
                 event_log_level: str = "info",
                 predicate_plugins: list[str] | None = None,
                 ignored_query_params: list[str] | None = None):
        self.browser_factory = browser_factory
        self.out_dir = out_dir
        self.allow = re.compile(allow_pattern)
        self.max_depth, self.max_nodes = max_depth, max_nodes
        self._ignored_query_params = tuple(
            ignored_query_params
            if ignored_query_params is not None
            else DEFAULT_IGNORED_QUERY_PARAMS
        )
        self.terminal_goal = terminal_goal
        self.goal_instruction = goal_instruction
        self.checkout_mode = checkout_mode
        self.auto_terminal_goals = auto_terminal_goals
        self.place_order_allowed = place_order_allowed
        self.max_goal_attempts = max(1, max_goal_attempts)
        self._task_retry_limit = max(1, task_retry_limit)
        self._prefix_retry_limit = max(1, prefix_retry_limit)
        self._load_retry_limit = max(1, load_retry_limit)
        self._predicate_plugin_names = list(predicate_plugins or ["auto"])
        explicit_plugins = [p for p in self._predicate_plugin_names if p != "auto"]
        self.predicate_extractor = build_predicate_extractor(explicit_plugins)
        # support both old single-llm API and new separate explorer/solver llms
        _explorer_llm = explorer_llm or llm
        _solver_llm = solver_llm or llm
        if not _explorer_llm or not _solver_llm:
            raise ValueError("Must provide llm= or both explorer_llm= and solver_llm=")
        self.explorer = PageExplorer(
            _explorer_llm,
            max_tasks=max(1, explorer_max_tasks),
            profile=explorer_profile,
            checkout_mode=checkout_mode,
            place_order_allowed=place_order_allowed,
        )
        self.solver = Solver(_solver_llm, max_steps=max_steps, profile=solver_profile)
        self.goal_composer_llm = _explorer_llm
        self.graph = HierarchicalGraph()
        # Compatibility alias only; HierarchicalGraph owns the canonical
        # operator collection and all high-level composition semantics.
        self.opgraph = self.graph.operator_graph
        # HSGE discovery with verification gate: skills are verified by replaying
        # on contexts built from successful episodes (different pages/sites).
        self.library = SkillLibrary(
            _explorer_llm, embedder,
            verify_contexts_fn=make_verify_contexts_fn(out_dir, browser_factory),
            sim_threshold=skill_sim_threshold,
            maturity=max(1, skill_maturity),
            verify_k=max(0, skill_verify_k),
            prune_min_rate=skill_prune_min_rate,
            predicate_extractor=self.predicate_extractor,
        )
        self.discovery = Discovery(
            self.library, self.graph, predicate_extractor=self.predicate_extractor
        )
        self._curriculum_initial_predicates: set[str] = set()
        self.episode = 0
        # Callback-discovered URLs with versioned prefix traces (for frontier expansion).
        # Stored as {normalized_url: PrefixTrace}; legacy dict entries are normalized
        # at checkpoint/replay boundaries for backward compatibility.
        self._discovered_urls: dict[str, PrefixTrace | dict] = {}
        # Skill admission callback: log + save to JSON
        self._skills_log: list[dict] = []
        self._curriculum_log: list[dict] = []
        self._transfer_log: list[dict] = []
        self._node_url_stats: Counter[str] = Counter()
        self._node_solver_urls: set[str] = set()
        self._active_node_id: int | None = None
        self._active_task_id: str | None = None
        self._active_episode_id: int | None = None
        self.library._on_admit = self._on_skill_admitted
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
            _lookahead_base_url = lookahead_base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
            _lookahead_model = lookahead_model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
            if _lookahead_api_key:
                _lookahead_llm = OpenAILLM(
                    model=_lookahead_model,
                    api_key=_lookahead_api_key,
                    base_url=_lookahead_base_url,
                    timeout_seconds=lookahead_timeout_seconds,
                    max_retries=max(0, lookahead_max_retries),
                )
            else:
                _lookahead_llm = None
        except Exception:
            _lookahead_llm = None
        self._lookahead_predictor = LookaheadPredictor(
            llm=_lookahead_llm, num_candidates=max(1, lookahead_candidates)
        )
        self._frontier_scorer = FrontierScorer(
            alpha=frontier_alpha, beta=frontier_beta, theta=0.0,
            epsilon=frontier_epsilon,
        )
        # Track per-URL stats for the scorer
        self._url_successes: dict[str, int] = {}       # url -> successful trajectories
        self._url_attempts: dict[str, int] = {}         # url -> total trajectories
        self._frontier_selection_counts: dict[str, int] = {}
        self._frontier_select_pool = max(1, frontier_select_pool)
        self._frontier_score_band = frontier_score_band
        self._frontier_max_size = (
            max(1, frontier_max_size)
            if frontier_max_size is not None
            else max(20, min(120, max_nodes * 4))
        )
        self._prefix_retry_counts: dict[str, int] = {}
        self._prefix_retry_limit = max(0, prefix_retry_limit)
        self._load_retry_counts: dict[str, int] = {}
        self._load_retry_limit = max(0, load_retry_limit)
        self._last_node_load_status: dict = {}

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
        self._skill_diversity_target = max(1, skill_diversity_target)

        # Log file (must open BEFORE _replay_episodes so _on_skill_admitted can write)
        log_mode = "a" if resume else "w"
        self._log_file = open(os.path.join(out_dir, "run.log"), log_mode, encoding="utf-8")
        self.event_logger = ExploreEventLogger(
            out_dir,
            level=event_log_level,
            resume=resume,
        )
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

    def _node_key(self, url: str) -> str:
        return _normalize_trace_url(
            url,
            getattr(self, "_ignored_query_params", DEFAULT_IGNORED_QUERY_PARAMS),
        )

    def _emit_event(
        self,
        component: str,
        event: str,
        *,
        level: str = "info",
        data: dict | None = None,
        node_id: int | None = None,
        task_id: str | None = None,
        episode_id: int | None = None,
    ) -> None:
        logger = getattr(self, "event_logger", None)
        if logger is None:
            return
        logger.emit(
            component,
            event,
            level=level,
            node_id=node_id if node_id is not None else getattr(self, "_active_node_id", None),
            task_id=task_id if task_id is not None else getattr(self, "_active_task_id", None),
            episode_id=(
                episode_id
                if episode_id is not None
                else getattr(self, "_active_episode_id", None)
            ),
            data=data,
        )

    def _count_url_metric(self, name: str, amount: int = 1) -> None:
        stats = getattr(self, "_node_url_stats", None)
        if stats is not None:
            stats[name] = stats.get(name, 0) + amount
        metrics = getattr(self, "metrics", None)
        if metrics is not None and hasattr(metrics, name):
            setattr(metrics, name, getattr(metrics, name) + amount)

    def _observed_operator_count(self) -> int:
        graph = getattr(self, "graph", None)
        if graph is not None:
            return len(graph.operator_graph.ops)
        return len(getattr(getattr(self, "opgraph", None), "ops", {}))

    def _observed_composition_count(self) -> int:
        graph = getattr(self, "graph", None)
        if graph is None:
            return 0
        return sum(len(targets) for targets in graph.skill_to_skill.values())

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
        if getattr(self, "_log_file", None):
            self._log_file.write(msg + "\n")
            self._log_file.flush()

    def _prefix_trace_from_transition(
        self,
        action: str,
        url_before: str,
        url_after: str,
        traj_steps: list,
    ) -> PrefixTrace:
        norm_before = self._node_key(url_before)
        norm_after = self._node_key(url_after)
        raw_steps = list(traj_steps or [])
        steps: list[PrefixTraceStep] = []
        for i, step in enumerate(raw_steps):
            step_action = step.action if isinstance(step, Step) else step.get("action", "")
            step_action = (step_action or "").strip()
            thought = step.obs_summary if isinstance(step, Step) else (
                step.get("thought", "") or step.get("obs_summary", "")
            )
            source_url = step.url if isinstance(step, Step) else (
                step.get("source_url", "") or step.get("url", "")
            )
            planning = (
                (step.misc or {}).get("planning", {})
                if isinstance(step, Step)
                else step.get("planning", step.get("misc", {}).get("planning", {}))
            )
            if i + 1 < len(raw_steps):
                next_step = raw_steps[i + 1]
                target_url = next_step.url if isinstance(next_step, Step) else (
                    next_step.get("source_url", "") or next_step.get("url", "")
                )
            else:
                target_url = norm_after
            source_url = self._node_key(source_url) or (steps[-1].target_url if steps else norm_before)
            target_url = self._node_key(target_url) or norm_after
            steps.append(PrefixTraceStep(
                action=step_action,
                source_url=source_url,
                target_url=target_url,
                thought=thought or "",
                stateful_hint=self._text_suggests_state_change(f"{step_action} {thought or ''}"),
                target_bid=str(planning.get("target_bid") or ""),
                target_role=str(planning.get("target_role") or "").lower(),
                target_name=str(planning.get("target_name") or ""),
                target_fingerprint=str(planning.get("target_fingerprint") or ""),
            ))

        if not steps:
            steps.append(PrefixTraceStep(
                action=(action or "").strip(),
                source_url=norm_before,
                target_url=norm_after,
                stateful_hint=self._text_suggests_state_change(action or ""),
            ))

        source_url = steps[0].source_url or norm_before
        return PrefixTrace(
            source_url=source_url,
            target_url=norm_after,
            discovered_by_action=(action or "").strip(),
            steps=steps,
        )

    def _coerce_prefix_trace(self, target_url: str, info) -> PrefixTrace:
        """Accept current and legacy prefix trace records as PrefixTrace."""
        norm_target = self._node_key(target_url)
        if isinstance(info, PrefixTrace):
            if info.target_url == norm_target:
                return info
            return PrefixTrace(
                source_url=info.source_url,
                target_url=norm_target,
                discovered_by_action=info.discovered_by_action,
                steps=info.steps,
                created_at=info.created_at,
                schema_version=info.schema_version,
            )

        info = info or {}
        source_url = self._node_key(info.get("source_url", ""))
        discovered_by_action = info.get("discovered_by_action", info.get("action", ""))
        created_at = info.get("created_at", time.time())
        raw_steps = info.get("steps")
        if raw_steps is None:
            raw_steps = info.get("prefix_steps", [])

        steps: list[PrefixTraceStep] = []
        for i, step in enumerate(raw_steps or []):
            if isinstance(step, PrefixTraceStep):
                steps.append(step)
                continue
            action = step.action if isinstance(step, Step) else step.get("action", "")
            action = (action or "").strip()
            thought = step.obs_summary if isinstance(step, Step) else (
                step.get("thought", "") or step.get("obs_summary", "")
            )
            step_source = ""
            step_target = ""
            if isinstance(step, Step):
                step_source = step.url
            else:
                step_source = step.get("source_url", "") or step.get("url", "")
                step_target = step.get("target_url", "")
            step_source = self._node_key(step_source) or (steps[-1].target_url if steps else source_url)
            step_target = self._node_key(step_target) or norm_target
            stateful_hint = bool(
                (not isinstance(step, Step) and step.get("stateful_hint", False))
                or self._text_suggests_state_change(f"{action} {thought or ''}")
            )
            planning = (
                (step.misc or {}).get("planning", {})
                if isinstance(step, Step)
                else step.get("planning", step.get("misc", {}).get("planning", {}))
            )
            steps.append(PrefixTraceStep(
                action=action,
                source_url=step_source,
                target_url=step_target,
                thought=thought or "",
                stateful_hint=stateful_hint,
                target_bid=str(
                    planning.get("target_bid")
                    or ("" if isinstance(step, Step) else step.get("target_bid", ""))
                ),
                target_role=str(
                    planning.get("target_role")
                    or ("" if isinstance(step, Step) else step.get("target_role", ""))
                ).lower(),
                target_name=str(
                    planning.get("target_name")
                    or ("" if isinstance(step, Step) else step.get("target_name", ""))
                ),
                target_fingerprint=str(
                    planning.get("target_fingerprint")
                    or ("" if isinstance(step, Step) else step.get("target_fingerprint", ""))
                ),
            ))

        if steps and not source_url:
            source_url = steps[0].source_url
        return PrefixTrace(
            source_url=source_url,
            target_url=norm_target,
            discovered_by_action=(discovered_by_action or "").strip(),
            steps=steps,
            created_at=float(created_at or time.time()),
            schema_version=int(info.get("schema_version", PREFIX_TRACE_SCHEMA_VERSION) or PREFIX_TRACE_SCHEMA_VERSION),
        )

    def _prefix_trace_metadata(self, target_url: str) -> dict:
        norm_target = self._node_key(target_url)
        key = norm_target if norm_target in self._discovered_urls else target_url
        if key not in self._discovered_urls:
            return {}
        trace = self._coerce_prefix_trace(norm_target, self._discovered_urls[key])
        return {
            "schema_version": trace.schema_version,
            "source_url": trace.source_url,
            "target_url": trace.target_url,
            "discovered_by_action": trace.discovered_by_action,
            "step_count": len(trace.steps),
            "stateful": self._prefix_contains_state_change(trace.steps),
            "last_replay_status": getattr(self, "_last_prefix_replay_status", {}),
        }

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
        if not url_after or not url_before:
            return

        norm_before = self._node_key(url_before)
        norm_after = self._node_key(url_after)

        # Only capture actual navigations (URL changes)
        if norm_after == norm_before:
            return

        self._count_url_metric("solver_navigation_events")
        seen = getattr(self, "_node_solver_urls", None)
        if seen is None:
            seen = set()
            self._node_solver_urls = seen
        if norm_after in seen:
            self._count_url_metric("solver_urls_duplicate")
            self._emit_event("solver", "url_rejected", data={
                "source_url": norm_before,
                "target_url": norm_after,
                "reason": "duplicate_in_node",
                "action_family": action_family(action),
            })
            return
        seen.add(norm_after)
        self._count_url_metric("solver_unique_urls_discovered")

        # Only capture same-origin URLs
        try:
            if urlparse(norm_before).netloc != urlparse(norm_after).netloc:
                self._count_url_metric("solver_urls_cross_origin")
                self._emit_event("solver", "url_rejected", data={
                    "source_url": norm_before,
                    "target_url": norm_after,
                    "reason": "cross_origin",
                    "action_family": action_family(action),
                })
                return
        except Exception:
            return

        active_visited = getattr(self, "_active_visited", set())
        if norm_after in active_visited:
            self._count_url_metric("solver_urls_already_visited")
            self._emit_event("solver", "url_rejected", data={
                "source_url": norm_before, "target_url": norm_after,
                "reason": "already_visited", "action_family": action_family(action),
            })
            return
        if norm_after in getattr(self, "_active_queued", set()):
            self._count_url_metric("solver_urls_already_queued")
            self._emit_event("solver", "url_rejected", data={
                "source_url": norm_before, "target_url": norm_after,
                "reason": "already_queued", "action_family": action_family(action),
            })
            return
        if norm_after in self._discovered_urls:
            self._count_url_metric("solver_urls_duplicate")
            self._emit_event("solver", "url_rejected", data={
                "source_url": norm_before, "target_url": norm_after,
                "reason": "already_discovered", "action_family": action_family(action),
            })
            return
        if any(pattern.search(norm_after) for pattern in getattr(self, "_denylist", [])):
            self._count_url_metric("solver_urls_denied")
            self._emit_event("solver", "url_rejected", data={
                "source_url": norm_before, "target_url": norm_after,
                "reason": "denylist", "action_family": action_family(action),
            })
            return
        allow = getattr(self, "allow", None)
        if allow is not None and not allow.search(norm_after):
            self._count_url_metric("solver_urls_outside_allowlist")
            self._emit_event("solver", "url_rejected", data={
                "source_url": norm_before, "target_url": norm_after,
                "reason": "outside_allowlist", "action_family": action_family(action),
            })
            return

        self._discovered_urls[norm_after] = self._prefix_trace_from_transition(
            action=action,
            url_before=norm_before,
            url_after=norm_after,
            traj_steps=traj_steps,
        )
        self._count_url_metric("solver_urls_frontier_eligible")
        self._emit_event("solver", "url_discovered", data={
            "source_url": norm_before,
            "target_url": norm_after,
            "disposition": "frontier_eligible",
            "action_family": action_family(action),
            "prefix_steps": len(traj_steps),
        })

    def _on_skill_admitted(self, card):
        """Called by SkillLibrary when a new skill is verified and admitted."""
        if self.terminal_goal and self.terminal_goal in card.planning_effects:
            card.terminal = True
        if card.planning_ready:
            self._register_skill_operator(card)
        self._emit_event("skill", "admitted", level="summary", data={
            "skill_id": card.skill_id,
            "name": card.name,
            "preconditions": sorted(card.planning_preconditions),
            "effects": sorted(card.planning_effects),
            "terminal": card.terminal,
            "verify_attempts": card.stats.n_verify_attempts,
            "verify_successes": card.stats.n_verify_success,
            "planning_ready": card.planning_ready,
            "planning_rejection_reason": card.planning_rejection_reason,
        })
        if card.planning_ready:
            self._emit_event("graph", "operator_added", data={
                "skill_id": card.skill_id,
                "operators": len(self.graph.operator_graph.ops),
                "composition_edges": sum(
                    len(targets) for targets in self.graph.skill_to_skill.values()
                ),
            })
        self.metrics.skills_verified += 1
        self.metrics.execution_skills_verified += 1
        if card.planning_ready:
            self.metrics.planner_ready_skills += 1
        elif not card.planning_effects:
            self.metrics.effectless_skills += 1
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
            "verified": card.verified,
            "n_verify_attempts": card.stats.n_verify_attempts,
            "n_verify_success": card.stats.n_verify_success,
            "sites_seen": sorted(card.stats.sites_seen),
            "bootstrap_verified": bool(getattr(card.stats, "bootstrap_verified", False)),
            "execution_plan": getattr(card, 'execution_plan', []),
            "alternative_templates": getattr(card, 'alternative_templates', []),
            "planning_preconditions": sorted(card.planning_preconditions),
            "planning_effects": sorted(card.planning_effects),
            "terminal": card.terminal,
            "planning_ready": card.planning_ready,
            "planning_rejection_reason": card.planning_rejection_reason,
            "predicate_schema_version": card.predicate_schema_version,
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
        if card.planning_ready:
            self._write_graph()
            self._write_curriculum()
        self._write_metrics_snapshot()

    def _on_skill_diagnostic(self, event: dict) -> None:
        """Persist discovery/abstraction/verification diagnostics."""
        event = dict(event)
        event["episode"] = self.episode
        self._skill_diagnostics.append(event)
        self._emit_event("skill", event.get("event", "diagnostic"), data=event)
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
        self.graph.rebuild_composition_edges()
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
                "planning_preconditions": sorted(card.planning_preconditions),
                "planning_effects": sorted(card.planning_effects),
                "terminal": card.terminal,
                "planning_ready": card.planning_ready,
                "planning_rejection_reason": card.planning_rejection_reason,
                "predicate_schema_version": card.predicate_schema_version,
            }
        graph_out = {
            "low_level": {
                "n_states": len(self.graph.states),
                "states": sorted(self.graph.states),
                "trajectory_edges": {u: sorted(vs) for u, vs in self.graph.trajectory_edges.items()},
            },
            "high_level": {
                "n_skills": len(self.graph.skills),
                "n_operators": len(self.graph.operator_graph.ops),
                "n_composition_edges": sum(
                    len(targets) for targets in self.graph.skill_to_skill.values()
                ),
                "skills": skills_serialized,
                "operators": {
                    skill_id: {
                        "skill_id": operator.skill_id,
                        "name": operator.name,
                        "preconditions": sorted(operator.preconditions),
                        "effects": sorted(operator.effects),
                        "terminal": operator.terminal,
                    }
                    for skill_id, operator in sorted(
                        self.graph.operator_graph.ops.items()
                    )
                },
                "state_to_skill": {s: sorted(sk) for s, sk in self.graph.state_to_skill.items()},
                "skill_to_state": {s: sorted(st) for s, st in self.graph.skill_to_state.items()},
                "skill_to_skill": {s: sorted(ss) for s, ss in self.graph.skill_to_skill.items()},
            },
        }
        path = os.path.join(self.out_dir, "graph.json")
        _atomic_json_dump(path, graph_out, indent=2)
        n_states = len(self.graph.states)
        n_skills = len(self.graph.skills)
        n_comp = sum(len(v) for v in self.graph.skill_to_skill.values())
        msg = (f"  [graph] {n_states} states, {n_skills} skills, "
               f"{n_comp} composition edges → {path}")
        print(msg)
        if getattr(self, "_log_file", None):
            self._log_file.write(msg + "\n")
            self._log_file.flush()

    # ---- curriculum generation from the hierarchical graph ------------------
    def _write_curriculum(self):
        """Generate a goal-conditioned curriculum with the operator planner.

        Called periodically during the run and at the end. Curriculum tasks
        are ordered easy→hard by skill-chain length and can be used for
        curriculum-ordered fine-tuning of the agent.
        """
        tasks = generate_curriculum(
            self.graph,
            site="webarena",
            initial_predicates=getattr(
                self, "_curriculum_initial_predicates", set()
            ),
        )
        self._curriculum_log = [
            {
                "instruction": t.instruction,
                "skill_chain": t.skill_chain,
                "skill_names": [self.graph.skills[s].name for s in t.skill_chain if s in self.graph.skills],
                "difficulty": t.difficulty,
                "site": t.site,
                "goal_predicate": t.goal_predicate,
                "terminal": t.terminal,
            }
            for t in tasks
        ]
        path = os.path.join(self.out_dir, "curriculum.json")
        _atomic_json_dump(path, self._curriculum_log, indent=2)
        all_effects = {
            effect
            for operator in self.graph.operator_graph.ops.values()
            for effect in operator.effects
        }
        if not self.graph.operator_graph.ops:
            status = "no_planner_ready_skills"
        elif not all_effects:
            status = "no_reachable_effects"
        elif not self.graph.operator_graph.goal_predicates:
            status = "no_terminal_goal" if tasks else "no_reachable_effects"
        else:
            status = "generated" if tasks else "no_reachable_effects"
        diagnostics = {
            "status": status,
            "planner_ready_skills": len(self.graph.operator_graph.ops),
            "reachable_goals": len(tasks),
            "terminal_tasks": sum(1 for task in tasks if task.terminal),
            "all_effects": sorted(all_effects),
        }
        _atomic_json_dump(
            os.path.join(self.out_dir, "curriculum_diagnostics.json"),
            diagnostics,
            indent=2,
        )
        if hasattr(self, "metrics"):
            self.metrics.reachable_goals = len(tasks)
            self.metrics.terminal_tasks = diagnostics["terminal_tasks"]
        self._emit_event("curriculum", "generated", level="summary", data={
            "tasks": len(tasks),
            "status": status,
            "terminal_tasks": sum(1 for task in tasks if task.terminal),
            "max_difficulty": max((task.difficulty for task in tasks), default=0),
            "initial_predicates": sorted(getattr(
                self, "_curriculum_initial_predicates", set()
            )),
        })
        n_skills = len(self.graph.skills)
        msg = (f"  [curriculum] {len(tasks)} tasks from {n_skills} skills "
               f"→ {path}")
        print(msg)
        if getattr(self, "_log_file", None):
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
                screenshots: list | None = None, final_obs: dict | None = None):
        ep = os.path.join(self.out_dir, "episodes", f"ep_{self.episode:04d}")
        os.makedirs(os.path.join(ep, "page_state"), exist_ok=True)
        final_obs = final_obs or {}
        final_ax_path = "page_state/final_axtree.txt"
        open(os.path.join(ep, final_ax_path), "w", encoding="utf-8").write(
            final_obs.get("axtree", "")
        )
        meta = {"kind": "low_level_trajectory", "goal": goal,
                "outcome": {"success": bool(success), "reward": 1.0 if success else 0.0, "response": ""},
                "metadata": {"difficulty": difficulty, "tags": [tag]}, "step_count": len(steps),
                "final_state": {
                    "url": final_obs.get("url", ""),
                    "axtree_txt": {"path": final_ax_path},
                    "predicates": sorted(predicates_from(
                        final_obs.get("url", ""), final_obs.get("axtree", ""),
                        getattr(self, "predicate_extractor", None),
                    )),
                    "predicate_schema_version": getattr(
                        getattr(self, "predicate_extractor", None),
                        "schema_version", "core-v2",
                    ),
                }}
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

    def _register_skill_operator(self, card) -> None:
        """Expose a verified SkillCard's planning view under the same identity."""
        self.graph.add_skill(card, init_states=[], effect_states=[])
        self.opgraph = self.graph.operator_graph

    def _goal_task(
        self,
        initial_predicates: set[str] | None = None,
        observation: dict | None = None,
    ):
        initial = frozenset(initial_predicates or set())
        goal = self.terminal_goal
        instruction = self.goal_instruction
        if not goal and self.auto_terminal_goals:
            goal, _ = self._auto_transaction_goal(initial)
        if not goal:
            self._active_plan_summary = {
                "goal": None, "status": "no_goal", "plan_length": 0,
            }
            return None
        self._emit_event("planner", "requested", data={
            "goal": goal,
            "initial_predicates": sorted(initial),
            "operators": len(self.graph.operator_graph.ops),
        })
        chain = plan(self.graph.operator_graph, initial, goal)
        if not chain:
            self._active_plan_summary = {
                "goal": goal, "status": "unreachable", "plan_length": 0,
            }
            self._emit_event("planner", "goal_unreachable", level="summary", data={
                "goal": goal,
                "initial_predicates": sorted(initial),
            })
            return None
        self._active_plan_summary = {
            "goal": goal, "status": "planned", "plan_length": len(chain),
            "chain": chain,
        }
        self._emit_event("planner", "plan_found", level="summary", data={
            "goal": goal,
            "plan_length": len(chain),
            "chain": chain,
        })
        instruction = instruction or self._compose_goal_instruction(chain, goal, observation or {})
        return {"goal": instruction,
                "difficulty": len(chain), "chain": chain, "terminal_goal": goal}

    def _compose_goal_instruction(
        self, chain: list[str], goal: str, observation: dict
    ) -> str:
        cards = [self._skill_by_id(sid) for sid in chain]
        cards = [card for card in cards if card is not None]
        fallback = " Then ".join(
            f"Complete '{card.name.replace('_', ' ')}'" for card in cards
        )
        fallback = (fallback + f". Reach the verified condition '{goal}'.").strip()
        payload = {
            "skill_ids": chain,
            "terminal_goal": goal,
            "current_url": observation.get("url", ""),
            "page": observation.get("axtree", "")[:3000],
            "skills": [
                {
                    "skill_id": card.skill_id,
                    "name": card.name,
                    "description": card.description,
                    "effects": sorted(card.planning_effects),
                }
                for card in cards
            ],
        }
        try:
            out = self.goal_composer_llm.complete_json(
                "Compose one concrete, domain-neutral long-horizon browser goal. "
                "Preserve the supplied skill order. Return JSON with exactly "
                "'instruction' and 'skill_ids'. Do not include action selectors.",
                json.dumps(payload),
            )
            instruction = out.get("instruction", "") if isinstance(out, dict) else ""
            returned_chain = out.get("skill_ids", []) if isinstance(out, dict) else []
            if isinstance(instruction, str) and instruction.strip() and returned_chain == chain:
                return instruction.strip()
        except Exception:
            pass
        return fallback

    def _skill_by_id(self, skill_id: str):
        for card in self.library.all_skills():
            if card.skill_id == skill_id:
                return card
        return None

    def _auto_transaction_goal(self, initial: frozenset[str]) -> tuple[str | None, str | None]:
        if not self._transactional_state_available(initial):
            return None, None
        candidates = [
            ("has_confirmation_cue", "Safely advance the transaction flow until a confirmation cue is visible, without placing a final order."),
            ("path:checkout", "Safely reach the checkout flow and report the next required step."),
            ("has_progress_control", "Advance the visible transaction flow one step and report the next required action."),
        ]
        for goal, instruction in candidates:
            chain = plan(self.graph.operator_graph, initial, goal)
            if chain:
                return goal, instruction
        return None, None

    def _transactional_state_available(self, initial: frozenset[str]) -> bool:
        joined = " ".join(initial)
        if re.search(r"path:(cart|checkout)|has_progress_control", joined):
            return True
        for op in self.graph.operator_graph.ops.values():
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

    def _write_metrics_snapshot(self) -> None:
        import dataclasses

        if not hasattr(self, "metrics"):
            return
        skills = self.library.all_skills() if hasattr(self, "library") else []
        self.metrics.execution_skills_verified = sum(card.verified for card in skills)
        self.metrics.planner_ready_skills = sum(card.planning_ready for card in skills)
        self.metrics.effectless_skills = sum(
            card.verified and not card.planning_effects for card in skills
        )
        self.metrics.operators_mined = self._observed_operator_count()
        logger = getattr(self, "event_logger", None)
        if logger is not None:
            self.metrics.event_counts = dict(sorted(logger.counts.items()))
        path = os.path.join(self.out_dir, "metrics_latest.json")
        _atomic_json_dump(path, dataclasses.asdict(self.metrics), indent=2)

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

        Version 4 persists semantic-query node identities plus graph, clustering,
        and scoring state.
        Verified cards live in skills.json; operators are derived on resume.
        """
        # Serialize hierarchical graph (skill-level only; states can be large)
        hierarchical_graph = {
            "state_to_skill": {s: sorted(sk) for s, sk in self.graph.state_to_skill.items()},
            "skill_to_state": {s: sorted(st) for s, st in self.graph.skill_to_state.items()},
        }

        # Serialize clusterer state (centroids)
        clusterer_state = self._serialize_clusterer()

        ckpt = {
            "version": 4,
            "frontier": [[u, d] for u, d in frontier],
            "visited": sorted(visited),
            "queued": sorted(queued),
            "nodes_processed": self._nodes_done,
            "episode": self.episode,
            "discovered_urls": {
                url: self._coerce_prefix_trace(url, info).to_dict()
                for url, info in self._discovered_urls.items()
            },
            "frontier_scorer": self._frontier_scorer.to_dict(),
            "url_attempts": dict(self._url_attempts),
            "url_successes": dict(self._url_successes),
            "frontier_selection_counts": dict(getattr(self, "_frontier_selection_counts", {})),
            "prefix_retry_counts": dict(getattr(self, "_prefix_retry_counts", {})),
            "load_retry_counts": dict(getattr(self, "_load_retry_counts", {})),
            "curriculum_initial_predicates": sorted(
                getattr(self, "_curriculum_initial_predicates", set())
            ),
            # NEW: full state for resume without replay
            "hierarchical_graph": hierarchical_graph,
            "clusterer": clusterer_state,
        }
        _atomic_json_dump(self._checkpoint_path, ckpt, indent=2)
        self._emit_event("checkpoint", "saved", data={
            "nodes_processed": ckpt["nodes_processed"],
            "frontier_size": len(frontier),
            "visited": len(visited),
            "queued": len(queued),
        })
        self._write_graph()
        self._write_curriculum()
        self._write_metrics_snapshot()

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
        version = ckpt.get("version", 1)
        if version < 4:
            raise ValueError(
                f"checkpoint version {version} is incompatible with the unified "
                "visited-node schema (requires version 4); start a new run directory"
            )
        print(f"[resume] Loaded checkpoint: {ckpt['nodes_processed']} nodes done, "
              f"{len(ckpt['frontier'])} URLs in frontier, "
              f"{ckpt['episode']} episodes recorded")
        return ckpt

    def _resume_from_checkpoint(self, ckpt: dict) -> None:
        """Restore in-memory state from a checkpoint dict.

        Version 4 restores semantic-query node identities and verified skills.
        """
        version = ckpt.get("version", 1)
        if version < 4:
            raise ValueError(
                f"checkpoint version {version} is incompatible with the unified "
                "visited-node schema (requires version 4); start a new run directory"
            )
        self._skills_log = getattr(self, "_skills_log", [])
        self._curriculum_log = getattr(self, "_curriculum_log", [])
        self._transfer_log = getattr(self, "_transfer_log", [])
        self.episode = ckpt.get("episode", 0)
        # Restore callback-discovered URLs with prefix traces
        self._discovered_urls = {}
        for url, info in ckpt.get("discovered_urls", {}).items():
            norm_url = self._node_key(url)
            self._discovered_urls[norm_url] = self._coerce_prefix_trace(norm_url, info)
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
        self._frontier_selection_counts = ckpt.get("frontier_selection_counts", {})
        self._prefix_retry_counts = ckpt.get("prefix_retry_counts", {})
        self._load_retry_counts = ckpt.get("load_retry_counts", {})
        self._curriculum_initial_predicates = set(
            ckpt.get("curriculum_initial_predicates", [])
        )

        self._restore_skills(self._skills_log)
        self._restore_hierarchical_graph(ckpt.get("hierarchical_graph", {}))
        self._deserialize_clusterer(ckpt.get("clusterer", {}))
        self._full_state_restored = True

    def _restore_skills(self, records: list[dict]) -> None:
        """Restore verified cards, then derive OperatorGraph from those cards."""
        for index, item in enumerate(records):
            if not item.get("verified", True):
                continue
            stats = SkillStats(
                n_members=int(item.get("n_members", 0) or 0),
                n_verify_attempts=int(item.get("n_verify_attempts", 0) or 0),
                n_verify_success=int(item.get("n_verify_success", 0) or 0),
                sites_seen=set(item.get("sites_seen", [])),
                bootstrap_verified=bool(item.get("bootstrap_verified", False)),
            )
            card = SkillCard(
                name=item.get("name", "activate_named_control"),
                description=item.get("description", ""),
                slots=[ParamSlot(**slot) for slot in item.get("slots", [])],
                action_template=item.get("action_template", []),
                precondition=item.get("precondition", ""),
                success_predicate=item.get("success_predicate", ""),
                cluster_id=str(item.get("cluster_id", index)),
                stats=stats,
                verified=True,
                skill_id=item["skill_id"],
                planning_preconditions=set(item.get("planning_preconditions", [])),
                planning_effects=set(item.get("planning_effects", [])),
                terminal=bool(item.get("terminal", False)),
                planning_ready=bool(
                    item.get("planning_ready", bool(item.get("planning_effects", [])))
                ),
                planning_rejection_reason=item.get(
                    "planning_rejection_reason",
                    "" if item.get("planning_effects") else "empty_planning_effects",
                ),
                predicate_schema_version=item.get("predicate_schema_version", "legacy-v1"),
                execution_plan=item.get("execution_plan", []),
                alternative_templates=item.get("alternative_templates", []),
            )
            if self.terminal_goal and self.terminal_goal in card.planning_effects:
                card.terminal = True
            try:
                cid = int(card.cluster_id)
            except ValueError:
                cid = index
            self.library.skills[cid] = card
            self.library._abstracted.add(cid)
            if card.planning_ready:
                self._register_skill_operator(card)

    def _restore_hierarchical_graph(self, hg_data: dict) -> None:
        """Restore hierarchical graph edges from serialized state.

        Skill cards are restored from skills.json; edge structures are restored
        directly and operators are derived from those verified cards.
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
        # Legacy checkpoints may contain URL/co-occurrence-derived composition
        # edges.  Ignore them and rebuild exclusively from restored operators.
        self.graph.rebuild_composition_edges()

    @staticmethod
    def _semantic_element(role: str, line: str) -> tuple[str, str]:
        match = re.match(r"^\s*\[\d+\]\s+([A-Za-z]+)\s+(.*)$", line or "")
        if not match:
            return role.lower(), ""
        name = re.sub(r"\s+", " ", match.group(2)).strip().lower()
        return match.group(1).lower(), name

    @staticmethod
    def _replace_action_bid(action: str, old_bid: str, new_bid: str) -> str:
        """Replace only the first positional BID while preserving other args."""
        pattern = re.compile(
            rf"(\(\s*['\"]?){re.escape(str(old_bid))}(['\"]?)(?=\s*[,\)])"
        )
        return pattern.sub(
            lambda match: f"{match.group(1)}{new_bid}{match.group(2)}",
            action,
            count=1,
        )

    def _reground_prefix_action(
        self, step: PrefixTraceStep, axtree: str
    ) -> tuple[str | None, str, str]:
        """Return (action, outcome, reason) using exact or semantic grounding."""
        action = (step.action or "").strip()
        try:
            parsed = parse_hsge_action(action)
        except ValueError as exc:
            return None, "invalid_action", str(exc)
        if not parsed.bid:
            return action, "no_target", ""

        elements = axtree_elements(axtree)
        old_bid = str(step.target_bid or parsed.bid)
        expected_role = (step.target_role or "").lower()
        expected_name = re.sub(r"\s+", " ", step.target_name or "").strip().lower()

        if old_bid in elements:
            role, name = self._semantic_element(*elements[old_bid])
            if not expected_role or (role == expected_role and name == expected_name):
                return self._replace_action_bid(action, parsed.bid, old_bid), "exact_bid", ""

        if not expected_role or not expected_name:
            # Version-1 traces did not store semantic metadata. Preserve their
            # legacy validation path; only version-2 traces may re-ground.
            return action, "legacy_target", "semantic fingerprint unavailable"

        matches = []
        for bid, element in elements.items():
            role, name = self._semantic_element(*element)
            if role == expected_role and name == expected_name:
                matches.append(bid)
        if len(matches) == 1:
            return (
                self._replace_action_bid(action, parsed.bid, matches[0]),
                "semantic_reground",
                f"{old_bid}->{matches[0]}",
            )
        if len(matches) > 1:
            return None, "ambiguous_target", f"{len(matches)} role/name matches"
        return None, "target_not_found", f"no {expected_role}/{expected_name!r} match"

    def _navigate_via_prefix(self, browser, target_url: str) -> dict | None:
        """Navigate to target_url by replaying prefix steps from source page.

        Instead of doing browser.goto(target_url) directly (which can break
        state), this replays the actual click/fill actions that were recorded
        when the URL was first discovered. This preserves login and session state.

        Returns the observation dict at the target URL, or None if navigation
        fails (fall back to direct goto).
        """
        norm_target = self._node_key(target_url)
        info = self._discovered_urls.get(norm_target) or self._discovered_urls.get(target_url)
        self._last_prefix_replay_status = {
            "attempted": False,
            "ok": False,
            "reason": "no_prefix",
            "arrived_url": "",
            "expected_url": norm_target,
            "stateful": False,
            "used_direct_goto": False,
            "outcomes": [],
        }
        if not info:
            return None

        trace = self._coerce_prefix_trace(norm_target, info)
        prefix_steps = trace.steps
        source_url = trace.source_url
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
            goto_obs = browser.act(f"goto('{source_url}')")
            if goto_obs.get("_action_error"):
                raise RuntimeError(goto_obs["_action_error"])
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
            action = step.action if isinstance(step, (Step, PrefixTraceStep)) else step.get("action", "")
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
            if isinstance(step, PrefixTraceStep):
                grounded_action, outcome, detail = self._reground_prefix_action(
                    step, current_obs.get("axtree", "")
                )
                self._last_prefix_replay_status["outcomes"].append(outcome)
                if grounded_action is None:
                    self._last_prefix_replay_status["reason"] = f"{outcome}:{detail}"
                    msg = f"      [prefix] step {i} {outcome}: {detail}"
                    print(msg)
                    if self._log_file:
                        self._log_file.write(msg + "\n")
                        self._log_file.flush()
                    self._emit_event("prefix", outcome, level="warning", data={
                        "step": i, "target_url": norm_target, "detail": detail,
                    })
                    return None
                action = grounded_action
                if outcome in {"exact_bid", "semantic_reground"}:
                    self._emit_event("prefix", outcome, data={
                        "step": i, "target_url": norm_target, "detail": detail,
                    })
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
                replay_obs = browser.act(action)
                if replay_obs.get("_action_error"):
                    raise RuntimeError(replay_obs["_action_error"])
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
        arrived = self._node_key(obs.get("url", ""))
        self._last_prefix_replay_status["arrived_url"] = arrived

        if arrived == norm_target:
            self._last_prefix_replay_status.update({"ok": True, "reason": "arrived"})
            msg = f"      [prefix] ✅ Arrived at {norm_target[:60]}"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            return obs
        else:
            self._last_prefix_replay_status["reason"] = "url_mismatch"
            msg = f"      [prefix] ⚠️  Expected {norm_target[:60]}, got {arrived[:60]}"
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
            action = step.action if isinstance(step, (Step, PrefixTraceStep)) else step.get("action", "")
            if isinstance(step, PrefixTraceStep):
                summary = step.thought
                if step.stateful_hint:
                    return True
            elif isinstance(step, Step):
                summary = step.obs_summary
            else:
                summary = step.get("thought", "") or step.get("obs_summary", "")
                if step.get("stateful_hint", False):
                    return True
            if cls._text_suggests_state_change(f"{action} {summary}"):
                return True
        return False

    def _reset_browser_to_node(self, browser, url: str, actual_url: str) -> dict:
        """Return browser to the node state before each local task.

        Correctness first: if the node was reached through a prefix trace, replay
        that trace again instead of relying on BrowserGym reset, which may go
        back to the original start URL and lose query/stateful navigation.

        When prefix replay fails (stale actions, URL mismatch, etc.), fall back
        to browser.reset() + goto(actual_url) so that local tasks are not all
        silently skipped.
        """
        if getattr(self, "_node_reset_unavailable", False):
            self._node_reset_short_circuits = (
                getattr(self, "_node_reset_short_circuits", 0) + 1
            )
            return {"url": "", "axtree": "", "_reset_error": "node reset unavailable"}
        norm_url = self._node_key(url)
        if norm_url in self._discovered_urls or url in self._discovered_urls:
            obs = self._navigate_via_prefix(browser, norm_url)
            if obs and obs.get("url"):
                return obs
            status = getattr(self, "_last_prefix_replay_status", {}) or {}
            if status.get("stateful"):
                self._node_reset_unavailable = True
                self._emit_event("prefix", "stateful_requeue", level="warning", data={
                    "url": norm_url,
                    "reason": status.get("reason", "replay_failed"),
                    "scope": "remaining_node_tasks",
                })
                return {"url": "", "axtree": "", "_reset_error": "stateful prefix failed"}
            # Prefix replay failed — fall back to direct reset + goto
            msg = (f"      [prefix] reset fallback: direct goto to {actual_url[:80]}")
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            self._emit_event("prefix", "direct_goto", data={
                "url": actual_url, "reason": "stateless_prefix_replay_failed",
            })

        obs = browser.reset()
        if obs.get("url") and self._node_key(obs.get("url", "")) != actual_url:
            try:
                obs = browser.act(f"goto('{actual_url}')")
                if obs.get("_action_error"):
                    return {"url": "", "axtree": "", "_action_error": obs["_action_error"]}
            except Exception:
                return {"url": "", "axtree": ""}
        return obs

    def _recover_unprocessed_prefix_url(
        self,
        url: str,
        depth: int,
        frontier: list[tuple[str, int]],
        queued: set[str],
    ) -> bool:
        """Recover selected URLs that failed because their prefix became stale.

        Returns True when the URL was requeued for another bounded attempt.
        Once the limit is reached, release it from queued/discovered state so a
        future successful action can rediscover it with a fresh prefix trace.
        """
        status = getattr(self, "_last_prefix_replay_status", {}) or {}
        reason = status.get("reason", "")
        if not status.get("attempted") or not status.get("stateful"):
            return False
        if not reason.startswith((
            "stale_action", "stale_bid", "target_not_found", "ambiguous_target",
            "url_mismatch", "goto_source_failed", "step_failed",
        )):
            return False

        norm_url = self._node_key(url)
        retry_counts = getattr(self, "_prefix_retry_counts", {})
        self._prefix_retry_counts = retry_counts
        attempts = retry_counts.get(norm_url, 0)
        limit = getattr(self, "_prefix_retry_limit", 2)

        if attempts < limit:
            retry_counts[norm_url] = attempts + 1
            if norm_url not in {u for u, _ in frontier}:
                frontier.append((norm_url, depth))
            queued.add(norm_url)
            msg = (
                f"      [prefix] requeued stale prefix {norm_url[:60]} "
                f"(retry {retry_counts[norm_url]}/{limit}, reason={reason})"
            )
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            self._emit_event("prefix", "stateful_requeue", level="warning", data={
                "url": norm_url,
                "retry": retry_counts[norm_url],
                "retry_limit": limit,
                "reason": reason,
            })
            return True

        queued.discard(norm_url)
        queued.discard(url)
        self._discovered_urls.pop(norm_url, None)
        self._discovered_urls.pop(url, None)
        retry_counts.pop(norm_url, None)
        msg = f"      [prefix] released stale prefix {norm_url[:60]} (reason={reason})"
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()
        return False

    def _recover_empty_observation_url(
        self,
        url: str,
        depth: int,
        frontier: list[tuple[str, int]],
        queued: set[str],
    ) -> bool:
        """Retry transient node failures, or release terminal redirect aliases."""
        status = getattr(self, "_last_node_load_status", {}) or {}
        reason = status.get("reason")
        norm_url = self._node_key(url)
        if reason == "redirect_visited":
            queued.discard(norm_url)
            queued.discard(url)
            getattr(self, "_discovered_urls", {}).pop(norm_url, None)
            return False
        if reason not in {"empty_observation", "load_error", "process_error"}:
            return False
        if reason == "empty_observation" and status.get("prefix_attempted"):
            return False

        retry_counts = getattr(self, "_load_retry_counts", {})
        self._load_retry_counts = retry_counts
        attempts = retry_counts.get(norm_url, 0)
        limit = getattr(self, "_load_retry_limit", 2)
        detail = status.get("detail") or "no reset diagnostic"

        if attempts < limit:
            retry_counts[norm_url] = attempts + 1
            if norm_url not in {u for u, _ in frontier}:
                frontier.append((norm_url, depth))
            queued.add(norm_url)
            msg = (
                f"      [load] requeued node {norm_url[:60]} "
                f"(retry {retry_counts[norm_url]}/{limit}, type={reason}, reason={detail})"
            )
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            return True

        queued.discard(norm_url)
        queued.discard(url)
        retry_counts.pop(norm_url, None)
        self.metrics.nodes_error += 1
        getattr(self, "_discovered_urls", {}).pop(norm_url, None)
        msg = f"      [load] released node {norm_url[:60]} (type={reason}, reason={detail})"
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()
        return False

    def _process_node(self, url, depth, root_url, frontier, visited, queued, node_num):
        """Process one node with full error isolation.

        Each node: reset env → create browser → navigate (via prefix or direct) →
        explore local tasks → attempt goal task → expand frontier.

        Navigation prefers prefix trace replay over direct browser.goto()
        to preserve session state (Go-Browse style).
        """
        # KHÔNG gọi _reset_env() ở đây — nó xóa session trên server,
        # làm cho storage_state cookie (PHPSESSID) trở nên vô dụng.
        # Mỗi node đã dùng browser context mới (state sạch), và
        # storage_state cung cấp session login sẵn.

        self._active_node_id = node_num
        self._active_task_id = None
        self._active_episode_id = None
        self._node_url_stats = Counter()
        self._node_solver_urls = set()
        self._active_node_started_at = time.time()
        # The selected node has already been removed by run(); include it so the
        # summary represents the queue size at selection time.
        self._active_frontier_size_before = len(frontier) + 1
        self._active_plan_summary = None
        self._node_reset_unavailable = False
        self._node_reset_short_circuits = 0
        self._node_observability_baseline = {
            "segments": getattr(self.metrics, "segments_created", 0),
            "skills": len(self.library.all_skills()),
            "operators": self._observed_operator_count(),
        }
        self._emit_event("node", "started", level="summary", data={
            "requested_url": url,
            "depth": depth,
            "frontier_size": len(frontier),
        })

        # Create browser with timeout protection
        browser = None
        self._last_node_load_status = {}
        try:
            # Try prefix-based navigation first (replay natural clicks)
            browser = self.browser_factory(url)
            self._active_browser = browser
            obs = browser.reset()

            # If we have a prefix trace for this URL, use it instead of direct goto
            norm_url = self._node_key(url)
            if obs.get("url") and (norm_url in self._discovered_urls or url in self._discovered_urls):
                prefix_obs = self._navigate_via_prefix(browser, norm_url)
                if prefix_obs is not None:
                    obs = prefix_obs
                else:
                    status = getattr(self, "_last_prefix_replay_status", {})
                    stateful = status.get("stateful", False)
                    if stateful:
                        msg = (
                            f"      [prefix] stale stateful prefix for {url[:60]} "
                            f"(reason={status.get('reason')}); "
                            "skipping this node and scheduling a bounded retry"
                        )
                    else:
                        msg = f"      [prefix] Fallback to direct goto for {url[:60]}"
                    print(msg)
                    if self._log_file:
                        self._log_file.write(msg + "\n")
                        self._log_file.flush()
                    if stateful:
                        self._emit_event("node", "prefix_unavailable", level="warning", data={
                            "url": url,
                            "reason": "stale_stateful_prefix",
                            "detail": status,
                        })
                        self._last_node_load_status = {
                            "reason": "stateful_prefix_unavailable",
                            "detail": status,
                            "prefix_attempted": True,
                        }
                        self._recover_unprocessed_prefix_url(
                            url, depth, frontier, queued
                        )
                        try:
                            browser.close()
                        except Exception:
                            pass
                        return None
                    status["used_direct_goto"] = True
                    self._emit_event("prefix", "direct_goto", data={
                        "url": url,
                        "reason": "stateless_prefix_replay_failed",
                        "detail": status,
                    })
                    try:
                        browser.close()
                    except Exception:
                        pass
                    browser = self.browser_factory(url)
                    self._active_browser = browser
                    obs = browser.reset()
                    # Clear stale prefix so _reset_browser_to_node skips
                    # prefix replay for subsequent tasks on this node.
                    self._discovered_urls.pop(norm_url, None)
                    self._discovered_urls.pop(url, None)
        except Exception as e:
            self._last_node_load_status = {
                "reason": "load_error",
                "detail": str(e),
                "prefix_attempted": False,
            }
            msg = f"[node {node_num} depth={depth}] SKIP {url}  (load error: {e})"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            self._emit_event("node", "failed", level="error", data={
                "url": url, "reason": "load_error", "error": str(e),
            })
            return None

        if not obs.get("url"):
            detail = obs.get("_reset_error") or obs.get("_start_url") or "no url after reset"
            self._last_node_load_status = {
                "reason": "empty_observation",
                "detail": detail,
                "prefix_attempted": bool(norm_url in self._discovered_urls or url in self._discovered_urls),
            }
            msg = (
                f"[node {node_num} depth={depth}] SKIP {url}  "
                f"(empty observation after reset: {detail})"
            )
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            try:
                browser.close()
            except Exception:
                pass
            self._emit_event("node", "skipped", level="warning", data={
                "url": url, "reason": "empty_observation", "detail": detail,
            })
            return None

        actual_url = self._node_key(obs['url'])
        self._emit_event("node", "loaded", data={
            "requested_url": url,
            "actual_url": actual_url,
            "depth": depth,
            "observation_chars": len(obs.get("axtree", "")),
        })

        if depth == 0 and not getattr(
            self, "_curriculum_initial_predicates", set()
        ):
            self._curriculum_initial_predicates = predicates_from(
                actual_url, obs.get("axtree", "")
            )

        # Lưu axtree vào cache (nếu chưa có từ lần fetch trước)
        if actual_url not in self._axtree_cache:
            self._axtree_cache[actual_url] = obs.get("axtree", "")

        # Skip if redirected to an already-visited page (e.g. wishlist → login)
        if actual_url in visited and actual_url != url:
            self._last_node_load_status = {
                "reason": "redirect_visited",
                "detail": f"redirected to {actual_url}",
                "actual_url": actual_url,
                "prefix_attempted": False,
            }
            msg = f"[node {node_num} depth={depth}] SKIP {url} → redirect to already-visited {actual_url}"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            try:
                browser.close()
            except Exception:
                pass
            self._emit_event("node", "skipped", level="warning", data={
                "url": url,
                "actual_url": actual_url,
                "reason": "redirect_already_visited",
            })
            return None

        msg = f"[node {node_num} depth={depth}] {actual_url}"
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()

        # Track episode range cho node này
        _ep_start = self.episode

        # Root node: capture initial predicates for curriculum
        if depth == 0:
            self._curriculum_initial_predicates = predicates_from(
                actual_url,
                obs.get("axtree", ""),
                getattr(self, "predicate_extractor", None),
            )

        # Track whether any task succeeded on this node (for UVD scorer)
        _any_success = False

        # 1) local exploration. Learned skills never enter the explorer prompt.
        _node_task_records = []  # track task outcomes for this node
        raw_proposed_tasks = self.explorer.propose(obs)
        proposed_tasks = self._rank_tasks_for_coverage(raw_proposed_tasks)
        skipped_repeats = len(raw_proposed_tasks) - len(proposed_tasks)
        self._emit_event("explorer", "tasks_proposed", data={
            "proposed": len(raw_proposed_tasks),
            "accepted": len(proposed_tasks),
            "filtered": skipped_repeats,
            "task_families": dict(Counter(task_family(task) for task in proposed_tasks)),
        })
        if skipped_repeats:
            msg_repeat = f"  [tasks] Skipped {skipped_repeats} repeated/saturated proposal(s)"
            print(msg_repeat)
            if self._log_file:
                self._log_file.write(msg_repeat + "\n")
                self._log_file.flush()
        for task_index, task in enumerate(proposed_tasks, start=1):
            self._active_task_id = f"n{node_num}-local-{task_index}"
            self._active_episode_id = self.episode
            self.metrics.tasks_proposed += 1
            is_checkout_task = self._is_checkout_task(task)
            if is_checkout_task:
                self.metrics.checkout_tasks_attempted += 1
            task_record = {
                "task_id": self._active_task_id,
                "goal": task,
                "family": task_family(task),
                "status": "attempted",
                "episode_id": None,
            }
            _node_task_records.append(task_record)
            task_key = self._task_key(task)
            self._task_attempt_counts[task_key] += 1
            task_retry_limit = getattr(self, "_task_retry_limit", 3)
            task_success = False
            task_steps = []
            task_obs_texts = []
            task_final_obs = {}
            task_screenshots = []
            for task_attempt in range(1, task_retry_limit + 1):
                try:
                    reset_obs = self._reset_browser_to_node(browser, url, actual_url)
                    if not reset_obs.get("url"):
                        task_record["status"] = "skipped"
                        if task_attempt > 1:
                            msg_skip = f"    local: {task!r} SKIP (reset failed, attempt {task_attempt})"
                        else:
                            msg_skip = f"    local: {task!r} SKIP (reset failed)"
                        print(msg_skip)
                        if self._log_file:
                            self._log_file.write(msg_skip + "\n")
                            self._log_file.flush()
                        break
                    context_hints = ""
                    safe_hint = self._checkout_safety_hint(task)
                    if safe_hint:
                        context_hints = safe_hint
                    # Append account credentials to solver prompt
                    if self._account_info:
                        context_hints = self._account_info + "\n\n" + context_hints if context_hints else self._account_info
                    steps, obs_texts, final_obs, success, screenshots = self.solver.solve(
                        browser, task, context_hints=context_hints,
                        step_callback=self._on_step_completed,
                        predicate_extractor=getattr(self, "predicate_extractor", None))
                    task_steps = steps
                    task_obs_texts = obs_texts
                    task_final_obs = final_obs
                    task_screenshots = screenshots
                    task_success = success
                    if success:
                        break
                    if task_attempt < task_retry_limit:
                        msg_retry = f"    local: {task!r} attempt {task_attempt}/{task_retry_limit} failed, retrying..."
                        print(msg_retry)
                        if self._log_file:
                            self._log_file.write(msg_retry + "\n")
                            self._log_file.flush()
                except Exception as e:
                    if task_attempt < task_retry_limit:
                        msg_retry = f"    local: {task!r} attempt {task_attempt}/{task_retry_limit} error ({e}), retrying..."
                        print(msg_retry)
                        if self._log_file:
                            self._log_file.write(msg_retry + "\n")
                            self._log_file.flush()
                    else:
                        task_record["status"] = "error"
                        self.metrics.errors += 1
                        msg_err = f"    local: {task!r} ERROR (final): {e}"
                        print(msg_err)
                        if self._log_file:
                            self._log_file.write(msg_err + "\n")
                            self._log_file.flush()
            # --- post-retry recording ---
            if task_record["status"] not in ("skipped", "error"):
                ep_id = self.episode
                self._record(task, task_steps, task_obs_texts, task_success, difficulty=1, tag="LOCAL",
                             screenshots=task_screenshots, final_obs=task_final_obs)
                self._emit_event("solver", "completed", level="summary", data={
                    "kind": "local",
                    "goal": task,
                    "success": bool(task_success),
                    "steps": len(task_steps),
                    "action_error": task_final_obs.get("_action_error"),
                    "action_timed_out": task_final_obs.get("_action_timed_out", False),
                }, episode_id=ep_id)
                task_record["episode_id"] = ep_id
                if task_success:
                    task_record["status"] = "solved"
                    if is_checkout_task:
                        self.metrics.checkout_tasks_solved += 1
                    self._task_success_counts[task_key] += 1
                    _any_success = True
                    self.metrics.tasks_solved += 1
                    self._emit_event("discovery", "trajectory_received", data={
                        "goal": task,
                        "steps": len(task_steps),
                        "source": "local_success",
                    }, episode_id=ep_id)
                    self.discovery.on_trajectory(
                        task_steps, site=root_url, task=task,
                        obs_texts=task_obs_texts, final_obs=task_final_obs,
                    )
                else:
                    task_record["status"] = "failed"
                    self.metrics.tasks_failed += 1
                    self._task_failure_counts[task_key] += 1
                    self._task_family_failure_counts[task_family(task)] += 1
                msg2 = f"    local: {task!r} success={task_success}"
                print(msg2)
                if self._log_file:
                    self._log_file.write(msg2 + "\n")
                    self._log_file.flush()

        # 2) goal-conditioned composed task (once a plan to the goal exists)
        gt = self._goal_task(
            predicates_from(
                actual_url,
                obs.get("axtree", ""),
                getattr(self, "predicate_extractor", None),
            ),
            observation=obs,
        )
        if gt:
            for attempt in range(1, self.max_goal_attempts + 1):
                self._active_task_id = f"n{node_num}-goal-{attempt}"
                self._active_episode_id = self.episode
                self.metrics.goal_tasks_attempted += 1
                self.metrics.composed_goal_tasks_attempted += 1
                goal_record = {
                    "task_id": self._active_task_id,
                    "goal": gt["goal"],
                    "family": task_family(gt["goal"]),
                    "status": "attempted",
                    "attempt": attempt,
                    "episode_id": None,
                }
                _node_task_records.append(goal_record)
                episode_before_attempt = self.episode
                try:
                    reset_obs = self._reset_browser_to_node(browser, url, actual_url)
                    if not reset_obs.get("url"):
                        goal_record["status"] = "skipped"
                        self._record(
                            gt["goal"], [], [], False,
                            difficulty=gt["difficulty"], tag="GOAL",
                        )
                        goal_record["episode_id"] = episode_before_attempt
                        msg_skip = f"    GOAL attempt={attempt} SKIP (reset failed)"
                        print(msg_skip)
                        if self._log_file:
                            self._log_file.write(msg_skip + "\n")
                            self._log_file.flush()
                        continue
                    context_hints = self._checkout_safety_hint(gt["goal"])
                    if self._account_info:
                        context_hints = self._account_info + "\n\n" + context_hints if context_hints else self._account_info
                    steps, obs_texts, final_obs, success, screenshots = self.solver.solve(
                        browser, gt["goal"], goal_predicate=gt["terminal_goal"],
                        context_hints=context_hints,
                        step_callback=self._on_step_completed,
                        predicate_extractor=getattr(self, "predicate_extractor", None))
                    ep_id = self.episode
                    self._record(
                        gt["goal"], steps, obs_texts, success,
                        difficulty=gt["difficulty"], tag="GOAL",
                        screenshots=screenshots,
                        final_obs=final_obs,
                    )
                    self._emit_event("solver", "completed", level="summary", data={
                        "kind": "goal",
                        "goal": gt["goal"],
                        "goal_predicate": gt["terminal_goal"],
                        "success": bool(success),
                        "steps": len(steps),
                        "plan_length": gt["difficulty"],
                        "action_error": final_obs.get("_action_error"),
                        "action_timed_out": final_obs.get("_action_timed_out", False),
                    }, episode_id=ep_id)
                    goal_record["episode_id"] = ep_id
                    if success:
                        goal_record["status"] = "solved"
                        _any_success = True
                        self.metrics.goal_tasks_solved += 1
                    else:
                        goal_record["status"] = "failed"
                        self.metrics.tasks_failed += 1
                    msg3 = (
                        f"    GOAL attempt={attempt}/{self.max_goal_attempts} "
                        f"chain={gt['chain']} verified={success}"
                    )
                    print(msg3)
                    if self._log_file:
                        self._log_file.write(msg3 + "\n")
                        self._log_file.flush()
                    if success:
                        break
                except Exception as e:
                    goal_record["status"] = "error"
                    if self.episode == episode_before_attempt:
                        self._record(
                            gt["goal"], [], [], False,
                            difficulty=gt["difficulty"], tag="GOAL",
                        )
                        goal_record["episode_id"] = episode_before_attempt
                    self.metrics.errors += 1
                    self.metrics.tasks_error += 1
                    msg_err = f"    GOAL attempt={attempt} ERROR: {e}"
                    print(msg_err)
                    if self._log_file:
                        self._log_file.write(msg_err + "\n")
                        self._log_file.flush()

        self._active_task_id = None
        self._active_episode_id = None

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

        # 3) expand frontier. Prefer callback-discovered URLs from actual solver
        # navigation; fall back to same-origin DOM links when solver tasks did
        # not reveal new pages, so exploration does not exhaust on a navigable page.
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
            source = "callback discovery"
            if not new_urls and depth < self.max_depth:
                fallback_items = []
                seen_links = set()
                for raw_link in browser.links():
                    link = self._node_key(raw_link)
                    if not link or link in seen_links:
                        continue
                    seen_links.add(link)
                    self._count_url_metric("dom_urls_considered")
                    if (link not in queued
                        and link not in visited
                        and link not in {url, actual_url}
                        and self.allow.search(link)
                        and not any(d.search(link) for d in self._denylist)):
                        fallback_items.append({"url": link, "depth": depth + 1})

                if fallback_items:
                    remaining_slots = max(0, getattr(self, "_frontier_max_size", 80) - len(frontier))
                    if remaining_slots > 0:
                        filtered = filter_frontier(
                            fallback_items,
                            max_output=min(remaining_slots, len(fallback_items)),
                        )
                        new_urls = [item["url"] for item in filtered]
                        source = "DOM links"

            if new_urls:
                remaining_slots = max(0, getattr(self, "_frontier_max_size", 80) - len(frontier))
                if len(new_urls) > remaining_slots:
                    dropped = new_urls[remaining_slots:]
                    if source == "callback discovery":
                        dropped_from_node = sum(
                            1 for candidate in dropped
                            if candidate in self._node_solver_urls
                        )
                        self._count_url_metric(
                            "solver_urls_dropped_capacity", dropped_from_node
                        )
                    new_urls = new_urls[:remaining_slots]

            for link in new_urls:
                _node_children.append(link)
                queued.add(link)
                frontier.append((link, depth + 1))
                if source == "callback discovery" and link in self._node_solver_urls:
                    self._count_url_metric("solver_urls_added_to_frontier")
                elif source == "DOM links":
                    self._count_url_metric("dom_urls_added_to_frontier")
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
                msg = f"  [frontier] +{len(new_urls)} URLs from {source}"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
            self._emit_event("frontier", "expanded", level="summary", data={
                "source": source,
                "added": len(new_urls),
                "frontier_size": len(frontier),
                "url_funnel": dict(self._node_url_stats),
            })
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
            self._active_browser = None

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
        self._write_node_summary(
            node_num=node_num,
            url=actual_url,
            depth=depth,
            frontier_size=len(frontier),
            tasks=_node_task_records,
        )
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
            prefix_trace=self._prefix_trace_metadata(url),
            url_discovery=dict(self._node_url_stats),
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
            n_ops = len(self.graph.operator_graph.ops)
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
            tags = meta.get("metadata", {}).get("tags", [])
            if not meta.get("outcome", {}).get("success") or "LOCAL" not in tags:
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
            final_obs = {"url": steps[-1].url if steps else "",
                         "axtree": obs_texts[-1] if obs_texts else ""}
            self.discovery.on_trajectory(
                steps, site="webarena", task=goal,
                obs_texts=obs_texts, final_obs=final_obs,
            )
            rebuilt += 1
        print(f"[resume] Rebuilt library from {rebuilt}/{len(episodes)} successful episodes "
              f"→ {len(self.library.all_skills())} skills, "
              f"{len(self.graph.operator_graph.ops)} operators")

    # ---- per-node info persistence (Go-Browse style) -------------------------
    def _write_node_summary(
        self,
        *,
        node_num: int,
        url: str,
        depth: int,
        frontier_size: int,
        tasks: list[dict],
    ) -> None:
        baseline = getattr(self, "_node_observability_baseline", {})
        task_records = self._normalize_node_task_records(tasks)
        attempted = sum(1 for task in task_records if task["status"] != "skipped")
        solved = sum(1 for task in task_records if task["status"] == "solved")
        failed = sum(1 for task in task_records if task["status"] == "failed")
        errors = sum(1 for task in task_records if task["status"] == "error")
        duration_ms = round(
            (time.time() - getattr(self, "_active_node_started_at", time.time())) * 1000
        )
        summary = {
            "node_id": node_num,
            "url": url,
            "depth": depth,
            "duration_ms": duration_ms,
            "frontier": {
                "before": getattr(self, "_active_frontier_size_before", 0),
                "after": frontier_size,
            },
            "tasks": {
                "attempted": attempted,
                "solved": solved,
                "failed": failed,
                "errors": errors,
                "reset_replay_failures_avoided": getattr(
                    self, "_node_reset_short_circuits", 0
                ),
            },
            "urls": dict(sorted(self._node_url_stats.items())),
            "skills": {
                "segments_created": (
                    self.metrics.segments_created - baseline.get("segments", 0)
                ),
                "admitted": len(self.library.all_skills()) - baseline.get("skills", 0),
                "operators_added": (
                    self._observed_operator_count() - baseline.get("operators", 0)
                ),
                "total": len(self.library.all_skills()),
                "operators_total": self._observed_operator_count(),
                "composition_edges": self._observed_composition_count(),
            },
            "planner": getattr(self, "_active_plan_summary", None),
        }
        nodes_dir = os.path.join(self.out_dir, "nodes", f"node_{node_num}")
        os.makedirs(nodes_dir, exist_ok=True)
        with open(os.path.join(nodes_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        urls = summary["urls"]
        status = "✓" if solved else "·"
        lines = [
            f"[N{node_num:03d} {status}] {url}  {duration_ms / 1000:.1f}s",
            f"  Frontier : {summary['frontier']['before']} → {frontier_size}",
            f"  Tasks    : {solved}/{attempted} solved, failed={failed}, errors={errors}",
            "  URLs     : "
            f"navigation={urls.get('solver_navigation_events', 0)} "
            f"unique={urls.get('solver_unique_urls_discovered', 0)} "
            f"eligible={urls.get('solver_urls_frontier_eligible', 0)} "
            f"frontier_added={urls.get('solver_urls_added_to_frontier', 0)}",
            "  Skills   : "
            f"segments=+{summary['skills']['segments_created']} "
            f"admitted=+{summary['skills']['admitted']} "
            f"operators={summary['skills']['operators_total']} "
            f"edges={summary['skills']['composition_edges']}",
        ]
        if summary["tasks"]["reset_replay_failures_avoided"]:
            lines.insert(3, (
                "  Prefix   : "
                f"{summary['tasks']['reset_replay_failures_avoided']} repeated "
                "stateful replay failure(s) avoided"
            ))
        if summary["planner"]:
            planner = summary["planner"]
            lines.append(
                f"  Planner  : goal={planner.get('goal')} "
                f"status={planner.get('status')} length={planner.get('plan_length', 0)}"
            )
        msg = "\n".join(lines)
        print(msg)
        if self._log_file:
            self._log_file.write(msg + "\n")
            self._log_file.flush()
        self._emit_event("node", "completed", level="summary", data=summary)

    def _save_node_info(self, node_num: int, url: str, depth: int,
                         children: list[str], visited: bool,
                         total_trajs: int, successful_trajs: int,
                         selected_child_count: int,
                         frontier_score: float, frontier_breakdown: dict,
                         lookahead_candidates: list[dict],
                         parent_url: str | None = None,
                         tasks: list[dict | str] | None = None,
                         episode_range: list[int] | None = None,
                         prefix_trace: dict | None = None,
                         url_discovery: dict | None = None) -> None:
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
            "reset_replay_failures_avoided": getattr(
                self, "_node_reset_short_circuits", 0
            ),
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
            "prefix_trace": prefix_trace or {},
            "url_discovery": url_discovery or {},
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
                    "task_id": item.get("task_id"),
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

    def _select_frontier_node(self, scored: list[tuple[float, str, int]]) -> tuple[float, str, int] | None:
        """Pick from a small top-score band to avoid overly strict ranking."""
        eligible = [(s, u, d) for s, u, d in scored if d <= self.max_depth]
        if not eligible:
            return None
        best = eligible[0][0]
        threshold = best * getattr(self, "_frontier_score_band", 0.98)
        pool_limit = getattr(self, "_frontier_select_pool", 5)
        pool = [
            item for item in eligible[:pool_limit]
            if item[0] >= threshold
        ] or eligible[:1]

        retry_counts = getattr(self, "_prefix_retry_counts", {})
        selection_counts = getattr(self, "_frontier_selection_counts", {})

        def key(item: tuple[float, str, int]):
            score, url, depth = item
            norm_url = self._node_key(url)
            return (
                retry_counts.get(norm_url, 0),
                selection_counts.get(norm_url, 0),
                depth,
                -score,
                norm_url,
            )

        selected = sorted(pool, key=key)[0]
        norm_selected = self._node_key(selected[1])
        selection_counts[norm_selected] = selection_counts.get(norm_selected, 0) + 1
        self._frontier_selection_counts = selection_counts
        return selected

    def _mark_node_visited(
        self, requested_url: str, processed_url: str,
        visited: set[str], queued: set[str],
    ) -> None:
        """Commit successful node identities and release their reservations."""
        requested = self._node_key(requested_url)
        processed = self._node_key(processed_url)
        visited.update({requested, processed})
        queued.discard(requested)
        queued.discard(processed)
        self._discovered_urls.pop(requested, None)
        self._discovered_urls.pop(processed, None)
        self._prefix_retry_counts.pop(requested, None)
        self._load_retry_counts.pop(requested, None)

    # ---- the loop ------------------------------------------------------------
    def run(self, root_url: str):
        # Use checkpoint loaded in __init__ (if any)
        if self._ckpt:
            root_url = self._node_key(root_url)
            frontier = [
                (self._node_key(url), depth)
                for url, depth in self._ckpt["frontier"]
            ]
            visited = {self._node_key(url) for url in self._ckpt["visited"]}
            queued = {self._node_key(url) for url in self._ckpt["queued"]}
        else:
            root_url = self._node_key(root_url)
            frontier: list[tuple[str, int]] = [(root_url, 0)]
            visited: set[str] = set()
            queued: set[str] = {root_url}
        self._active_visited = visited
        self._active_queued = queued
        self._emit_event(
            "run",
            "resumed" if self._ckpt else "started",
            level="summary",
            data={
                "root_url": root_url,
                "frontier_size": len(frontier),
                "visited": len(visited),
                "max_nodes": self.max_nodes,
                "max_depth": self.max_depth,
            },
        )
        nodes_processed = self._nodes_done
        interrupted = False
        self._write_graph()
        self._write_curriculum()
        self._write_metrics_snapshot()
        # Lưu axtree đã fetch cho từng URL (tránh fetch lại khi explore)
        self._axtree_cache: dict[str, str] = {}
        while frontier and nodes_processed < self.max_nodes:
            self._active_node_id = None
            self._active_task_id = None
            self._active_episode_id = None
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
            self._emit_event("frontier", "ranked", data={
                "size": len(scored),
                "top": frontier_log[:5],
            })
            # Print top-5 to console
            print(f"  [frontier] ranking ({len(scored)} nodes):")
            for entry in frontier_log[:5]:
                print(f"    #{entry['rank']} score={entry['score']:.3f} "
                      f"U={entry['U']:.3f} V={entry['V']:.3f} "
                      f"depth={entry['depth']} {entry['url'][:80]}")
            if len(scored) > 5:
                print(f"    ... and {len(scored) - 5} more")

            # Remove the selected node from frontier. Selection is intentionally
            # loose within a small top-score band to avoid one stale branch
            # monopolizing exploration.
            selected = self._select_frontier_node(scored)
            if not selected:
                break
            _score, url, depth = selected
            self._emit_event("frontier", "selected", level="summary", data={
                "url": url,
                "depth": depth,
                "score": round(_score, 6),
                "rank": next(
                    (index + 1 for index, item in enumerate(scored) if item[1] == url),
                    None,
                ),
            }, node_id=nodes_processed + 1)
            if scored and url != scored[0][1]:
                msg = f"  [frontier] loose select score={_score:.3f} {url[:80]}"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
            frontier = [(u, d) for u, d in frontier if u != url]
            if url in visited or depth > self.max_depth:
                queued.discard(url)
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
            except KeyboardInterrupt:
                interrupted = True
                active_browser = getattr(self, "_active_browser", None)
                if active_browser is not None:
                    try:
                        active_browser.close()
                    except Exception:
                        pass
                    self._active_browser = None
                if url not in {candidate for candidate, _ in frontier}:
                    frontier.insert(0, (url, depth))
                queued.add(url)
                self._emit_event("run", "interrupt_requested", level="warning", data={
                    "node_id": node_num,
                    "url": url,
                    "nodes_processed": nodes_processed,
                }, node_id=node_num)
                self.save_checkpoint(frontier, visited, queued)
                print(
                    f"\n[interrupt] Saved checkpoint at node {node_num}; "
                    "resume with --resume."
                )
                break
            except Exception as e:
                self.metrics.errors += 1
                self._last_node_load_status = {
                    "reason": "process_error",
                    "detail": str(e),
                    "prefix_attempted": False,
                }
                msg = f"[node {node_num} depth={depth}] ERROR: {e}"
                print(msg)
                if self._log_file:
                    self._log_file.write(msg + "\n")
                    self._log_file.flush()
                self._emit_event("node", "failed", level="error", data={
                    "url": url, "depth": depth, "error": str(e),
                }, node_id=node_num)
                self._recover_empty_observation_url(url, depth, frontier, queued)
                self.save_checkpoint(frontier, visited, queued)
                continue

            if not processed_url:
                recovered = self._recover_unprocessed_prefix_url(url, depth, frontier, queued)
                if not recovered:
                    self._recover_empty_observation_url(url, depth, frontier, queued)
                self.save_checkpoint(frontier, visited, queued)
                continue

            self._mark_node_visited(url, processed_url, visited, queued)
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
        self.metrics.operators_mined = len(self.graph.operator_graph.ops)

        self._active_node_id = None
        self._active_task_id = None
        self._active_episode_id = None
        self._emit_event("run", "interrupted" if interrupted else "completed", level=(
            "warning" if interrupted else "summary"
        ), data={
            "nodes_processed": nodes_processed,
            "episodes": self.episode,
            "skills": len(self.library.all_skills()),
            "operators": len(self.graph.operator_graph.ops),
            "solver_urls_added_to_frontier": self.metrics.solver_urls_added_to_frontier,
        })
        logger = getattr(self, "event_logger", None)
        if logger is not None:
            self.metrics.event_counts = dict(sorted(logger.counts.items()))
            logger.flush()

        print(f"\ndone: {nodes_processed} nodes, {self.episode} episodes, "
              f"{len(self.library.all_skills())} skills, "
              f"{len(self.graph.operator_graph.ops)} operators")
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
