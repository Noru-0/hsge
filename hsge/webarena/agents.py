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


READONLY_NOTE = ("\nREAD-ONLY MODE: propose ONLY [INFO] and [NAV] tasks. Do NOT "
                 "propose any [MOD] / content-modification tasks (no posting, "
                 "commenting, voting, adding to cart, or checkout).")


class PageExplorer:
    def __init__(self, llm, max_tasks: int = 4, read_only: bool = False,
                 vision: bool = False, som: bool = True, image_detail: str = "low"):
        self.llm = llm
        self.max_tasks = max_tasks
        self.read_only = read_only
        self.vision = vision
        self.som = som
        self.image_detail = image_detail

    @staticmethod
    def _coerce_task(t) -> str | None:
        """Some models (observed with gpt-4o, not DeepSeek) don't follow the
        requested flat {"tasks": ["...", ...]} schema and wrap a task in an
        object instead (e.g. {"task": "...", "type": "NAV"}). Salvage the
        text instead of letting a non-string crash the rest of the pipeline,
        which assumes list[str]."""
        if isinstance(t, str):
            return t
        if isinstance(t, dict):
            for key in ("task", "description", "text"):
                val = t.get(key)
                if isinstance(val, str):
                    return val
        return None

    def propose(self, obs: dict, screenshot_b64: str | None = None) -> list[str]:
        system = EXPLORER_SYS + (READONLY_NOTE if self.read_only else "")
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}"
        image = screenshot_b64 if self.vision else None
        out = self.llm.complete_json(system, prompt, image_b64=image, image_detail=self.image_detail)
        if image and not out.get("tasks"):
            # A vision call can come back empty (some providers get stricter about
            # a screenshot of a real, named site -- e.g. one annotated with
            # Set-of-Marks bounding boxes -- than the same request as text-only).
            # Retry once without the image before giving up on this node entirely.
            print("    [explorer] empty response with image attached, retrying text-only")
            out = self.llm.complete_json(system, prompt, image_b64=None, image_detail=self.image_detail)
        tasks = [t for t in map(self._coerce_task, out.get("tasks", [])) if t]
        if self.read_only:                       # belt-and-suspenders: drop any [MOD]
            tasks = [t for t in tasks if "[MOD]" not in t.upper()]
        return tasks[: self.max_tasks]


class Solver:
    def __init__(self, llm, max_steps: int = 15,
                 vision: bool = False, som: bool = True, image_detail: str = "low"):
        self.llm = llm
        self.max_steps = max_steps
        self.vision = vision
        self.som = som
        self.image_detail = image_detail

    def solve(self, browser, goal: str, goal_predicate: str | None = None):
        """Drive the browser toward `goal`.

        Returns (steps, obs_texts, obs_screenshots, final_obs, success).
        """
        steps: list[Step] = []
        obs_texts: list[str] = []
        obs_screenshots: list[str | None] = []
        history: list[str] = []
        obs = browser.observation()
        last_error = ""
        success = False
        for _ in range(self.max_steps):
            prompt = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n"
                      + ("\n".join(f"- {h}" for h in history[-6:]) or "(none)")
                      + (f"\n\nLAST ACTION ERROR: {last_error}" if last_error else "")
                      + f"\n\nURL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}")
            screenshot_b64 = browser.screenshot_b64(som=self.som) if self.vision else None
            out = self.llm.complete_json(SOLVER_SYS, prompt,
                                          image_b64=screenshot_b64, image_detail=self.image_detail)
            if screenshot_b64 and not (out.get("action") or "").strip():
                # same rationale as PageExplorer.propose(): don't let a refused/
                # empty vision call silently end the episode -- try text-only.
                print("    [solver] empty response with image attached, retrying text-only")
                out = self.llm.complete_json(SOLVER_SYS, prompt,
                                              image_b64=None, image_detail=self.image_detail)
            action = (out.get("action") or "").strip()
            thought = out.get("thought", "")
            steps.append(Step(action=action, url=obs["url"], obs_summary=thought[:100],
                              axtree=obs["axtree"]))
            obs_texts.append(obs["axtree"])
            obs_screenshots.append(screenshot_b64)
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
        return steps, obs_texts, obs_screenshots, obs, success
