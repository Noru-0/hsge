"""_goal_task: depth-based chains are the primary goal source on every site
(attempted once per run, capped per node); the legacy terminal-predicate
plan is the backup when the graph is too shallow; reached()-verification
kicks back in exactly when a depth chain ends at a terminal operator.

Run:  python -m pytest hsge/tests/test_goal_task.py -q
 (or) PYTHONPATH=. python hsge/tests/test_goal_task.py
"""
import tempfile

from hsge.llm import HashingEmbedder, MockLLM
from hsge.operators import Operator
from hsge.webarena.runtime import WebArenaExplorer


def _explorer(terminal_goal=None, goal_chains_per_node=3):
    return WebArenaExplorer(
        browser_factory=lambda url: None, llm=MockLLM(),
        embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
        allow_pattern=".*", terminal_goal=terminal_goal,
        goal_chains_per_node=goal_chains_per_node)


def _add_chain_ops(ex, terminal_last=False):
    ex.opgraph.add(Operator("search", frozenset(), frozenset({"results"})))
    ex.opgraph.add(Operator("add_cart", frozenset({"results"}),
                            frozenset({"in_cart"}), terminal=terminal_last))
    ex._op_meta["search"] = {"card_name": "Search", "description": "search for an item",
                             "init_url": "http://shop/home"}
    ex._op_meta["add_cart"] = {"card_name": "AddToCart",
                               "description": "add the item to the cart",
                               "init_url": "http://shop/item.html"}


def test_shallow_graph_and_no_terminal_goal_yields_nothing():
    ex = _explorer(terminal_goal=None)
    ex.opgraph.add(Operator("lonely", frozenset({"p"}), frozenset({"q"})))

    assert ex._goal_task() == []


def test_shallow_graph_with_terminal_goal_falls_back_to_legacy_task():
    ex = _explorer(terminal_goal="order_confirmed")
    ex.opgraph.add(Operator("purchase", frozenset(),
                            frozenset({"confirmed"}), terminal=True))

    tasks = ex._goal_task()

    assert len(tasks) == 1
    assert tasks[0]["kind"] == "terminal"
    assert tasks[0]["goal_predicate"] == "order_confirmed"
    assert tasks[0]["goal"].startswith("Purchase an item")


def test_deep_graph_yields_depth_task_with_generated_instruction():
    ex = _explorer(terminal_goal=None)
    _add_chain_ops(ex)

    tasks = ex._goal_task()

    depth = [t for t in tasks if t["chain"] == ["search", "add_cart"]]
    assert len(depth) == 1
    t = depth[0]
    assert t["kind"] == "depth"
    assert t["goal_predicate"] is None                 # self-graded + judge
    assert t["difficulty"] == 2
    assert "http://shop/home" in t["goal"]             # init URL of first op
    assert "search for an item" in t["goal"]
    assert "add the item to the cart" in t["goal"]
    assert "Purchase an item" not in t["goal"]         # no hardcoded wording


def test_terminal_chain_end_restores_deterministic_verify():
    ex = _explorer(terminal_goal="order_confirmed")
    _add_chain_ops(ex, terminal_last=True)

    tasks = ex._goal_task()

    t = [t for t in tasks if t["chain"] == ["search", "add_cart"]][0]
    assert t["kind"] == "depth"
    assert t["goal_predicate"] == "order_confirmed"    # backup verify kicks in


def test_each_chain_attempted_once_per_run():
    ex = _explorer(terminal_goal=None)
    _add_chain_ops(ex)

    first = ex._goal_task()
    second = ex._goal_task()

    assert first                                       # emitted once...
    assert second == []                                # ...never again


def test_per_node_cap_defers_extra_chains_to_later_nodes():
    ex = _explorer(terminal_goal=None, goal_chains_per_node=1)
    _add_chain_ops(ex)
    # a third operator so the graph holds >1 distinct chain:
    # [search, add_cart], [add_cart, checkout], [search, add_cart, checkout]
    ex.opgraph.add(Operator("checkout", frozenset({"in_cart"}), frozenset({"ordered"})))
    ex._op_meta["checkout"] = {"card_name": "Checkout", "description": "check out",
                               "init_url": "http://shop/cart"}

    first = ex._goal_task()
    second = ex._goal_task()

    assert len(first) == 1
    assert len(second) >= 1                            # deferred, not lost
    assert first[0]["chain"] != second[0]["chain"]


# --- Task 4: seed capabilities as a top-down GOAL source ---------------------

def _seed(ex, caps):
    ex.site_seed = {"description": "d", "capabilities": caps}


def test_seed_capabilities_become_goal_tasks_when_no_chains():
    ex = _explorer(terminal_goal=None)          # empty operator graph -> no chains
    _seed(ex, [{"name": "checkout", "goal": "Buy a mouse and confirm the order."},
               {"name": "review", "goal": "Write a review for a purchased item."}])

    tasks = ex._goal_task()

    assert [t["kind"] for t in tasks] == ["seed", "seed"]
    assert tasks[0]["goal"] == "Buy a mouse and confirm the order."
    assert tasks[0]["goal_predicate"] is None
    assert tasks[0]["chain"] == ()


def test_seed_capabilities_attempted_once_per_run():
    ex = _explorer(terminal_goal=None)
    _seed(ex, [{"name": "checkout", "goal": "Buy a mouse and confirm the order."}])

    assert len(ex._goal_task()) == 1        # first node emits it
    assert ex._goal_task() == []            # second node: already attempted


def test_seed_respects_goal_chains_per_node_cap():
    ex = _explorer(terminal_goal=None, goal_chains_per_node=1)
    _seed(ex, [{"name": "a", "goal": "goal a"}, {"name": "b", "goal": "goal b"}])

    assert len(ex._goal_task()) == 1        # capped at 1 per node


def test_chains_take_precedence_over_seed_when_budget_is_tight():
    # budget = 1: the depth chain fills the single slot, so seed is excluded
    ex = _explorer(terminal_goal=None, goal_chains_per_node=1)
    _add_chain_ops(ex)                       # yields a depth chain
    _seed(ex, [{"name": "x", "goal": "seed goal"}])

    assert [t["kind"] for t in ex._goal_task()] == ["depth"]


def test_seed_fills_remaining_budget_after_chains():
    # budget = 3, one chain -> depth first, then seed fills the remaining slots
    ex = _explorer(terminal_goal=None, goal_chains_per_node=3)
    _add_chain_ops(ex)
    _seed(ex, [{"name": "x", "goal": "seed goal one"},
               {"name": "y", "goal": "seed goal two"}])

    kinds = [t["kind"] for t in ex._goal_task()]
    assert kinds[0] == "depth"               # chain taken first
    assert kinds.count("seed") == 2          # seed fills the remaining 2 slots


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
