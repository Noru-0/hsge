"""Show how the operator model makes a PURCHASE trajectory appear.

Run: python demo_purchase.py

Contrast with the flat pipeline, which only ever emits the atomic tasks
(search / sort / filter) because nothing composes them toward a goal state.
"""
from __future__ import annotations

from hsge.curriculum import generate_curriculum_from_operators
from hsge.operators import Operator, OperatorGraph

# These 7 skills are exactly what online discovery would abstract from
# sub-trajectories on a shopping site. Here we hand-specify their pre/effects;
# in the full system the LLM induces preconditions/effects during abstraction.
SHOPPING = [
    Operator("search",        frozenset(),                       frozenset({"results_shown"})),
    Operator("open_product",  frozenset({"results_shown"}),      frozenset({"item_selected", "on_product"})),
    Operator("add_to_cart",   frozenset({"item_selected"}),      frozenset({"cart_nonempty"})),
    Operator("view_cart",     frozenset({"cart_nonempty"}),      frozenset({"on_cart"})),
    Operator("checkout",      frozenset({"cart_nonempty"}),      frozenset({"on_checkout"})),
    Operator("enter_payment", frozenset({"on_checkout"}),        frozenset({"payment_entered"})),
    Operator("place_order",   frozenset({"payment_entered"}),    frozenset({"order_confirmed"}), terminal=True),
    # a couple of page-local atoms that DON'T advance toward purchase:
    Operator("sort_results",  frozenset({"results_shown"}),      frozenset({"results_shown"})),
    Operator("filter_results",frozenset({"results_shown"}),      frozenset({"results_shown"})),
]


def main():
    g = OperatorGraph()
    for op in SHOPPING:
        g.add(op)

    print("=" * 72)
    print("graph.py's job: derive skill->skill edges from effect/precondition match")
    print("=" * 72)
    for a, b in g.edges():
        share = sorted(g.ops[a].effects & g.ops[b].preconditions)
        print(f"  {a:14s} -> {b:14s}   (because {a} establishes {share})")
    print(f"\n  terminal (goal) predicates: {sorted(g.goal_predicates)}")

    print("\n" + "=" * 72)
    print("curriculum.py's job: plan from start to a goal predicate -> the task")
    print("=" * 72)
    initial = frozenset()        # fresh page, nothing established yet
    tasks = generate_curriculum_from_operators(
        g,
        initial_predicates=initial,
        goal_predicates={
            "results_shown", "cart_nonempty", "on_checkout", "order_confirmed",
        },
    )
    for task in tasks:
        label = "TERMINAL" if task.terminal else "INTERMEDIATE"
        chain = " -> ".join(task.skill_chain)
        print(f"  [{label}] goal={task.goal_predicate:16s} difficulty={task.difficulty}")
        print(f"             task chain: {chain}")

    print("\n" + "=" * 72)
    print("WHY the purchase appears (and why the flat pipeline never produces it)")
    print("=" * 72)
    print("  place_order needs {payment_entered}; the ONLY producer is enter_payment,")
    print("  which needs {on_checkout} <- checkout <- {cart_nonempty} <- add_to_cart")
    print("  <- {item_selected} <- open_product <- {results_shown} <- search.")
    print("  The goal predicate pulls the whole chain into existence. Bottom-up")
    print("  affordance enumeration has no goal, so it stops at 'search' / 'sort'.")


if __name__ == "__main__":
    main()
