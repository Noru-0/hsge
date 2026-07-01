"""Run HSGE exploration on WebArena.

REAL run (needs a hosted WebArena + keys; see docs/04_webarena_runbook.md):
    pip install browsergym-core browsergym-webarena sentence-transformers openai
    playwright install chromium
    export WA_SHOPPING="http://<host>:7770"   OPENAI_API_KEY=sk-...
    python run_webarena.py --root-url "$WA_SHOPPING" --out outputs/wa_run --max-nodes 15

DRY run (no browser, no network -- verifies the whole pipeline wiring):
    python run_webarena.py --dry-run --out /tmp/wa_dry
"""
from __future__ import annotations

import argparse
import os
import re

from hsge.llm import HashingEmbedder, MockLLM
from hsge.webarena.runtime import WebArenaExplorer


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


def main():
    _load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--root-url", default="http://shop/home")
    ap.add_argument("--out", default="outputs/wa_run")
    ap.add_argument("--allow", default=None, help="regex of allowed child URLs")
    ap.add_argument("--denylist", default=r"logout|\?p=|product_list_|[?&]sort=",
                    help="regex of blocked child URLs (denylist wins over allow)")
    ap.add_argument("--max-nodes", type=int, default=15)
    ap.add_argument("--max-depth", type=int, default=6)
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--maturity", type=int, default=2,
                    help="min times a skill must recur before it becomes an operator")
    ap.add_argument("--model", default=None, help="LLM model id (e.g. gpt-4o-mini, deepseek-chat)")
    ap.add_argument("--base-url", default=None,
                    help="OpenAI-compatible base URL (e.g. https://api.deepseek.com); "
                         "falls back to $OPENAI_BASE_URL")
    ap.add_argument("--headed", action="store_true", help="run browser headed (for debugging)")
    ap.add_argument("--full-reset-url", default=os.environ.get("WA_FULL_RESET") or None,
                    help="POST here once before exploring to reset WebArena state")
    ap.add_argument("--success-url-re", default=None,
                    help="override the order_confirmed success-URL regex")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    allow = args.allow or (re.escape(args.root_url.rsplit("/", 1)[0]) + ".*")

    if args.dry_run:
        llm, embedder = _DryLLM(), HashingEmbedder()
        browser_factory = lambda url: _FakeBrowser(url)
    else:
        from hsge.backends import OpenAILLM, STEmbedder
        from hsge.webarena import predicates
        from hsge.webarena.browser import WebArenaBrowser
        if args.success_url_re:
            predicates.configure_terminal(args.success_url_re)
        if args.full_reset_url:
            perform_full_reset(args.full_reset_url)
        llm = OpenAILLM(model=args.model, base_url=args.base_url)
        embedder = STEmbedder()
        browser_factory = lambda url: WebArenaBrowser(url, headless=not args.headed)

    explorer = WebArenaExplorer(
        browser_factory=browser_factory, llm=llm, embedder=embedder, out_dir=args.out,
        allow_pattern=allow, deny_pattern=args.denylist, max_depth=args.max_depth,
        max_nodes=args.max_nodes, max_steps=args.max_steps, maturity=args.maturity,
    )
    explorer.run(args.root_url)
    print("\nnext: python build_sft_dataset.py", os.path.join(args.out, "episodes"), "train.jsonl")


if __name__ == "__main__":
    main()
