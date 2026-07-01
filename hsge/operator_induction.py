"""Induce a planning operator (preconditions/effects) from a *verified* skill.

This replaces `webarena/predicates.py::predicates_from` for the planning side: an
LLM reads the abstracted SkillCard plus the boundary page states (accessibility
tree before/after the skill ran, from a few cluster members) and states, in free
NL, what must hold to apply the skill (preconditions) and what it establishes
(effects). Those NL predicates are then canonicalized by `PredicateRegistry`.

Verification (did the episode reach the goal) still uses the deterministic
terminal-URL check in `webarena/predicates.py`; this module only shapes what the
planner composes over.
"""
from __future__ import annotations

import json

from .llm import LLM
from .schema import SkillCard

_SYS = (
    "You convert a reusable web skill into a PLANNING OPERATOR. Given the skill "
    "and the page state before/after it ran on a few sites, state the world "
    "conditions in short, site-agnostic natural language. Preconditions = what "
    "must already be true to apply the skill; effects = what becomes true after. "
    "Keep each predicate a terse phrase (e.g. 'search results are shown', 'an "
    "item is in the cart'). Mark terminal=true only if an effect is a final/"
    "transactional state (order placed, purchase confirmed). "
    'Return JSON {"preconditions": ["..."], "effects": ["..."], "terminal": bool}.'
)

_AXTREE_CAP = 2000


def induce_operator(
    llm: LLM,
    card: SkillCard,
    boundary_obs: list[tuple[str, str]],
) -> dict:
    """Return {"preconditions": [NL...], "effects": [NL...], "terminal": bool}.

    `boundary_obs` is a list of (start_axtree, end_axtree) pairs from a few
    members of the skill's cluster; only a couple are needed for context.
    """
    examples = [
        {"before": (start or "")[:_AXTREE_CAP], "after": (end or "")[:_AXTREE_CAP]}
        for start, end in boundary_obs[:2]
    ]
    payload = {
        "skill": {
            "name": card.name,
            "description": card.description,
            "action_template": card.action_template,
        },
        "boundary_states": examples,
    }
    out = llm.complete_json(_SYS, f"<payload>{json.dumps(payload)}</payload>")
    return {
        "preconditions": [p for p in out.get("preconditions", []) if p],
        "effects": [e for e in out.get("effects", []) if e],
        "terminal": bool(out.get("terminal", False)),
    }
