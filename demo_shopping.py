"""HSGE in the SHOPPING domain, end-to-end.

Unlike demo_purchase.py (planning only), this builds an executable mock store and
runs the full loop: plan a purchase chain over the skill graph, EXECUTE it through
the environment, and VERIFY it at the order-confirmation terminal state. This is
exactly the long-horizon trajectory a flat/affordance-enumeration pipeline never
produces.

    python demo_shopping.py
"""
from __future__ import annotations

from hsge.env import PageState, WebEnv
from hsge.operators import Operator, OperatorGraph, plan


# --------------------------------------------------------------------------- #
# 1. The store: home -> results -> product -> cart -> checkout -> payment ->
#    confirmation (the terminal/goal page). sort/filter are lateral dead-ends.
# --------------------------------------------------------------------------- #
def build_store() -> WebEnv:
    pages = {
        "home":     PageState("/shop/home", ["search_box", "search_btn"], {"search_btn": "results"}),
        "results":  PageState("/shop/catalogsearch/result", ["product_link", "sort", "filter"], {"product_link": "product"}),
        "product":  PageState("/shop/product", ["add_cart_btn", "qty"], {"add_cart_btn": "cart"}),
        "cart":     PageState("/shop/checkout/cart", ["checkout_btn", "remove"], {"checkout_btn": "checkout"}),
        "checkout": PageState("/shop/checkout", ["address", "shipping_next"], {"shipping_next": "payment"}),
        "payment":  PageState("/shop/checkout/payment", ["card", "place_order_btn"], {"place_order_btn": "confirmation"}),
        "confirmation": PageState("/shop/checkout/onepage/success", ["order_number"], {}),
    }
    return WebEnv("shop", pages, start="home", goal_pages={"confirmation"})


# --------------------------------------------------------------------------- #
# 2. The skills (in the real system these are DISCOVERED + VERIFIED from
#    sub-trajectories; here we specify their pre/effects and the action that
#    advances the page, so the plan is executable).
# --------------------------------------------------------------------------- #
SKILLS = [
    Operator("search",        frozenset(),                    frozenset({"results_shown"})),
    Operator("open_product",  frozenset({"results_shown"}),   frozenset({"item_selected", "on_product"})),
    Operator("add_to_cart",   frozenset({"item_selected"}),   frozenset({"cart_nonempty", "on_cart"})),
    Operator("checkout",      frozenset({"cart_nonempty"}),   frozenset({"on_checkout"})),
    Operator("enter_payment", frozenset({"on_checkout"}),     frozenset({"payment_entered", "on_payment"})),
    Operator("place_order",   frozenset({"payment_entered"}), frozenset({"order_confirmed"}), terminal=True),
    # lateral skills that DON'T advance toward purchase (the search/sort/filter trap):
    Operator("sort_results",  frozenset({"results_shown"}),   frozenset({"results_shown"})),
    Operator("filter_results",frozenset({"results_shown"}),   frozenset({"results_shown"})),
]

# how each skill advances the store (the grounded click that fires the goto)
ADVANCE = {
    "search": "click [search_btn]", "open_product": "click [product_link]",
    "add_to_cart": "click [add_cart_btn]", "checkout": "click [checkout_btn]",
    "enter_payment": "click [shipping_next]", "place_order": "click [place_order_btn]",
}


def main():
    store = build_store()
    g = OperatorGraph()
    for op in SKILLS:
        g.add(op)

    print("=" * 70)
    print("1) skill graph (edges derived from precondition/effect matching)")
    print("=" * 70)
    for a, b in g.edges():
        print(f"     {a:14s} -> {b}")

    print("\n" + "=" * 70)
    print("2) plan a PURCHASE: goal predicate = order_confirmed")
    print("=" * 70)
    chain = plan(g, frozenset(), "order_confirmed")
    print("   task chain:", " -> ".join(chain))
    print("   (sort/filter excluded: they don't change state, so the shortest plan skips them)")

    print("\n" + "=" * 70)
    print("3) EXECUTE the plan through the store and VERIFY at the terminal state")
    print("=" * 70)
    store.reset()
    print(f"   start: {store.state().url}")
    for skill in chain:
        store.step(ADVANCE[skill])
        print(f"   {skill:14s} -> {store.state().url}")
    success = store.check("order_confirmed")
    print(f"\n   terminal check (order_confirmed): {success}")
    print(f"   reward = {1.0 if success else 0.0}   (programmatic, not self-reported)")

    print("\n" + "=" * 70)
    print("4) curriculum: same planner, deeper goals = harder tasks")
    print("=" * 70)
    for goal, label in [("results_shown", "EASY"), ("cart_nonempty", "MEDIUM"),
                        ("on_checkout", "HARD"), ("order_confirmed", "PURCHASE")]:
        p = plan(g, frozenset(), goal)
        print(f"   [{label:8s}] difficulty {len(p)}: {' -> '.join(p)}")

    print("\n" + "=" * 70)
    print("5) contrast: a flat/affordance proposer on the results page")
    print("=" * 70)
    print("   would propose only local atoms: search / sort_results / filter_results,")
    print("   each 'complete' on its own page -> trajectory stops at results, never")
    print("   reaching checkout. That is the behavior in your sample_trajectory.json.")


if __name__ == "__main__":
    main()
