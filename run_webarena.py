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
"""
from __future__ import annotations

import argparse
import os
import re


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


# --------------------------- dry-run fakes --------------------------------- #
class _DryLLM(LLM):
    """Scripted LLM: proposes two tasks, advances one step then declares done."""
    def complete_json(self, system: str, prompt: str) -> dict:
        if system.startswith("PROPOSE"):
            return {"tasks": ["search for an item", "add an item to cart"]}
        if "web agent" in system.lower():                       # solver
            if "click('1')" in prompt:                          # already acted -> finish
                return {"thought": "done", "action": "send_msg_to_user('done')"}
            return {"thought": "advance", "action": "click('1')"}
        return {}                                               # segment/abstract: no-op


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root-url", default="http://shop/home")
    ap.add_argument("--out", default="outputs/wa_run")
    ap.add_argument("--allow", default=None, help="regex of allowed child URLs")
    ap.add_argument("--max-nodes", type=int, default=15)
    ap.add_argument("--max-depth", type=int, default=6)
    ap.add_argument("--max-steps", type=int, default=15)

    # --- provider & model selection ---
    ap.add_argument("--provider", default=None,
                    choices=["deepseek", "openai", "custom"],
                    help="LLM provider preset (default: from LLM_PROVIDER env or 'openai')")
    ap.add_argument("--model", default=None,
                    help="Model for BOTH explorer & solver (shorthand, overridden by --explorer-model/--solver-model)")
    ap.add_argument("--explorer-model", default=None,
                    help="Model for PageExplorer (task proposal). Env: EXPLORER_MODEL")
    ap.add_argument("--solver-model", default=None,
                    help="Model for Solver (action planning). Env: SOLVER_MODEL")

    ap.add_argument("--headless", action="store_true", default=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

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

        explorer_llm = OpenAILLM(model=explorer_model, api_key=api_key, base_url=base_url)
        solver_llm = OpenAILLM(model=solver_model, api_key=api_key, base_url=base_url)
        embedder = STEmbedder()
        browser_factory = lambda url: WebArenaBrowser(url, headless=args.headless)

        print(f"[config] provider={provider}")
        print(f"[config] explorer model={explorer_model}")
        print(f"[config] solver   model={solver_model}")
        print(f"[config] base URL ={base_url}")

    explorer = WebArenaExplorer(
        browser_factory=browser_factory,
        explorer_llm=explorer_llm,
        solver_llm=solver_llm,
        embedder=embedder, out_dir=args.out,
        allow_pattern=allow, max_depth=args.max_depth, max_nodes=args.max_nodes,
        max_steps=args.max_steps,
    )
    explorer.run(args.root_url)
    print("\nnext: python build_sft_dataset.py", os.path.join(args.out, "episodes"), "train.jsonl")


if __name__ == "__main__":
    main()
