"""Tests for segmentation v2: candidate boundaries, LLM cut-point protocol,
trivial-nav safety net.

Run:  python -m pytest hsge/tests/test_segmentation.py -q
 (or) PYTHONPATH=. python hsge/tests/test_segmentation.py
"""
from hsge.llm import MockLLM
from hsge.schema import Step
from hsge.segmentation import (
    _axtree_similarity, _candidate_boundaries, _spans_from_cuts, segment_trajectory,
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


class ScriptedLLM:
    """Returns one canned JSON response, whatever the prompt."""
    def __init__(self, response):
        self.response = response

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return self.response


def _login_steps():
    # candidates: URL change at index 2 only (axtrees empty -> axtree signal off)
    return [Step("type [user] a", "/login"), Step("type [pwd] b", "/login"),
            Step("click [go]", "/home"), Step("type [q] x", "/home")]


def test_llm_merge_is_trusted():
    llm = ScriptedLLM({"segments": [{"span": [0, 4], "subgoal": "log in and search"}]})
    subs = segment_trajectory(llm, _login_steps(), "site", "task")
    assert len(subs) == 1
    assert subs[0].subgoal == "log in and search"
    assert len(subs[0].steps) == 4


def test_llm_split_is_trusted():
    llm = ScriptedLLM({"segments": [
        {"span": [0, 1], "subgoal": "enter username"},
        {"span": [1, 4], "subgoal": "finish login and search"},
    ]})
    subs = segment_trajectory(llm, _login_steps(), "site", "task")
    assert [len(s.steps) for s in subs] == [1, 3]
    assert subs[0].subgoal == "enter username"


def test_invalid_cuts_dropped_individually():
    llm = ScriptedLLM({"segments": [
        {"span": [0, 2], "subgoal": "log in"},
        {"span": [99, 100], "subgoal": "out of range"},      # dropped alone
        {"span": ["x", 4], "subgoal": "not an int"},         # dropped alone
        {"span": [2, 4], "subgoal": "search"},
    ]})
    subs = segment_trajectory(llm, _login_steps(), "site", "task")
    assert [len(s.steps) for s in subs] == [2, 2]
    assert [s.subgoal for s in subs] == ["log in", "search"]


def test_garbage_falls_back_to_candidates():
    subs = segment_trajectory(ScriptedLLM({}), _login_steps(), "site", "task",
                              subgoal_hints=["log in", "search"])
    assert [len(s.steps) for s in subs] == [2, 2]
    assert [s.subgoal for s in subs] == ["log in", "search"]


def test_mockllm_reproduces_old_url_boundary_behavior():
    subs = segment_trajectory(MockLLM(), _login_steps(), "site", "task",
                              subgoal_hints=["log in", "search"])
    assert [len(s.steps) for s in subs] == [2, 2]
    assert [s.subgoal for s in subs] == ["log in", "search"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
