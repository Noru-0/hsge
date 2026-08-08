"""_promote_skill_to_operator: vocabulary-aware induction wiring, the
eff - pre anti-tautology gate, and _op_meta recording for goal-task
instruction generation.

Run:  python -m pytest hsge/tests/test_operator_promotion.py -q
 (or) PYTHONPATH=. python hsge/tests/test_operator_promotion.py
"""
import json
import os
import tempfile

from hsge.llm import HashingEmbedder, MockLLM
from hsge.schema import SkillCard, Step, SubTrajectory
from hsge.webarena.runtime import WebArenaExplorer


class _ScriptedInducerLLM:
    """Answers induce_operator with a scripted result and, by default, a
    grounding check that confirms every predicate on every member -- these
    tests are about the anti-tautology gate, not the grounding gate, so the
    latter must not be what rejects the operator. Pass grounded=False to make
    the grounding check confirm nothing instead.
    Captures the induction payload for assertions."""

    def __init__(self, preconditions, effects, terminal=False, grounded=True):
        self._induced = {"preconditions": preconditions, "effects": effects,
                         "terminal": terminal}
        self._grounded = grounded
        self.induce_payload = None

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        if "PLANNING OPERATOR" in system:
            self.induce_payload = json.loads(
                prompt.split("<payload>", 1)[1].rsplit("</payload>", 1)[0])
            return dict(self._induced)
        if not self._grounded:
            return {"results": []}
        payload = json.loads(prompt.split("<payload>", 1)[1].rsplit("</payload>", 1)[0])
        holds = [True] * len(payload["occurrences"])
        return {"results": [{"predicate": p, "type": kind, "member_holds": holds}
                            for kind, key in (("precondition", "preconditions"),
                                              ("effect", "effects"))
                            for p in payload[key]]}


def _explorer(llm, terminal_goal=None):
    ex = WebArenaExplorer(
        browser_factory=lambda url: None, llm=MockLLM(),
        embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
        allow_pattern=".*", terminal_goal=terminal_goal)
    ex.operator_llm = llm
    return ex


def _install_skill(ex, name="AddToCart", description="add an item to the cart",
                   init_url="http://shop/item.html"):
    steps = [Step(action="click('1')", url=init_url, axtree="before ax"),
             Step(action="click('2')", url="http://shop/cart", axtree="after ax")]
    sub = SubTrajectory(steps=steps, subgoal=name, source_site="shop")
    card = SkillCard(name=name, description=description, slots=[],
                     action_template=["click {btn}"], precondition="",
                     success_predicate="", cluster_id=0, member_ids=[sub.sub_id])
    ex.library.skills[0] = card
    ex.library.subtrajs[sub.sub_id] = sub
    return card


def _log_events(ex):
    path = os.path.join(ex.out_dir, "run_log.jsonl")
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path)]


def test_promotion_passes_registry_vocabulary_to_inducer():
    llm = _ScriptedInducerLLM(["the item page is open"], ["an item is in the cart"])
    ex = _explorer(llm)
    ex.registry.canonical("the user is logged in")     # pre-existing vocabulary
    card = _install_skill(ex)

    ex._promote_skill_to_operator(card.skill_id)

    assert llm.induce_payload["known_predicates"] == ["the user is logged in"]


def test_tautological_operator_is_rejected_and_logged():
    llm = _ScriptedInducerLLM(["a page with history is open"],
                              ["a page with history is open"])
    ex = _explorer(llm)
    card = _install_skill(ex, name="NavHistory")

    ex._promote_skill_to_operator(card.skill_id)

    assert ex.opgraph.ops == {}
    rejected = [e for e in _log_events(ex) if e["event"] == "operator_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "tautological"
    assert rejected[0]["effects_dropped"]              # names the dropped ids


def test_mixed_effects_keep_novel_subset_and_log_dropped():
    llm = _ScriptedInducerLLM(
        ["a comment is displayed entirely unique alpha"],
        ["a comment is displayed entirely unique alpha",
         "a reply is posted entirely unique beta"])
    ex = _explorer(llm)
    card = _install_skill(ex, name="ReplyToComment")

    ex._promote_skill_to_operator(card.skill_id)

    op = ex.opgraph.ops["replytocomment"]
    assert len(op.effects) == 1                        # tautological one dropped
    assert not (op.effects & op.preconditions)
    induced = [e for e in _log_events(ex) if e["event"] == "operator_induced"]
    assert induced[0]["effects_dropped"]


def test_empty_effects_rejected_with_no_effects_reason():
    llm = _ScriptedInducerLLM(["something must hold"], [])
    ex = _explorer(llm)
    card = _install_skill(ex)

    ex._promote_skill_to_operator(card.skill_id)

    assert ex.opgraph.ops == {}
    rejected = [e for e in _log_events(ex) if e["event"] == "operator_rejected"]
    assert rejected[0]["reason"] == "no_effects"


def test_op_meta_recorded_on_promotion():
    llm = _ScriptedInducerLLM(["the item page is open unique gamma"],
                              ["an item is in the cart unique delta"])
    ex = _explorer(llm)
    card = _install_skill(ex, name="AddToCart",
                          description="add an item to the cart",
                          init_url="http://shop/item.html")

    ex._promote_skill_to_operator(card.skill_id)

    meta = ex._op_meta["addtocart"]
    assert meta["card_name"] == "AddToCart"
    assert meta["description"] == "add an item to the cart"
    assert meta["init_url"] == "http://shop/item.html"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
