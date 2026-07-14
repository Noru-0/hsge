"""LLM agents for WebArena exploration:
  - PageExplorer: proposes feasible tasks for the current page (local task source)
  - Solver: an action-planner loop that drives the browser toward a goal

Both take an `LLM` backend (use hsge.backends.OpenAILLM for real runs, MockLLM
for dry runs). The Solver returns a list of `Step`, which feeds HSGE Discovery.
"""
from __future__ import annotations

import json
import re

from ..schema import Step
from .predicates import reached

ACTIONS_DOC = ("Allowed actions (return exactly one): click('bid'), "
               "fill('bid','text'), select_option('bid','opt'), goto('url'), "
               "go_back(), send_msg_to_user('done message'), "
               "report_infeasible('reason') -- report_infeasible ONLY when the "
               "task cannot be done on this site/page.")

EXPLORER_SYS = (
    "PROPOSE concrete, feasible tasks a typical user could do on THIS page. "
    "Return JSON {\"tasks\": [{\"text\": \"...\", \"type\": \"INFO\"|\"NAV\"|\"MOD\"}, ...]}.\n"
    "Rules:\n"
    "- Be SPECIFIC using names/values visible on the page (e.g. 'Add the Sony PS5 "
    "to the cart', 'Open the post titled \"Best budget GPU\"'), NOT generic templates "
    "like 'add item to cart' or 'search for a product'.\n"
    "- \"type\" must be exactly one of: INFO (read/extract info), NAV (go to a "
    "specific page), MOD (change content/state). List them INFO first, then NAV, "
    "then MOD.\n"
    "- INFO tasks must name WHAT to find (e.g. 'Find the number of submissions for "
    "r/relationship_advice'), but must NEVER state the value/answer itself in the task "
    "text (NOT 'Find the number of submissions for r/relationship_advice (5,718 "
    "submissions)'). If the answer is already written in the task, it isn't a task -- "
    "whoever solves it must still have to read the page to answer it.\n"
    "- Do NOT propose a NAV task to a page the user is already on (check the URL "
    "given below) -- e.g. if URL already ends in /wiki, do not propose 'Go to the "
    "Wiki page'.\n"
    "- Do NOT re-propose a task you (or an earlier page) already proposed this run -- "
    "see 'ALREADY PROPOSED' below if present. Sitewide nav-menu links (header/footer, "
    "present on every page) are especially prone to this: once a destination has been "
    "proposed from one page, do not propose 'go to <that same destination>' again from "
    "a different page. Prefer content unique to THIS page.\n"
    "- Prefer tasks that make progress or reveal new pages over pure search/sort/filter.\n"
    "- Focus on common things a real user of THIS site would do; skip niche tasks.\n"
    "- NEVER propose a task that would delete, deactivate, or close the user's "
    "account (e.g. 'Delete your account', 'Deactivate your profile'). This account "
    "is shared across exploration runs.")

SOLVER_SYS = (
    "You are a web agent. Reach the GOAL by choosing the single best next action from "
    "the page accessibility tree (elements shown as [bid] role 'name'). " + ACTIONS_DOC +
    " Think step by step; reflect on your past actions and any error from your last "
    "action before deciding. Output ONE action as JSON "
    "{\"thought\": \"...\", \"action\": \"<one action>\"}. "
    "Examples: {\"thought\": \"Open the product\", \"action\": \"click('12')\"} ; "
    "{\"thought\": \"Goal met\", \"action\": \"send_msg_to_user('done: price is $19')\"}. "
    "Call send_msg_to_user ONLY when the goal is fully achieved."
    " For 'go to page X' goals: once the URL/page has changed to the requested "
    "destination the goal is DONE -- call send_msg_to_user immediately; do NOT "
    "click the same link again.")


READONLY_NOTE = ("\nREAD-ONLY MODE: propose ONLY tasks with type INFO or NAV. Do NOT "
                 "propose any type MOD / content-modification tasks (no posting, "
                 "commenting, voting, adding to cart, or checkout).")


class PageExplorer:
    _TAG_RE = re.compile(r"^\s*\[(INFO|NAV|MOD)\]\s*", re.I)
    _PUNCT_RE = re.compile(r"[^\w\s]")
    _SEEN_HINT_SIZE = 25  # cap how many prior tasks get echoed back as negative context

    def __init__(self, llm, max_tasks: int = 4, read_only: bool = False,
                 vision: bool = False, som: bool = True, image_detail: str = "low"):
        self.llm = llm
        self.max_tasks = max_tasks
        self.read_only = read_only
        self.vision = vision
        self.som = som
        self.image_detail = image_detail
        # Tasks already proposed this run: normalized key -> original text,
        # kept across every propose() call since one PageExplorer instance
        # lives for the whole run (see runtime.py). Used both as negative
        # context in the prompt (original text, readable) and as a
        # defensive code-level dedup filter (normalized key).
        self._seen: dict[str, str] = {}

    @classmethod
    def _normalize(cls, text: str) -> str:
        text = cls._TAG_RE.sub("", text)
        text = cls._PUNCT_RE.sub("", text.lower())
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _parse_task(cls, t) -> tuple[str, str] | None:
        """Extract (text, tag) from one task entry, tag in {INFO, NAV, MOD,
        UNKNOWN}. Some models (observed with gpt-4o, not DeepSeek) don't
        follow the requested flat {"tasks": ["...", ...]} schema and wrap a
        task in an object instead (e.g. {"task": "...", "type": "NAV"}) --
        salvage the text AND the type field (the type used to be silently
        discarded, which is why most real-run tasks came back untagged even
        though the model had already classified them). A legacy leading
        [TAG] bracket in the text is a fallback for models that still use
        that convention. UNKNOWN (neither an explicit type nor a bracket)
        means the caller must not assume it's safe to treat as non-MOD."""
        explicit_type = None
        text = None
        if isinstance(t, str):
            text = t
        elif isinstance(t, dict):
            for key in ("text", "task", "description"):
                val = t.get(key)
                if isinstance(val, str):
                    text = val
                    break
            raw_type = t.get("type")
            if isinstance(raw_type, str) and raw_type.strip().upper() in ("INFO", "NAV", "MOD"):
                explicit_type = raw_type.strip().upper()
        if not text:
            return None
        m = cls._TAG_RE.match(text)
        bracket_type = m.group(1).upper() if m else None
        if m:
            text = text[m.end():]
        tag = explicit_type or bracket_type or "UNKNOWN"
        text = text.strip()
        return (text, tag) if text else None

    def propose(self, obs: dict, screenshot_b64: str | None = None) -> list[str]:
        system = EXPLORER_SYS + (READONLY_NOTE if self.read_only else "")
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}"
        if self._seen:
            recent = list(self._seen.values())[-self._SEEN_HINT_SIZE:]
            prompt += ("\n\nALREADY PROPOSED (do not repeat these or near-duplicates):\n"
                       + "\n".join(f"- {s}" for s in recent))
        image = screenshot_b64 if self.vision else None
        out = self.llm.complete_json(system, prompt, image_b64=image, image_detail=self.image_detail)
        if image and not out.get("tasks"):
            # A vision call can come back empty (some providers get stricter about
            # a screenshot of a real, named site -- e.g. one annotated with
            # Set-of-Marks bounding boxes -- than the same request as text-only).
            # Retry once without the image before giving up on this node entirely.
            print("    [explorer] empty response with image attached, retrying text-only")
            out = self.llm.complete_json(system, prompt, image_b64=None, image_detail=self.image_detail)
        parsed = [p for p in map(self._parse_task, out.get("tasks", [])) if p]
        if self.read_only:
            # Fail closed: only tasks confirmed INFO/NAV are safe. A task we
            # couldn't classify (UNKNOWN) might be a MOD the model forgot to
            # tag -- e.g. a real run had an untagged "Click 'Save' to create
            # the new page." that a literal "[MOD]" substring check would
            # have let straight through.
            parsed = [(text, tag) for text, tag in parsed if tag in ("INFO", "NAV")]
        fresh = []
        for text, tag in parsed:
            key = self._normalize(text)
            if key in self._seen:
                continue
            self._seen[key] = text
            fresh.append((text, tag))
        parsed = fresh
        if len(parsed) > self.max_tasks:
            # INFO tasks never grow the frontier (solving one reads the page,
            # it doesn't navigate); NAV/MOD do. EXPLORER_SYS asks the model
            # to list INFO first, so naively slicing to max_tasks would silently
            # drop every NAV/MOD task whenever a page offers more INFO
            # candidates than fit -- exactly the tasks that matter for
            # exploration. Drop INFO first instead.
            nav_mod = [p for p in parsed if p[1] != "INFO"]
            info = [p for p in parsed if p[1] == "INFO"]
            parsed = (nav_mod + info)[: self.max_tasks]
        return [f"[{tag}] {text}" if tag != "UNKNOWN" else text for text, tag in parsed]


class Solver:
    _TARGET_RE = re.compile(r"\('([^']*)'")
    _WARN_AFTER_REPEATS = 2   # nudge once the same target is hit this many times in a row
    _MAX_REPEATS = 4          # give up if nudging didn't help after this many

    def __init__(self, llm, max_steps: int = 15,
                 vision: bool = False, som: bool = True, image_detail: str = "low"):
        self.llm = llm
        self.max_steps = max_steps
        self.vision = vision
        self.som = som
        self.image_detail = image_detail

    @classmethod
    def _action_target(cls, action: str) -> str:
        """The bid/url an action operates on, e.g. click('117') -> '117'.
        Falls back to the whole action string for argument-less actions
        (go_back()) so repeats of those still group together."""
        m = cls._TARGET_RE.search(action)
        return m.group(1) if m else action

    @classmethod
    def _stuck_streak(cls, history: list[str], progressed: list[bool]) -> int:
        """How many trailing actions targeted the same element as the one
        before them AND produced no observable change (url/axtree
        identical before vs. after). Grouping by target (not exact action
        string) is what catches a real-run failure mode where the model
        keeps re-trying the same stuck element with different-looking
        arguments each time (e.g. select_option('378', 'Forum Name') then
        select_option('378', 'Another Forum Name'), neither of which ever
        changed the page). Requiring no observable change (not just a
        repeated target) is what avoids flagging a legitimate multi-step
        sequence that happens to reuse the same bid across different pages
        (e.g. a scripted/mock solver whose 'advance' bid is always '1' but
        each click genuinely moves to a new page)."""
        streak = 0
        for i in range(len(history) - 1, -1, -1):
            if progressed[i]:
                break
            if i < len(history) - 1 and cls._action_target(history[i]) != cls._action_target(history[i + 1]):
                break
            streak += 1
        return streak

    def solve(self, browser, goal: str, goal_predicate: str | None = None):
        """Drive the browser toward `goal`.

        Returns (steps, obs_texts, obs_screenshots, final_obs, success, infeasible).
        """
        steps: list[Step] = []
        obs_texts: list[str] = []
        obs_screenshots: list[str | None] = []
        history: list[str] = []
        outcomes: list[str] = []     # human-readable result of history[i]
        progressed: list[bool] = []  # did url/axtree change as a result of history[i]?
        obs = browser.observation()
        last_error = ""
        success = False
        exhausted = True   # loop ended by budget/hard-stop, not by a terminal action
        for _ in range(self.max_steps):
            streak = self._stuck_streak(history, progressed)
            if streak >= self._MAX_REPEATS:
                # A text nudge alone isn't reliably obeyed (verified against a
                # real run: the warning was present in the prompt from the 3rd
                # call onward and the model kept issuing the exact same click
                # anyway for all 15 steps). Stop spending steps on a target
                # that clearly isn't moving instead of exhausting max_steps.
                print(f"    [solver] giving up: target {self._action_target(history[-1])!r} "
                      f"hit {streak}x in a row with no progress")
                break
            repeat_warning = ""
            if streak >= self._WARN_AFTER_REPEATS:
                # The same target just got hit >=2 times in a row with no error --
                # e.g. clicking a nav link that navigated fine but re-appears
                # under a new bid on the destination page, so the model keeps
                # clicking it without realizing it already arrived. Nudge
                # instead of silently repeating the same prompt.
                repeat_warning = (
                    f"\n\nWARNING: your last {streak} actions all targeted "
                    f"{self._action_target(history[-1])!r} with no visible progress -- "
                    "repeating it again will not help. If the goal is already achieved, "
                    "call send_msg_to_user(...) now instead. Otherwise choose a "
                    "genuinely different action/target.")
            recent = [f"- {h} -> {o}" for h, o in zip(history[-6:], outcomes[-6:])]
            prompt = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n"
                      + ("\n".join(recent) or "(none)")
                      + (f"\n\nLAST ACTION ERROR: {last_error}" if last_error else "")
                      + repeat_warning
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
            if (not action or action.startswith("send_msg_to_user")
                    or action.startswith("report_infeasible")):
                exhausted = False
                break
            pre_url, pre_axtree = obs["url"], obs["axtree"]
            try:
                obs = browser.act(action)
                last_error = ""
            except Exception as e:
                # feed the error back so the agent can recover, instead of aborting
                last_error = str(e)[:200]
                steps[-1].obs_summary += f" [action error: {last_error}]"
                continue
            history.append(action)
            if obs["url"] != pre_url:
                outcomes.append(f"now at {obs['url']}")
            elif obs["axtree"] != pre_axtree:
                outcomes.append("page changed")
            else:
                outcomes.append("no change")
            progressed.append(obs["url"] != pre_url or obs["axtree"] != pre_axtree)
            if getattr(browser, "terminated", False):
                exhausted = False
                break
            if goal_predicate and reached(goal_predicate, obs["url"], obs["axtree"]):
                success = True
                exhausted = False
                break

        if exhausted and goal_predicate is None and steps:
            # One last chance: real runs (wa_run_07) showed the dominant NAV
            # failure is arriving at the right page and then looping on the
            # same sitewide nav link until the budget dies -- achieved, but
            # never declared. Ask once, accept ONLY a terminal action, never
            # execute it in the browser.
            recent = [f"- {h} -> {o}" for h, o in zip(history, outcomes)]
            wrap_prompt = (f"GOAL: {goal}\n\nACTIONS TAKEN:\n"
                           + ("\n".join(recent) or "(none)")
                           + f"\n\nURL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}"
                           + "\n\nYour action budget is exhausted. If the goal has "
                             "ALREADY been achieved (e.g. you are on the requested "
                             "page), call send_msg_to_user('done: ...') NOW. If the "
                             "goal cannot be achieved, call report_infeasible('why'). "
                             "Answer with one of those two actions only.")
            out = self.llm.complete_json(SOLVER_SYS, wrap_prompt)
            action = (out.get("action") or "").strip()
            if action.startswith("send_msg_to_user") or action.startswith("report_infeasible"):
                steps.append(Step(action=action, url=obs["url"],
                                  obs_summary=str(out.get("thought", ""))[:100],
                                  axtree=obs["axtree"]))
                obs_texts.append(obs["axtree"])
                obs_screenshots.append(None)

        infeasible = bool(steps) and steps[-1].action.startswith("report_infeasible")
        # success for non-predicate goals = agent declared done without error
        if goal_predicate is None and steps and steps[-1].action.startswith("send_msg_to_user"):
            success = True
        return steps, obs_texts, obs_screenshots, obs, success, infeasible
