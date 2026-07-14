"""PredicateRegistry usage counts + vocabulary() selection (frequent + recent
mix, so the induction prompt keeps both the core vocabulary and new concepts).

Run:  python -m pytest hsge/tests/test_predicate_registry.py -q
 (or) PYTHONPATH=. python hsge/tests/test_predicate_registry.py
"""
from hsge.llm import HashingEmbedder
from hsge.predicate_registry import PredicateRegistry


def _registry():
    return PredicateRegistry(HashingEmbedder(), sim_threshold=0.99)


def test_counts_increment_per_canonical_call():
    reg = _registry()
    reg.canonical("the cart is empty")
    reg.canonical("the cart is empty")          # same text -> same cluster
    reg.canonical("search results are shown")

    assert reg.counts[0] == 2
    assert reg.counts[1] == 1


def test_vocabulary_orders_frequent_first_then_recent():
    reg = _registry()
    reg.canonical("alpha predicate")            # p0, used 3x
    reg.canonical("alpha predicate")
    reg.canonical("alpha predicate")
    reg.canonical("beta predicate")             # p1, used 1x
    reg.canonical("gamma predicate")            # p2, used 1x (most recent)

    vocab = reg.vocabulary(max_frequent=1, max_recent=1)

    assert vocab == ["alpha predicate", "gamma predicate"]


def test_vocabulary_dedupes_when_frequent_is_also_recent():
    reg = _registry()
    reg.canonical("only predicate")
    reg.canonical("only predicate")

    vocab = reg.vocabulary(max_frequent=25, max_recent=25)

    assert vocab == ["only predicate"]


def test_vocabulary_caps_total_size():
    reg = _registry()
    for i in range(10):
        reg.canonical(f"predicate number {i} entirely unique wording {i}")

    vocab = reg.vocabulary(max_frequent=3, max_recent=3)

    assert len(vocab) == 6


def test_vocabulary_empty_registry_returns_empty_list():
    assert _registry().vocabulary() == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
