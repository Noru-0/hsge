"""PredicateRegistry usage counts + vocabulary() selection (frequent + recent
mix, so the induction prompt keeps both the core vocabulary and new concepts).

Run:  python -m pytest hsge/tests/test_predicate_registry.py -q
 (or) PYTHONPATH=. python hsge/tests/test_predicate_registry.py
"""
import numpy as np

from hsge.llm import Embedder, HashingEmbedder
from hsge.predicate_registry import PredicateRegistry


def _registry():
    return PredicateRegistry(HashingEmbedder(), sim_threshold=0.99)


# --------------------------------------------------------------------------- #
# LLM adjudication in the borderline band (synonym canonicalization).
#
# The hashing embedder can't place two predicates at a chosen cosine, so these
# tests use a fixed-vector embedder to land a pair exactly inside / above /
# below the adjudication band and assert the merge/spawn decision.
# --------------------------------------------------------------------------- #
class _VecEmbedder(Embedder):
    """Maps preset predicate texts to preset unit vectors, so a test can place
    two predicates at an exact cosine similarity."""

    def __init__(self, mapping):
        self.mapping = mapping

    def encode(self, texts):
        return np.vstack([self.mapping[t] for t in texts]).astype(np.float32)


class _ScriptedAdjudicator:
    """Adjudication-call stub: returns a preset verdict, counts invocations."""

    def __init__(self, equivalent):
        self.equivalent = equivalent
        self.calls = 0

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls += 1
        return {"equivalent": self.equivalent}


class _ExplodingLLM:
    """Fails the test if adjudication is ever invoked (proves it stayed out of
    the band)."""

    def complete_json(self, *a, **k):
        raise AssertionError("adjudicator must not be called outside the band")


_A = np.array([1.0, 0.0], dtype=np.float32)
_BAND = np.array([0.6, 0.8], dtype=np.float32)                # cos(_A, _BAND) = 0.60
_HIGH = np.array([0.9, np.sqrt(1 - 0.81)], dtype=np.float32)  # cos = 0.90 (above band)
_LOW = np.array([0.2, np.sqrt(1 - 0.04)], dtype=np.float32)   # cos = 0.20 (below band)


def _adj_registry(mapping, llm):
    # sim_threshold 0.6 +/- default band 0.15 -> band [0.45, 0.75).
    return PredicateRegistry(_VecEmbedder(mapping), llm=llm, sim_threshold=0.6)


def test_band_pair_merges_when_adjudicator_says_equivalent():
    llm = _ScriptedAdjudicator(equivalent=True)
    reg = _adj_registry({"logged in": _A, "signed in": _BAND}, llm)

    p0 = reg.canonical("logged in")
    p1 = reg.canonical("signed in")

    assert p0 == p1                      # synonym collapsed onto one canonical id
    assert llm.calls == 1                # exactly one adjudication for the band pair


def test_band_pair_stays_split_when_adjudicator_says_not_equivalent():
    llm = _ScriptedAdjudicator(equivalent=False)
    reg = _adj_registry({"cart open": _A, "menu open": _BAND}, llm)

    assert reg.canonical("cart open") != reg.canonical("menu open")
    assert llm.calls == 1


def test_above_high_band_merges_without_calling_adjudicator():
    reg = _adj_registry({"a": _A, "b": _HIGH}, _ExplodingLLM())

    assert reg.canonical("a") == reg.canonical("b")   # would raise if adjudicated


def test_below_low_band_spawns_without_calling_adjudicator():
    reg = _adj_registry({"a": _A, "b": _LOW}, _ExplodingLLM())

    assert reg.canonical("a") != reg.canonical("b")


def test_llm_none_keeps_single_threshold_behaviour():
    # No adjudicator: a band-cosine pair (0.60) collapses iff sim >= sim_threshold,
    # exactly the old behaviour. At threshold 0.6, 0.60 >= 0.6 -> merge.
    reg = PredicateRegistry(_VecEmbedder({"a": _A, "b": _BAND}), sim_threshold=0.6)

    assert reg.canonical("a") == reg.canonical("b")


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
