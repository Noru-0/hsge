"""The operator-induction system prompt must ask for page-state
precondition/effect vocabulary (part B of the multi-step/page-state design),
and must not collide with MockLLM's system-prompt routing keywords.

Run:  PYTHONPATH=. python -m pytest hsge/tests/test_operator_induction_prompt.py -q
"""
from hsge.operator_induction import _SYS


def test_sys_prompt_requires_page_state_vocabulary():
    s = _SYS.lower()
    assert "page state" in s or "page-state" in s
    assert "entry" in s and "exit" in s


def test_sys_prompt_does_not_collide_with_mockllm_routing():
    # MockLLM.complete_json routes on these exact substrings in the system
    # prompt; if the induction prompt contained one it would be mis-handled
    # in the deterministic pipeline.
    for token in ("SEGMENT", "ABSTRACT", "GROUND"):
        assert token not in _SYS
