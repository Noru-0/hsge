"""Abstraction = 'lifting' a cluster of concrete sub-trajectories into one
parameterized SkillCard (an option). Site-specific selectors/values become slots.

Phase 4 improvement: produces structured execution plans with alternative
selectors and fallback instructions, not just raw template strings.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from .llm import LLM
from .schema import ParamSlot, SkillCard, SubTrajectory
from .webarena.action_validation import parse_hsge_action

_SYS = (
    "You ABSTRACT several concrete sub-trajectories that achieve the same "
    "sub-goal into ONE reusable, domain-neutral, executable skill. "
    "Use the examples in the payload; do not invent page/domain details. "
    "The skill must transfer across unrelated sites such as commerce, forums, "
    "docs, admin tools, and issue trackers.\n\n"
    "Rules:\n"
    "- Skill names MUST be generic snake_case, for example "
    "open_visible_item, open_visible_detail, submit_search_query, "
    "inspect_feedback_indicator, activate_named_control.\n"
    "- Do NOT use core domain nouns such as product, cart, wishlist, sku, "
    "shopping, checkout, order, category, review, or price in the skill name "
    "or description. Use generic words like item, collection, feedback, "
    "detail, field, control, or record.\n"
    "- action_template MUST contain only canonical HSGE actions with placeholders: "
    "click({selector_slot}), hover({selector_slot}), "
    "fill({selector_slot}, {value_slot}), type({selector_slot}, {value_slot}, '0'), "
    "press('Enter'), scroll('down').\n"
    "- Selector targets MUST use slot_type selector. Text/input values MUST use "
    "slot_type value. Never click a value slot.\n"
    "- execution_plan must describe the same canonical actions as action_template.\n\n"
    "Return ONLY valid JSON with these EXACT keys:\n"
    '{\n'
    '  "name": "<generic_snake_case_skill_name>",\n'
    '  "description": "<one sentence>",\n'
    '  "slots": [{"name":"<slot>", "slot_type":"selector|value", "description":"<hint>"}],\n'
    '  "action_template": ["<canonical action template>", "..."],\n'
    '  "precondition": "<precondition predicate>",\n'
    '  "success_predicate": "<success predicate>",\n'
    '  "execution_plan": [\n'
    '    {\n'
    '      "action_type": "click|fill|type|hover|press|scroll",\n'
    '      "target_desc": "description of the element",\n'
    '      "value_ref": "slot_name_or_null",\n'
    '      "fallback": "what to try if element not found",\n'
    '      "success_check": "how to verify this step"\n'
    '    }\n'
    '  ],\n'
    '  "alternative_templates": ["<alt1>", "<alt2>"]\n'
    '}'
)

_DOMAIN_TERMS = {
    "product", "products", "cart", "wishlist", "wish list", "sku", "shopping",
    "checkout", "order", "orders", "category", "categories", "price", "prices",
}

_NAME_ALIASES = [
    (re.compile(r"\b(product|item|record).*(link|page|detail)|\b(click|navigate).*product", re.I), "open_visible_item"),
    (re.compile(r"\b(detail|details|description)\b", re.I), "open_visible_detail"),
    (re.compile(r"\b(wish\s*list|wishlist|favorite|save)\b", re.I), "save_visible_item"),
    (re.compile(r"\b(cart|checkout|purchase|order|submit|save|apply|confirm)\b", re.I), "activate_state_change_control"),
    (re.compile(r"\b(review|reviews|feedback|rating|comment|comments)\b", re.I), "inspect_feedback_indicator"),
    (re.compile(r"\b(menu|hover|submenu)\b", re.I), "inspect_menu_options"),
    (re.compile(r"\b(search|query|find|sku)\b", re.I), "submit_search_query"),
]


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
        "examples": _representative_examples(members),
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
        name=_normalize_skill_name(out.get("name", f"skill_{cluster_id}"), dominant),
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

    reason = validate_skill_card(card)
    if reason:
        print(f"  [abstraction] WARNING: rejected skill "
              f"(cluster={cluster_id}, name={card.name!r}, reason={reason})")
        return None

    return card


def _representative_examples(members: list[SubTrajectory], max_examples: int = 3) -> list[dict]:
    examples = []
    for m in members[:max_examples]:
        start_url = m.steps[0].url if m.steps else ""
        end_url = m.steps[-1].url if m.steps else ""
        examples.append({
            "source_task": m.source_task,
            "subgoal": m.subgoal,
            "action_sequence": [s.action for s in m.steps],
            "action_kinds": [s.action_kind() for s in m.steps],
            "start_url": start_url,
            "end_url": end_url,
            "observation_summaries": [s.obs_summary[:180] for s in m.steps if s.obs_summary][:3],
        })
    return examples


def _normalize_skill_name(name: str, dominant_subgoal: str = "") -> str:
    raw = (name or "").strip()
    if re.fullmatch(r"[a-z][a-z0-9_]{2,48}", raw) and not _contains_domain_terms(raw):
        return raw
    text = f"{name or ''} {dominant_subgoal or ''}"
    for pattern, replacement in _NAME_ALIASES:
        if pattern.search(text):
            return replacement
    tokens = [
        t for t in re.findall(r"[a-z0-9]+", (name or "").lower())
        if t not in {"skill", "to", "the", "a", "an", "visible", "specified"}
    ]
    return "_".join(tokens[:4]) or "activate_named_control"


def validate_skill_card(card: SkillCard) -> str:
    """Return a rejection reason, or empty string when the card is usable."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,48}", card.name or ""):
        return "name_not_generic_snake_case"
    if _contains_domain_terms(" ".join([
        card.name,
        card.description,
        card.precondition,
        card.success_predicate,
        " ".join(card.action_template),
    ])):
        return "domain_specific_vocabulary"
    if _looks_overfit_to_literal(card):
        return "overfit_literal"

    slot_types = {s.name: s.slot_type for s in card.slots}
    if not card.action_template:
        return "missing_action_template"
    for tmpl in card.action_template:
        reason = _validate_action_template(tmpl, slot_types)
        if reason:
            return reason
    for step in card.execution_plan:
        action_type = step.get("action_type", "")
        if action_type not in {"click", "fill", "type", "hover", "press", "scroll"}:
            return "invalid_execution_plan_action"
    return ""


def _contains_domain_terms(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in _DOMAIN_TERMS)


def _validate_action_template(template: str, slot_types: dict[str, str]) -> str:
    rendered = _render_template_for_validation(template, slot_types)
    try:
        parsed = parse_hsge_action(rendered)
    except ValueError:
        return "noncanonical_template"

    placeholders = re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", template or "")
    unknown = [p for p in placeholders if p not in slot_types]
    if unknown:
        return "unknown_slot_in_template"
    targeted = {"click", "hover", "fill", "type"}
    if parsed.name in targeted:
        if not parsed.args:
            return "missing_selector_argument"
        slot = _slot_for_argument(template, 0)
        if not slot or slot_types.get(slot) != "selector":
            return "target_argument_not_selector_slot"
    if parsed.name in {"fill", "type"}:
        slot = _slot_for_argument(template, 1)
        if not slot or slot_types.get(slot) != "value":
            return "input_argument_not_value_slot"
    if parsed.name in {"goto", "send_msg_to_user"}:
        return "non_executable_skill_action"
    return ""


def _render_template_for_validation(template: str, slot_types: dict[str, str]) -> str:
    rendered = template or ""
    for name, typ in slot_types.items():
        value = "101" if typ == "selector" else "sample"
        rendered = rendered.replace("{" + name + "}", repr(value))
    return rendered


def _slot_for_argument(template: str, arg_index: int) -> str:
    match = re.match(r"\s*[A-Za-z_][A-Za-z0-9_]*\s*\((.*)\)\s*$", template or "")
    if not match:
        return ""
    args = [a.strip() for a in match.group(1).split(",")]
    if arg_index >= len(args):
        return ""
    m = re.fullmatch(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", args[arg_index])
    return m.group(1) if m else ""


def _looks_overfit_to_literal(card: SkillCard) -> bool:
    """Reject skills that bake long concrete entities into non-slot fields."""
    fields = " ".join([
        card.name,
        card.description,
        card.precondition,
        card.success_predicate,
    ])
    quoted_literals = [
        m.strip()
        for m in re.findall(r"'([^']+)'|\"([^\"]+)\"", fields)
        for m in m
        if m.strip()
    ]
    for literal in quoted_literals:
        tokens = re.findall(r"[A-Za-z0-9]+", literal)
        if len(tokens) >= 6 or "," in literal:
            return True

    name_tokens = re.findall(r"[A-Za-z0-9]+", card.name)
    if len(name_tokens) >= 5 and not card.slots:
        return True

    return False
