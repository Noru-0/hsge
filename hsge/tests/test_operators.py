"""OperatorGraph.all_chains: bounded enumeration of composable operator
chains over effect->precondition edges. min_len gates shallow graphs,
max_len/max_paths are circuit breakers for densely connected graphs
(unbounded simple-path enumeration is O(V!) in the worst case).

Run:  python -m pytest hsge/tests/test_operators.py -q
 (or) PYTHONPATH=. python hsge/tests/test_operators.py
"""
from hsge.operators import Operator, OperatorGraph


def _graph(*ops):
    g = OperatorGraph()
    for op in ops:
        g.add(op)
    return g


def test_linear_chain_enumerated_with_prefixes():
    g = _graph(
        Operator("search", frozenset(), frozenset({"results"})),
        Operator("open_item", frozenset({"results"}), frozenset({"item_open"})),
        Operator("add_cart", frozenset({"item_open"}), frozenset({"in_cart"})),
    )

    chains = g.all_chains(min_len=2)

    assert ["search", "open_item"] in chains
    assert ["open_item", "add_cart"] in chains
    assert ["search", "open_item", "add_cart"] in chains


def test_min_len_excludes_single_operators():
    g = _graph(
        Operator("a", frozenset(), frozenset({"x"})),
        Operator("b", frozenset({"x"}), frozenset({"y"})),
    )

    assert all(len(c) >= 2 for c in g.all_chains(min_len=2))


def test_disconnected_graph_yields_no_chains():
    g = _graph(
        Operator("a", frozenset({"p"}), frozenset({"q"})),
        Operator("b", frozenset({"r"}), frozenset({"s"})),
    )

    assert g.all_chains(min_len=2) == []


def test_cycle_is_safe_and_terminates():
    g = _graph(
        Operator("a", frozenset({"y"}), frozenset({"x"})),
        Operator("b", frozenset({"x"}), frozenset({"y"})),
    )

    chains = g.all_chains(min_len=2)

    assert ["a", "b"] in chains and ["b", "a"] in chains
    assert all(len(set(c)) == len(c) for c in chains)   # simple paths only


def test_max_len_stops_descent():
    ops = [Operator(f"op{i}", frozenset({f"p{i}"}) if i else frozenset(),
                    frozenset({f"p{i+1}"})) for i in range(8)]
    g = _graph(*ops)

    chains = g.all_chains(min_len=2, max_len=3)

    assert max(len(c) for c in chains) == 3


def test_max_paths_bounds_result_count():
    ops = [Operator(f"op{i}", frozenset({f"p{i}"}) if i else frozenset(),
                    frozenset({f"p{i+1}"})) for i in range(8)]
    g = _graph(*ops)

    assert len(g.all_chains(min_len=2, max_paths=3)) == 3


def test_deterministic_ordering():
    g = _graph(
        Operator("z_first", frozenset(), frozenset({"m"})),
        Operator("a_second", frozenset({"m"}), frozenset({"n"})),
    )

    assert g.all_chains(min_len=2) == g.all_chains(min_len=2)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
