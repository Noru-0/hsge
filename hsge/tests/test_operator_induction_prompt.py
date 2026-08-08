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


def test_sys_prompt_requires_the_exit_state_to_differ_from_the_entry_state():
    """The page-state vocabulary alone produced effects that merely restate the
    precondition, and the anti-tautology gate then threw the operator away: 3 of
    6 shopping_admin skills were rejected that way (entry 'on the currency
    configuration page' -> exit the same phrase). The prompt must ask for the
    same page QUALIFIED by what the skill established, not a different page and
    not an element-level effect."""
    s = _SYS.lower()
    assert "must differ" in s
    assert "qualified" in s
    # a qualified page-state, not a fallback to element level
    assert "element-level" in s


def test_sys_prompt_does_not_collide_with_mockllm_routing():
    # MockLLM.complete_json routes on these exact substrings in the system
    # prompt; if the induction prompt contained one it would be mis-handled
    # in the deterministic pipeline.
    for token in ("SEGMENT", "ABSTRACT", "GROUND"):
        assert token not in _SYS
