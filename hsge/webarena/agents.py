"""LLM agents for WebArena exploration:
  - PageExplorer: proposes feasible tasks for the current page (local task source)
  - Solver: an action-planner loop that drives the browser toward a goal

Both take an `LLM` backend (use hsge.backends.OpenAILLM for real runs, MockLLM
for dry runs). The Solver returns a list of `Step`, which feeds HSGE Discovery.
"""
from __future__ import annotations

import json
import re
from collections import Counter, deque
from urllib.parse import urlparse

from ..schema import Step
from .action_validation import (
    action_family,
    axtree_elements,
    answer_has_evidence,
    parse_hsge_action,
    repair_thought,
    validate_hsge_action,
)
from .predicates import PredicateExtractor, predicates_from, reached

# Full action space documentation (Go-Browse style) placed in solver user prompts.
_ACTION_SPACE_DOC = """\
# Action Space
17 different types of actions are available.

noop(wait_ms: float = 1000)
  Description: Do nothing, and optionally wait for the given time (in milliseconds).
  Examples:
  noop()
  noop(500)

send_msg_to_user(text: str)
  Description: Sends a message to the user. Use when the task is
  complete to report the result, or to communicate findings.
  Examples:
  send_msg_to_user('Based on the results of my search, the city was built in 1751.')
  send_msg_to_user('The product details page has been opened successfully.')

scroll(delta_x: float, delta_y: float)
  Description: Scroll horizontally and vertically. Amounts in pixels,
  positive for right or down scrolling, negative for left or up scrolling.
  Dispatches a wheel event.
  Examples:
  scroll(0, 200)
  scroll(-50.2, -100.5)

fill(bid: str, value: str)
  Description: Fill out a form field. Focuses the element and types the text.
  Works for textbox, searchbox, and combobox elements.
  Examples:
  fill('332', 'controller')
  fill('420', 'Emma Lopez')

select_option(bid: str, options: str | list[str])
  Description: Select one or multiple options in a <select> element.
  You can specify option value or label to select. Multiple options can be selected.
  Examples:
  select_option('a48', 'blue')
  select_option('c48', ['red', 'green', 'blue'])

click(bid: str, button: str = 'left', modifiers: list[str] = [])
  Description: Click an element by its numeric id from the accessibility tree.
  Optional: button ('left', 'middle', 'right') and modifiers (e.g. ['Shift', 'Control']).
  Examples:
  click('332')
  click('1480')
  click('b22', button='right')
  click('48', button='middle', modifiers=['Shift'])

dblclick(bid: str, button: str = 'left', modifiers: list[str] = [])
  Description: Double click an element by its numeric id.
  Examples:
  dblclick('12')
  dblclick('ca42', button='right')

hover(bid: str)
  Description: Hover over an element by its numeric id.
  Examples:
  hover('332')

press(bid: str, key_comb: str)
  Description: Focus the matching element and press a combination of keys.
  Supported keys: Enter, Escape, Backspace, ArrowDown, ArrowUp, ArrowLeft,
  ArrowRight, Tab, PageDown, PageUp, Home, End, F1-F12, Digit0-Digit9,
  KeyA-KeyZ, etc. Supports modifiers: Shift, Control, Alt, Meta, ControlOrMeta.
  Examples:
  press('88', 'Backspace')
  press('a26', 'ControlOrMeta+a')
  press('a61', 'Meta+Shift+t')

focus(bid: str)
  Description: Focus the matching element.
  Examples:
  focus('b455')

clear(bid: str)
  Description: Clear the input field.
  Examples:
  clear('996')

drag_and_drop(from_bid: str, to_bid: str)
  Description: Perform a drag & drop. Hover the element that will be dragged.
  Press left mouse button. Move mouse to the element that will receive the drop.
  Release left mouse button.
  Examples:
  drag_and_drop('56', '498')

upload_file(bid: str, file: str | list[str])
  Description: Click an element and wait for a file chooser event,
  then select one or multiple files for upload. Relative file paths are resolved
  relative to the current working directory.
  Examples:
  upload_file('572', 'my_receipt.pdf')
  upload_file('63', ['/home/bob/Documents/image.jpg', '/home/bob/Documents/file.zip'])

report_infeasible(reason: str)
  Description: Notifies the user that their instructions are infeasible.
  Examples:
  report_infeasible('I cannot follow these instructions because there is no email field in this form.')

go_back()
  Description: Navigate to the previous page in history.
  Examples:
  go_back()

go_forward()
  Description: Navigate to the next page in history.
  Examples:
  go_forward()

goto(url: str)
  Description: Navigate to a URL. Only use when the exact URL
  is explicitly present in the goal or page context.
  Examples:
  goto('http://www.example.com')

# Output Format
Respond with a JSON object:
{"thought": "<step-by-step reasoning connecting goal → page → element → action>",
 "action": "<one action>"}

The thought MUST explain: what subgoal you are pursuing, which element
(bid) you are interacting with and why, and the visible evidence from
the page that supports your choice.

Here are examples of actions with chain-of-thought reasoning:

{"thought": "I now need to click on the Submit button to send the form. I will use the click action on the button, which has bid 12.", "action": "click('12')"}

{"thought": "I found the information requested by the user, I will send it to the chat.", "action": "send_msg_to_user('The price for a 15 inch laptop is 1499 USD.')"}

{"thought": "I have finished navigating to the Products page. I will inform the user that I have completed the task.", "action": "send_msg_to_user('I have finished navigating to the Products page.')"}

Only a single action can be provided at once."""

# Legacy short doc kept for backward compatibility with other consumers.
ACTIONS_DOC = ("Allowed actions (return exactly one): click('bid'), "
               "fill('bid','text'), type('bid','text'), "
               "press('bid','key_comb'), scroll(delta_x,delta_y), hover('bid'), "
               "dblclick('bid'), focus('bid'), clear('bid'), "
               "select_option('bid','option'), drag_and_drop('from','to'), "
               "upload_file('bid','path'), noop(), go_back(), go_forward(), "
               "report_infeasible('reason'), "
               "goto('url') only when the exact URL is explicitly present in the goal/page context, "
               "send_msg_to_user('done message').")

EXPLORER_SYS = (
    "You are building a training dataset for a web agent that performs tasks in a browser. "
    "Your job is to PROPOSE concrete, feasible tasks from the CURRENT page. "
    "The agent that will execute these tasks may start from a different page, so each task "
    "must be self-contained and specific enough to understand without seeing this page.\n\n"
    "=== TASK TYPES ===\n"
    "Prefix every task with exactly one type tag:\n"
    "  [INFO] — Information seeking: obtain facts, prices, reviews, counts, dates, comparisons\n"
    "  [NAV]  — Navigation: go to a specific page, section, or view\n"
    "  [MOD]  — Content modification: add to cart, fill a form, change a setting, post a comment\n\n"
    "=== TASK QUALITY RULES ===\n"
    "1. BE SPECIFIC: \"[MOD] Add the Sony WH-1000XM5 headphones to the cart\" NOT \"[MOD] Add item to cart\".\n"
    "   Include the actual product name, person, date, or value visible on the page.\n"
    "2. SELF-CONTAINED: A solver reading only the task text (without seeing this page) must understand\n"
    "   exactly what to do. Use visible names, labels, and values — never rely on implicit page context.\n"
    "3. EXPLORATION ORDER — propose tasks in this priority:\n"
    "   a) [INFO] tasks answerable from visible content with no interaction\n"
    "   b) [NAV] tasks for links/buttons that lead to interesting pages\n"
    "   c) [MOD] tasks requiring form input, selection, or state changes\n"
    "4. FOCUS ON COMMON TASKS: prioritize what a typical user of this website would want to do.\n"
    "   Avoid niche or edge-case tasks. For frequent task patterns, include 1-2 variants to help\n"
    "   the agent learn reusable skills (e.g. add different visible products to cart).\n"
    "5. Each task should require 1-3 primitive actions with a clear stop condition.\n"
    "   Do NOT return action chains with arrows like A -> B -> C.\n\n"
    "=== SAFETY ===\n"
    "- NEVER invent names, categories, people, quantities, amounts, dates, or IDs not visible on the page.\n"
    "- NEVER propose login, sign in, sign up, register, or account creation — agent is already logged in.\n"
    "- NEVER propose irreversible commit, payment, place-order, or destructive tasks.\n"
    "  For checkout/order-flow controls, propose inspection/report tasks instead.\n"
    "- If cart, checkout, address, shipping, payment, review, or confirmation controls are visible,\n"
    "  include a safe inspection task that reports the next required step without submitting.\n\n"
    "=== OUTPUT ===\n"
    "Return JSON: {\"tasks\": [\"[INFO] ...\", \"[NAV] ...\", \"[MOD] ...\", ...]}\n"
    "Aim for 6-12 diverse tasks covering all applicable types."
)

def _build_solver_sys(context_hints: str = "") -> str:
    """Short system role (Go-Browse style). Action space goes in user prompt."""
    base = (
        "You are a web agent. Your goal is to help the user perform tasks "
        "using a web browser. Review the goal, the current page accessibility "
        "tree (elements shown as [bid] role 'name'), and your history of "
        "past actions to find the best next action. "
        "Your answer will be interpreted and executed by a program — "
        "follow the formatting instructions exactly. "
        "IMPORTANT: The accessibility tree only shows visible elements. "
        "If you need to find content that may be further down the page, "
        "scroll down first (e.g., scroll(0, 300)) before concluding the "
        "element is absent. Scroll saturation is detected automatically — "
        "stop scrolling once the page content stops changing."
    )
    parts = [context_hints, base]
    return "\n".join(p for p in parts if p)


class PageExplorer:
    def __init__(
        self,
        llm,
        max_tasks: int = 12,
        profile: str = "training_quality",
        checkout_mode: str = "safe",
        place_order_allowed: bool = False,
    ):
        self.llm = llm
        self.max_tasks = max_tasks
        self.profile = profile
        self.checkout_mode = checkout_mode
        self.place_order_allowed = place_order_allowed
        self.rejected_task_counts: Counter[str] = Counter()

    _LOGIN_KEYWORDS = [
        "login", "sign in", "signin", "sign up", "signup",
        "register", "create account", "log in", "log into",
        "authenticate", "forgot password", "reset password",
    ]
    _RISKY_CONTROL_GROUPS = {
        "destructive": (
            r"\b(delete|remove|cancel|archive|deactivate|disable|close)\b",
            r"\b(delete|remove|cancel|archive|deactivate|disable|close)\b",
        ),
        "commit": (
            r"\b(submit|send|publish|post|save|apply|confirm|book|reserve)\b",
            r"\b(submit|send|publish|post|save|apply|confirm|book|reserve)\b",
        ),
        "commit_or_transaction_flow": (
            r"\b(checkout|purchase|buy now|place order|payment|pay|refund|return item)\b",
            r"\b(checkout|purchase|buy now|place order|payment|pay|refund|return|order)\b",
        ),
        "account_or_record_update": (
            r"\b(update|change|edit)\b.*\b(address|profile|settings|preference|password|quantity|record|ticket|issue)\b",
            r"\b(update|change|edit|save|address|profile|settings|preference|password|quantity|record|ticket|issue)\b",
        ),
    }

    @classmethod
    def _is_login_task(cls, task: str) -> bool:
        """Check if a task is login/registration related."""
        task_lower = task.lower()
        return any(kw in task_lower for kw in cls._LOGIN_KEYWORDS)

    _VALID_TAGS = {"[INFO]", "[NAV]", "[MOD]"}

    @classmethod
    def _normalize_task_tag(cls, task: str) -> tuple[str, bool]:
        """Ensure task starts with a valid [INFO]/[NAV]/[MOD] tag. Returns (normalized_task, ok)."""
        for tag in cls._VALID_TAGS:
            if task.startswith(tag):
                return (task, True)
        # Try to auto-tag based on content keywords
        task_lower = task.lower()
        if re.search(r'\b(add|fill|type|select|change|modify|update|delete|remove|post|submit|set|configure|upload|edit)\b', task_lower):
            return (f"[MOD] {task}", True)
        if re.search(r'\b(navigate|go to|open|visit|find|browse)\b', task_lower):
            return (f"[NAV] {task}", True)
        if re.search(r'\b(read|report|inspect|review|check|list|show|tell|identify|compare|count|how many|what|which|describe|summarize|look up|find out)\b', task_lower):
            return (f"[INFO] {task}", True)
        return (task, False)

    def propose(self, obs: dict) -> list[str]:
        sys = EXPLORER_SYS
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}"
        seeded_tasks = self._seed_tasks(obs) if self.profile == "training_quality" else []
        screenshot = obs.get("screenshot_base64")
        use_vision = screenshot and getattr(self.llm, "supports_vision", False)
        if use_vision:
            out = self.llm.complete_vision_json(sys, prompt, screenshot_base64=screenshot)
        else:
            out = self.llm.complete_json(sys, prompt)
        llm_tasks, rejected = self._filter_llm_tasks(out.get("tasks", []), obs)
        if rejected:
            self.rejected_task_counts.update(rejected)
            summary = ", ".join(f"{reason}={count}" for reason, count in rejected.items())
            print(f"  [tasks] Filtered {sum(rejected.values())} weak proposal(s): {summary}")
        tasks = seeded_tasks + llm_tasks
        deduped = []
        seen = set()
        for task in tasks:
            key = task.lower().strip()
            if key and key not in seen:
                deduped.append(task)
                seen.add(key)
        return deduped[: self.max_tasks]

    def _filter_llm_tasks(self, tasks: list[str], obs: dict) -> tuple[list[str], Counter[str]]:
        """Keep only local, grounded task proposals suitable for training data."""
        page_text = self._visible_text(obs)
        affordances = self._page_affordances(obs)
        filtered: list[str] = []
        rejected: Counter[str] = Counter()
        for task in tasks:
            if not isinstance(task, str):
                rejected["non_string"] += 1
                continue
            task = re.sub(r"\s+", " ", task).strip()
            if not task or self._is_login_task(task):
                rejected["login_or_empty"] += 1
                continue
            # Validate and normalize task type tag
            task, tag_ok = self._normalize_task_tag(task)
            if not tag_ok:
                rejected["missing_or_invalid_tag"] += 1
                continue
            if self._looks_like_action_chain(task):
                rejected["action_chain"] += 1
                continue
            if self._looks_too_complex(task):
                rejected["too_complex"] += 1
                continue
            if not self._quoted_phrases_are_visible(task, page_text):
                rejected["ungrounded_quote"] += 1
                continue
            if not self._task_matches_page_affordance(task, affordances):
                rejected["missing_page_affordance"] += 1
                continue
            if self._needs_missing_risky_control(task, page_text):
                rejected["missing_risky_control"] += 1
                continue
            filtered.append(task)
        return filtered, rejected

    def _visible_text(self, obs: dict) -> str:
        axtree = obs.get("axtree", "")
        elements = axtree_elements(axtree)
        lines = [line for _, line in elements.values()]
        return "\n".join(lines).lower()

    def _looks_like_action_chain(self, task: str) -> bool:
        if "->" in task or "→" in task:
            return True
        separators = len(re.findall(r"\b(?:then|and then|after that|next)\b", task.lower()))
        return separators >= 2

    def _looks_too_complex(self, task: str) -> bool:
        words = re.findall(r"\w+", task)
        if len(words) > 24:
            return True
        verbs = re.findall(
            r"\b(open|search|select|click|view|read|add|update|change|edit|"
            r"proceed|checkout|compare|filter|sort|submit|identify|answer|draft|send|"
            r"publish|post|save|apply|book|reserve|delete|remove|cancel)\b",
            task.lower(),
        )
        return len(verbs) > 4

    def _quoted_phrases_are_visible(self, task: str, page_text: str) -> bool:
        quoted = re.findall(r"'([^']+)'|\"([^\"]+)\"", task)
        for single, double in quoted:
            phrase = (single or double).strip().lower()
            if len(phrase) > 2 and phrase not in page_text:
                return False
        return True

    def _needs_missing_risky_control(self, task: str, page_text: str) -> bool:
        task_lower = task.lower()
        for _, (task_pattern, page_pattern) in self._RISKY_CONTROL_GROUPS.items():
            if re.search(task_pattern, task_lower) and not re.search(page_pattern, page_text):
                return True
        return False

    def _page_affordances(self, obs: dict) -> dict[str, bool]:
        lines = self._interactive_lines(obs)
        all_text = self._visible_text(obs)
        visible_content = self._content_text_without_bids(obs.get("axtree", ""))
        return {
            "search": self._has_line(lines, r"\bsearch\b"),
            "feedback": bool(re.search(r"review|comments?|feedback|discussion|rating|stars?", all_text)),
            "hover": self._has_line(lines, r"haspopup|menuitem"),
            "filter_sort": self._has_line(lines, r"sort|filter|refine|facet"),
            "state_change": self._has_line(
                lines,
                r"add|submit|send|save|apply|confirm|continue|next|"
                r"book|reserve|subscribe|delete|remove|cancel|compare",
            ),
            "profile": self._has_line(lines, r"account|profile|settings|address|preferences"),
            "history": self._has_line(lines, r"history|status|orders?|tickets?|requests?|cases?|incidents?"),
            "communication": self._has_line(lines, r"contact|message|email|reply|draft"),
            "numeric": bool(re.search(r"\$|amount|cost|total|date|latest|recent|percent|%|\b\d+(?:[.,]\d+)?\b", visible_content)),
            "deep_progression": self._has_line(
                lines,
                self._progression_pattern(),
            ),
            "transaction_flow": self._has_line(
                lines,
                r"cart|checkout|shipping|payment|billing|review order|place order|"
                r"proceed|continue|next|order summary",
            ),
            "address_form": self._has_line(lines, r"address|street|city|state|zip|postal|country|phone"),
            "shipping_payment": self._has_line(lines, r"shipping|payment|billing|method"),
            "order_review": self._has_line(lines, r"review order|order summary|subtotal|grand total|place order"),
        }

    def _task_matches_page_affordance(self, task: str, affordances: dict[str, bool]) -> bool:
        task_l = task.lower()
        required = [
            ("communication", r"communication|contact|message|email|\bform\b|required fields"),
            ("history", r"history|records?|orders?|tickets?|requests?|cases?|incidents?"),
            ("profile", r"profile|settings|address|account|preferences"),
            ("filter_sort", r"sort|filter|narrow|refine|facet"),
            ("feedback", r"feedback|review|rating|comments?|discussion"),
            ("search", r"\bsearch\b|\bfind\b"),
            ("hover", r"\bhover\b|submenu|expandable"),
            ("numeric", r"numeric|dated|amount|price|cost|total|count|compare|latest|recent"),
            ("deep_progression", r"confirm|continue|next|required step"),
            ("transaction_flow", r"cart|checkout|payment|shipping|billing|review order|place order|order summary"),
        ]
        for key, pattern in required:
            if re.search(pattern, task_l) and not affordances.get(key, False):
                return False
        return True

    def _interactive_lines(self, obs: dict) -> list[str]:
        axtree = obs.get("axtree", "")
        elements = axtree_elements(axtree)
        out: list[str] = []
        for role, line in elements.values():
            if role in {
                "button", "link", "checkbox", "radio", "menuitem",
                "option", "tab", "combobox", "textbox", "searchbox",
            }:
                out.append(line)
        return out

    @staticmethod
    def _has_line(lines: list[str], pattern: str) -> bool:
        return any(re.search(pattern, line, re.IGNORECASE) for line in lines)

    def _first_label(self, lines: list[str], pattern: str) -> str:
        for line in lines:
            if re.search(pattern, line, re.IGNORECASE):
                quoted = re.findall(r"'([^']+)'|\"([^\"]+)\"", line)
                for single, double in quoted:
                    label = (single or double).strip()
                    if label:
                        return label
                return re.sub(r"\s+", " ", line).strip()
        return ""

    def _seed_tasks(self, obs: dict) -> list[str]:
        """Deterministic small-skill tasks to improve SFT coverage. All tagged with [INFO]/[NAV]/[MOD]."""
        axtree = obs.get("axtree", "")
        lines = self._interactive_lines(obs)
        lower = "\n".join(lines).lower()
        all_text = self._visible_text(obs)
        tasks: list[str] = []

        deep_label = self._first_label(lines, self._progression_pattern())
        if deep_label and not self._is_pagination_control(deep_label, all_text):
            if self._is_final_order_control(deep_label) and not self.place_order_allowed:
                tasks.append(f"[INFO] Review the visible '{deep_label}' final order control and report what confirmation would be required before using it.")
            elif self.checkout_mode != "discover-only":
                tasks.append(f"[INFO] Use the visible '{deep_label}' progression control and report the next required step or confirmation that appears.")
            else:
                tasks.append(f"[INFO] Inspect the visible '{deep_label}' progression control and report the next required step without submitting it.")

        search_label = self._first_label(lines, r"\b(searchbox|textbox|combobox)\b.*search")
        if search_label:
            tasks.append(f"[NAV] Use the visible '{search_label}' search field to submit a page-relevant search.")

        feedback_label = self._first_label(lines, r"reviews?|comments?|feedback|discussion|rating|stars?")
        if feedback_label:
            feedback_count = self._feedback_count(feedback_label)
            if feedback_count:
                tasks.append(f"[INFO] Report the visible feedback count shown by '{feedback_label}'.")
            else:
                tasks.append(f"[INFO] Report whether the visible '{feedback_label}' feedback control indicates available feedback.")

        hover_label = self._first_label(lines, r"haspopup|menuitem")
        if hover_label:
            tasks.append(f"[INFO] Hover over the visible '{hover_label}' menu or expandable control and report one submenu option that appears.")

        filter_label = self._first_label(lines, r"sort by|filter|facet|refine")
        if filter_label:
            tasks.append(f"[INFO] Open the visible '{filter_label}' sort or filter control and report one available option.")

        state_label = self._first_label(
            lines,
            r"checkout|payment|pay|place order|subscribe|apply|book|reserve|submit|send|"
            r"publish|post|save|confirm|continue|next|delete|remove|cancel|compare|wishlist|cart",
        )
        if state_label:
            tasks.append(f"[INFO] Open the visible '{state_label}' state-changing control and report the available action.")

        if self.checkout_mode != "discover-only":
            checkout_label = self._first_label(lines, r"proceed to checkout|checkout|cart|shipping|payment|billing|review order|order summary")
            if checkout_label:
                tasks.append(f"[INFO] Use the visible '{checkout_label}' checkout or order-flow control and report the next required step.")
        payment_label = self._first_label(lines, r"shipping method|payment method|billing|order summary|grand total|subtotal")
        if payment_label:
            tasks.append(f"[INFO] Review the visible '{payment_label}' order-flow section and report one required option or summary detail.")
        address_label = self._first_label(lines, r"street address|address|city|state|zip|postal|country|phone")
        if address_label:
            tasks.append(f"[INFO] Inspect the visible '{address_label}' address or checkout field and report what input is required.")

        profile_label = self._first_label(lines, r"my account|account|profile|settings|address book|address|preferences")
        if profile_label:
            tasks.append(f"[NAV] Open the visible '{profile_label}' account or settings control and report one visible option.")

        history_label = self._first_label(lines, r"my orders|orders?|ticket|issue|request|case|incident|history|refund|reorder")
        if history_label:
            tasks.append(f"[INFO] Open the visible '{history_label}' history or record-status control and answer one detail.")

        communication_label = self._first_label(lines, r"contact us|contact|message|email|reply|draft")
        if communication_label:
            tasks.append(f"[INFO] Open the visible '{communication_label}' communication control and report one visible field or option.")

        numeric_hint = self._first_visible_snippet(
            axtree,
            r"\$|price|amount|cost|compare|count|total|date|latest|recent|percent|%|\b\d+(?:[.,]\d+)?\b",
        )
        if numeric_hint:
            tasks.append(f"[INFO] Read the visible numeric or dated detail near '{numeric_hint}' and answer a simple lookup question.")
        return tasks[:6]

    @staticmethod
    def _progression_pattern() -> str:
        return (
            r"\b(proceed(?: to checkout)?|checkout|continue|next|confirm|"
            r"review order|complete|finish|submit|place order)\b"
        )

    @staticmethod
    def _is_final_order_control(label: str) -> bool:
        return bool(re.search(r"\b(place order|pay now|complete order|submit order)\b", label or "", re.I))

    @staticmethod
    def _is_pagination_control(label: str, page_text: str = "") -> bool:
        text = f"{label or ''}\n{page_text or ''}"
        if re.search(r"\b(checkout|shipping|billing|payment|review order|order summary|place order)\b", text, re.I):
            return False
        if re.search(r"\b(page\s+next|next\s+page|pagination|pager)\b", label or "", re.I):
            return True
        visible_words = re.findall(r"[A-Za-z]+", label or "")
        return visible_words and visible_words[-1].lower() == "next" and bool(
            re.search(r"\b(gallery|carousel|image|photo|product)\b", page_text or "", re.I)
        )

    @staticmethod
    def _feedback_count(label: str) -> str:
        match = re.search(r"\b(\d+)\s*(?:reviews?|comments?|ratings?|feedback)\b", label, re.I)
        return match.group(1) if match else ""

    def _first_visible_snippet(self, axtree: str, pattern: str) -> str:
        for line in (axtree or "").splitlines():
            text = re.sub(r"^\s*(?:\[\d+\]\s+)?[A-Za-z]+\s+", "", line).strip()
            text = re.sub(r"\s+", " ", text)
            if re.search(pattern, text, re.IGNORECASE):
                if text:
                    return text[:80]
        return ""

    @staticmethod
    def _content_text_without_bids(axtree: str) -> str:
        lines: list[str] = []
        for line in (axtree or "").splitlines():
            text = re.sub(r"^\s*(?:\[\d+\]\s+)?[A-Za-z]+\s+", "", line).strip()
            if text:
                lines.append(text)
        return "\n".join(lines).lower()


class Solver:
    def __init__(self, llm, max_steps: int = 15, profile: str = "training_quality"):
        self.llm = llm
        self.max_steps = max_steps
        self.profile = profile

    def solve(self, browser, goal: str, goal_predicate: str | None = None,
              context_hints: str = "",
              step_callback=None,
              predicate_extractor: PredicateExtractor | None = None):
        """Drive the browser toward `goal`.
        Returns (steps, obs_texts, final_obs, success, screenshots).
        screenshots is list[bytes|None] parallel to steps.

        If `step_callback` is provided, it is called after each step with:
            step_callback(action, url_before, url_after, traj_steps_so_far)
        This enables real-time URL discovery (callback-based, not DOM-query).
        """
        # Strip [INFO]/[NAV]/[MOD] tag prefix if present — these are dataset
        # metadata, not part of the agent's goal instruction.
        cleaned_goal = re.sub(r'^\[(?:INFO|NAV|MOD)\]\s*', '', goal)
        steps: list[Step] = []
        obs_texts: list[str] = []
        screenshots: list[bytes | None] = []
        history: list[str] = []
        last_action_str = "(none)"
        last_result_url = ""
        sys = _build_solver_sys(context_hints)
        obs = browser.observation()
        success = False
        prev_url = obs.get("url", "")
        invalid_attempts = 0
        recent_pairs = deque(maxlen=8)
        recent_scroll_signatures = deque(maxlen=5)
        for _ in range(self.max_steps):
            prompt_text = (
                f"# Goal\n{cleaned_goal}\n\n"
                f"# Current page Accessibility Tree\n{obs['axtree'][:6000]}\n\n"
                f"{_ACTION_SPACE_DOC}\n\n"
                f"# History of past actions\n"
                + ("\n".join(f"- {h}" for h in history[-5:]) or "(none)")
                + f"\n\n# Last action\n{last_action_str}\n"
                + (f"# Resulting URL\n{last_result_url}\n" if last_result_url else "")
                + f"\n# Next action"
            )

            screenshot = obs.get("screenshot_base64")
            use_vision = screenshot and getattr(self.llm, "supports_vision", False)
            if use_vision:
                out = self.llm.complete_vision_json(
                    sys, prompt_text, screenshot_base64=screenshot)
            else:
                out = self.llm.complete_json(sys, prompt_text)
            action = (out.get("action") or "").strip()
            thought = out.get("thought", "")

            validation = validate_hsge_action(
                action,
                obs.get("axtree", ""),
                allow_goto=self._allow_goto(action, goal, obs),
            )
            if not validation.ok:
                invalid_attempts += 1
                last_action_str = (
                    f"ERROR: Invalid action {action!r}. {validation.reason}. "
                    "Return exactly one grounded canonical action using a visible numeric BID."
                )
                last_result_url = obs.get("url", "")
                if invalid_attempts >= 3:
                    break
                continue
            invalid_attempts = 0

            thought, _ = repair_thought(thought, action, obs.get("axtree", ""))
            target_role = ""
            target_name = ""
            if validation.target_line:
                match = re.match(
                    r"^\s*\[(?:\w+)\]\s+(?P<role>[A-Za-z]+)\s+(?P<name>.*)$",
                    validation.target_line,
                )
                if match:
                    target_role = match.group("role").lower()
                    target_name = re.sub(r"\s+", " ", match.group("name")).strip()
            planning = {
                "schema_version": getattr(predicate_extractor, "schema_version", "core-v2"),
                "pre_url": obs.get("url", ""),
                "pre_predicates": sorted(predicates_from(
                    obs.get("url", ""), obs.get("axtree", ""), predicate_extractor
                )),
                "target_bid": validation.parsed.bid if validation.parsed else None,
                "target_role": target_role,
                "target_name": target_name,
                "target_fingerprint": f"{target_role}|{target_name.lower()}",
            }
            steps.append(Step(
                action=action, url=obs["url"], obs_summary=thought,
                misc={"planning": planning},
            ))
            obs_texts.append(obs["axtree"])
            screenshots.append(obs.get("screenshot_base64"))
            if not action or action.startswith("send_msg_to_user"):
                planning["post_url"] = obs.get("url", "")
                planning["post_predicates"] = planning["pre_predicates"]
                break
            try:
                url_before_action = obs.get("url", "")
                sig_before_action = self._obs_signature(obs)
                obs = browser.act(action)
            except Exception as e:
                err_msg = f"{type(e).__name__}: {e}"
                steps[-1].obs_summary += f" [action error: {err_msg}]"
                # Timeout during navigation wait after click is normal for
                # AJAX-heavy commerce sites — the action itself succeeded
                # (element was clicked), the page just didn't reload.
                # Don't break; let the solver observe the result and continue.
                if isinstance(e, TimeoutError):
                    history.append(action)
                    last_action_str = (
                        f"{{'thought': {thought[:80]}, 'action': {action[:80]}, "
                        f"'note': 'action executed but navigation timed out (site may use AJAX)'}}"
                    )
                    last_result_url = obs.get("url", "")
                    new_url = obs.get("url", "")
                    if step_callback:
                        step_callback(action, prev_url, new_url, steps)
                    prev_url = new_url
                    continue
                break
            planning["post_url"] = obs.get("url", "")
            planning["post_predicates"] = sorted(predicates_from(
                obs.get("url", ""), obs.get("axtree", ""), predicate_extractor
            ))
            if obs.get("_action_error"):
                action_err = obs["_action_error"]
                elapsed = obs.get("_action_elapsed_ms", 0)
                steps[-1].obs_summary += (
                    f" [action error: {action_err}; "
                    f"elapsed_ms={elapsed}]"
                )
                # Timeout during post-click navigation wait: the click itself
                # resolved and was performed.  The page likely used AJAX.
                # Continue the loop so the solver can work with the result.
                is_nav_timeout = (
                    "Timeout" in str(action_err)
                    and "navigation" in str(action_err).lower()
                ) or obs.get("_action_timed_out", False)
                if is_nav_timeout:
                    history.append(action)
                    last_action_str = (
                        f"{{'thought': {thought[:80]}, 'action': {action[:80]}, "
                        f"'note': 'action executed but navigation timed out "
                        f"({elapsed}ms, site may use AJAX)'}}"
                    )
                    last_result_url = obs.get("url", "")
                    new_url = obs.get("url", "")
                    if step_callback:
                        step_callback(action, prev_url, new_url, steps)
                    prev_url = new_url
                    continue
                break
            history.append(action)
            last_action_str = f"{{'thought': {thought[:80]}, 'action': {action[:80]}}}"
            last_result_url = obs.get("url", "")
            if self._is_repeating_loop(recent_pairs, action, url_before_action, obs.get("url", "")):
                steps[-1].obs_summary += " [loop detected: repeated action/url transition]"
                break
            if action_family(action) == "scroll":
                sig_after_action = self._obs_signature(obs)
                recent_scroll_signatures.append((sig_before_action, sig_after_action))
                if self._scroll_saturated(recent_scroll_signatures):
                    steps[-1].obs_summary += " [scroll saturation: page content did not change]"
                    break
            else:
                recent_scroll_signatures.clear()

            # Step callback for URL discovery
            new_url = obs.get("url", "")
            if step_callback:
                step_callback(action, prev_url, new_url, steps)
            prev_url = new_url

            if goal_predicate and reached(
                goal_predicate, obs["url"], obs["axtree"], predicate_extractor
            ):
                success = True
                break

        # success for non-predicate goals = agent declared done without error
        if goal_predicate is None and steps and steps[-1].action.startswith("send_msg_to_user"):
            parsed = validate_hsge_action(steps[-1].action, obs.get("axtree", "")).parsed
            answer = parsed.args[0] if parsed and parsed.args else ""
            actions = [s.action for s in steps]
            success = (
                answer_has_evidence(goal, answer, obs_texts, actions)
                and self._terminal_success_gate(goal, answer, obs, obs_texts, actions)
            )
        return steps, obs_texts, obs, success, screenshots

    def _allow_goto(self, action: str, goal: str, obs: dict) -> bool:
        """Permit goto only for explicit URLs already present in context."""
        try:
            parsed = parse_hsge_action(action)
        except ValueError:
            return True
        if parsed.name != "goto":
            return True
        target = parsed.args[0] if parsed.args else ""
        if not target:
            return False
        context = "\n".join([goal or "", obs.get("url", ""), obs.get("axtree", "")])
        if target in context:
            return True
        target_host = urlparse(target).netloc
        current_host = urlparse(obs.get("url", "")).netloc
        if target_host and current_host and target_host != current_host:
            return False
        return False

    @staticmethod
    def _obs_signature(obs: dict) -> str:
        axtree = obs.get("axtree", "") or ""
        lines = [ln.strip() for ln in axtree.splitlines() if ln.strip()]
        return "\n".join(lines[:40])

    @staticmethod
    def _is_repeating_loop(recent_pairs, action: str, url_before: str, url_after: str) -> bool:
        pair = (action, url_before, url_after)
        recent_pairs.append(pair)
        counts = Counter(recent_pairs)
        if counts[pair] >= 3:
            return True
        if len(recent_pairs) >= 6:
            tail = list(recent_pairs)[-6:]
            if tail[:3] == tail[3:]:
                return True
        return False

    @staticmethod
    def _scroll_saturated(scroll_sigs) -> bool:
        if len(scroll_sigs) < 4:
            return False
        return all(before == after for before, after in list(scroll_sigs)[-4:])

    @staticmethod
    def _terminal_success_gate(goal: str, answer: str, obs: dict,
                               obs_texts: list[str], actions: list[str]) -> bool:
        g = (goal or "").lower()
        recent_text = "\n".join([obs.get("url", ""), obs.get("axtree", ""), *obs_texts[-3:]])
        ax = recent_text.lower()
        action_counts = Counter(action_family(a) for a in actions)
        if re.search(r"\bhover\b|\bsubmenu\b|\bmenu option\b|\bexpandable control\b", g):
            if action_counts["hover"] < 1:
                return False
            return bool(re.search(r"menuitem|haspopup|expanded=true|submenu|option", ax))

        if re.search(r"\bsearch\b|\bquery\b", g):
            if action_counts["fill"] + action_counts["type"] < 1:
                return False
            search_terms = Solver._goal_or_input_terms(goal, actions)
            if search_terms:
                return any(Solver._contains_all_terms(ax, term) for term in search_terms)
            return Solver._answer_has_nontrivial_visible_token(answer, ax)

        if "report the available action" in g:
            return Solver._answer_has_nontrivial_visible_token(answer, ax)

        state_changing = re.search(
            r"add|remove|update|change|edit|delete|cancel|archive|deactivate|disable|"
            r"save|submit|send|publish|post|apply|confirm|book|reserve|subscribe|"
            r"checkout|purchase|payment|pay|refund|return item|cart|wishlist|reorder",
            g,
        )
        if state_changing:
            if action_counts["click"] + action_counts["fill"] + action_counts["type"] + action_counts["press"] < 1:
                return False
            success_markers = (
                "success", "successful", "saved", "updated", "added", "removed", "submitted",
                "sent", "posted", "published", "applied", "confirmed", "completed",
                "created", "deleted", "canceled", "cancelled", "archived",
                "thank you", "confirmation",
            )
            return any(marker in ax for marker in success_markers)

        if re.search(
            r"\bread\b|\banswer\b|\bidentify\b|\binspect\b|\breport\b|\bvisible\b|"
            r"\bcompare\b|\bcount\b|\bdate\b|\bstatus\b|\brating\b|\bfeedback\b",
            g,
        ):
            return Solver._answer_has_nontrivial_visible_token(answer, ax)

        return True

    @staticmethod
    def _goal_or_input_terms(goal: str, actions: list[str]) -> list[str]:
        terms = [
            (single or double).strip()
            for single, double in re.findall(r"'([^']+)'|\"([^\"]+)\"", goal or "")
            if (single or double).strip()
        ]
        for action in actions:
            try:
                parsed = parse_hsge_action(action)
            except ValueError:
                continue
            if parsed.name in {"fill", "type"} and len(parsed.args) >= 2:
                terms.append(parsed.args[1].strip())
        out: list[str] = []
        seen = set()
        for term in terms:
            key = term.lower()
            if len(key) >= 3 and key not in seen:
                out.append(term)
                seen.add(key)
        return out

    @staticmethod
    def _contains_all_terms(text: str, phrase: str) -> bool:
        tokens = [
            t for t in re.findall(r"[a-z0-9][a-z0-9+_.-]{1,}", (phrase or "").lower())
            if t not in {"the", "and", "for", "with", "into", "from"}
        ]
        if not tokens:
            return False
        return all(t in text for t in tokens[:5])

    @staticmethod
    def _answer_has_nontrivial_visible_token(answer: str, text: str) -> bool:
        tokens = [
            t for t in re.findall(r"[a-z0-9$][a-z0-9$.,+_-]{2,}", (answer or "").lower())
            if t not in {
                "the", "and", "that", "this", "with", "found", "answer", "user",
                "not", "available", "visible", "success", "successful", "successfully",
                "completed", "complete", "done", "information", "requested",
            }
        ]
        return any(t in text for t in tokens[:12])
