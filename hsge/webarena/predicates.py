"""State abstraction for WebArena (shopping / OneStopShop): map a page to a small
fixed predicate vocabulary, and define terminal-goal checkers. URL rules are
primary; AXTree keyword cues cover what URLs can't (e.g. a non-empty cart).
"""
from __future__ import annotations

import re

PREDICATES = frozenset({
    "results_shown", "item_selected", "cart_nonempty",
    "on_checkout", "payment_entered", "order_confirmed",
})


def predicates_from(url: str, axtree: str = "") -> set[str]:
    p: set[str] = set()
    ax = (axtree or "").lower()
    if re.search(r"/catalogsearch/result", url):
        p.add("results_shown")
    if re.search(r"/checkout/onepage/success|/checkout/success", url) or \
            "thank you for your purchase" in ax:
        p.add("order_confirmed")
    elif re.search(r"/checkout/cart", url):
        if re.search(r"\b[1-9]\d*\s+items?\s+in\s+cart|shopping cart\b", ax):
            p.add("cart_nonempty")
    elif re.search(r"/checkout", url):
        p.add("on_checkout")
    elif re.search(r"\.html(\?|$)", url) and "add to cart" in ax:
        p.update({"item_selected"})
    return p


TERMINALS = {
    "order_confirmed": dict(url=r"/checkout/onepage/success|/checkout/success",
                            text="thank you for your purchase"),
    "results_shown":   dict(url=r"/catalogsearch/result", text=None),
    "cart_nonempty":   dict(url=r"/checkout/cart", text=None),
    "on_checkout":     dict(url=r"/checkout(?!/cart)", text=None),
}


def configure_terminal(success_url_re: str, text: str | None = None) -> None:
    """Override the success-URL regex (and optional required text) for `order_confirmed`.

    WebArena instances may land checkout on a non-default success URL; point the
    terminal checker at it without editing code. `text` defaults to None so matching
    is URL-only (a custom instance may not show the default confirmation phrase);
    pass a phrase to also require it.
    """
    TERMINALS["order_confirmed"]["url"] = success_url_re
    TERMINALS["order_confirmed"]["text"] = text


def reached(goal: str, url: str, axtree: str = "") -> bool:
    spec = TERMINALS.get(goal)
    if not spec:
        return goal in predicates_from(url, axtree)
    ok = bool(re.search(spec["url"], url))
    if spec["text"]:
        ok = ok and spec["text"] in (axtree or "").lower()
    return ok
