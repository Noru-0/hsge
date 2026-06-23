"""Validation helpers for HSGE-style WebArena actions.

The training and exploration paths both use the compact HSGE action dialect:
``click('123')``, ``fill('123','text')``, ``scroll('down')``, etc.  Keeping the
parser and grounding rules in one place prevents the dataset builder and the
exploration solver from accepting different action spaces.
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any


CANONICAL_ACTIONS = {
    "click",
    "fill",
    "type",
    "press",
    "scroll",
    "hover",
    "goto",
    "send_msg_to_user",
}

TARGETED_ACTIONS = {"click", "fill", "type", "hover"}
INPUT_ACTIONS = {"fill", "type"}
INTERACTIVE_ROLES = {
    "button",
    "link",
    "checkbox",
    "radio",
    "menuitem",
    "option",
    "tab",
    "combobox",
    "textbox",
    "searchbox",
}
INPUT_ROLES = {"textbox", "searchbox", "combobox"}
ACTION_RE = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")
AXTREE_LINE_RE = re.compile(
    r"^\s*\[(?P<bid>\d+)\]\s+(?P<role>[A-Za-z]+)\s+(?P<name>.*)$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class ParsedAction:
    name: str
    args: tuple[str, ...]
    raw: str

    @property
    def bid(self) -> str | None:
        if self.name in TARGETED_ACTIONS and self.args:
            return self.args[0]
        return None


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str = ""
    parsed: ParsedAction | None = None
    target_line: str = ""


def parse_hsge_action(action: str) -> ParsedAction:
    """Parse a canonical HSGE action string with Python's AST parser."""
    raw = (action or "").strip()
    try:
        expr = ast.parse(raw, mode="eval").body
    except SyntaxError as exc:
        raise ValueError(f"invalid action syntax: {exc.msg}") from exc
    if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Name):
        raise ValueError("action must be a function call")
    name = expr.func.id
    if name not in CANONICAL_ACTIONS:
        raise ValueError(f"unsupported action {name!r}")
    if expr.keywords:
        raise ValueError("keyword arguments are not supported")
    args: list[str] = []
    for arg in expr.args:
        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, (str, int, float)):
            raise ValueError("action arguments must be string or numeric literals")
        args.append(str(arg.value))
    return ParsedAction(name=name, args=tuple(args), raw=raw)


def parse_assistant_json(target: str) -> dict[str, Any]:
    """Parse an assistant target, accepting plain JSON or fenced JSON."""
    text = (target or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def extract_action_from_target(target: str) -> tuple[str, str]:
    """Return (thought, action) from a training target JSON string."""
    obj = parse_assistant_json(target)
    thought = str(obj.get("thought", ""))
    action = str(obj.get("action", "")).strip()
    return thought, action


def axtree_elements(axtree: str) -> dict[str, tuple[str, str]]:
    """Map BID to (role, full_line) from flattened AXTree text."""
    out: dict[str, tuple[str, str]] = {}
    for match in AXTREE_LINE_RE.finditer(axtree or ""):
        bid = match.group("bid")
        role = match.group("role").lower()
        line = match.group(0).strip()
        out.setdefault(bid, (role, line))
    return out


def validate_hsge_action(
    action: str,
    axtree: str = "",
    *,
    allow_goto: bool = True,
) -> ValidationResult:
    """Validate syntax and AXTree grounding for one HSGE action."""
    try:
        parsed = parse_hsge_action(action)
    except ValueError as exc:
        return ValidationResult(False, str(exc))

    args = parsed.args
    name = parsed.name
    if name in {"click", "hover"} and len(args) != 1:
        return ValidationResult(False, f"{name} requires exactly one bid", parsed)
    if name == "fill" and len(args) != 2:
        return ValidationResult(False, "fill requires bid and text", parsed)
    if name == "type" and (len(args) not in {2, 3} or (len(args) == 3 and args[2] not in {"0", "1"})):
        return ValidationResult(False, "type requires bid, text, and optional 0/1 enter flag", parsed)
    if name == "press" and len(args) != 1:
        return ValidationResult(False, "press requires one key argument", parsed)
    if name == "scroll" and (len(args) != 1 or args[0] not in {"up", "down"}):
        return ValidationResult(False, "scroll requires 'up' or 'down'", parsed)
    if name == "goto" and len(args) != 1:
        return ValidationResult(False, "goto requires one url argument", parsed)
    if name == "goto" and not allow_goto:
        return ValidationResult(False, "goto is disabled for this policy; use visible UI actions instead", parsed)
    if name == "send_msg_to_user" and len(args) != 1:
        return ValidationResult(False, "send_msg_to_user requires one message argument", parsed)

    if parsed.bid is None:
        return ValidationResult(True, parsed=parsed)
    if not parsed.bid.isdigit():
        return ValidationResult(False, f"bid must be numeric, got {parsed.bid!r}", parsed)

    elements = axtree_elements(axtree)
    if axtree and parsed.bid not in elements:
        return ValidationResult(False, f"bid {parsed.bid} is not present in current AXTree", parsed)
    if not axtree:
        return ValidationResult(True, parsed=parsed)

    role, line = elements[parsed.bid]
    if re.search(r"\bdisabled\s*=\s*true\b|\bdisabled\b", line, re.IGNORECASE):
        return ValidationResult(False, f"{name} target [{parsed.bid}] is disabled", parsed, line)
    if name in INPUT_ACTIONS and role not in INPUT_ROLES:
        return ValidationResult(False, f"{name} target [{parsed.bid}] is {role}, not an input", parsed, line)
    if name in {"click", "hover"} and role not in INTERACTIVE_ROLES:
        return ValidationResult(False, f"{name} target [{parsed.bid}] is non-interactive role {role}", parsed, line)
    return ValidationResult(True, parsed=parsed, target_line=line)


def action_family(action: str) -> str:
    try:
        return parse_hsge_action(action).name
    except ValueError:
        match = ACTION_RE.search(action or "")
        return match.group(1) if match else "invalid"


def task_family(goal: str) -> str:
    g = (goal or "").lower()
    if re.search(r"contact|message|email|comment|post|reply|draft|send|publish", g):
        return "communication"
    if re.search(r"delete|remove|cancel|archive|deactivate|disable|close", g):
        return "destructive_change"
    if re.search(r"submit|save|apply|confirm|book|reserve|subscribe|purchase|checkout|payment|pay|refund|return item|cart|wish\s*list|wishlist|reorder|add to compare|proceed to checkout|place order", g):
        return "state_change"
    if re.search(r"record|history|status|ticket|issue|request|case|incident|order|orders|recent orders|delivery|shipping|billing|fulfilled|pending", g):
        return "records_status"
    if re.search(r"address|account|profile|settings|preference|password", g):
        return "profile_settings"
    if re.search(r"review|complain|critic|rating|star|feedback|sentiment|discussion", g):
        return "feedback_analysis"
    if re.search(r"amount|price|cost|cheapest|expensive|market|compare|survey|range|count|total|date|latest|most recent|percent|percentage", g):
        return "analysis"
    if re.search(r"search|find", g):
        return "search"
    return "other"


def thought_mentions_action(thought: str, action: str) -> bool:
    family = action_family(action)
    if family == "invalid":
        return False
    return family in (thought or "").lower()


def _target_description(line: str, fallback: str) -> str:
    if not line:
        return fallback
    match = re.match(r"\[(?P<bid>\d+)\]\s+(?P<role>[A-Za-z]+)\s+(?P<name>.*)", line)
    if not match:
        return line
    role = match.group("role").lower()
    name = match.group("name").strip() or fallback
    return f"{role} {name}".strip()


def _debug_thought(subgoal: str, next_action: str, evidence: str) -> str:
    return (
        f"I need to {subgoal}. "
        f"The next action is to {next_action}. "
        f"Evidence: {evidence}."
    )


def repair_thought(thought: str, action: str, axtree: str) -> tuple[str, bool]:
    """Deterministically ground weak thoughts to a debug-friendly action rationale."""
    validation = validate_hsge_action(action, axtree)
    if not validation.ok or not validation.parsed:
        return thought, False
    has_action = thought_mentions_action(thought, action)
    has_bid = not validation.parsed.bid or validation.parsed.bid in thought
    has_debug_shape = "next action" in (thought or "").lower() and "evidence" in (thought or "").lower()
    if has_action and has_bid and has_debug_shape:
        return thought, False

    parsed = validation.parsed
    target = _target_description(validation.target_line, "the grounded element")
    match parsed.name:
        case "click":
            repaired = _debug_thought(
                f"activate the visible control [{parsed.args[0]}]",
                f"click [{parsed.args[0]}]",
                f"[{parsed.args[0]}] is {target}",
            )
        case "hover":
            repaired = _debug_thought(
                f"open or inspect the menu/control [{parsed.args[0]}]",
                f"hover [{parsed.args[0]}]",
                f"[{parsed.args[0]}] is {target}",
            )
        case "fill":
            repaired = _debug_thought(
                f"enter the required text into input [{parsed.args[0]}]",
                f"fill [{parsed.args[0]}]",
                f"[{parsed.args[0]}] is {target}",
            )
        case "type":
            submit_note = " and submit it" if len(parsed.args) >= 3 and parsed.args[2] == "1" else ""
            repaired = _debug_thought(
                f"type the required text into input [{parsed.args[0]}]{submit_note}",
                f"type [{parsed.args[0]}]",
                f"[{parsed.args[0]}] is {target}",
            )
        case "press":
            repaired = _debug_thought(
                "continue the current keyboard-driven interaction",
                f"press {parsed.args[0]}",
                f"the requested key is {parsed.args[0]}",
            )
        case "scroll":
            repaired = _debug_thought(
                "inspect more page content before deciding",
                f"scroll {parsed.args[0]}",
                "the needed information or controls may be outside the current visible region",
            )
        case "goto":
            repaired = _debug_thought(
                "navigate to the requested page",
                "goto the target URL",
                "the task or previous context provides a direct URL",
            )
        case "send_msg_to_user":
            repaired = _debug_thought(
                "answer because the requested information is available",
                "send_msg_to_user",
                "the recent visible page text contains the answer",
            )
        case _:
            repaired = thought
    return repaired, repaired != thought


def answer_has_evidence(goal: str, answer: str, recent_observations: list[str], actions: list[str]) -> bool:
    """Conservative success gate for free-form answer tasks.

    Navigation/action tasks often finish with ``send_msg_to_user('done')``. For
    information extraction tasks, require at least one meaningful answer token to
    appear in recent AXTree text. Negative feedback/content-analysis answers
    require an inspect/scroll attempt first so the solver cannot stop immediately
    above the fold.
    """
    answer_l = (answer or "").lower()
    if answer_l.strip() in {"done", "complete", "completed"}:
        return True
    goal_l = (goal or "").lower()
    obs_l = "\n".join(recent_observations[-3:]).lower()
    action_families = Counter(action_family(a) for a in actions)
    if re.search(r"review|complain|critic|rating|star|feedback|sentiment|discussion|comment", goal_l):
        evidence_markers = (
            "review", "comment", "feedback", "rating", "discussion",
            "complain", "critic", "sentiment",
        )
        if "scroll" not in action_families and not any(marker in obs_l for marker in evidence_markers):
            return False
    tokens = [
        t for t in re.findall(r"[a-z0-9$][a-z0-9$.,-]{2,}", answer_l)
        if t not in {"the", "and", "that", "this", "with", "found", "answer", "user", "not"}
    ]
    if not tokens:
        return False
    return any(t in obs_l for t in tokens[:8])
