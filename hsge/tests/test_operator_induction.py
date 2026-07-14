"""induce_operator: vocabulary-aware prompting. The LLM must see the existing
predicate vocabulary and be told to reuse matching phrases verbatim, so
canonicalization happens at the source instead of relying on embedding
similarity alone (measured on wa_run_09: the true synonym pair scored 0.570,
below the 0.6 threshold, while a false pair scored 0.606 -- no threshold works).

Run:  python -m pytest hsge/tests/test_operator_induction.py -q
 (or) PYTHONPATH=. python hsge/tests/test_operator_induction.py
"""
import json

from hsge.operator_induction import _SYS, induce_operator
from hsge.schema import SkillCard


class _CapturingLLM:
    def __init__(self):
        self.system = None
        self.prompt = None

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.system = system
        self.prompt = prompt
        return {"preconditions": ["a"], "effects": ["b"], "terminal": False}


def _card():
    return SkillCard(name="AddToCart", description="add an item to the cart",
                     slots=[], action_template=["click {add_button}"],
                     precondition="item page is open",
                     success_predicate="cart count increased", cluster_id="c0")


def _payload(llm):
    return json.loads(llm.prompt.split("<payload>", 1)[1].rsplit("</payload>", 1)[0])


def test_known_predicates_included_in_payload():
    llm = _CapturingLLM()

    induce_operator(llm, _card(), [("before", "after")],
                    known_predicates=["the user is logged in", "an item is in the cart"])

    payload = _payload(llm)
    assert payload["known_predicates"] == [
        "the user is logged in", "an item is in the cart"]


def test_payload_shape_unchanged_without_known_predicates():
    llm = _CapturingLLM()

    induce_operator(llm, _card(), [("before", "after")])

    payload = _payload(llm)
    assert "known_predicates" not in payload
    assert set(payload) == {"skill", "boundary_states"}


def test_empty_known_predicates_omitted():
    llm = _CapturingLLM()

    induce_operator(llm, _card(), [("before", "after")], known_predicates=[])

    assert "known_predicates" not in _payload(llm)


def test_system_prompt_mandates_verbatim_reuse():
    assert "verbatim" in _SYS
    assert "known predicate" in _SYS.lower()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
