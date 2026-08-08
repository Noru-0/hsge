"""Regression tests for the P2 fixes from the shopping_admin audit
(outputs/wa_eval_shopping_admin):

  1. The grounding check only LOGGED. `enter_new_description` entered the graph
     with effect accuracy 0.0 -- an effect confirmed on no member at all -- so
     any plan built on it could not work. It now gates effects.
  2. A seed capability the agent itself declared infeasible was re-offered from
     the next page template: "view-advanced-reports" (a Magento SaaS feature the
     instance does not have) was declared infeasible at step 3 and offered twice
     more. A self-declared infeasible now retires it immediately; a wrap-up
     infeasible (the solver merely ran out of steps) still just counts as one
     failure, since that verdict is not the agent's own conclusion.

The induction-prompt change (the exit page-state must differ from the entry one,
qualified rather than repeated) is covered by test_operator_induction_prompt.py.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hsge.llm import HashingEmbedder, MockLLM
from hsge.schema import SkillCard, Step, SubTrajectory
from hsge.webarena.runtime import WebArenaExplorer


class _InducerLLM:
    """Induces a fixed operator; confirms each predicate on the fraction of
    members given in `holds_by_predicate` (default: all of them)."""

    def __init__(self, preconditions, effects, holds_by_predicate=None):
        self._induced = {"preconditions": preconditions, "effects": effects,
                         "terminal": False}
        self._holds = holds_by_predicate or {}

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        payload = json.loads(prompt.split("<payload>", 1)[1].rsplit("</payload>", 1)[0])
        if "PLANNING OPERATOR" in system:
            return dict(self._induced)
        n = len(payload["occurrences"])
        results = []
        for kind, key in (("precondition", "preconditions"), ("effect", "effects")):
            for p in payload[key]:
                frac = self._holds.get(p, 1.0)
                results.append({"predicate": p, "type": kind,
                                "member_holds": [i < round(frac * n) for i in range(n)]})
        return {"results": results}


def _explorer(llm=None):
    ex = WebArenaExplorer(
        browser_factory=lambda url: None, llm=MockLLM(),
        embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
        allow_pattern=".*", terminal_goal=None)
    if llm is not None:
        ex.operator_llm = llm
    return ex


def _install_skill(ex, name="EnterNewDescription", n_members=2):
    ids = []
    for i in range(n_members):
        steps = [Step(action="click('1')", url=f"http://shop/item{i}", axtree=f"before {i}"),
                 Step(action="click('2')", url=f"http://shop/item{i}", axtree=f"after {i}")]
        sub = SubTrajectory(steps=steps, subgoal=name, source_site="shop")
        ex.library.subtrajs[sub.sub_id] = sub
        ids.append(sub.sub_id)
    card = SkillCard(name=name, description="type a new description", slots=[],
                     action_template=["fill {text}"], precondition="",
                     success_predicate="", cluster_id=0, member_ids=ids)
    ex.library.skills[0] = card
    return card


def _events(ex):
    path = os.path.join(ex.out_dir, "run_log.jsonl")
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


# ---- 1. the grounding check gates effects ---------------------------------

def test_effect_confirmed_on_no_member_is_rejected():
    """The exact shopping_admin case: pre accuracy 1.0, effect accuracy 0.0."""
    llm = _InducerLLM(["on the product edit page unique alpha"],
                      ["the description field is filled unique beta"],
                      holds_by_predicate={"the description field is filled unique beta": 0.0})
    ex = _explorer(llm)
    card = _install_skill(ex)

    ex._promote_skill_to_operator(card.skill_id)

    assert ex.opgraph.ops == {}
    rejected = [e for e in _events(ex) if e["event"] == "operator_rejected"]
    assert rejected[-1]["reason"] == "ungrounded"
    assert rejected[-1]["effects_ungrounded"]


def test_partly_confirmed_effect_survives():
    """0.5 on 2 members is the threshold -- only "held on no member" is dropped."""
    llm = _InducerLLM(["on the product edit page unique gamma"],
                      ["a save confirmation is shown unique delta"],
                      holds_by_predicate={"a save confirmation is shown unique delta": 0.5})
    ex = _explorer(llm)
    card = _install_skill(ex)

    ex._promote_skill_to_operator(card.skill_id)

    assert "enternewdescription" in ex.opgraph.ops


def test_ungrounded_effect_is_dropped_but_a_grounded_one_keeps_the_operator():
    llm = _InducerLLM(
        ["on the product edit page unique eps"],
        ["the description field is filled unique zeta",
         "a save confirmation is shown unique eta"],
        holds_by_predicate={"the description field is filled unique zeta": 0.0})
    ex = _explorer(llm)
    card = _install_skill(ex)

    ex._promote_skill_to_operator(card.skill_id)

    op = ex.opgraph.ops["enternewdescription"]
    assert len(op.effects) == 1
    induced = [e for e in _events(ex) if e["event"] == "operator_induced"]
    assert induced[-1]["effects_ungrounded"]


def test_no_usable_members_skips_the_gate_entirely():
    """member_count 0 means nothing could be checked -- score nothing rather
    than reject every operator induced without page context."""
    llm = _InducerLLM(["on some page unique theta"], ["something changed unique iota"])
    ex = _explorer(llm)
    card = _install_skill(ex, n_members=1)
    ex.library.subtrajs.clear()          # members unresolvable -> no boundary obs

    ex._promote_skill_to_operator(card.skill_id)

    assert "enternewdescription" in ex.opgraph.ops


# ---- 2. a self-declared infeasible retires the capability ------------------

def test_self_declared_infeasible_retires_the_capability_at_once():
    ex = _explorer()
    ex._score_capability("view-advanced-reports", success=False, infeasible=True,
                         stop_reason="")
    assert ex._capability_failures["view-advanced-reports"] >= ex._CAPABILITY_MAX_FAILS
    assert [e["event"] for e in _events(ex)] == ["capability_retired"]


def test_wrapup_infeasible_only_counts_as_one_failure():
    """Running out of steps is not the agent concluding it's impossible."""
    ex = _explorer()
    ex._score_capability("manage-orders", success=False, infeasible=True,
                         stop_reason="budget")
    assert ex._capability_failures["manage-orders"] == 1
    assert ex._capability_failures["manage-orders"] < ex._CAPABILITY_MAX_FAILS


def test_a_success_resets_the_failure_count():
    ex = _explorer()
    ex._score_capability("edit-product", success=False, infeasible=False, stop_reason="stuck")
    ex._score_capability("edit-product", success=True, infeasible=False, stop_reason="")
    assert ex._capability_failures["edit-product"] == 0


def test_retired_capability_is_no_longer_offered():
    ex = _explorer()
    ex.site_seed = {"description": "admin panel", "capabilities": [
        {"name": "view-advanced-reports",
         "goal": "Navigate to Advanced Reporting and generate a report."}]}
    ex._capability_failures["view-advanced-reports"] = ex._CAPABILITY_MAX_FAILS

    assert ex._goal_task("http://admin/dashboard/") == []


def test_a_fresh_capability_is_offered():
    ex = _explorer()
    ex.site_seed = {"description": "admin panel", "capabilities": [
        {"name": "edit-product", "goal": "Open the first product and set its price to $19.99."}]}

    tasks = ex._goal_task("http://admin/catalog/product/")

    assert [t["capability"] for t in tasks] == ["edit-product"]
