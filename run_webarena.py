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

import yaml

from hsge.llm import HashingEmbedder, MockLLM
from hsge.webarena.runtime import WebArenaExplorer


# Built-in defaults; config.yaml overrides these, CLI flags override config.yaml.
DEFAULTS = {
    "run": {"site": "shopping", "root_url": None, "out_dir": "outputs/wa_run",
            "allow": None, "denylist": r"logout|\?p=|product_list_|[?&]sort=",
            "max_nodes": 15, "max_depth": 6, "max_steps": 15, "maturity": 2,
            "headed": False, "success_url_re": None, "full_reset_url": None},
    "llm": {"provider": None, "model": None, "base_url": None, "temperature": 0.2},
    "embedder": {"model": "all-MiniLM-L6-v2"},
}


def _load_config(path: str | None) -> dict:
    """Merge config.yaml (if present) onto DEFAULTS, section by section."""
    cfg = copy.deepcopy(DEFAULTS)
    if path and os.path.exists(path):
        loaded = yaml.safe_load(open(path)) or {}
        for section in cfg:
            cfg[section].update(loaded.get(section) or {})
    return cfg


def _pick(cli_val, cfg_val):
    """CLI wins when the user passed it (not None), else fall back to config."""
    return cli_val if cli_val is not None else cfg_val


# --------------------------- dry-run fakes --------------------------------- #
class _DryLLM(MockLLM):
    """Scripted LLM for the dry run. Delegates segmentation/abstraction to MockLLM
    (deterministic) and only scripts the explorer, the solver, and operator
    induction. The solver walks the fake purchase all the way to the success page
    so Discovery admits skills that then become operators, including a terminal one.
    """
    def complete_json(self, system: str, prompt: str) -> dict:
        if system.startswith("PROPOSE"):                        # explorer
            return {"tasks": ["search for an item", "add an item to cart"]}
        if "web agent" in system.lower():                       # solver
            if "thank you for your purchase" in prompt.lower():  # goal page -> finish
                return {"thought": "done", "action": "send_msg_to_user('done')"}
            return {"thought": "advance", "action": "click('1')"}
        if "PLANNING OPERATOR" in system:                       # operator induction
            return self._induce(prompt)
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
    def close(self): pass


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


def _resolve_llm(cli, llm_cfg):
    """Pick provider (CLI > config > $LLM_PROVIDER > openai) and resolve its
    model/base_url/api_key from .env, e.g. DEEPSEEK_API_KEY/_BASE_URL/_MODEL."""
    provider = (cli.provider or llm_cfg.get("provider")
                or os.environ.get("LLM_PROVIDER") or "openai").lower()
    p = provider.upper()
    model = cli.model or llm_cfg.get("model") or os.environ.get(f"{p}_MODEL")
    base_url = cli.base_url or llm_cfg.get("base_url") or os.environ.get(f"{p}_BASE_URL")
    api_key = os.environ.get(f"{p}_API_KEY")
    from hsge.backends import OpenAILLM
    print(f"[llm] provider={provider} model={model} base_url={base_url or '(default)'}")
    return OpenAILLM(model=model, base_url=base_url, api_key=api_key,
                     temperature=float(llm_cfg.get("temperature", 0.2)))


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
    ap.add_argument("--maturity", type=int, default=None)
    ap.add_argument("--provider", default=None, help="openai | deepseek")
    ap.add_argument("--model", default=None, help="LLM model id (e.g. gpt-4o-mini, deepseek-chat)")
    ap.add_argument("--base-url", default=None, help="OpenAI-compatible base URL")
    ap.add_argument("--headed", action="store_const", const=True, default=None,
                    help="run browser headed (for debugging)")
    ap.add_argument("--full-reset-url", default=None,
                    help="POST here once before exploring to reset WebArena state")
    ap.add_argument("--success-url-re", default=None,
                    help="override the order_confirmed success-URL regex")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = _load_config(args.config)
    run, llm_cfg, emb_cfg = cfg["run"], cfg["llm"], cfg["embedder"]

    out_dir = _pick(args.out, run["out_dir"])
    max_nodes = _pick(args.max_nodes, run["max_nodes"])
    max_depth = _pick(args.max_depth, run["max_depth"])
    max_steps = _pick(args.max_steps, run["max_steps"])
    maturity = _pick(args.maturity, run["maturity"])
    denylist = _pick(args.denylist, run["denylist"])
    headed = _pick(args.headed, run["headed"])

    if args.dry_run:
        root_url = args.root_url or "http://shop/home"
        allow = _pick(args.allow, run["allow"]) or (re.escape(root_url.rsplit("/", 1)[0]) + ".*")
        llm, embedder = _DryLLM(), HashingEmbedder()
        browser_factory = lambda url: _FakeBrowser(url)
    else:
        from hsge.backends import STEmbedder
        from hsge.webarena import predicates
        from hsge.webarena.browser import WebArenaBrowser
        # root URL: explicit --root-url/config, else resolve WA_<SITE> from .env
        root_url = args.root_url or run["root_url"]
        if not root_url:
            site = args.site or run["site"]
            root_url = os.environ.get(f"WA_{site.upper()}") if site else None
        if not root_url:
            ap.error("no start URL: set --root-url, run.root_url, or --site/run.site + WA_<SITE> in .env")
        allow = _pick(args.allow, run["allow"]) or (re.escape(root_url.rsplit("/", 1)[0]) + ".*")

        success_url_re = _pick(args.success_url_re, run["success_url_re"])
        if success_url_re:
            predicates.configure_terminal(success_url_re)
        full_reset_url = _pick(args.full_reset_url, run["full_reset_url"]) or os.environ.get("WA_FULL_RESET")
        if full_reset_url:
            perform_full_reset(full_reset_url)

        llm = _resolve_llm(args, llm_cfg)
        embedder = STEmbedder(emb_cfg["model"])
        browser_factory = lambda url: WebArenaBrowser(url, headless=not headed)

    explorer = WebArenaExplorer(
        browser_factory=browser_factory, llm=llm, embedder=embedder, out_dir=out_dir,
        allow_pattern=allow, deny_pattern=denylist, max_depth=max_depth,
        max_nodes=max_nodes, max_steps=max_steps, maturity=maturity,
    )
    explorer.run(root_url)
    print("\nnext: python build_sft_dataset.py", os.path.join(out_dir, "episodes"), "train.jsonl")


if __name__ == "__main__":
    main()
