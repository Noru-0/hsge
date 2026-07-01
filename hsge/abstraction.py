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
    '"precondition": "...", "success_predicate": "..."}')


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
