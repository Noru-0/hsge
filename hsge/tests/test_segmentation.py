"""Tests for segmentation v2: candidate boundaries, LLM cut-point protocol,
trivial-nav safety net.

Run:  python -m pytest hsge/tests/test_segmentation.py -q
 (or) PYTHONPATH=. python hsge/tests/test_segmentation.py
"""
from hsge.schema import Step
from hsge.segmentation import (
    _axtree_similarity, _candidate_boundaries, _spans_from_cuts,
)

AX_A = "RootWebArea 'Home'\n[1] link 'Forums'\n[2] link 'Wiki'"
AX_B = "RootWebArea 'Forum'\n[10] heading 'AskReddit'\n[11] article 'post'"


def test_similarity_identical():
    assert _axtree_similarity(AX_A, AX_A) == 1.0


def test_similarity_disjoint():
    assert _axtree_similarity(AX_A, AX_B) == 0.0


def test_similarity_unavailable_when_empty():
    assert _axtree_similarity("", AX_A) is None
    assert _axtree_similarity(AX_A, "") is None


def test_candidates_url_change_only():
    steps = [Step("click [a]", "/login"), Step("click [b]", "/login"),
             Step("click [c]", "/home")]
    assert _candidate_boundaries(steps, 0.6) == [2]


def test_candidates_axtree_drop_same_url():
    steps = [Step("click [a]", "/app", axtree=AX_A),
             Step("click [b]", "/app", axtree=AX_A),
             Step("click [c]", "/app", axtree=AX_B)]
    assert _candidate_boundaries(steps, 0.6) == [2]


def test_candidates_axtree_signal_off_when_missing():
    steps = [Step("click [a]", "/app"), Step("click [b]", "/app")]
    assert _candidate_boundaries(steps, 0.6) == []


def test_spans_from_cuts():
    assert _spans_from_cuts([], 3) == [(0, 3)]
    assert _spans_from_cuts([1, 2], 3) == [(0, 1), (1, 2), (2, 3)]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
