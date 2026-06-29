"""Run HSGE exploration on WebArena.

REAL run (needs a hosted WebArena + keys; see docs/04_webarena_runbook.md):
    pip install browsergym-core browsergym-webarena sentence-transformers openai
    playwright install chromium

    # Copy .env.example -> .env, fill in keys & choose provider:
    python run_webarena.py --root-url "$WA_SHOPPING" --out outputs/wa_run --max-nodes 15

    # Or override via CLI:
    python run_webarena.py --provider deepseek --root-url "http://host:7770/" --out outputs/wa_run

    # Dùng model riêng cho explorer (rẻ) và solver (mạnh):
    python run_webarena.py --explorer-model deepseek-chat --solver-model deepseek-reasoner ...

DRY run (no browser, no network -- verifies the whole pipeline wiring):
    python run_webarena.py --dry-run --out /tmp/wa_dry

YAML config (config.yaml is loaded automatically when present):
    python run_webarena.py
    python run_webarena.py --config configs/experiment.yaml --max-nodes 50
"""
from __future__ import annotations

import argparse
import os
import re
import sys


# ---------------------------------------------------------------------------
# .env loader (lightweight, no extra dependency)
# ---------------------------------------------------------------------------
def _load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (no override)."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k not in os.environ:                     # don't override existing env
                os.environ[k] = v


_load_dotenv()


# ---------------------------------------------------------------------------
# Model resolution: provider presets + explicit CLI overrides
# ---------------------------------------------------------------------------
def _resolve_models(args) -> tuple[str | None, str | None]:
    """Return (explorer_model, solver_model) from env/args priority chain.
    Priority: CLI flag > EXPLORER_MODEL/SOLVER_MODEL env > provider preset.
    """
    provider = args.provider or os.environ.get("LLM_PROVIDER", "openai").lower()

    def _resolve(role: str, cli_val: str | None) -> str | None:
        env_key = f"{role.upper()}_MODEL"
        if cli_val:
            return cli_val
        if os.environ.get(env_key):
            return os.environ[env_key]
        # provider preset
        if provider == "deepseek":
            return os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        elif provider == "openai":
            return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        elif provider == "custom":
            return os.environ.get("CUSTOM_MODEL")
        return None

    explorer_model = _resolve("explorer", args.explorer_model)
    solver_model = _resolve("solver", args.solver_model) or explorer_model
    return explorer_model, solver_model


def _resolve_api_config(provider: str) -> tuple[str | None, str | None, str | None]:
    """Return (api_key, base_url, default_model) for the provider."""
    provider = provider.lower()
    if provider == "deepseek":
        return (
            os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "https://api.deepseek.com/v1",
            os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )
    elif provider == "openai":
        return (
            os.environ.get("OPENAI_API_KEY"),
            os.environ.get("OPENAI_BASE_URL"),
            os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        )
    elif provider == "custom":
        return (
            os.environ.get("CUSTOM_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            os.environ.get("CUSTOM_BASE_URL") or os.environ.get("OPENAI_BASE_URL"),
            os.environ.get("CUSTOM_MODEL"),
        )
    else:
        # fallback: treat any unknown provider as custom
        return (
            os.environ.get("OPENAI_API_KEY"),
            os.environ.get("OPENAI_BASE_URL"),
            os.environ.get("HSGE_MODEL", "gpt-4o-mini"),
        )


# ---------------------------------------------------------------------------

from hsge.llm import LLM, HashingEmbedder
from hsge.webarena.runtime import WebArenaExplorer


CONFIG_FIELDS = {
    "run": {
        "root_url": "root_url", "out": "out", "allow": "allow",
        "dry_run": "dry_run", "resume": "resume",
        "transfer_query": "transfer_query",
    },
    "exploration": {
        "max_nodes": "max_nodes", "max_depth": "max_depth",
        "max_steps": "max_steps",
    },
    "llm": {
        "provider": "provider", "model": "model",
        "explorer_model": "explorer_model", "solver_model": "solver_model",
        "api_base_url": "api_base_url",
        "temperature": "llm_temperature",
        "request_timeout_seconds": "llm_timeout_seconds",
        "max_retries": "llm_max_retries",
    },
    "browser": {
        "headless": "headless", "screenshot": "screenshot",
        "timeout_ms": "timeout", "action_timeout_ms": "action_timeout",
        "storage_state": "storage_state",
        "denylist": "denylist", "full_reset_url": "full_reset_url",
        "ignore_query_params": "ignored_query_params",
    },
    "goals": {
        "terminal_goal": "terminal_goal", "instruction": "goal_instruction",
        "auto_terminal_goals": "auto_terminal_goals",
        "max_attempts": "max_goal_attempts",
    },
    "checkout": {
        "mode": "checkout_mode", "place_order_allowed": "place_order_allowed",
    },
    "tasks": {
        "explorer_max_tasks": "explorer_max_tasks",
        "explorer_profile": "explorer_profile",
        "solver_profile": "solver_profile",
        "retry_limit": "task_retry_limit",
    },
    "skills": {
        "similarity_threshold": "skill_sim_threshold",
        "maturity": "skill_maturity", "verify_k": "skill_verify_k",
        "prune_min_rate": "skill_prune_min_rate",
        "diversity_target": "skill_diversity_target",
    },
    "frontier": {
        "alpha": "frontier_alpha", "beta": "frontier_beta",
        "epsilon": "frontier_epsilon", "select_pool": "frontier_select_pool",
        "score_band": "frontier_score_band", "max_size": "frontier_max_size",
        "prefix_retry_limit": "prefix_retry_limit",
        "load_retry_limit": "load_retry_limit",
    },
    "lookahead": {
        "candidates": "lookahead_candidates", "model": "lookahead_model",
        "base_url": "lookahead_base_url",
        "request_timeout_seconds": "lookahead_timeout_seconds",
        "max_retries": "lookahead_max_retries",
    },
    "observability": {
        "event_log_level": "event_log_level",
    },
    "predicates": {
        "plugins": "predicate_plugins",
    },
}


def _load_yaml_defaults(path: str, *, required: bool = False) -> dict:
    """Load and flatten the documented YAML schema into argparse destinations."""
    if not os.path.isfile(path):
        if required:
            raise FileNotFoundError(f"config file not found: {path}")
        return {}
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise RuntimeError("PyYAML is required to use --config; install pyyaml>=6.0") from exc
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError("config root must be a YAML mapping")
    unknown_sections = sorted(set(raw) - set(CONFIG_FIELDS))
    if unknown_sections:
        raise ValueError(f"unknown config section(s): {', '.join(unknown_sections)}")
    defaults = {}
    for section, values in raw.items():
        if values is None:
            continue
        if not isinstance(values, dict):
            raise ValueError(f"config section '{section}' must be a mapping")
        unknown = sorted(set(values) - set(CONFIG_FIELDS[section]))
        if unknown:
            raise ValueError(
                f"unknown key(s) in config section '{section}': {', '.join(unknown)}"
            )
        for key, value in values.items():
            defaults[CONFIG_FIELDS[section][key]] = value
    return defaults


def _config_path_from_argv(argv: list[str]) -> tuple[str, bool]:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default="config.yaml")
    known, _ = pre.parse_known_args(argv)
    explicit = any(arg == "--config" or arg.startswith("--config=") for arg in argv)
    return known.config, explicit


def _validate_args(ap: argparse.ArgumentParser, args) -> None:
    positive = {
        "max_nodes": args.max_nodes, "max_steps": args.max_steps,
        "timeout": args.timeout, "action_timeout": args.action_timeout,
        "max_goal_attempts": args.max_goal_attempts,
        "explorer_max_tasks": args.explorer_max_tasks,
        "skill_maturity": args.skill_maturity,
        "skill_diversity_target": args.skill_diversity_target,
        "frontier_select_pool": args.frontier_select_pool,
        "lookahead_candidates": args.lookahead_candidates,
    }
    for name, value in positive.items():
        if value <= 0:
            ap.error(f"--{name.replace('_', '-')} must be > 0")
    nonnegative = {
        "max_depth": args.max_depth, "skill_verify_k": args.skill_verify_k,
        "prefix_retry_limit": args.prefix_retry_limit,
        "load_retry_limit": args.load_retry_limit,
        "llm_max_retries": args.llm_max_retries,
        "lookahead_max_retries": args.lookahead_max_retries,
    }
    for name, value in nonnegative.items():
        if value < 0:
            ap.error(f"--{name.replace('_', '-')} must be >= 0")
    for name, value in {
        "frontier_alpha": args.frontier_alpha,
        "frontier_beta": args.frontier_beta,
    }.items():
        if value < 0:
            ap.error(f"--{name.replace('_', '-')} must be >= 0")
    if args.frontier_epsilon <= 0:
        ap.error("--frontier-epsilon must be > 0")
    if args.llm_timeout_seconds <= 0 or args.lookahead_timeout_seconds <= 0:
        ap.error("LLM request timeouts must be > 0")
    if not 0.0 <= args.llm_temperature <= 2.0:
        ap.error("--llm-temperature must be between 0 and 2")
    for name, value in {
        "skill_sim_threshold": args.skill_sim_threshold,
        "skill_prune_min_rate": args.skill_prune_min_rate,
        "frontier_score_band": args.frontier_score_band,
    }.items():
        if not 0.0 <= value <= 1.0:
            ap.error(f"--{name.replace('_', '-')} must be between 0 and 1")
    if args.frontier_max_size is not None and args.frontier_max_size <= 0:
        ap.error("--frontier-max-size must be > 0 when set")
    if args.provider not in {None, "deepseek", "openai", "custom"}:
        ap.error("--provider must be deepseek, openai, or custom")
    if args.checkout_mode not in {"safe", "full", "discover-only"}:
        ap.error("--checkout-mode must be safe, full, or discover-only")
    if args.denylist is not None and not isinstance(args.denylist, list):
        ap.error("browser.denylist must be a YAML list")
    if not isinstance(args.ignored_query_params, list):
        ap.error("browser.ignore_query_params must be a YAML list")


def _check_overwrite_safety(out_dir: str) -> None:
    """Warn if output directory has existing data that would be overwritten."""
    ep_dir = os.path.join(out_dir, "episodes")
    skills = os.path.join(out_dir, "skills.json")
    has_episodes = os.path.isdir(ep_dir) and os.listdir(ep_dir)
    has_skills = os.path.isfile(skills) and os.path.getsize(skills) > 0
    if has_episodes or has_skills:
        print("\n" + "!" * 60)
        print("  WARNING: Output directory already has data!")
        if has_episodes:
            n_eps = len([d for d in os.listdir(ep_dir) if d.startswith("ep_")])
            print(f"  - {n_eps} episodes in {ep_dir}")
        if has_skills:
            print(f"  - skills.json exists in {out_dir}")
        print("  Running without --resume will OVERWRITE run.log and frontier.")
        print("  Use --resume to continue from checkpoint instead.")
        print("!" * 60 + "\n")


# --------------------------- dry-run fakes --------------------------------- #
class _DryLLM(LLM):
    """Scripted LLM: proposes two tasks, advances one step then declares done."""
    def complete_json(self, system: str, prompt: str) -> dict:
        if system.startswith("PROPOSE"):
            return {"tasks": ["use the visible search control", "open a visible detail link"]}
        if "web agent" in system.lower():                       # solver
            if "click('1')" in prompt:                          # already acted -> finish
                return {"thought": "done", "action": "send_msg_to_user('done')"}
            return {"thought": "advance", "action": "click('1')"}
        return {}                                               # segment/abstract: no-op

    def complete_vision_json(self, system: str, prompt: str,
                             screenshot_base64: bytes | None = None) -> dict:
        return self.complete_json(system, prompt)


class _FakeBrowser:
    SEQ = [("http://example.test/home", ""),
           ("http://example.test/search?q=x", "search results"),
           ("http://example.test/detail/123", "details and status"),
           ("http://example.test/form", "Continue"),
           ("http://example.test/complete", "Success")]

    def __init__(self, url): self.i = 0
    def reset(self): self.i = 0; return self.observation()
    def observation(self):
        u, ax = self.SEQ[min(self.i, len(self.SEQ) - 1)]
        return {"url": u, "axtree": f"[1] link 'next'\n{ax}", "bids": ["1"]}
    def act(self, a):
        if not a.startswith("send_msg"):
            self.i = min(self.i + 1, len(self.SEQ) - 1)
        return self.observation()
    def links(self): return []
    def close(self): pass


def _build_parser(defaults: dict | None = None) -> argparse.ArgumentParser:
    defaults = defaults or {}

    def d(name, fallback):
        return defaults.get(name, fallback)

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml",
                    help="YAML config path (default: config.yaml when present).")
    ap.add_argument("--root-url", default=d("root_url", None))
    ap.add_argument("--out", default=d("out", "outputs/wa_run"))
    ap.add_argument("--allow", default=d("allow", None), help="regex of allowed child URLs")
    ap.add_argument("--max-nodes", type=int, default=d("max_nodes", 20))
    ap.add_argument("--max-depth", type=int, default=d("max_depth", 6))
    ap.add_argument("--max-steps", type=int, default=d("max_steps", 20))

    # --- provider & model selection ---
    ap.add_argument("--provider", default=d("provider", None),
                    choices=["deepseek", "openai", "custom"],
                    help="LLM provider preset (default: from LLM_PROVIDER env or 'openai')")
    ap.add_argument("--model", default=d("model", None),
                    help="Model for BOTH explorer & solver (shorthand, overridden by --explorer-model/--solver-model)")
    ap.add_argument("--explorer-model", default=d("explorer_model", None),
                    help="Model for PageExplorer (task proposal). Env: EXPLORER_MODEL")
    ap.add_argument("--solver-model", default=d("solver_model", None),
                    help="Model for Solver (action planning). Env: SOLVER_MODEL")
    ap.add_argument("--api-base-url", default=d("api_base_url", None),
                    help="Override provider API base URL (API keys still come from environment).")
    ap.add_argument("--llm-temperature", type=float, default=d("llm_temperature", 0.2))
    ap.add_argument("--llm-timeout-seconds", type=float, default=d("llm_timeout_seconds", 60.0))
    ap.add_argument("--llm-max-retries", type=int, default=d("llm_max_retries", 2))

    ap.add_argument("--headless", action=argparse.BooleanOptionalAction,
                    default=d("headless", True))
    ap.add_argument("--screenshot", action=argparse.BooleanOptionalAction,
                    default=d("screenshot", False),
                    help="Include screenshots in observations (for vision-enabled models)")
    ap.add_argument("--timeout", type=int, default=d("timeout", 30000),
                    help="Browser page load timeout in ms (default: 30000)")
    ap.add_argument("--action-timeout", type=int, default=d("action_timeout", 5000),
                    help="Playwright action timeout in ms (default: 5000)")
    ap.add_argument("--dry-run", action=argparse.BooleanOptionalAction,
                    default=d("dry_run", False))
    ap.add_argument("--resume", action=argparse.BooleanOptionalAction,
                    default=d("resume", False),
                    help="Resume from previous checkpoint in --out dir")
    ap.add_argument("--transfer-query", default=d("transfer_query", None),
                    help="Extra transfer query to evaluate after exploration "
                         "(e.g. 'find a record and read its status').")
    ap.add_argument("--terminal-goal", default=d("terminal_goal", None),
                    help="Optional predicate for a composed goal task. By default, "
                         "the run performs local exploration only.")
    ap.add_argument("--goal-instruction", default=d("goal_instruction", None),
                    help="Natural-language instruction used with --terminal-goal.")
    ap.add_argument("--denylist", default=d("denylist", None), nargs="*",
                    help="Additional URL regex patterns to exclude from frontier "
                         "(/logout is always blocked by default). "
                         "Example: --denylist '/customer/account/logout' '/wishlist'")
    ap.add_argument("--full-reset-url", default=d("full_reset_url", None),
                    help="POST URL to reset server state before each node "
                         "(e.g. http://host:3000/reset) so each node starts fresh.")
    ap.add_argument("--ignore-query-params", dest="ignored_query_params", nargs="*",
                    default=d("ignored_query_params", [
                        "utm_*", "gclid", "fbclid", "msclkid", "dclid", "_ga", "_gl",
                    ]),
                    help="Query parameter names/patterns ignored in visited-node identity.")
    ap.add_argument("--checkout-mode", default=d("checkout_mode", "safe"),
                    choices=["safe", "full", "discover-only"],
                    help="How far to explore checkout/order flows. Default: safe.")
    ap.add_argument("--auto-terminal-goals", action=argparse.BooleanOptionalAction,
                    default=d("auto_terminal_goals", True),
                    help="Automatically attempt composed transactional goals when an operator chain exists.")
    ap.add_argument("--place-order-allowed", action=argparse.BooleanOptionalAction,
                    default=d("place_order_allowed", False),
                    help="Allow final irreversible order/payment submission. Default: false.")
    ap.add_argument("--max-goal-attempts", type=int, default=d("max_goal_attempts", 3),
                    help="Maximum full attempts for each composed goal (default: 3).")
    ap.add_argument("--storage-state", default=d("storage_state", None),
                    help="Path to Playwright storageState JSON file containing "
                         "pre-saved cookies and session data. When provided, the "
                         "browser will start already logged in. "
                         "Generate with: python generate_auth_state.py")
    ap.add_argument("--explorer-max-tasks", type=int, default=d("explorer_max_tasks", 12))
    ap.add_argument("--task-retry-limit", type=int, default=d("task_retry_limit", 3),
                    help="Max attempts per local task (1 + N retries, default 3).")
    ap.add_argument("--explorer-profile", default=d("explorer_profile", "training_quality"))
    ap.add_argument("--solver-profile", default=d("solver_profile", "training_quality"))
    ap.add_argument("--skill-sim-threshold", type=float, default=d("skill_sim_threshold", 0.6))
    ap.add_argument("--skill-maturity", type=int, default=d("skill_maturity", 3))
    ap.add_argument("--skill-verify-k", type=int, default=d("skill_verify_k", 2))
    ap.add_argument("--skill-prune-min-rate", type=float, default=d("skill_prune_min_rate", 0.34))
    ap.add_argument("--skill-diversity-target", type=int, default=d("skill_diversity_target", 4))
    ap.add_argument("--frontier-alpha", type=float, default=d("frontier_alpha", 1.0))
    ap.add_argument("--frontier-beta", type=float, default=d("frontier_beta", 1.0))
    ap.add_argument("--frontier-epsilon", type=float, default=d("frontier_epsilon", 1e-5))
    ap.add_argument("--frontier-select-pool", type=int, default=d("frontier_select_pool", 5))
    ap.add_argument("--frontier-score-band", type=float, default=d("frontier_score_band", 0.98))
    ap.add_argument("--frontier-max-size", type=int, default=d("frontier_max_size", None))
    ap.add_argument("--prefix-retry-limit", type=int, default=d("prefix_retry_limit", 2))
    ap.add_argument("--load-retry-limit", type=int, default=d("load_retry_limit", 2))
    ap.add_argument("--lookahead-candidates", type=int, default=d("lookahead_candidates", 5))
    ap.add_argument("--lookahead-model", default=d("lookahead_model", None))
    ap.add_argument("--lookahead-base-url", default=d("lookahead_base_url", None))
    ap.add_argument("--lookahead-timeout-seconds", type=float,
                    default=d("lookahead_timeout_seconds", 30.0))
    ap.add_argument("--lookahead-max-retries", type=int,
                    default=d("lookahead_max_retries", 1))
    ap.add_argument(
        "--event-log-level",
        choices=["debug", "info", "summary", "warning", "error"],
        default=d("event_log_level", "info"),
        help="Minimum level written to events.jsonl (default: info).",
    )
    ap.add_argument(
        "--predicate-plugins",
        nargs="*",
        choices=["auto", "commerce"],
        default=d("predicate_plugins", ["auto"]),
        help="Predicate plugins layered over the domain-neutral core.",
    )
    return ap


def main(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    config_path, explicit_config = _config_path_from_argv(argv)
    try:
        defaults = _load_yaml_defaults(config_path, required=explicit_config)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"[config] {exc}") from exc
    ap = _build_parser(defaults)
    args = ap.parse_args(argv)
    _validate_args(ap, args)
    if os.path.isfile(config_path):
        print(f"[config] loaded {config_path}")
    if not args.root_url:
        args.root_url = "http://example.test/home" if args.dry_run else None
    if not args.root_url:
        ap.error("--root-url is required unless --dry-run is used")

    # Safety: warn if output dir has existing data and not resuming
    if not args.resume and not args.dry_run:
        _check_overwrite_safety(args.out)

    allow = args.allow or (re.escape(args.root_url.rsplit("/", 1)[0]) + ".*")

    if args.dry_run:
        llm, embedder = _DryLLM(), HashingEmbedder()
        browser_factory = lambda url: _FakeBrowser(url)
        explorer_llm = solver_llm = llm
    else:
        from hsge.backends import OpenAILLM, STEmbedder
        from hsge.webarena.browser import WebArenaBrowser

        provider = args.provider or os.environ.get("LLM_PROVIDER", "openai").lower()
        api_key, base_url, _default_model = _resolve_api_config(provider)
        base_url = args.api_base_url or base_url

        explorer_model, solver_model = _resolve_models(args)
        # --model shorthand overrides both if set
        if args.model:
            explorer_model = solver_model = args.model

        if not api_key:
            print("[ERROR] No API key found. Set env var for your provider:")
            print("  DeepSeek: DEEPSEEK_API_KEY=sk-...  (or OPENAI_API_KEY)")
            print("  OpenAI:   OPENAI_API_KEY=sk-...")
            print("  Or copy .env.example -> .env and fill in keys.")
            return

        # DeepSeek does not support vision; only enable for OpenAI
        vision_ok = (provider == "openai")

        explorer_llm = OpenAILLM(model=explorer_model, api_key=api_key, base_url=base_url,
                                 supports_vision=vision_ok,
                                 temperature=args.llm_temperature,
                                 timeout_seconds=args.llm_timeout_seconds,
                                 max_retries=args.llm_max_retries)
        solver_llm = OpenAILLM(model=solver_model, api_key=api_key, base_url=base_url,
                               supports_vision=vision_ok,
                               temperature=args.llm_temperature,
                               timeout_seconds=args.llm_timeout_seconds,
                               max_retries=args.llm_max_retries)
        try:
            embedder = STEmbedder()
        except ModuleNotFoundError as e:
            if e.name != "sentence_transformers":
                raise
            print("[WARN] sentence_transformers is not installed; using HashingEmbedder fallback.")
            print("       For higher-quality skill clustering, install it with:")
            print("       pip install sentence-transformers")
            embedder = HashingEmbedder()
        _storage_state = args.storage_state
        browser_factory = lambda url, _ss=_storage_state: WebArenaBrowser(
            url, headless=args.headless,
            screenshot=args.screenshot,
            timeout_ms=args.timeout,
            action_timeout_ms=args.action_timeout,
            storage_state=_ss,
        )

        print(f"[config] provider={provider}")
        print(f"[config] explorer model={explorer_model}")
        print(f"[config] solver   model={solver_model}")
        print(f"[config] base URL ={base_url}")
        print(f"[config] vision  ={vision_ok}")

    explorer = WebArenaExplorer(
        browser_factory=browser_factory,
        explorer_llm=explorer_llm,
        solver_llm=solver_llm,
        embedder=embedder, out_dir=args.out,
        allow_pattern=allow, max_depth=args.max_depth, max_nodes=args.max_nodes,
        max_steps=args.max_steps,
        terminal_goal=args.terminal_goal,
        goal_instruction=args.goal_instruction,
        resume=args.resume,
        denylist_patterns=args.denylist,
        full_reset_url=args.full_reset_url,
        checkout_mode=args.checkout_mode,
        auto_terminal_goals=args.auto_terminal_goals,
        place_order_allowed=args.place_order_allowed,
        max_goal_attempts=args.max_goal_attempts,
        explorer_max_tasks=args.explorer_max_tasks,
        explorer_profile=args.explorer_profile,
        solver_profile=args.solver_profile,
        skill_sim_threshold=args.skill_sim_threshold,
        skill_maturity=args.skill_maturity,
        skill_verify_k=args.skill_verify_k,
        skill_prune_min_rate=args.skill_prune_min_rate,
        skill_diversity_target=args.skill_diversity_target,
        frontier_alpha=args.frontier_alpha,
        frontier_beta=args.frontier_beta,
        frontier_epsilon=args.frontier_epsilon,
        frontier_select_pool=args.frontier_select_pool,
        frontier_score_band=args.frontier_score_band,
        frontier_max_size=args.frontier_max_size,
        prefix_retry_limit=args.prefix_retry_limit,
        load_retry_limit=args.load_retry_limit,
        task_retry_limit=args.task_retry_limit,
        lookahead_candidates=args.lookahead_candidates,
        lookahead_model=args.lookahead_model,
        lookahead_base_url=args.lookahead_base_url,
        lookahead_timeout_seconds=args.lookahead_timeout_seconds,
        lookahead_max_retries=args.lookahead_max_retries,
        event_log_level=args.event_log_level,
        predicate_plugins=args.predicate_plugins,
        ignored_query_params=args.ignored_query_params,
    )
    explorer.run(args.root_url)
    if args.transfer_query:
        explorer.transfer_eval(args.transfer_query, top_k=5)
    print("\nnext: python build_sft_dataset.py", os.path.join(args.out, "episodes"), "train.jsonl")


if __name__ == "__main__":
    main()
