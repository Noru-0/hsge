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
    "State preconditions and effects as PAGE STATES -- what page or screen the "
    "user is on and what is visible on it (e.g. 'on the product listing page', "
    "'the cart page is shown', 'the checkout page is shown') -- NOT the mere "
    "presence of one element ('a cart link is present'). Include at least one "
    "precondition naming the ENTRY page-state and at least one effect naming the "
    "EXIT page-state, worded so a later skill starting from that exit state would "
    "phrase its own entry precondition identically. This shared page-state "
    "vocabulary is what lets one skill's effect satisfy another skill's "
    "precondition so the planner can chain them. "
    "The EXIT page-state MUST DIFFER from the ENTRY page-state. If the skill "
    "stays on the same page, do not repeat the entry phrase -- name the same "
    "page QUALIFIED by what the skill established on it, e.g. entry 'on the "
    "product edit page' -> exit 'on the product edit page with a save "
    "confirmation'. An effect that merely restates a precondition is discarded "
    "and the whole operator is thrown away, so a bare repetition wastes the "
    "skill. A qualified page-state is still a page-state: never fall back to an "
    "element-level effect ('the description field is filled') to make it "
    "differ -- no other skill can phrase that as its entry precondition. "
    "Keep each predicate a terse "
    "phrase. Mark terminal=true only if an effect is a final/transactional state "
    "(order placed, purchase confirmed). "
    "A list of KNOWN predicates from previously induced operators may be "
    "provided. If a precondition or effect you want to state is semantically "
    "equivalent to a known predicate, you MUST reuse that predicate's exact "
    "text verbatim instead of rephrasing it. Only coin a new phrase when no "
    "known predicate matches. "
    'Return JSON {"preconditions": ["..."], "effects": ["..."], "terminal": bool}.'
)

_AXTREE_CAP = 2000


def induce_operator(
    llm: LLM,
    card: SkillCard,
    boundary_obs: list[tuple[str, str]],
    known_predicates: list[str] | None = None,
) -> dict:
    """Return {"preconditions": [NL...], "effects": [NL...], "terminal": bool}.

    `boundary_obs` is a list of (start_axtree, end_axtree) pairs from a few
    members of the skill's cluster; only a couple are needed for context.
    `known_predicates` is the registry's existing vocabulary (see
    PredicateRegistry.vocabulary()) -- shown to the LLM so equivalent
    predicates are reused verbatim instead of re-coined, which is what lets
    operators share canonical ids and chain.
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
    if known_predicates:
        payload["known_predicates"] = list(known_predicates)
    out = llm.complete_json(_SYS, f"<payload>{json.dumps(payload)}</payload>")
    return {
        "preconditions": [p for p in out.get("preconditions", []) if p],
        "effects": [e for e in out.get("effects", []) if e],
        "terminal": bool(out.get("terminal", False)),
    }


_GROUNDING_SYS = (
    "You verify PLANNING PREDICATES against real page states. You are given "
    "a list of predicates (each tagged precondition or effect) and, for "
    "each occurrence of the skill, the page's accessibility tree BEFORE and "
    "AFTER the skill ran. For a precondition, check it against the BEFORE "
    "tree of every occurrence; for an effect, check it against the AFTER "
    "tree of every occurrence. "
    'Return JSON {"results": [{"predicate": "<exact text>", "type": '
    '"precondition"|"effect", "member_holds": [true|false, ...]}, ...]}, '
    "one entry per predicate, with member_holds having exactly one boolean "
    "per occurrence in the order given."
)


def verify_operator_grounding(
    llm: LLM,
    preconditions: list[str],
    effects: list[str],
    boundary_obs: list[tuple[str, str]],
) -> dict:
    """Check induced preconditions/effects against every member's real
    boundary axtree (unlike induce_operator, which only samples 2 for
    context). Returns per-predicate confirmation accuracy; never raises on a
    malformed LLM response -- an unconfirmed predicate degrades to 0.0
    rather than breaking the run, since this is a quality signal, not a gate.
    """
    member_count = len(boundary_obs)
    occurrences = [
        {"before": (start or "")[:_AXTREE_CAP], "after": (end or "")[:_AXTREE_CAP]}
        for start, end in boundary_obs
    ]
    payload = {
        "preconditions": preconditions,
        "effects": effects,
        "occurrences": occurrences,
    }
    precondition_accuracy = {p: 0.0 for p in preconditions}
    effect_accuracy = {e: 0.0 for e in effects}
    if member_count == 0 and not preconditions and not effects:
        return {"precondition_accuracy": {}, "effect_accuracy": {}, "member_count": 0}

    out = llm.complete_json(_GROUNDING_SYS, f"<payload>{json.dumps(payload)}</payload>")
    results = out.get("results", [])
    if not isinstance(results, list):
        results = []

    for entry in results:
        if not isinstance(entry, dict):
            continue
        predicate = entry.get("predicate")
        holds = entry.get("member_holds", [])
        if not isinstance(holds, list):
            holds = []
        confirmed = sum(1 for h in holds[:member_count] if h is True)
        accuracy = (confirmed / member_count) if member_count else 0.0
        if entry.get("type") == "precondition" and predicate in precondition_accuracy:
            precondition_accuracy[predicate] = accuracy
        elif entry.get("type") == "effect" and predicate in effect_accuracy:
            effect_accuracy[predicate] = accuracy

    return {
        "precondition_accuracy": precondition_accuracy,
        "effect_accuracy": effect_accuracy,
        "member_count": member_count,
    }
