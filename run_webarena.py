"""Run HSGE exploration on WebArena.

REAL run (needs a hosted WebArena + keys; see docs/04_webarena_runbook.md):
    pip install browsergym-core browsergym-webarena sentence-transformers openai
    playwright install chromium
    # secrets + WA_* URLs go in .env; run params in config.yaml:
    python run_webarena.py                       # uses config.yaml + .env
    python run_webarena.py --site shopping --max-nodes 5 --headed   # CLI overrides

DRY run (no browser, no network -- verifies the whole pipeline wiring):
    python run_webarena.py --dry-run --out /tmp/wa_dry
"""
from __future__ import annotations

import argparse
import copy
import os
import re
from urllib.parse import urlsplit

import yaml

from hsge.llm import HashingEmbedder, MockLLM
from hsge.webarena.runtime import WebArenaExplorer


# Built-in defaults; config.yaml overrides these, CLI flags override config.yaml.
DEFAULTS = {
    "run": {"site": "shopping", "root_url": None, "out_dir": "outputs/wa_run",
            "allow": None, "denylist": r"logout|\?p=|product_list_|[?&]sort=",
            "max_nodes": 15, "max_depth": 6, "max_steps": 15, "max_tasks": 6, "maturity": 2,
            "task_retries": 0,
            "goal_chains_per_node": 3,
            "use_site_seed": False, "seed_capability_repeats": 3,
            "goal_max_steps": None,
            "unprefixed_sampling": False,
            "verify_episodes": False,
            "plan_subgoals": False,
            "predicate_sim": 0.6, "seg_axtree_sim": 0.6, "headed": False, "success_url_re": None,
            "full_reset_url": None, "terminal_goal": None,
            "mine_hrefs": True, "per_template_cap": 3, "reached_template_cap": 8,
            "max_hrefs_per_page": 100},
    "llm": {"provider": None, "model": None, "base_url": None, "temperature": 0.2,
            "agents": {}},
    "embedder": {"model": "all-MiniLM-L6-v2"},
}

# Every model-backed helper in the real exploration pipeline. Values under
# llm.agents.<role> override the shared llm defaults in config.yaml.
AGENT_ROLES = (
    "site_seeder",
    "page_explorer",
    "solver",
    "trajectory_segmenter",
    "skill_abstractor",
    "skill_verifier",
    "operator_inducer",
    "episode_judge",
    "goal_planner",
)


def _load_config(path: str | None) -> dict:
    """Merge config.yaml (if present) onto DEFAULTS, section by section."""
    cfg = copy.deepcopy(DEFAULTS)
    if path and os.path.exists(path):
        loaded = yaml.safe_load(open(path, encoding="utf-8")) or {}
        for section in cfg:
            cfg[section].update(loaded.get(section) or {})
    return cfg


def _pick(cli_val, cfg_val):
    """CLI wins when the user passed it (not None), else fall back to config."""
    return cli_val if cli_val is not None else cfg_val


def _default_allow_pattern(root_url: str) -> str:
    """Restrict the frontier to the site's own scheme+host by default.

    The old approach (``root_url.rsplit("/", 1)[0]``) assumed root_url has at
    least one path segment beyond the host -- true for shopping_admin's
    ".../admin", false for a bare ``WA_<SITE>`` root
    (``https://x.trycloudflare.com``, no trailing path). For a bare host,
    ``rsplit("/", 1)`` cuts at the "//" *after the scheme*, producing
    "https:/" -- a pattern effectively matching any https URL at all. Real
    fallout: ``outputs/wa_run_21_reddit`` wandered onto
    ncbi.nlm.nih.gov/auth.nih.gov/support.google.com (72/177 nodes, 244/532
    episodes ended up off-domain); ``wa_run_20_reddit``/``wa_run_20_gitlab``
    were hit the same way (news sites, gitlab.com/docs.gitlab.com) whenever a
    page happened to link off-site. Anchoring on scheme+netloc via urlsplit
    (with a leading ``^``, since callers use ``re.search``) fixes both the
    missing-path case and a latent substring-match risk in the old pattern.
    """
    parsed = urlsplit(root_url)
    return "^" + re.escape(f"{parsed.scheme}://{parsed.netloc}") + r"(/|$)"


# --------------------------- dry-run fakes --------------------------------- #
class _DryLLM(MockLLM):
    """Scripted LLM for the dry run. Delegates segmentation/abstraction to MockLLM
    (deterministic) and only scripts the explorer, the solver, and operator
    induction. The solver walks the fake purchase all the way to the success page
    so Discovery admits skills that then become operators, including a terminal one.
    """
    def complete_json(self, system: str, prompt: str,
                       image_b64: str | None = None, image_detail: str = "low") -> dict:
        if system.startswith("DECOMPOSE"):                      # goal planner
            return {"subgoals": ["open the item", "add it to the cart"]}
        if system.startswith("You are a strict grader"):        # inline episode verifier
            # PASS the local tasks (the scripted solver really does walk the fake
            # site) but FAIL the checkout GOAL, whose success page it never
            # reaches -- so the dry run exercises BOTH sides: verified successes
            # still feed Discovery/promotion, and a false positive is caught.
            goal = str(MockLLM._payload(prompt).get("goal", "")).lower()
            if "order confirmation" in goal:
                return {"verdict": "FAIL", "reason": "never reached the success page"}
            return {"verdict": "PASS", "reason": "the final page shows the task was done"}
        if system.startswith("SUMMARIZE"):                      # site seeder
            return {"description": "A demo shopping site.",
                    "capabilities": [{"name": "checkout",
                                      "goal": "Buy an item and reach the order confirmation page."}]}
        if system.startswith("PROPOSE"):                        # explorer
            return {"tasks": ["search for an item", "add an item to cart"]}
        if "web agent" in system.lower():                       # solver
            if "thank you for your purchase" in prompt.lower():  # goal page -> finish
                return {"thought": "done", "action": "send_msg_to_user('done')"}
            return {"thought": "advance", "action": "click('1')"}
        if "PLANNING OPERATOR" in system:                       # operator induction
            return self._induce(prompt)
        if "PLANNING PREDICATES" in system:                     # operator grounding gate
            return self._ground_predicates(prompt)
        return super().complete_json(system, prompt)            # segment / abstract

    @staticmethod
    def _induce(prompt: str) -> dict:
        # Derive a distinct NL effect from the page content (as a real LLM would),
        # not the near-identical skill name -- otherwise the coarse hashing embedder
        # collapses them into one canonical predicate.
        p = MockLLM._payload(prompt)
        after = " ".join(b.get("after", "") for b in p.get("boundary_states", [])).lower()
        if "thank you for your purchase" in after:
            return {"preconditions": [], "effects": ["the purchase is confirmed"], "terminal": True}
        if "cart" in after:
            return {"preconditions": [], "effects": ["an item is in the cart"], "terminal": False}
        if "result" in after:
            return {"preconditions": [], "effects": ["search results are shown"], "terminal": False}
        return {"preconditions": [], "effects": ["a page action completed"], "terminal": False}

    @staticmethod
    def _ground_predicates(prompt: str) -> dict:
        """Confirm every induced predicate on every occurrence. `_induce` reads
        the effect straight off the page it is scored against, so they really do
        hold here; without this the effect-grounding gate would reject every
        dry-run operator and the run would stop exercising the planning path."""
        p = MockLLM._payload(prompt)
        holds = [True] * len(p.get("occurrences", []))
        return {"results": [{"predicate": pred, "type": kind, "member_holds": holds}
                            for kind, key in (("precondition", "preconditions"),
                                              ("effect", "effects"))
                            for pred in p.get(key, [])]}


class _FakeBrowser:
    SEQ = [("http://shop/home", ""),
           ("http://shop/catalogsearch/result/?q=x", "search results"),
           ("http://shop/item.html", "Add to Cart"),
           ("http://shop/checkout/cart", "2 items in cart"),
           ("http://shop/checkout", "payment"),
           ("http://shop/checkout/onepage/success", "Thank you for your purchase")]

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
    def page_hrefs(self, limit: int = 100):
        # a couple of in-host URLs so --dry-run exercises the href-mining path
        return ["http://shop/catalog/category/1", "http://shop/catalog/category/2"][:limit]
    def close(self): pass

    def screenshot_b64(self, som: bool = False) -> str | None:
        """Tiny stub screenshot so --dry-run exercises the vision code path
        (capture -> attach -> persist) with no real browser."""
        try:
            import base64
            import io
            from PIL import Image
            buf = io.BytesIO()
            Image.new("RGB", (2, 2), color=(200, 200, 200)).save(buf, format="JPEG")
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except ImportError:
            return None


def _check_resume_precondition(out_dir: str, resume: bool):
    """Guard the --resume flag against the checkpoint on disk. Returns the
    checkpoint path to resume from, or None for a fresh run. Raises ValueError on
    a mismatch: --resume without a checkpoint, or an existing checkpoint (an
    interrupted run) without --resume -- refusing the latter avoids silently
    truncating run_log.jsonl and overwriting a run that could be continued."""
    ckpt = os.path.join(out_dir, "checkpoint.pkl")
    exists = os.path.exists(ckpt)
    if resume and not exists:
        raise ValueError(f"--resume given but no checkpoint at {ckpt}")
    if exists and not resume:
        raise ValueError(f"{ckpt} exists (interrupted run). Pass --resume to "
                         f"continue it, or choose a new --out.")
    return ckpt if resume else None


def _load_dotenv():
    """Load a .env if python-dotenv is installed; no-op otherwise."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def perform_full_reset(url: str, retries: int = 3):
    """POST to a WebArena full-reset endpoint (optional). Mirrors go-browse."""
    import requests
    for _ in range(retries):
        try:
            r = requests.post(url, timeout=180)
            if r.status_code == 200:
                print(f"[reset] full reset ok: {r.text[:120]}")
                return
            print(f"[reset] status {r.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[reset] error: {e}")
    print("[reset] giving up after retries")


def _first_not_none(*values):
    return next((value for value in values if value is not None), None)


def _effective_llm_config(cli, llm_cfg, role: str | None = None) -> dict:
    """Resolve one helper's effective config without constructing a client.

    Global CLI flags intentionally override every helper. Otherwise a role-level
    value wins over the shared ``llm`` value, then provider-specific environment
    variables supply the final fallback.
    """
    role_cfg = ((llm_cfg.get("agents") or {}).get(role) or {}) if role else {}
    provider = (_first_not_none(
        cli.provider, role_cfg.get("provider"), llm_cfg.get("provider"),
        os.environ.get("LLM_PROVIDER"), "openai",
    ) or "openai").lower()
    p = provider.upper()
    return {
        "provider": provider,
        "model": _first_not_none(
            cli.model, role_cfg.get("model"), llm_cfg.get("model"),
            os.environ.get(f"{p}_MODEL"),
        ),
        "base_url": _first_not_none(
            cli.base_url, role_cfg.get("base_url"), llm_cfg.get("base_url"),
            os.environ.get(f"{p}_BASE_URL"),
        ),
        "api_key": os.environ.get(f"{p}_API_KEY"),
        "temperature": float(_first_not_none(
            role_cfg.get("temperature"), llm_cfg.get("temperature"), 0.2,
        )),
        # GPT-5-only params; None -> never sent (what gpt-4o / deepseek need).
        "reasoning_effort": _first_not_none(
            role_cfg.get("reasoning_effort"), llm_cfg.get("reasoning_effort"),
        ),
        "verbosity": _first_not_none(
            role_cfg.get("verbosity"), llm_cfg.get("verbosity"),
        ),
    }


def _resolve_agent_vision(llm_cfg) -> dict[str, dict]:
    """Per-role {vision, som, image_detail}: role > shared > default (no CLI override)."""
    result = {}
    for role in AGENT_ROLES:
        role_cfg = (llm_cfg.get("agents") or {}).get(role) or {}
        result[role] = {
            "vision": bool(_first_not_none(role_cfg.get("vision"), llm_cfg.get("vision"), False)),
            "som": bool(_first_not_none(role_cfg.get("som"), llm_cfg.get("som"), True)),
            "image_detail": _first_not_none(
                role_cfg.get("image_detail"), llm_cfg.get("image_detail"), "low"),
        }
    return result


def _resolve_llm(cli, llm_cfg, role: str | None = None):
    """Construct the OpenAI-compatible backend for one helper role."""
    cfg = _effective_llm_config(cli, llm_cfg, role)
    from hsge.backends import OpenAILLM
    label = f":{role}" if role else ""
    extra = "".join(f" {p}={cfg[p]}" for p in ("reasoning_effort", "verbosity") if cfg[p])
    print(f"[llm{label}] provider={cfg['provider']} model={cfg['model']} "
          f"base_url={cfg['base_url'] or '(default)'} temp={cfg['temperature']}{extra}")
    return OpenAILLM(
        model=cfg["model"], base_url=cfg["base_url"], api_key=cfg["api_key"],
        temperature=cfg["temperature"], provider=cfg["provider"],
        reasoning_effort=cfg["reasoning_effort"], verbosity=cfg["verbosity"],
    )


def _resolve_agent_llms(cli, llm_cfg) -> dict[str, object]:
    llms = {role: _resolve_llm(cli, llm_cfg, role) for role in AGENT_ROLES}
    # solver_goal (C5) is an OPTIONAL role: only build it when the user configured
    # llm.agents.solver_goal, so GOAL solving falls back to the LOCAL solver otherwise.
    if "solver_goal" in (llm_cfg.get("agents") or {}):
        llms["solver_goal"] = _resolve_llm(cli, llm_cfg, "solver_goal")
    return llms


def main():
    _load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml", help="path to config.yaml")
    # All below default to None so they only override config.yaml when passed.
    ap.add_argument("--site", default=None, help="WA_<SITE> to explore (e.g. shopping)")
    ap.add_argument("--root-url", default=None, help="explicit start URL (overrides --site)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--allow", default=None, help="regex of allowed child URLs")
    ap.add_argument("--denylist", default=None, help="regex of blocked child URLs")
    ap.add_argument("--max-nodes", type=int, default=None)
    ap.add_argument("--max-depth", type=int, default=None)
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--max-tasks", type=int, default=None,
                    help="max tasks PageExplorer proposes per node")
    ap.add_argument("--maturity", type=int, default=None)
    ap.add_argument("--task-retries", type=int, default=None,
                    help="retry a failed task up to N more times (default 0; "
                         "infeasible tasks are never retried)")
    ap.add_argument("--goal-chains-per-node", type=int, default=None,
                    help="max NEW depth-based goal chains attempted per node "
                         "(default 3; each distinct chain is attempted once per run)")
    ap.add_argument("--goal-max-steps", type=int, default=None,
                    help="step budget for GOAL/composite tasks (default: same as "
                         "--max-steps); multi-step goals need more room than LOCAL")
    ap.add_argument("--unprefixed", dest="unprefixed_sampling", action="store_const",
                    const=True, default=None,
                    help="also re-solve every SOLVED task from the site root "
                         "(Go-Browse unprefixed sampling): +1 episode per solved "
                         "task, but the trajectories include the navigation")
    ap.add_argument("--no-unprefixed", dest="unprefixed_sampling", action="store_const",
                    const=False, help="disable unprefixed sampling")
    ap.add_argument("--seg-axtree-sim", type=float, default=None,
                    help="axtree-similarity threshold for segmentation boundary "
                         "candidates (default 0.6; lower = fewer candidate cuts)")
    ap.add_argument("--no-mine-hrefs", dest="mine_hrefs", action="store_const",
                    const=False, default=None,
                    help="disable mining <a href> links into the frontier (reproduces "
                         "the old navigated-only behavior)")
    ap.add_argument("--reached-template-cap", type=int, default=None,
                    help="max visited nodes per URL template for tier-0 (navigated-to) "
                         "URLs; stops one page shape from monopolising the frontier")
    ap.add_argument("--per-template-cap", type=int, default=None,
                    help="max mined nodes admitted per URL template (default 3)")
    ap.add_argument("--max-hrefs-per-page", type=int, default=None,
                    help="cap on <a href> links mined per page (default 100)")
    ap.add_argument("--provider", default=None, help="openai | deepseek")
    ap.add_argument("--model", default=None, help="LLM model id (e.g. gpt-4o-mini, deepseek-chat)")
    ap.add_argument("--base-url", default=None, help="OpenAI-compatible base URL")
    ap.add_argument("--headed", action="store_const", const=True, default=None,
                    help="run browser headed (for debugging)")
    ap.add_argument("--full-reset-url", default=None,
                    help="POST here once before exploring to reset WebArena state")
    ap.add_argument("--success-url-re", default=None,
                    help="override the order_confirmed success-URL regex")
    ap.add_argument("--read-only", action="store_true",
                    help="propose only [INFO]/[NAV] tasks; never [MOD] (no writes to the site)")
    ap.add_argument("--resume", action="store_true",
                    help="continue an interrupted run from <out_dir>/checkpoint.pkl "
                         "(same --out; frontier, visited set, and discovered skills/"
                         "operators are restored)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = _load_config(args.config)
    run, llm_cfg, emb_cfg = cfg["run"], cfg["llm"], cfg["embedder"]

    out_dir = _pick(args.out, run["out_dir"])
    try:
        resume_ckpt = _check_resume_precondition(out_dir, args.resume)
    except ValueError as e:
        ap.error(str(e))
    max_nodes = _pick(args.max_nodes, run["max_nodes"])
    max_depth = _pick(args.max_depth, run["max_depth"])
    max_steps = _pick(args.max_steps, run["max_steps"])
    max_tasks = _pick(args.max_tasks, run["max_tasks"])
    maturity = _pick(args.maturity, run["maturity"])
    task_retries = _pick(args.task_retries, run["task_retries"])
    goal_chains_per_node = _pick(args.goal_chains_per_node, run["goal_chains_per_node"])
    goal_max_steps = _pick(args.goal_max_steps, run["goal_max_steps"])
    unprefixed_sampling = _pick(args.unprefixed_sampling, run["unprefixed_sampling"])
    denylist = _pick(args.denylist, run["denylist"])
    headed = _pick(args.headed, run["headed"])
    predicate_sim = run["predicate_sim"]
    seg_axtree_sim = _pick(args.seg_axtree_sim, run["seg_axtree_sim"])
    mine_hrefs = _pick(args.mine_hrefs, run["mine_hrefs"])
    per_template_cap = _pick(args.per_template_cap, run["per_template_cap"])
    reached_template_cap = _pick(args.reached_template_cap, run["reached_template_cap"])
    seed_capability_repeats = run["seed_capability_repeats"]
    max_hrefs_per_page = _pick(args.max_hrefs_per_page, run["max_hrefs_per_page"])
    # dry-run turns the seed on so --dry-run exercises the seed->GOAL path end-to-end
    use_site_seed = True if args.dry_run else run["use_site_seed"]
    # `verify_goals` is the pre-rename key: honour it so an older config.yaml
    # doesn't silently turn episode verification OFF.
    verify_episodes = (True if args.dry_run
                       else run.get("verify_episodes", run.get("verify_goals", False)))
    plan_subgoals = True if args.dry_run else run["plan_subgoals"]

    if args.dry_run:
        root_url = args.root_url or "http://shop/home"
        allow = _pick(args.allow, run["allow"]) or _default_allow_pattern(root_url)
        terminal_goal = "order_confirmed"                # fake browser reaches success
        llm, embedder = _DryLLM(), HashingEmbedder()
        agent_llms = {role: llm for role in AGENT_ROLES}
        # vision=True for page_explorer/solver exercises the full capture/attach/
        # persist wiring against _FakeBrowser's stub screenshot, no API key needed.
        agent_vision = {role: {"vision": role in ("page_explorer", "solver"),
                                "som": True, "image_detail": "low"}
                        for role in AGENT_ROLES}
        browser_factory = lambda url: _FakeBrowser(url)
    else:
        from hsge.backends import STEmbedder
        from hsge.webarena import predicates
        from hsge.webarena.auth import ensure_login
        from hsge.webarena.browser import WebArenaBrowser
        # root URL: explicit --root-url/config, else resolve WA_<SITE> from .env
        site = args.site or run["site"]
        root_url = args.root_url or run["root_url"]
        if not root_url:
            root_url = os.environ.get(f"WA_{site.upper()}") if site else None
        if not root_url:
            ap.error("no start URL: set --root-url, run.root_url, or --site/run.site + WA_<SITE> in .env")
        allow = _pick(args.allow, run["allow"]) or _default_allow_pattern(root_url)

        success_url_re = _pick(args.success_url_re, run["success_url_re"])
        if success_url_re:
            predicates.configure_terminal(success_url_re)
        # terminal goal: explicit config wins; else auto (shopping has a checker, others
        # are exploration-only). A custom success-url-re also implies order_confirmed.
        terminal_goal = run["terminal_goal"]
        if terminal_goal is None and (success_url_re or site == "shopping"):
            terminal_goal = "order_confirmed"
        full_reset_url = _pick(args.full_reset_url, run["full_reset_url"]) or os.environ.get("WA_FULL_RESET")
        auth_dir = ".auth"
        if full_reset_url:
            perform_full_reset(full_reset_url)
            # a full reset reseeds the instance's DB, which can invalidate a
            # previously-cached session -- force ensure_login to log in fresh.
            stale = os.path.join(auth_dir, f"{site}_state.json")
            if site and os.path.exists(stale):
                os.remove(stale)

        agent_llms = _resolve_agent_llms(args, llm_cfg)
        agent_vision = _resolve_agent_vision(llm_cfg)
        llm = agent_llms["page_explorer"]  # backwards-compatible runtime fallback
        embedder = STEmbedder(emb_cfg["model"])
        auth_path = ensure_login(site, root_url, auth_dir=auth_dir, headless=not headed) if site else None
        browser_factory = lambda url: WebArenaBrowser(url, headless=not headed, storage_state=auth_path)

    explorer = WebArenaExplorer(
        browser_factory=browser_factory, llm=llm, embedder=embedder, out_dir=out_dir,
        allow_pattern=allow, deny_pattern=denylist, max_depth=max_depth,
        max_nodes=max_nodes, max_steps=max_steps, max_tasks=max_tasks, maturity=maturity,
        terminal_goal=terminal_goal, predicate_sim=predicate_sim, seg_axtree_sim=seg_axtree_sim,
        read_only=args.read_only,
        mine_hrefs=mine_hrefs, per_template_cap=per_template_cap,
        reached_template_cap=reached_template_cap,
        seed_capability_repeats=seed_capability_repeats,
        max_hrefs_per_page=max_hrefs_per_page, task_retries=task_retries,
        goal_chains_per_node=goal_chains_per_node,
        use_site_seed=use_site_seed, goal_max_steps=goal_max_steps,
        unprefixed_sampling=unprefixed_sampling,
        verify_episodes=verify_episodes, plan_subgoals=plan_subgoals,
        agent_llms=agent_llms, agent_vision=agent_vision,
    )
    if resume_ckpt:
        explorer.load_checkpoint(resume_ckpt)
        print(f"[resume] restored from {resume_ckpt}: "
              f"{len(explorer.library.all_skills())} skills, "
              f"{len(explorer.opgraph.ops)} operators")
    explorer.run(root_url)
    print("\nnext: python build_sft_dataset.py", os.path.join(out_dir, "episodes"), "train.jsonl")


if __name__ == "__main__":
    main()
