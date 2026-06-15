"""Abstraction = 'lifting' a cluster of concrete sub-trajectories into one
parameterized SkillCard (an option). Site-specific selectors/values become slots.
"""
from __future__ import annotations

import json
from collections import Counter

from .llm import LLM
from .schema import ParamSlot, SkillCard, SubTrajectory

_SYS = (
    "You ABSTRACT several concrete sub-trajectories that achieve the same "
    "sub-goal into ONE reusable, parameterized skill. "
    "Return ONLY valid JSON with these EXACT keys:\n"
    '{\n'
    '  "name": "<short_skill_name>",\n'
    '  "description": "<one sentence>",\n'
    '  "slots": [{"name":"<slot>", "slot_type":"selector|value", "description":"<hint>"}],\n'
    '  "action_template": "<template with {slot_name} placeholders>",\n'
    '  "precondition": "<precondition predicate>",\n'
    '  "success_predicate": "<success predicate>"\n'
    '}'
)


def abstract_cluster(
    llm: LLM,
    cluster_id: int,
    members: list[SubTrajectory],
) -> SkillCard | None:
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

    if not out or "name" not in out:
        # LLM returned empty/invalid response — skip abstraction for this cluster
        print(f"  [abstraction] WARNING: LLM returned invalid response "
              f"(cluster={cluster_id}, n_members={len(members)}, "
              f"dominant_subgoal={dominant[:50]})")
        return None

    slots = [ParamSlot(**s) for s in out.get("slots", [])]
    return SkillCard(
        name=out.get("name", f"skill_{cluster_id}"),
        description=out.get("description", ""),
        slots=slots,
        action_template=out.get("action_template", ""),
        precondition=out.get("precondition", ""),
        success_predicate=out.get("success_predicate", f"{dominant} completed"),
        cluster_id=str(cluster_id),
        member_ids=[m.sub_id for m in members],
    )
