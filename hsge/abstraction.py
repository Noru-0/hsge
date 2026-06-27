"""Abstraction = 'lifting' a cluster of concrete sub-trajectories into one
parameterized SkillCard (an option). Site-specific selectors/values become slots.
"""
from __future__ import annotations

import json
from collections import Counter

from .llm import LLM
from .schema import ParamSlot, SkillCard, SubTrajectory

_SYS = ("You ABSTRACT several concrete sub-trajectories that achieve the same "
        "sub-goal into ONE reusable, parameterized skill. Return JSON.")


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

    slots = [ParamSlot(**s) for s in out.get("slots", [])]
    return SkillCard(
        name=out["name"],
        description=out["description"],
        slots=slots,
        action_template=out["action_template"],
        precondition=out["precondition"],
        success_predicate=out["success_predicate"],
        cluster_id=str(cluster_id),
        member_ids=[m.sub_id for m in members],
    )
