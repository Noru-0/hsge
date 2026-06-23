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
from .predicates import reached

ACTIONS_DOC = ("Allowed actions (return exactly one): click('bid'), "
               "fill('bid','text'), type('bid','text','1_or_0'), "
               "press('key'), scroll('down'|'up'), hover('bid'), "
               "goto('url') only when the exact URL is explicitly present in the goal/page context, "
               "send_msg_to_user('done message').")

EXPLORER_SYS = (
    "PROPOSE diverse, local tasks a user could accomplish from THIS page. "
    "Each task must be grounded in visible controls or visible page text, with a clear stop condition. "
    "Prefer one local objective that should take 1-3 primitive actions, such as search, browse, compare, "
    "read, inspect, filter, open a form, or report a visible detail. "
    "Return a balanced portfolio when the page supports it: atomic navigation/detail tasks, "
    "state-change tasks, form tasks, menu/filter tasks, and checkout/order-flow tasks. "
    "If cart, checkout, address, shipping, payment, review, or confirmation controls are visible, "
    "include a safe task that progresses to or reports the next required step. "
    "Do NOT return action-chain labels with arrows like A -> B -> C. "
    "Do NOT invent item names, categories, records, people, quantities, amounts, dates, or IDs that are not visible. "
    "Avoid irreversible commit, payment, destructive, or submit tasks unless the exact reversible control is visible. "
    "Avoid proposing the same action pattern for multiple items; vary the task structure instead. "
    "Return JSON {\"tasks\": [\"...\", ...]}. "
    "IMPORTANT: Do NOT propose any login, sign in, sign up, register, "
    "or account creation tasks — the agent is already logged in."
)

_DOMAIN_DETECT_SYS = (
    "You are analyzing a web page to determine what kind of website it is "
    "and what common tasks users typically do on it. "
    "Return ONLY valid JSON."
)

_DOMAIN_DETECT_PROMPT = """\
Analyze the page accessibility tree below and determine:
1. What type of website is this? (e.g. e-commerce, forum, wiki, admin panel, social media, etc.)
2. What are the most common high-level tasks users do on this type of website?
3. What are common local interaction patterns users typically follow from one page state?

IMPORTANT: The agent is ALREADY LOGGED IN. Do NOT include any login, sign in,
sign up, register, create account, or authentication related tasks or actions.

Look at the page structure, navigation elements, and content to determine the domain.

Page accessibility tree:
{axtree}

Respond with ONLY valid JSON in this exact format:
{{
  "domain_type": "<website type>",
  "common_tasks": ["<task1>", "<task2>", "<task3>", ...],
  "common_actions": ["<local interaction pattern>", ...]
}}

Example for a transactional site:
{{
  "domain_type": "transactional website",
  "common_tasks": [
    "Search for an item or record",
    "Open a detail page",
    "Compare visible attributes",
    "Read user feedback or comments",
    "Submit or update a form",
    "Check history or status"
  ],
  "common_actions": [
    "Use search to find a visible item or record",
    "Open a menu or filter control",
    "Read details from a visible result or record"
  ]
}}
"""


def _build_solver_sys(skill_hints: str = "") -> str:
    base = (
        "You are a web agent. Given the goal, the page accessibility tree "
        "(elements shown as [bid] role 'name'), and your recent actions, "
        "choose the single best next action. "
        + ACTIONS_DOC
        + ' Return JSON {"thought": "...", "action": "<one action>"}. '
        + "The thought MUST use this shape: "
        + "'I need to <local subgoal>. The next action is to <action verb> "
        + "[bid if any]. Evidence: <visible UI evidence or recent-action reason>.' "
        + "Use RECENT ACTIONS to avoid loops and repeated actions. "
        + "Call send_msg_to_user only when the goal is fully achieved."
    )
    parts = [skill_hints, base]
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
        self.domain_type: str = ""
        self.common_tasks: list[str] = []
        self.common_actions: list[str] = []
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

    def detect_domain(self, obs: dict) -> None:
        """Phân tích axtree root node để xác định domain type, common tasks và common actions."""
        axtree = obs.get("axtree", "")[:4000]
        if not axtree:
            return
        prompt = _DOMAIN_DETECT_PROMPT.format(axtree=axtree)
        try:
            out = self.llm.complete_json(_DOMAIN_DETECT_SYS, prompt)
            self.domain_type = out.get("domain_type", "")
            self.common_tasks = out.get("common_tasks", [])
            self.common_actions = out.get("common_actions", [])
            print(f"  [domain] Detected: {self.domain_type} "
                  f"({len(self.common_tasks)} tasks, {len(self.common_actions)} local patterns)")
        except Exception as e:
            print(f"  [domain] Detection failed: {e}")

    def propose(self, obs: dict, skill_hints: str = "") -> list[str]:
        sys = EXPLORER_SYS
        # Thêm domain context nếu có — chỉ làm tham khảo, không dùng nguyên
        domain_context = ""
        if self.domain_type:
            domain_context = f"Website type: {self.domain_type}.\n"
        if self.common_tasks:
            domain_context += "Reference — common task types on this site:\n" + "\n".join(f"- {t}" for t in self.common_tasks) + "\n"
        if self.common_actions:
            domain_context += "Reference — common local interaction patterns (adapt to current page):\n" + "\n".join(f"- {a}" for a in self.common_actions) + "\n"
        if domain_context:
            domain_context += "\nIMPORTANT: Propose tasks specific to the CURRENT page and its elements. Use the references above only as inspiration — combine them with what you see on the page. Each goal must be concrete and grounded in visible controls/content, not a generic action-chain label.\n"
        if domain_context:
            sys = domain_context + "\n" + sys
        if skill_hints:
            sys = skill_hints + "\n" + sys
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}"
        seeded_tasks = self._seed_tasks(obs) if self.profile == "training_quality" else []
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
        """Deterministic small-skill tasks to improve SFT coverage."""
        axtree = obs.get("axtree", "")
        lines = self._interactive_lines(obs)
        lower = "\n".join(lines).lower()
        all_text = self._visible_text(obs)
        tasks: list[str] = []

        deep_label = self._first_label(lines, self._progression_pattern())
        if deep_label:
            if self._is_final_order_control(deep_label) and not self.place_order_allowed:
                tasks.append(f"Review the visible '{deep_label}' final order control and report what confirmation would be required before using it.")
            elif self.checkout_mode != "discover-only":
                tasks.append(f"Use the visible '{deep_label}' progression control and report the next required step or confirmation that appears.")
            else:
                tasks.append(f"Inspect the visible '{deep_label}' progression control and report the next required step without submitting it.")

        search_label = self._first_label(lines, r"\b(searchbox|textbox|combobox)\b.*search")
        if search_label:
            tasks.append(f"Use the visible '{search_label}' search field to submit a page-relevant search.")

        feedback_label = self._first_label(lines, r"reviews?|comments?|feedback|discussion|rating|stars?")
        if feedback_label:
            feedback_count = self._feedback_count(feedback_label)
            if feedback_count:
                tasks.append(f"Report the visible feedback count shown by '{feedback_label}'.")
            else:
                tasks.append(f"Report whether the visible '{feedback_label}' feedback control indicates available feedback.")

        hover_label = self._first_label(lines, r"haspopup|menuitem")
        if hover_label:
            tasks.append(f"Hover over the visible '{hover_label}' menu or expandable control and report one submenu option that appears.")

        filter_label = self._first_label(lines, r"sort by|filter|facet|refine")
        if filter_label:
            tasks.append(f"Open the visible '{filter_label}' sort or filter control and report one available option.")

        state_label = self._first_label(
            lines,
            r"checkout|payment|pay|place order|subscribe|apply|book|reserve|submit|send|"
            r"publish|post|save|confirm|continue|next|delete|remove|cancel|compare|wishlist|cart",
        )
        if state_label:
            tasks.append(f"Open the visible '{state_label}' state-changing control and report the available action.")

        if self.checkout_mode != "discover-only":
            checkout_label = self._first_label(lines, r"proceed to checkout|checkout|cart|shipping|payment|billing|review order|order summary")
            if checkout_label:
                tasks.append(f"Use the visible '{checkout_label}' checkout or order-flow control and report the next required step.")
        payment_label = self._first_label(lines, r"shipping method|payment method|billing|order summary|grand total|subtotal")
        if payment_label:
            tasks.append(f"Review the visible '{payment_label}' order-flow section and report one required option or summary detail.")
        address_label = self._first_label(lines, r"street address|address|city|state|zip|postal|country|phone")
        if address_label:
            tasks.append(f"Inspect the visible '{address_label}' address or checkout field and report what input is required.")

        profile_label = self._first_label(lines, r"my account|account|profile|settings|address book|address|preferences")
        if profile_label:
            tasks.append(f"Open the visible '{profile_label}' account or settings control and report one visible option.")

        history_label = self._first_label(lines, r"my orders|orders?|ticket|issue|request|case|incident|history|refund|reorder")
        if history_label:
            tasks.append(f"Open the visible '{history_label}' history or record-status control and answer one detail.")

        communication_label = self._first_label(lines, r"contact us|contact|message|email|reply|draft")
        if communication_label:
            tasks.append(f"Open the visible '{communication_label}' communication control and report one visible field or option.")

        numeric_hint = self._first_visible_snippet(
            axtree,
            r"\$|price|amount|cost|compare|count|total|date|latest|recent|percent|%|\b\d+(?:[.,]\d+)?\b",
        )
        if numeric_hint:
            tasks.append(f"Read the visible numeric or dated detail near '{numeric_hint}' and answer a simple lookup question.")
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
              skill_hints: str = "", tools: list[dict] | None = None,
              step_callback=None):
        """Drive the browser toward `goal`.
        Returns (steps, obs_texts, final_obs, success, screenshots).
        screenshots is list[bytes|None] parallel to steps.

        If `tools` is provided (list of OpenAI/DeepSeek function definitions),
        the solver will use tool-calling (function calling) API instead of
        text-only JSON completion. When the LLM calls a tool, the runtime
        executes the skill's action template with the bound parameters.

        If `step_callback` is provided, it is called after each step with:
            step_callback(action, url_before, url_after, traj_steps_so_far)
        This enables real-time URL discovery (callback-based, not DOM-query).
        """
        steps: list[Step] = []
        obs_texts: list[str] = []
        screenshots: list[bytes | None] = []
        history: list[str] = []
        last_action_str = "(none)"
        last_result_url = ""
        sys = _build_solver_sys(skill_hints)
        obs = browser.observation()
        success = False
        prev_url = obs.get("url", "")
        invalid_attempts = 0
        recent_pairs = deque(maxlen=8)
        recent_scroll_signatures = deque(maxlen=5)
        for _ in range(self.max_steps):
            prompt_text = (f"GOAL: {goal}\n\nLAST ACTION:\n{last_action_str}\n"
                      + (f"RESULTING URL: {last_result_url}\n" if last_result_url else "")
                      + f"\nRECENT ACTIONS:\n"
                      + ("\n".join(f"- {h}" for h in history[-5:]) or "(none)")
                      + f"\n\nURL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}")

            # --- Tool-calling branch ---
            if tools:
                out = self.llm.complete_with_tools(sys, prompt_text, tools=tools)
                if out.get("type") == "tool_call":
                    # LLM invoked a skill tool — expand into detailed actions
                    tool_name = out.get("name", "")
                    arguments = out.get("arguments", {})
                    thought = json.dumps({"tool": tool_name, "args": arguments})

                    # Execute the tool: get rendered actions
                    rendered_actions, tool_success = self._execute_tool(
                        browser, tool_name, arguments)

                    if rendered_actions:
                        # Step đầu: action = rendered action thật (click('bid')),
                        # misc chứa tool_call info để biết là dùng skill.
                        first_action = rendered_actions[0]
                        grounded_thought, _ = repair_thought(
                            thought, first_action, obs.get("axtree", "")
                        )
                        steps.append(Step(
                            action=first_action, url=obs["url"],
                            obs_summary=grounded_thought,
                            misc={"skill": tool_name, "args": arguments,
                                  "tool_call": f"tool_call({tool_name})",
                                  "rendered_actions": rendered_actions},
                        ))
                        obs_texts.append(obs["axtree"])
                        screenshots.append(obs.get("screenshot_base64"))
                        history.append(first_action)

                        # Các action còn lại ghi rendered action thật
                        for act in rendered_actions[1:]:
                            obs = browser.observation()
                            grounded_thought, _ = repair_thought(
                                "I should execute the next concrete skill action.",
                                act,
                                obs.get("axtree", ""),
                            )
                            steps.append(Step(
                                action=act, url=obs.get("url", ""),
                                obs_summary=grounded_thought,
                            ))
                            obs_texts.append(obs.get("axtree", ""))
                            screenshots.append(obs.get("screenshot_base64"))
                            history.append(act)
                    else:
                        last_action_str = (
                            f"ERROR: tool {tool_name} did not render to valid "
                            "grounded concrete actions. Return one canonical action."
                        )
                        invalid_attempts += 1
                        if invalid_attempts >= 3:
                            break
                        continue

                    obs = browser.observation()

                    # Cập nhật last_action_str cho step kế tiếp
                    last_tool_action = action if not rendered_actions else rendered_actions[-1]
                    last_action_str = f"{{'tool': '{tool_name}', 'action': {last_tool_action[:80]}}}"
                    last_result_url = obs.get("url", "")

                    # Step callback for URL discovery
                    new_url = obs.get("url", "")
                    if step_callback:
                        step_callback(last_tool_action,
                                      prev_url, new_url, steps)
                    prev_url = new_url

                    if tool_success:
                        success = True
                        break
                    continue

                # Text response from tool-calling API
                action = (out.get("action") or "").strip()
                thought = out.get("thought", "")
            else:
                # --- Standard JSON completion branch ---
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
            steps.append(Step(action=action, url=obs["url"], obs_summary=thought))
            obs_texts.append(obs["axtree"])
            screenshots.append(obs.get("screenshot_base64"))
            if not action or action.startswith("send_msg_to_user"):
                break
            try:
                url_before_action = obs.get("url", "")
                sig_before_action = self._obs_signature(obs)
                obs = browser.act(action)
            except Exception as e:
                steps[-1].obs_summary += f" [action error: {e}]"
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

            if goal_predicate and reached(goal_predicate, obs["url"], obs["axtree"]):
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

        if re.search(r"\bsearch\b|\bfind\b", g):
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

    def _execute_tool(self, browser, tool_name: str, arguments: dict) -> tuple[list[str], bool]:
        """Execute a skill tool call by rendering its action template.

        Finds the skill by name, renders the template with the provided
        argument bindings, and executes each action step by step.

        Returns (rendered_actions, success) where rendered_actions is the list
        of concrete BrowserGym actions that were executed.
        """
        library = getattr(self, '_skill_library', None)
        if library is None:
            return [], False

        # Find the skill by name
        target_card = None
        for card in library.all_skills():
            if card.name == tool_name:
                target_card = card
                break

        if target_card is None:
            return [], False

        # Render and execute the action template
        templates = target_card.action_template
        if isinstance(templates, str):
            templates = [templates]

        rendered_actions = []
        for tmpl in templates:
            action = tmpl
            for name, val in arguments.items():
                action = action.replace("{" + name + "}", repr(str(val)))
            # Skip if unbound slots remain
            if "{" in action:
                continue
            obs = browser.observation()
            validation = validate_hsge_action(
                action, obs.get("axtree", ""), allow_goto=False
            )
            if not validation.ok:
                return rendered_actions, False
            rendered_actions.append(action)
            try:
                browser.act(action)
            except Exception:
                return rendered_actions, False

        return rendered_actions, True
