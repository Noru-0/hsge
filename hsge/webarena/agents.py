"""LLM agents for WebArena exploration:
  - PageExplorer: proposes feasible tasks for the current page (local task source)
  - Solver: an action-planner loop that drives the browser toward a goal

Both take an `LLM` backend (use hsge.backends.OpenAILLM for real runs, MockLLM
for dry runs). The Solver returns a list of `Step`, which feeds HSGE Discovery.
"""
from __future__ import annotations

import json

from ..schema import Step
from .predicates import reached

ACTIONS_DOC = ("Allowed actions (return exactly one): click('bid'), "
               "fill('bid','text'), select_option('bid','opt'), goto('url'), "
               "go_back(), send_msg_to_user('done message').")

EXPLORER_SYS = (
    "PROPOSE diverse, high-level tasks a user could accomplish on THIS page. "
    "Each task should represent a complete user goal (e.g. 'Search for coffee and add the cheapest result to cart'). "
    "Avoid proposing the same action pattern for multiple items — instead group similar items into one task "
    "or vary the task structure (search, browse, compare, add to cart, add to wishlist, view details, etc.). "
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
3. What are common action chains (sequences of steps around 3-6 steps) that users typically follow?

IMPORTANT: The agent is ALREADY LOGGED IN. Do NOT include any login, sign in,
sign up, register, create account, or authentication related tasks or actions.

Look at the page structure, navigation elements, and content to determine the domain.

Page accessibility tree:
{axtree}

Respond with ONLY valid JSON in this exact format:
{{
  "domain_type": "<website type>",
  "common_tasks": ["<task1>", "<task2>", "<task3>", ...],
  "common_actions": ["<step1> -> <step2> -> <step3>", ...]
}}

Example for an e-commerce site:
{{
  "domain_type": "e-commerce",
  "common_tasks": [
    "Browse products by category",
    "Search for a specific product",
    "Add a product to cart",
    "View product details and reviews",
    "Proceed to checkout",
    "View order history"
  ],
  "common_actions": [
    "Search product -> Select product -> Add to cart -> View cart -> Checkout",
    "Browse category -> Filter products -> Select product -> Add to cart",
    "View product -> Select options -> Add to cart -> Proceed to checkout -> Enter shipping -> Place order"
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
        + "Call send_msg_to_user only when the goal is fully achieved."
    )
    parts = [skill_hints, base]
    return "\n".join(p for p in parts if p)


class PageExplorer:
    def __init__(self, llm, max_tasks: int = 10):
        self.llm = llm
        self.max_tasks = max_tasks
        self.domain_type: str = ""
        self.common_tasks: list[str] = []
        self.common_actions: list[str] = []

    _LOGIN_KEYWORDS = [
        "login", "sign in", "signin", "sign up", "signup",
        "register", "create account", "log in", "log into",
        "authenticate", "forgot password", "reset password",
    ]

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
                  f"({len(self.common_tasks)} tasks, {len(self.common_actions)} action chains)")
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
            domain_context += "Reference — common action flows (adapt to current page):\n" + "\n".join(f"- {a}" for a in self.common_actions) + "\n"
        if domain_context:
            domain_context += "\nIMPORTANT: Propose tasks specific to the CURRENT page and its elements. Use the references above only as inspiration — combine them with what you see on the page. Each goal must be concrete (e.g. \"Search for 'coffee' and add the first result to cart\"), not generic (e.g. \"Search product -> Select product\").\n"
        if domain_context:
            sys = domain_context + "\n" + sys
        if skill_hints:
            sys = skill_hints + "\n" + sys
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}"
        out = self.llm.complete_json(sys, prompt)
        tasks = out.get("tasks", [])
        # Filter out any login-related tasks
        tasks = [t for t in tasks if not self._is_login_task(t)]
        return tasks[: self.max_tasks]


class Solver:
    def __init__(self, llm, max_steps: int = 15):
        self.llm = llm
        self.max_steps = max_steps

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
                        steps.append(Step(
                            action=first_action, url=obs["url"],
                            obs_summary=thought[:100],
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
                            steps.append(Step(action=act, url=obs.get("url", "")))
                            obs_texts.append(obs.get("axtree", ""))
                            screenshots.append(obs.get("screenshot_base64"))
                            history.append(act)
                    else:
                        # Fallback: ghi tool_call như cũ nếu không expand được
                        action = f"tool_call({tool_name})"
                        steps.append(Step(action=action, url=obs["url"],
                                          obs_summary=thought[:100]))
                        obs_texts.append(obs["axtree"])
                        screenshots.append(obs.get("screenshot_base64"))
                        history.append(action)

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

            steps.append(Step(action=action, url=obs["url"], obs_summary=thought[:100]))
            obs_texts.append(obs["axtree"])
            screenshots.append(obs.get("screenshot_base64"))
            if not action or action.startswith("send_msg_to_user"):
                break
            try:
                obs = browser.act(action)
            except Exception as e:
                steps[-1].obs_summary += f" [action error: {e}]"
                break
            history.append(action)
            last_action_str = f"{{'thought': {thought[:80]}, 'action': {action[:80]}}}"
            last_result_url = obs.get("url", "")

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
            success = True
        return steps, obs_texts, obs, success, screenshots

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
                action = action.replace("{" + name + "}", str(val))
            # Skip if unbound slots remain
            if "{" in action:
                continue
            rendered_actions.append(action)
            try:
                obs = browser.act(action)
            except Exception:
                return rendered_actions, False

        return rendered_actions, True
