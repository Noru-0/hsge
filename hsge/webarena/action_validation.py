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
    # Original HSGE actions
    "click",
    "fill",
    "type",
    "press",
    "scroll",
    "hover",
    "goto",
    "send_msg_to_user",
    # Go-Browse additions
    "noop",
    "select_option",
    "dblclick",
    "focus",
    "clear",
    "drag_and_drop",
    "upload_file",
    "report_infeasible",
    "go_back",
    "go_forward",
}

# Actions whose first positional arg is a BID (for grounding checks)
TARGETED_ACTIONS = {
    "click", "fill", "type", "hover",
    "dblclick", "focus", "clear", "press",
    "select_option",
}
# Actions that target input/editable elements
INPUT_ACTIONS = {"fill", "type", "clear"}
# Actions that expect two bids (from_bid, to_bid)
DUAL_BID_ACTIONS = {"drag_and_drop", "upload_file"}
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
    kwargs: dict[str, Any]
    raw: str

    @property
    def bid(self) -> str | None:
        if self.name in TARGETED_ACTIONS and self.args:
            return self.args[0]
        if self.name in DUAL_BID_ACTIONS and len(self.args) >= 1:
            return self.args[0]
        return None

    @property
    def bids(self) -> list[str]:
        """All bid arguments (for dual-bid actions like drag_and_drop)."""
        if self.name in DUAL_BID_ACTIONS and len(self.args) >= 2:
            return [self.args[0], self.args[1]]
        bid = self.bid
        return [bid] if bid else []


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str = ""
    parsed: ParsedAction | None = None
    target_line: str = ""


def _ast_value_to_str(node: ast.AST) -> str:
    """Convert an AST node to its string representation for validation.
    Handles constants (str/int/float), lists of constants, and negative numbers.
    """
    # Negative numbers: UnaryOp(USub(), Constant(value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        if isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float)):
            return str(-node.operand.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float)):
        return str(node.value)
    if isinstance(node, ast.List):
        elements = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, (str, int, float)):
                elements.append(str(elt.value))
            else:
                raise ValueError("list elements must be string or numeric literals")
        return "[" + ", ".join(repr(e) for e in elements) + "]"
    raise ValueError("action arguments must be string, numeric literals, or lists thereof")


def _ast_kwarg_to_value(node: ast.AST) -> Any:
    """Convert an AST keyword value node to its Python value."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float)):
        return node.value
    if isinstance(node, ast.List):
        return [_ast_kwarg_to_value(elt) for elt in node.elts]
    raise ValueError("keyword values must be string, numeric literals, or lists thereof")


def parse_hsge_action(action: str) -> ParsedAction:
    """Parse a canonical HSGE action string with Python's AST parser.

    Supports both HSGE-simple and Go-Browse style actions:
      - Positional args: click('332'), fill('420', 'text'), scroll(0, 200)
      - Keyword args: click('a51', button='right', modifiers=['Shift'])
      - List args: select_option('a48', ['red', 'green', 'blue'])
      - No-arg calls: go_back(), go_forward()
    """
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
    # Positional args
    args: list[str] = []
    for arg in expr.args:
        args.append(_ast_value_to_str(arg))
    # Keyword args (Go-Browse style: button='right', modifiers=['Shift'], etc.)
    kwargs: dict[str, Any] = {}
    for kw in expr.keywords:
        if kw.arg is None:
            raise ValueError("**kwargs unpacking is not supported")
        kwargs[kw.arg] = _ast_kwarg_to_value(kw.value)
    return ParsedAction(name=name, args=tuple(args), kwargs=kwargs, raw=raw)


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
    """Validate syntax and AXTree grounding for one HSGE/Go-Browse action."""
    try:
        parsed = parse_hsge_action(action)
    except ValueError as exc:
        return ValidationResult(False, str(exc))

    args = parsed.args
    name = parsed.name

    # --- No-arg actions ---
    if name in {"go_back", "go_forward"}:
        if len(args) != 0:
            return ValidationResult(False, f"{name} takes no arguments", parsed)
        return ValidationResult(True, parsed=parsed)

    # --- noop ---
    if name == "noop":
        if len(args) > 1:
            return ValidationResult(False, "noop takes 0 or 1 argument (wait_ms)", parsed)
        return ValidationResult(True, parsed=parsed)

    # --- report_infeasible ---
    if name == "report_infeasible":
        if len(args) != 1:
            return ValidationResult(False, "report_infeasible requires one reason argument", parsed)
        return ValidationResult(True, parsed=parsed)

    # --- Simple single-bid actions (click, hover, focus, dblclick) ---
    if name in {"click", "hover", "focus"}:
        if len(args) < 1:
            return ValidationResult(False, f"{name} requires at least a bid", parsed)
        # Extra kwargs (button, modifiers) are passed through — BrowserGym handles them
    if name == "dblclick":
        if len(args) < 1:
            return ValidationResult(False, "dblclick requires at least a bid", parsed)

    # --- fill ---
    if name == "fill":
        if len(args) != 2:
            return ValidationResult(False, "fill requires bid and text", parsed)

    # --- type (HSGE legacy: type(bid, text, enter_flag); Go-Browse: type(bid, text)) ---
    if name == "type":
        if len(args) < 2:
            return ValidationResult(False, "type requires bid and text", parsed)
        if len(args) == 3 and args[2] not in {"0", "1"}:
            return ValidationResult(False, "type third argument must be '0' or '1'", parsed)

    # --- press (HSGE legacy: press(key); Go-Browse: press(bid, key_comb)) ---
    if name == "press":
        if len(args) not in {1, 2}:
            return ValidationResult(False, "press requires key (legacy) or bid+key_comb", parsed)
        # Legacy single-arg press: no bid grounding needed
        if len(args) == 1:
            return ValidationResult(True, parsed=parsed)

    # --- scroll (HSGE legacy: scroll('up'|'down'); Go-Browse: scroll(delta_x, delta_y)) ---
    if name == "scroll":
        if len(args) == 1 and args[0] not in {"up", "down"}:
            return ValidationResult(False, "scroll requires 'up'/'down' or two numeric pixel values", parsed)
        if len(args) not in {1, 2}:
            return ValidationResult(False, "scroll requires 'up'/'down' or delta_x, delta_y", parsed)
        return ValidationResult(True, parsed=parsed)  # scroll needs no element grounding

    # --- clear ---
    if name == "clear":
        if len(args) != 1:
            return ValidationResult(False, "clear requires one bid", parsed)

    # --- select_option ---
    if name == "select_option":
        if len(args) < 2:
            return ValidationResult(False, "select_option requires bid and option(s)", parsed)

    # --- drag_and_drop ---
    if name == "drag_and_drop":
        if len(args) != 2:
            return ValidationResult(False, "drag_and_drop requires from_bid and to_bid", parsed)
        # Validate both bids exist
        elements = axtree_elements(axtree) if axtree else {}
        for i, bid in enumerate(args[:2]):
            if not bid.isdigit():
                return ValidationResult(False, f"drag_and_drop bid must be numeric, got {bid!r}", parsed)
            if axtree and bid not in elements:
                label = "from_bid" if i == 0 else "to_bid"
                return ValidationResult(False, f"drag_and_drop {label} {bid} not in AXTree", parsed)
        return ValidationResult(True, parsed=parsed)

    # --- upload_file ---
    if name == "upload_file":
        if len(args) < 2:
            return ValidationResult(False, "upload_file requires bid and file path(s)", parsed)

    # --- goto ---
    if name == "goto":
        if len(args) != 1:
            return ValidationResult(False, "goto requires one url argument", parsed)
        if not allow_goto:
            return ValidationResult(False, "goto is disabled for this policy; use visible UI actions instead", parsed)
        return ValidationResult(True, parsed=parsed)

    # --- send_msg_to_user ---
    if name == "send_msg_to_user":
        if len(args) != 1:
            return ValidationResult(False, "send_msg_to_user requires one message argument", parsed)
        return ValidationResult(True, parsed=parsed)

    # --- Grounding checks for targeted actions ---
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
    if name in {"click", "hover", "dblclick", "focus"} and role not in INTERACTIVE_ROLES:
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


def _narrative_thought(goal: str, action_type: str, bid: str,
                       target_desc: str, extra: str = "") -> str:
    """Generate a Go-Browse-style flowing narrative thought.

    Unlike the old template pattern ("I need to X. Evidence: Y. In summary..."),
    this produces a single natural paragraph that connects goal → page state →
    element → action in one coherent reasoning chain.
    """
    goal_text = goal.lower().rstrip('.') if goal else ""
    match action_type:
        case "click":
            return (
                f"Looking at the current page, the goal is to {goal_text}. "
                f"I can see {target_desc} at element [{bid}]. "
                f"Clicking this will advance the task."
            )
        case "hover":
            return (
                f"To {goal_text}, I first need to inspect [{bid}], "
                f"which is {target_desc}. "
                f"Hovering over it will reveal the available options or submenu."
            )
        case "dblclick":
            return (
                f"To {goal_text}, I need to double-click [{bid}], "
                f"which is {target_desc}."
            )
        case "focus":
            return (
                f"To {goal_text}, I need to focus element [{bid}], "
                f"which is {target_desc}, before interacting with it."
            )
        case "fill":
            text = extra if extra else "the required text"
            return (
                f"To {goal_text}, I need to type '{text}' into input [{bid}], "
                f"which is {target_desc}. "
                f"This is the first step of the task."
            )
        case "clear":
            return (
                f"To {goal_text}, I need to clear input [{bid}], "
                f"which is {target_desc}, before entering new text."
            )
        case "type":
            text = extra if extra else "the required text"
            submit_hint = " and submit" if extra.endswith("↵") else ""
            return (
                f"To {goal_text}, I need to type '{text}' into [{bid}]"
                f"{submit_hint}, which is {target_desc}."
            )
        case "scroll":
            direction = extra if extra else "down"
            return (
                f"The needed information or controls may be outside the current "
                f"visible region. I should scroll {direction} to inspect more "
                f"page content before deciding the next action."
            )
        case "press":
            key = extra if extra else "the requested key"
            if bid:
                return (
                    f"To {goal_text}, I need to focus [{bid}] "
                    f"({target_desc}) and press {key}."
                )
            return (
                f"Continuing the current keyboard-driven interaction, "
                f"I need to press {key}."
            )
        case "select_option":
            text = extra if extra else "the desired option"
            return (
                f"To {goal_text}, I need to select '{text}' from dropdown "
                f"[{bid}], which is {target_desc}."
            )
        case "drag_and_drop":
            return (
                f"To {goal_text}, I need to drag [{bid}] "
                f"({target_desc}) and drop it onto the target element."
            )
        case "upload_file":
            text = extra if extra else "the file"
            return (
                f"To {goal_text}, I need to upload '{text}' "
                f"using the file input [{bid}] ({target_desc})."
            )
        case "goto":
            return (
                f"The task requires navigating to a specific page. "
                f"I will go to the target URL provided by the context."
            )
        case "go_back":
            return "I need to navigate back to the previous page."
        case "go_forward":
            return "I need to navigate forward to the next page."
        case "noop":
            return "I should wait briefly for the page to settle."
        case "report_infeasible":
            return (
                f"The requested task cannot be completed: {extra}. "
                f"I will report this to the user."
            )
        case "send_msg_to_user":
            return (
                f"The task is now complete. "
                f"The current page contains the requested information, "
                f"confirming the task has been accomplished."
            )
        case _:
            return f"I need to perform the {action_type} action to advance the task."
    return ""  # unreachable


def repair_thought(thought: str, action: str, axtree: str,
                   goal: str = "") -> tuple[str, bool]:
    """Deterministically ground weak thoughts to Go-Browse-style narrative.

    When `goal` is provided, produces a flowing natural-language paragraph
    (no template markers like "Evidence:" or "In summary"). For send_msg_to_user,
    generates a task-completion statement instead of goal-prefixed text.
    """
    validation = validate_hsge_action(action, axtree)
    if not validation.ok or not validation.parsed:
        return thought, False
    # Keep original if it's already a rich narrative (not the old template)
    is_template = ("evidence:" in (thought or "").lower()
                   or "in summary" in (thought or "").lower()
                   or "next action" in (thought or "").lower())
    if not is_template and thought_mentions_action(thought, action):
        return thought, False

    parsed = validation.parsed
    target = _target_description(validation.target_line, "the grounded element")
    bid = parsed.args[0] if parsed.args else ""

    match parsed.name:
        case "click":
            repaired = _narrative_thought(goal, "click", bid, target)
        case "hover":
            repaired = _narrative_thought(goal, "hover", bid, target)
        case "dblclick":
            repaired = _narrative_thought(goal, "dblclick", bid, target)
        case "focus":
            repaired = _narrative_thought(goal, "focus", bid, target)
        case "fill":
            text = parsed.args[1] if len(parsed.args) >= 2 else ""
            repaired = _narrative_thought(goal, "fill", bid, target, extra=text)
        case "clear":
            repaired = _narrative_thought(goal, "clear", bid, target)
        case "type":
            text = parsed.args[1] if len(parsed.args) >= 2 else ""
            if len(parsed.args) >= 3 and parsed.args[2] == "1":
                text += "↵"
            repaired = _narrative_thought(goal, "type", bid, target, extra=text)
        case "press":
            key = parsed.args[0] if len(parsed.args) == 1 else (parsed.args[1] if len(parsed.args) >= 2 else "")
            repaired = _narrative_thought(goal, "press", bid, target, extra=key)
        case "scroll":
            direction = parsed.args[0] if len(parsed.args) == 1 else "by pixels"
            repaired = _narrative_thought(goal, "scroll", bid, "", extra=direction)
        case "select_option":
            opt = parsed.args[1] if len(parsed.args) >= 2 else ""
            repaired = _narrative_thought(goal, "select_option", bid, target, extra=opt)
        case "drag_and_drop":
            repaired = _narrative_thought(goal, "drag_and_drop", bid, target)
        case "upload_file":
            fname = parsed.args[1] if len(parsed.args) >= 2 else ""
            repaired = _narrative_thought(goal, "upload_file", bid, target, extra=fname)
        case "goto":
            repaired = _narrative_thought(goal, "goto", bid, "")
        case "go_back":
            repaired = _narrative_thought(goal, "go_back", "", "")
        case "go_forward":
            repaired = _narrative_thought(goal, "go_forward", "", "")
        case "noop":
            repaired = _narrative_thought(goal, "noop", "", "")
        case "report_infeasible":
            reason = parsed.args[0] if parsed.args else ""
            repaired = _narrative_thought(goal, "report_infeasible", "", "", extra=reason)
        case "send_msg_to_user":
            repaired = _narrative_thought("", "send_msg_to_user", "", "")
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
