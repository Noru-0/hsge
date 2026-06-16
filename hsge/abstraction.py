"""Abstraction = 'lifting' a cluster of concrete sub-trajectories into one
parameterized SkillCard (an option). Site-specific selectors/values become slots.

Phase 4 improvement: produces structured execution plans with alternative
selectors and fallback instructions, not just raw template strings.
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
    '  "success_predicate": "<success predicate>",\n'
    '  "execution_plan": [\n'
    '    {\n'
    '      "action_type": "click|fill|goto|select",\n'
    '      "target_desc": "description of the element",\n'
    '      "value_ref": "slot_name_or_null",\n'
    '      "fallback": "what to try if element not found",\n'
    '      "success_check": "how to verify this step"\n'
    '    }\n'
    '  ],\n'
    '  "alternative_templates": ["<alt1>", "<alt2>"]\n'
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

    # Extract action_template (backward compatible: str or list[str])
    action_template = out.get("action_template", "")
    if isinstance(action_template, str):
        action_template = [action_template]

    # Extract structured execution plan (Phase 4 improvement)
    execution_plan = out.get("execution_plan", [])
    if execution_plan and isinstance(execution_plan, list):
        # Validate and normalize execution plan entries
        validated_plan = []
        for step in execution_plan:
            if isinstance(step, dict) and "action_type" in step:
                validated_plan.append({
                    "action_type": step.get("action_type", "click"),
                    "target_desc": step.get("target_desc", ""),
                    "value_ref": step.get("value_ref"),
                    "fallback": step.get("fallback", ""),
                    "success_check": step.get("success_check", ""),
                })
        execution_plan = validated_plan

    # Extract alternative templates (Phase 4 improvement)
    alternative_templates = out.get("alternative_templates", [])
    if isinstance(alternative_templates, str):
        alternative_templates = [alternative_templates]

    card = SkillCard(
        name=out.get("name", f"skill_{cluster_id}"),
        description=out.get("description", ""),
        slots=slots,
        action_template=action_template,
        precondition=out.get("precondition", ""),
        success_predicate=out.get("success_predicate", f"{dominant} completed"),
        cluster_id=str(cluster_id),
        member_ids=[m.sub_id for m in members],
    )

    # Store execution plan and alternatives as extra attributes
    if execution_plan:
        card.execution_plan = execution_plan
    if alternative_templates:
        card.alternative_templates = alternative_templates

    return card
