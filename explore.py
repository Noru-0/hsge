"""Run the HSGE exploration loop (mock).

This mirrors the structure of a real frontier loop so it doubles as a wiring
reference: expand a frontier of pages, discover a skill (operator) at each
transition, grow the hierarchical skill graph, then -- once the graph can reach
a terminal goal -- propose and execute a GOAL-CONDITIONED composed task and
collect the resulting long-horizon trajectory.

    python explore.py

In the real system, replace the mock store with BrowserGym/WebArena and the
WebArena runtime's PageExplorer + Solver; the loop shape is the same.
"""
from __future__ import annotations

from collections import deque

from hsge.env import PageState, WebEnv
from hsge.operators import Operator, OperatorGraph, plan


def build_store() -> WebEnv:
    pages = {
        "home":     PageState("/shop/home", ["search_box", "search_btn"], {"search_btn": "results"}),
        "results":  PageState("/shop/catalogsearch/result", ["product_link", "sort"], {"product_link": "product"}),
        "product":  PageState("/shop/product", ["add_cart_btn"], {"add_cart_btn": "cart"}),
        "cart":     PageState("/shop/checkout/cart", ["checkout_btn"], {"checkout_btn": "checkout"}),
        "checkout": PageState("/shop/checkout", ["shipping_next"], {"shipping_next": "payment"}),
        "payment":  PageState("/shop/checkout/payment", ["place_order_btn"], {"place_order_btn": "confirmation"}),
        "confirmation": PageState("/shop/checkout/onepage/success", ["order_number"], {}),
    }
    return WebEnv("shop", pages, start="home", goal_pages={"confirmation"})


# page -> (skill name, preconditions, effects, advancing affordance, terminal?)
TRANSITIONS = {
    "home":     ("search",        frozenset(),                    frozenset({"results_shown"}),   "search_btn",     False),
    "results":  ("open_product",  frozenset({"results_shown"}),   frozenset({"item_selected"}),   "product_link",   False),
    "product":  ("add_to_cart",   frozenset({"item_selected"}),   frozenset({"cart_nonempty"}),   "add_cart_btn",   False),
    "cart":     ("checkout",      frozenset({"cart_nonempty"}),   frozenset({"on_checkout"}),     "checkout_btn",   False),
    "checkout": ("enter_payment", frozenset({"on_checkout"}),     frozenset({"payment_entered"}), "shipping_next",  False),
    "payment":  ("place_order",   frozenset({"payment_entered"}), frozenset({"order_confirmed"}), "place_order_btn",True),
}


def main():
    store = build_store()
    opgraph = OperatorGraph()
    advance = {}                       # skill name -> "click [aff]"
    frontier = deque(["home"])
    visited = set()

    print("=" * 68)
    print("PHASE 1 - frontier exploration: discover a skill at each transition")
    print("=" * 68)
    while frontier:
        node = frontier.popleft()
        if node in visited:
            continue
        visited.add(node)
        page = store.pages[node]
        print(f"  visit {node:11s} ({page.url})")
        if node in TRANSITIONS:
            name, pre, eff, aff, terminal = TRANSITIONS[node]
            opgraph.add(Operator(name, pre, eff, terminal=terminal))
            advance[name] = f"click [{aff}]"
            child = page.goto[aff]
            print(f"      discovered skill '{name}'  pre={sorted(pre) or '[]'} eff={sorted(eff)}")
            if child not in visited:
                frontier.append(child)

    print(f"\n  skills discovered: {len(opgraph.ops)}")
    print("  high-level edges:")
    for a, b in opgraph.edges():
        print(f"      {a} -> {b}")

    print("\n" + "=" * 68)
    print("PHASE 2 - goal-conditioned episode: plan + execute a composed task")
    print("=" * 68)
    chain = plan(opgraph, frozenset(), "order_confirmed")
    if not chain:
        print("  no plan to order_confirmed yet (need more discovery)"); return
    print(f"  proposed [GOAL] task chain: {' -> '.join(chain)}")

    # solve it: execute through the store, collecting the trajectory
    store.reset()
    trajectory = []
    for skill in chain:
        store.step(advance[skill])
        trajectory.append({"skill": skill, "url": store.state().url})
    verified = store.check("order_confirmed")

    print("\n  collected trajectory (this is the training-worthy episode):")
    for t in trajectory:
        print(f"      {t['skill']:14s} -> {t['url']}")
    print(f"\n  terminal verification (order_confirmed): {verified}")
    print(f"  reward = {1.0 if verified else 0.0}  ->  "
          f"{'kept for SFT (build_sft_dataset.py)' if verified else 'discarded'}")

    print("\n" + "=" * 68)
    print("loop summary")
    print("=" * 68)
    print(f"  pages explored        : {len(visited)}")
    print(f"  skills discovered     : {len(opgraph.ops)}")
    print(f"  composed episodes     : 1 (a full purchase)")
    print("  In the WebArena runtime, PHASE 1 = PageExplorer + Solver + Discovery,")
    print("  PHASE 2 = planner-composed goal task + Solver + terminal verification.")


if __name__ == "__main__":
    main()
