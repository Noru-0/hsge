"""Abstraction = 'lifting' a cluster of concrete sub-trajectories into one
parameterized SkillCard (an option). Site-specific selectors/values become slots.
"""
from __future__ import annotations

import json
from collections import Counter

from .llm import LLM
from .schema import ParamSlot, SkillCard, SubTrajectory

_SYS = (
    "You ABSTRACT several concrete sub-trajectories that achieve the same sub-goal "
    "into ONE reusable, parameterized skill. Site-specific selectors/values become "
    "slots. Return ONLY JSON with this exact shape:\n"
    '{"name": "...", "description": "...", '
    '"slots": [{"name": "...", "slot_type": "value|selector|url", '
    '"description": "...", "example": "..."}], '
    '"action_template": ["step 1", "step 2"], '
    '"precondition": "...", "success_predicate": "..."}\n'
    "\n"
    "action_template RULES -- every entry must be a runnable action string in the "
    "SAME action space as the <example_actions> in the payload, with a slot "
    "placeholder written as {slot_name} substituted for whatever is site-specific:\n"
    "  click('{bid}')                    -- ONE argument\n"
    "  fill('{bid}', '{text}')           -- TWO arguments, element FIRST, text SECOND\n"
    "  select_option('{bid}', '{option}')-- TWO arguments\n"
    "  press('{bid}', 'Enter')           -- TWO arguments, element then key name\n"
    "  goto('{url}') / go_back()         -- navigation\n"
    "  send_msg_to_user('{answer}')      -- answer/finish\n"
    "An element is addressed by its BID -- the short numeric id the accessibility "
    "tree assigns it, like '68' or '1790'. NEVER emit a CSS or XPath selector "
    "(no '#id', no '.class', no '//div'): those do not exist in this action space. "
    "A slot standing for an element must therefore use slot_type 'selector' with a "
    "BID example such as '68'. Quote every argument, and respect the argument count "
    "above exactly.")


_MAX_EXAMPLE_MEMBERS = 3   # enough to show the syntax without bloating the prompt


def _example_actions(members: list[SubTrajectory]) -> list[list[str]]:
    """The literal action strings of a few members, as syntax exemplars."""
    return [[s.action for s in m.steps] for m in members[:_MAX_EXAMPLE_MEMBERS]]


def abstract_cluster(
    llm: LLM,
    cluster_id: int,
    members: list[SubTrajectory],
) -> SkillCard:
    # Dominant sub-goal across members (robust to a few noisy labels).
    dominant = Counter(m.subgoal for m in members).most_common(1)[0][0]
    # Representative action-verb sequence = the modal signature in the cluster.
    sig = Counter(m.action_signature() for m in members).most_common(1)[0][0]
    verbs = [v.strip() for v in sig.split(">")] if sig else []

    payload = {
        "dominant_subgoal": dominant,
        "action_verbs": verbs,
        # The concrete action strings the members actually executed. Without these
        # the model only sees bare verbs and invents a plausible-looking but
        # unrunnable syntax -- a real run produced "click({sel})" (unquoted),
        # "fill('{text}', '')" (arguments swapped) and CSS examples like
        # "#notification-bell" for an action space that only addresses bids.
        "example_actions": _example_actions(members),
        "success_predicate": f"{dominant} completed",
        "n_examples": len(members),
    }
    out = llm.complete_json(_SYS, f"<payload>{json.dumps(payload)}</payload>")

    # Real LLMs may omit or malform fields; fall back to payload-derived values so a
    # missing key never crashes admission. Slots are built explicitly (skip invalid).
    slots = []
    for s in out.get("slots") or []:
        if isinstance(s, dict) and s.get("name") and s.get("slot_type"):
            slots.append(ParamSlot(name=s["name"], slot_type=s["slot_type"],
                                   description=s.get("description", ""),
                                   example=s.get("example", "")))
    return SkillCard(
        name=out.get("name") or " ".join(dominant.split()[:3]).title() or "Skill",
        description=out.get("description") or f"Reusable routine to {dominant}.",
        slots=slots,
        action_template=out.get("action_template") or verbs,
        precondition=out.get("precondition") or f"page affords: {dominant}",
        success_predicate=out.get("success_predicate") or payload["success_predicate"],
        cluster_id=str(cluster_id),
        member_ids=[m.sub_id for m in members],
    )
