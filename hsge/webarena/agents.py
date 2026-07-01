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

EXPLORER_SYS = ("PROPOSE feasible, concrete tasks a user could do on THIS page. "
                "Return JSON {\"tasks\": [\"...\", ...]}. Prefer tasks that make "
                "progress (open an item, add to cart, proceed to checkout) over "
                "pure search/sort/filter.")

SOLVER_SYS = ("You are a web agent. Given the goal, the page accessibility tree "
              "(elements shown as [bid] role 'name'), and your recent actions, "
              "choose the single best next action. " + ACTIONS_DOC +
              " Return JSON {\"thought\": \"...\", \"action\": \"<one action>\"}. "
              "Call send_msg_to_user only when the goal is fully achieved.")


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
        """Drive the browser toward `goal`. Returns (steps, final_obs, success)."""
        steps: list[Step] = []
        obs_texts: list[str] = []
        history: list[str] = []
        obs = browser.observation()
        success = False
        for _ in range(self.max_steps):
            prompt = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n"
                      + ("\n".join(f"- {h}" for h in history[-6:]) or "(none)")
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
            except Exception as e:
                steps[-1].obs_summary += f" [action error: {e}]"
                break
            history.append(action)
            if goal_predicate and reached(goal_predicate, obs["url"], obs["axtree"]):
                success = True
                break
        # success for non-predicate goals = agent declared done without error
        if goal_predicate is None and steps and steps[-1].action.startswith("send_msg_to_user"):
            success = True
        return steps, obs_texts, obs, success
