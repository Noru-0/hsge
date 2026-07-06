"""verify_operator_grounding checks induced predicates against every
member's real boundary axtree, independent of the 2-member sample
induce_operator() itself uses for context."""

from hsge.operator_induction import verify_operator_grounding


class _StubLLM:
    def __init__(self, response):
        self._response = response
        self.last_prompt = None

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.last_prompt = prompt
        return self._response


def test_all_confirmed_across_all_members():
    llm = _StubLLM({
        "results": [
            {"predicate": "search results are shown", "type": "precondition",
             "member_holds": [True, True]},
            {"predicate": "an item is in the cart", "type": "effect",
             "member_holds": [True, True]},
        ]
    })
    boundary = [("before1", "after1"), ("before2", "after2")]

    out = verify_operator_grounding(
        llm, ["search results are shown"], ["an item is in the cart"], boundary)

    assert out == {
        "precondition_accuracy": {"search results are shown": 1.0},
        "effect_accuracy": {"an item is in the cart": 1.0},
        "member_count": 2,
    }


def test_mixed_confirmation_computes_fraction():
    llm = _StubLLM({
        "results": [
            {"predicate": "search results are shown", "type": "precondition",
             "member_holds": [True, False]},
        ]
    })
    boundary = [("before1", "after1"), ("before2", "after2")]

    out = verify_operator_grounding(llm, ["search results are shown"], [], boundary)

    assert out["precondition_accuracy"] == {"search results are shown": 0.5}
    assert out["member_count"] == 2


def test_missing_or_short_member_holds_counts_as_unconfirmed():
    llm = _StubLLM({
        "results": [
            {"predicate": "an item is in the cart", "type": "effect",
             "member_holds": [True]},  # only 1 entry for 3 members
        ]
    })
    boundary = [("b1", "a1"), ("b2", "a2"), ("b3", "a3")]

    out = verify_operator_grounding(llm, [], ["an item is in the cart"], boundary)

    assert out["effect_accuracy"] == {"an item is in the cart": 1 / 3}
    assert out["member_count"] == 3


def test_predicate_missing_from_response_defaults_to_zero():
    llm = _StubLLM({"results": []})
    boundary = [("b1", "a1")]

    out = verify_operator_grounding(llm, ["never mentioned"], ["also missing"], boundary)

    assert out["precondition_accuracy"] == {"never mentioned": 0.0}
    assert out["effect_accuracy"] == {"also missing": 0.0}
    assert out["member_count"] == 1


def test_empty_predicates_and_boundary_returns_zero_member_count():
    llm = _StubLLM({"results": []})

    out = verify_operator_grounding(llm, [], [], [])

    assert out == {"precondition_accuracy": {}, "effect_accuracy": {}, "member_count": 0}


def test_malformed_response_does_not_raise():
    llm = _StubLLM({"results": "not a list"})
    boundary = [("b1", "a1")]

    out = verify_operator_grounding(llm, ["p"], ["e"], boundary)

    assert out == {"precondition_accuracy": {"p": 0.0}, "effect_accuracy": {"e": 0.0},
                   "member_count": 1}
