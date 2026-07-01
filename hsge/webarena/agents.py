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
    "PROPOSE concrete, feasible tasks a typical user could do on THIS page. "
    "Return JSON {\"tasks\": [\"...\", ...]}.\n"
    "Rules:\n"
    "- Be SPECIFIC using names/values visible on the page (e.g. 'Add the Sony PS5 "
    "to the cart', 'Open the post titled \"Best budget GPU\"'), NOT generic templates "
    "like 'add item to cart' or 'search for a product'.\n"
    "- Tag each task by type: [INFO] read/extract info, [NAV] go to a specific page, "
    "[MOD] change content/state. List them INFO first, then NAV, then MOD.\n"
    "- Prefer tasks that make progress or reveal new pages over pure search/sort/filter.\n"
    "- Focus on common things a real user of THIS site would do; skip niche tasks.")

SOLVER_SYS = (
    "You are a web agent. Reach the GOAL by choosing the single best next action from "
    "the page accessibility tree (elements shown as [bid] role 'name'). " + ACTIONS_DOC +
    " Think step by step; reflect on your past actions and any error from your last "
    "action before deciding. Output ONE action as JSON "
    "{\"thought\": \"...\", \"action\": \"<one action>\"}. "
    "Examples: {\"thought\": \"Open the product\", \"action\": \"click('12')\"} ; "
    "{\"thought\": \"Goal met\", \"action\": \"send_msg_to_user('done: price is $19')\"}. "
    "Call send_msg_to_user ONLY when the goal is fully achieved.")


class PageExplorer:
    def __init__(self, llm, max_tasks: int = 4):
        self.llm = llm
        self.max_tasks = max_tasks

    def propose(self, obs: dict) -> list[str]:
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}"
        out = self.llm.complete_json(EXPLORER_SYS, prompt)
        return [t for t in out.get("tasks", [])][: self.max_tasks]


class Solver:
    def __init__(self, llm, max_steps: int = 15):
        self.llm = llm
        self.max_steps = max_steps

    def solve(self, browser, goal: str, goal_predicate: str | None = None):
        """Drive the browser toward `goal`.

        Returns (steps, obs_texts, final_obs, success).
        """
        steps: list[Step] = []
        obs_texts: list[str] = []
        history: list[str] = []
        obs = browser.observation()
        last_error = ""
        success = False
        for _ in range(self.max_steps):
            prompt = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n"
                      + ("\n".join(f"- {h}" for h in history[-6:]) or "(none)")
                      + (f"\n\nLAST ACTION ERROR: {last_error}" if last_error else "")
                      + f"\n\nURL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}")
            out = self.llm.complete_json(SOLVER_SYS, prompt)
            action = (out.get("action") or "").strip()
            thought = out.get("thought", "")
            steps.append(Step(action=action, url=obs["url"], obs_summary=thought[:100],
                              axtree=obs["axtree"]))
            obs_texts.append(obs["axtree"])
            if not action or action.startswith("send_msg_to_user"):
                break
            try:
                obs = browser.act(action)
                last_error = ""
            except Exception as e:
                # feed the error back so the agent can recover, instead of aborting
                last_error = str(e)[:200]
                steps[-1].obs_summary += f" [action error: {last_error}]"
                continue
            history.append(action)
            if getattr(browser, "terminated", False):
                break
            if goal_predicate and reached(goal_predicate, obs["url"], obs["axtree"]):
                success = True
                break
        # success for non-predicate goals = agent declared done without error
        if goal_predicate is None and steps and steps[-1].action.startswith("send_msg_to_user"):
            success = True
        return steps, obs_texts, obs, success
