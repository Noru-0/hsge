"""LLM agents for WebArena exploration:
  - PageExplorer: proposes feasible tasks for the current page (local task source)
  - Solver: an action-planner loop that drives the browser toward a goal

Both take an `LLM` backend (use hsge.backends.OpenAILLM for real runs, MockLLM
for dry runs). The Solver returns a list of `Step`, which feeds HSGE Discovery.
"""
from __future__ import annotations

import ast
import json
import re

from ..schema import Step
from .predicates import reached
from .urls import site_relative

ACTIONS_DOC = ("Allowed actions (return exactly one): click('bid'), "
               "fill('bid','text'), select_option('bid','opt'), "
               "press('bid','key_comb') -- e.g. press('12','Enter') to submit a "
               "search box or form when there is no separate submit button, "
               "goto('/path') -- a SITE-RELATIVE path on the current site, e.g. "
               "goto('/f/books'); never a full http(s):// URL and never another "
               "website, "
               "go_back(), new_tab(), tab_focus(index), tab_close(), "
               "scroll(0, 400) -- scroll the page down (negative to go up), "
               "hover('bid'), noop(500) -- wait 500ms for the page to settle. "
               "If an action failed with a Timeout, the element exists but was "
               "not clickable yet (off-screen, covered, or still loading): "
               "scroll(0, 400) or hover it first, or use a different element -- "
               "repeating the same click will time out again. "
               "send_msg_to_user('done message'), "
               "report_infeasible('reason') -- report_infeasible ONLY when the "
               "task is genuinely impossible on this site, NOT when you are "
               "stuck, out of ideas, or cannot find something yet. If an element "
               "is not visible, navigate or look elsewhere first.")

EXPLORER_SYS = (
    "PROPOSE concrete, feasible tasks a typical user could do on THIS page. "
    "Return JSON {\"tasks\": [{\"text\": \"...\", \"type\": \"INFO\"|\"NAV\"|\"MOD\"|\"COMPOSITE\"}, ...]}.\n"
    "Phrase every task the way a real user would state their GOAL or intent -- a "
    "natural request, NOT a click-by-click script. Say WHAT they want, not which "
    "buttons to press. \n"
    "  GOOD: 'How much did I spend on shopping in March?', 'Add a Samsung Galaxy "
    "S21 to my wish list', 'Show me the cheapest in-stock wireless mouse and add "
    "it to the cart'.\n"
    "  BAD (too rigid / step-by-step): 'Click the March filter, then read the "
    "total', 'Open the product page, click Add to Wishlist'.\n"
    "Rules:\n"
    "- Be SPECIFIC using names/values visible on the page (e.g. 'Add the Sony PS5 "
    "to the cart', 'Open the post titled \"Best budget GPU\"'), NOT generic templates "
    "like 'add item to cart' or 'search for a product'.\n"
    "- \"type\" must be exactly one of: INFO (find/extract a fact), NAV (reach a "
    "specific page), MOD (change content/state -- post, vote, add to cart, edit), "
    "COMPOSITE (a goal that inherently needs SEVERAL actions to satisfy, stated as "
    "ONE natural intent -- e.g. 'Buy the cheapest in-stock wireless mouse', 'Post a "
    "reply to the top comment on the newest post in r/technology', 'Add all books "
    "by Jane Smith to the cart and open the cart' -- name the concrete targets from "
    "THIS page, but do NOT spell out the individual steps). "
    "List COMPOSITE tasks FIRST, then MOD, then INFO. Include at least 2-3 "
    "COMPOSITE tasks whenever the page affords a multi-step goal -- these are how "
    "reusable, chainable skills get discovered -- and include a few INFO fact-lookup "
    "tasks specific to this page (information-seeking is common in real use). "
    "Propose AT MOST ONE NAV task (list it LAST), and only to reach an important "
    "page that no COMPOSITE/MOD task here would visit: COMPOSITE and MOD tasks "
    "already navigate to new pages as they act, so a single NAV is enough as a "
    "reserve.\n"
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
    "- If THIS page has a form with MULTIPLE input fields (e.g. checkout, create a "
    "listing/post, edit profile, contact/review form), do NOT propose a task that "
    "fills just one field in isolation ('Enter an email in the email box'). Propose "
    "ONE task that completes the WHOLE form to accomplish its purpose -- e.g. 'Fill "
    "out the checkout form and place the order', 'Create a new forum by completing "
    "the form', 'Submit a product review with a rating and comment'. Such a task is "
    "naturally COMPOSITE.\n"
    "- Focus on common things a real user of THIS site would do; skip niche tasks.\n"
    "- NEVER propose an account/authentication task -- log in, log out, sign in, "
    "sign up, register, create an account, change/reset/forgot password, edit "
    "email/username, manage security settings, or delete/deactivate/close the "
    "account. The session is already authenticated and the account is shared "
    "across exploration runs, so these are useless and risk locking the run out.")

SEEDER_SYS = (
    "SUMMARIZE this website into a reusable profile for an exploration agent. "
    "You are shown the landing page (its URL and accessibility tree). Infer what "
    "KIND of site this is and the main GOALS a real user comes here to accomplish.\n"
    "Return JSON: {\"description\": \"<one or two sentences: what this site is and "
    "who uses it>\", \"capabilities\": [{\"name\": \"<short slug, e.g. 'checkout'>\", "
    "\"goal\": \"<one natural user intent that exercises this capability>\"}, ...]}.\n"
    "Rules:\n"
    "- List 4-8 capabilities, ordered from most central to most peripheral.\n"
    "- Each \"goal\" must be a concrete, self-contained user intent phrased the way "
    "a real user would state it (WHAT they want), NOT a click-by-click script.\n"
    "- Each \"goal\" must inherently take SEVERAL actions to satisfy -- a multi-step "
    "flow, not a one-shot lookup. GOOD: 'Buy the cheapest in-stock wireless mouse "
    "and reach the order confirmation', 'Post a new question to the most active "
    "forum and add a first comment'. BAD (single lookup): 'Find the store's phone "
    "number'. BAD (step script): 'Click Cart, then click Checkout, then click Pay'.\n"
    "- Each \"goal\" must END in a CONCRETE, VERIFIABLE state that a checker (or a "
    "person) could confirm from the resulting page -- e.g. a specific item is in "
    "the cart, a specific product page is open, a new post is visible. AVOID "
    "open-ended activities whose completion is TRIVIAL TO CLAIM: never phrase a "
    "goal around 'explore', 'browse', 'look around', 'view the site/category', or "
    "'find items of interest'. BAD (open-ended): 'Explore the electronics "
    "category', 'Click product showcases to view details'. GOOD (verifiable): "
    "'Open the Electronics category and add the first in-stock item to the cart', "
    "'Search for \"wireless mouse\" and open the top result's product page'.\n"
    "- Every INPUT the goal needs must either be STATED in the goal itself or be "
    "derivable from the page (e.g. 'the cheapest one', 'the first result', 'the "
    "most recent order'). NEVER leave a value for the agent to invent -- it cannot "
    "know which one you meant and will correctly refuse. BAD (unspecified value): "
    "'Edit a product's price and quantity and save', 'Update an order's status'. "
    "GOOD (value stated): 'Set the price of the first product in the catalog to "
    "19.99 and save'. GOOD (value derivable): 'Open the most recent order and "
    "change its status to the next one its page offers'.\n"
    "- Ground every capability in what THIS site actually offers -- use section/menu "
    "names visible in the tree. Do NOT invent features you cannot see on the page.\n"
    "- Prefer capabilities whose completion CHANGES site state or reaches a NEW page "
    "(these yield chainable, reusable skills) over pure read-only lookups.\n"
    "- NEVER include an account/authentication goal -- log in/out, sign in/up, "
    "register, create an account, change/reset/forgot password, edit email/username, "
    "manage security settings, or delete/deactivate the account. The session is "
    "already authenticated and the account is shared across runs, so these are "
    "useless and risk locking the run out.")

SOLVER_SYS = (
    "You are a web agent. Reach the GOAL by choosing the single best next action from "
    "the page accessibility tree (elements shown as [bid] role 'name'). " + ACTIONS_DOC +
    " Think step by step; reflect on your past actions and any error from your last "
    "action before deciding. Output ONE action as JSON "
    "{\"thought\": \"...\", \"action\": \"<one action>\"}. "
    "Examples: {\"thought\": \"I need to open the product to read its price. It is "
    "the link with bid 12.\", \"action\": \"click('12')\"} ; "
    "{\"thought\": \"My last action failed because bid 41 does not exist on this "
    "page. Looking at the tree again, the search box is bid 57, so I will type "
    "there instead.\", \"action\": \"fill('57','wireless mouse')\"} ; "
    "{\"thought\": \"My click on bid 41 timed out, so the element is on the page "
    "but not clickable yet -- it is probably below the fold. I will scroll down "
    "to bring it into view before clicking it again.\", \"action\": "
    "\"scroll(0, 400)\"} ; "
    "{\"thought\": \"I found the information requested, I will send it to the "
    "user.\", \"action\": \"send_msg_to_user('done: price is $19')\"}. "
    "When the `# Error Message from Last Action` section is not (none), your "
    "thought MUST say what went wrong and what you are doing differently -- "
    "never repeat the action that just failed. "
    "Call send_msg_to_user ONLY when the goal is fully achieved."
    " For 'go to page X' goals: once the URL/page has changed to the requested "
    "destination the goal is DONE -- call send_msg_to_user immediately; do NOT "
    "click the same link again.")


READONLY_NOTE = ("\nREAD-ONLY MODE: propose ONLY tasks with type INFO or NAV. Do NOT "
                 "propose any type MOD / content-modification tasks (no posting, "
                 "commenting, voting, adding to cart, or checkout).")

_AXTREE_CAP = 6000
_HISTORY_WINDOW = 6      # how many past actions the prompt shows


def _cap_axtree(axtree: str) -> str:
    """Truncate axtree text to _AXTREE_CAP chars, appending an explicit
    marker when content was cut. Silently chopping the tree would let the
    model mistake a truncated view for the complete page; the marker at
    least tells it more content exists. Note: `scroll` (exposed so the model
    can make an off-screen element actionable) does NOT change what
    flatten_axtree_to_str returns here -- BrowserGym's axtree is not
    viewport-scoped, so scrolling never fixes truncation
    (see WebArenaBrowser.observation() for the filter_visible_only change
    that reduces how often this cap is even hit)."""
    text = axtree or ""
    if len(text) <= _AXTREE_CAP:
        return text
    return text[:_AXTREE_CAP] + f"\n... [TRUNCATED: {len(text) - _AXTREE_CAP} more characters not shown]"


_NEXT_ACTION_INSTRUCTION = (
    "Think step by step and produce your next best action. Reflect on your past "
    "actions, any resulting error message, and the current state of the page "
    "before deciding. All reasoning goes in the \"thought\" key; exactly one "
    "action goes in the \"action\" key.")


def build_solver_prompt(goal: str, history_lines: list[str], last_error: str,
                        url: str, axtree: str, guidance: str = "") -> str:
    """The Solver's user message, sectioned after Go-Browse's Appendix A.2.

    ONE builder for both the live Solver (agents.py) and the offline SFT
    exporter (build_sft_dataset.py) -- they used to assemble the same prompt by
    hand in two places and had already drifted: the live prompt carried a
    `LAST ACTION ERROR` block that the exporter dropped entirely, so every
    recovery step was trained without the evidence that motivated it.

    `# Error Message from Last Action` is always present, "(none)" when clean,
    so the section is a fixed part of the format the model learns to consult
    rather than a block that only materializes on the rare error step. The URL
    is site-relative (see urls.py) so no instance's host is memorized.
    """
    hist = "\n".join(history_lines[-_HISTORY_WINDOW:]) or "(none)"
    return (f"# Goal\n{goal}\n\n"
            f"# Current Page\nURL: {site_relative(url)}\n\n{_cap_axtree(axtree)}\n\n"
            f"# Error Message from Last Action\n{last_error or '(none)'}\n\n"
            f"# History of Past Actions\n{hist}\n\n"
            f"# Next Action\n{guidance}{_NEXT_ACTION_INSTRUCTION}")


def step_outcome(pre_url: str, pre_axtree: str, url: str, axtree: str) -> str:
    """Human-readable result of one action: shared by the live Solver prompt
    and the offline SFT dataset builder / thought re-annotator so all three
    describe trajectory history identically."""
    if url != pre_url:
        return f"now at {site_relative(url)}"
    if axtree != pre_axtree:
        return "page changed"
    return "no change"


_FAILED_OUTCOME_CAP = 80


def failed_outcome(error: str) -> str:
    """`step_outcome`'s counterpart for an action browser.act() rejected.

    A failed action produces no observation to compare, but it still happened
    and the agent must remember it: the history line is what stops the model
    re-deriving the same doomed action from an apparently untouched page.
    Shared by the live Solver and build_sft_dataset.py so both describe a
    failure identically. Collapsed to one capped line -- a Playwright timeout
    carries a multi-line "Call log:" tail that would swamp the history block.
    """
    msg = " ".join((error or "").split())[:_FAILED_OUTCOME_CAP]
    return f"action failed: {msg}" if msg else "action failed"


# Task tags whose goal is to change the site's state, so "I declared done" is not
# on its own evidence that anything happened (see Solver.solve's success gate).
_STATE_CHANGING_TAGS = ("[MOD]", "[COMPOSITE]")


def terminal_message(action: str) -> str:
    """The message argument of a terminal `send_msg_to_user(...)` /
    `report_infeasible(...)` action, or "" for any other action.

    An INFO task's whole answer lives in this argument ("done: Lifetime Sales
    value is $194.40"); without extracting it, `outcome.response` stayed empty
    for every episode and nothing downstream could score the answer.
    """
    a = (action or "").strip()
    for name in ("send_msg_to_user", "report_infeasible"):
        if a.startswith(name + "(") and a.endswith(")"):
            inner = a[len(name) + 1:-1].strip().rstrip(",").strip()
            try:
                val = ast.literal_eval(inner)
            except (ValueError, SyntaxError):
                return inner.strip("'\"")
            return val if isinstance(val, str) else str(val)
    return ""


class SiteSeeder:
    """One-shot per run: turns a landing page into a {description, capabilities[]}
    profile that conditions task proposals and seeds top-down GOAL tasks. LLM-backed;
    only used when run.use_site_seed is on, so the mock pipeline is untouched."""

    _AUTH_RE = re.compile(
        r"\b(log ?in|log ?out|sign ?in|sign ?up|register|create an account|"
        r"password|deactivate|delete (the |your )?account)\b", re.I)

    def __init__(self, llm):
        self.llm = llm

    def derive(self, obs: dict) -> dict:
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}"
        out = self.llm.complete_json(SEEDER_SYS, prompt)
        description = out.get("description")
        raw = out.get("capabilities")
        if not isinstance(description, str) or not isinstance(raw, list):
            return {"description": "", "capabilities": []}
        caps = []
        for c in raw:
            if not isinstance(c, dict):
                continue
            goal = c.get("goal")
            name = c.get("name") or (goal or "")
            if not isinstance(goal, str) or not goal.strip():
                continue
            if self._AUTH_RE.search(goal) or self._AUTH_RE.search(str(name)):
                continue
            caps.append({"name": str(name).strip(), "goal": goal.strip()})
        return {"description": description.strip(), "capabilities": caps}


PLANNER_SYS = (
    "DECOMPOSE the user's GOAL into an ordered list of concrete subgoals a web "
    "agent will complete one at a time, in order, to achieve the GOAL on the "
    "current site. You are given the GOAL and the current page (URL + "
    "accessibility tree).\n"
    "Return JSON {\"subgoals\": [\"<subgoal 1>\", \"<subgoal 2>\", ...]}.\n"
    "Rules:\n"
    "- 2-5 subgoals. Each is a single, concrete, checkable step stated as an "
    "intent (e.g. 'Open the Electronics category page', 'Select the first "
    "in-stock product', 'Add it to the cart'), NOT a click-by-click script.\n"
    "- Order them so each subgoal leaves the page in the state the next needs.\n"
    "- The LAST subgoal must correspond to the GOAL's final end-state (what a "
    "grader would check), so completing it means the whole GOAL is done.\n"
    "- Ground subgoals in what THIS page/site actually offers; do not invent "
    "steps for features you cannot see.\n"
    "- If the GOAL is already a single concrete step, return it as one subgoal.")


class GoalPlanner:
    """Turns a multi-step GOAL into an ordered subgoal list the Solver pursues
    one at a time. LLM-backed; only used when run.plan_subgoals is on."""

    def __init__(self, llm):
        self.llm = llm

    def plan(self, goal: str, obs: dict) -> list[str]:
        prompt = f"GOAL: {goal}\n\nURL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}"
        out = self.llm.complete_json(PLANNER_SYS, prompt)
        subs = out.get("subgoals")
        if not isinstance(subs, list):
            return []
        return [s.strip() for s in subs if isinstance(s, str) and s.strip()]


class PageExplorer:
    _TAG_RE = re.compile(r"^\s*\[(INFO|NAV|MOD|COMPOSITE)\]\s*", re.I)
    _PUNCT_RE = re.compile(r"[^\w\s]")
    _SEEN_HINT_SIZE = 25  # cap how many prior tasks get echoed back as negative context
    _COMPOSITE_RESERVE = 3  # min COMPOSITE tasks kept when a page overflows max_tasks
    _NAV_CAP = 1       # NAV is a thin reserve; COMPOSITE/MOD already grow the frontier
    _INFO_RESERVE = 2  # keep some INFO for SFT data (WebArena is info-seeking heavy)
    # INFO is capped UNCONDITIONALLY, like NAV: the reserve above only bounds INFO
    # when a page overflows max_tasks, so a page proposing few tasks let every INFO
    # through. Measured on a 158-node reddit run, that made INFO 49% of all
    # successful episodes (272/560) -- and 237 of those 272 finished with
    # send_msg_to_user and NO browser action at all, which is answer-lookup data,
    # not the acting behaviour the SFT target needs.
    _INFO_CAP = 2

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
            if isinstance(raw_type, str) and raw_type.strip().upper() in ("INFO", "NAV", "MOD", "COMPOSITE"):
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

    def propose(self, obs: dict, screenshot_b64: str | None = None,
                site_seed: dict | None = None) -> list[str]:
        system = EXPLORER_SYS + (READONLY_NOTE if self.read_only else "")
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}"
        caps = (site_seed or {}).get("capabilities") or []
        if caps:
            cap_lines = "\n".join(f"- {c['name']}: {c['goal']}" for c in caps)
            prompt += (
                "\n\nSITE GOALS (what this whole site is for) -- use as EXTRA "
                "context, NOT as a replacement for page-specific tasks:\n"
                f"{site_seed.get('description', '')}\n"
                "Capabilities a user comes here to accomplish:\n"
                f"{cap_lines}\n"
                "Still propose a DIVERSE mix of page-specific tasks grounded in THIS "
                "page (COMPOSITE, MOD, INFO, and at most one reserve NAV). In "
                "ADDITION, when this page affords it, include 1-2 COMPOSITE tasks "
                "that advance one of the site goals above. Do NOT let the site goals "
                "crowd out page-specific tasks, and do NOT propose a capability this "
                "page cannot support.")
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
        # NAV is a thin reserve, capped UNCONDITIONALLY: COMPOSITE/MOD tasks
        # already navigate to new pages as they act (adding tier-0 frontier
        # URLs), and pure-NAV skills are low value + prone to sitewide-menu
        # boilerplate, so keep at most _NAV_CAP NAV tasks regardless of budget.
        kept = {"NAV": 0, "INFO": 0}
        caps = {"NAV": self._NAV_CAP, "INFO": self._INFO_CAP}
        capped = []
        for text, tag in parsed:
            if tag in caps:
                if kept[tag] >= caps[tag]:
                    continue
                kept[tag] += 1
            capped.append((text, tag))
        parsed = capped
        if len(parsed) > self.max_tasks:
            # Keep-priority on overflow:
            #   COMPOSITE(reserve) -> MOD -> INFO(reserve) -> NAV(<=cap, already
            #   enforced above) -> COMPOSITE(extra) -> UNKNOWN -> INFO(extra).
            # INFO gets a guaranteed reserve (it is the WebArena-aligned SFT data),
            # but INFO beyond the reserve is dropped first (it never grows frontier).
            composite = [p for p in parsed if p[1] == "COMPOSITE"]
            mod = [p for p in parsed if p[1] == "MOD"]
            nav = [p for p in parsed if p[1] == "NAV"]
            unknown = [p for p in parsed if p[1] == "UNKNOWN"]
            info = [p for p in parsed if p[1] == "INFO"]
            parsed = (composite[: self._COMPOSITE_RESERVE]
                      + mod
                      + info[: self._INFO_RESERVE]
                      + nav
                      + composite[self._COMPOSITE_RESERVE:]
                      + unknown
                      + info[self._INFO_RESERVE:])[: self.max_tasks]
        return [f"[{tag}] {text}" if tag != "UNKNOWN" else text for text, tag in parsed]


class Solver:
    _TARGET_RE = re.compile(r"\('([^']*)'")
    _WARN_AFTER_REPEATS = 2   # nudge once the same target is hit this many times in a row
    _MAX_REPEATS = 4          # give up if nudging didn't help after this many
    _SUBGOAL_CAP = 8          # max steps on one subgoal before auto-advancing (C2)
    _NOVELTY_WARN = 4         # warn after this many steps reaching no new page (C3)
    _NOVELTY_MAX = 8          # hard-stop after this many (C3)
    # What the wrap-up prompt tells the model about WHY the episode stopped. Only
    # "budget" means the step allowance ran out; the guards fire much earlier, and
    # claiming otherwise puts a false reason into report_infeasible.
    _STOP_REASONS = {
        "budget": "Your action budget is exhausted.",
        "stuck": ("You were stopped early: your last actions kept targeting the same "
                  "element with no visible progress."),
        "novelty": ("You were stopped early: your recent actions reached no new page."),
    }

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

    def solve(self, browser, goal: str, goal_predicate: str | None = None,
              max_steps: int | None = None, subgoals=None):
        """Drive the browser toward `goal`.

        `max_steps` overrides self.max_steps for this call only (used to give
        GOAL tasks a larger budget than LOCAL); None keeps the instance default.
        `subgoals` (C2): an ordered list the solver pursues one at a time --
        the current subgoal is shown in the prompt and advances on the model's
        `subgoal_done` signal or after `_SUBGOAL_CAP` steps. None -> plain loop.
        Returns (steps, obs_texts, obs_screenshots, final_obs, success, infeasible,
        stop_reason). `stop_reason` is "" when the episode ended on a terminal
        action of its own, else the guard that stopped it ("budget"/"stuck"/
        "novelty") -- i.e. the terminal action came from the wrap-up call, so
        whatever it declared is a post-hoc rationalization, not a decision the
        agent reached while solving.
        """
        budget = max_steps if max_steps is not None else self.max_steps
        sg = list(subgoals) if subgoals else None
        sg_idx, sg_steps = 0, 0
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
        # Why the loop ended, for the wrap-up prompt below. The two guards stop an
        # episode after a handful of steps, so telling the model its budget ran out
        # would be false -- and a real shopping_admin run shows it repeats whatever
        # the prompt claims: episodes that stopped at 5-6 steps recorded
        # report_infeasible('action budget exhausted, ...'), which then became both
        # the analysis record and the SFT target.
        stop_reason = "budget"
        seen_obs = {(obs["url"], obs["axtree"])}  # observations already reached (C3)
        novelty_streak = 0                        # trailing steps reaching no new page
        for _ in range(budget):
            if novelty_streak >= self._NOVELTY_MAX:
                stop_reason = "novelty"
                # Churn across DIFFERENT targets that never reaches a new page is
                # missed by the same-target guard below (v2: 3 GOALs burned the
                # whole budget this way). Stop instead of exhausting the budget.
                print(f"    [solver] giving up: {novelty_streak} steps with no new page reached")
                break
            novelty_warning = ""
            if novelty_streak >= self._NOVELTY_WARN:
                novelty_warning = ("\n\nWARNING: your recent actions have not reached "
                                   "any new page. Try a genuinely different approach, or "
                                   "call report_infeasible if this cannot be done here.")
            streak = self._stuck_streak(history, progressed)
            if streak >= self._MAX_REPEATS:
                # A text nudge alone isn't reliably obeyed (verified against a
                # real run: the warning was present in the prompt from the 3rd
                # call onward and the model kept issuing the exact same click
                # anyway for all 15 steps). Stop spending steps on a target
                # that clearly isn't moving instead of exhausting max_steps.
                print(f"    [solver] giving up: target {self._action_target(history[-1])!r} "
                      f"hit {streak}x in a row with no progress")
                stop_reason = "stuck"
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
            subgoal_block = ""
            if sg is not None and sg_idx < len(sg):
                subgoal_block = (
                    f"\n\nOVERALL GOAL: {goal}\nCURRENT SUBGOAL "
                    f"({sg_idx + 1}/{len(sg)}): {sg[sg_idx]}\n"
                    "Work ONLY on the current subgoal right now. When THIS subgoal "
                    'is done, output {"subgoal_done": true, ...} to advance. Call '
                    "send_msg_to_user ONLY after the LAST subgoal is complete.")
            recent = [f"- {h} -> {o}" for h, o in
                      zip(history[-_HISTORY_WINDOW:], outcomes[-_HISTORY_WINDOW:])]
            guidance = "".join(b.strip("\n") + "\n\n"
                              for b in (repeat_warning, novelty_warning, subgoal_block) if b)
            prompt = build_solver_prompt(goal, recent, last_error, obs["url"],
                                          obs["axtree"], guidance=guidance)
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
            # C2: advance to the next subgoal on the model's signal. gpt-4o-mini
            # often emits it as a TERMINAL send_msg_to_user('subgoal_done...') rather
            # than the JSON field (run v3: episodes ended at subgoal 1), so BOTH a
            # `subgoal_done` field and a send_msg_to_user count as "advance" while a
            # next subgoal exists -- only the LAST subgoal may actually end the run.
            if sg is not None and sg_idx < len(sg) - 1 and (
                    out.get("subgoal_done") or action.startswith("send_msg_to_user")):
                sg_idx += 1
                sg_steps = 0
                continue
            # Full thought, not thought[:100]: obs_summary is persisted verbatim as
            # the SFT target's reasoning (runtime.py), and a real shopping_admin run
            # had 41% of steps cut off mid-word at the old ceiling. Prompt-side
            # consumers truncate at their own call site (segmentation.py).
            steps.append(Step(action=action, url=obs["url"], obs_summary=thought,
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
                # A failed action is still an action: record it like any other,
                # with no progress. It used to `continue` here, leaving
                # history/outcomes/progressed/novelty untouched, which made BOTH
                # anti-loop guards blind to a repeated failure -- only the budget
                # guard could end such an episode, and 118 episodes of a real
                # shopping run spent all 15 steps re-issuing one click whose
                # element was never actionable (500ms Playwright timeout).
                history.append(action)
                outcomes.append(failed_outcome(last_error))
                progressed.append(False)
                novelty_streak += 1
                continue
            history.append(action)
            outcomes.append(step_outcome(pre_url, pre_axtree, obs["url"], obs["axtree"]))
            # "progress" for the same-target stuck guard = the URL changed. Keying on
            # url-OR-axtree let run v3 hammer one control (click('247') x9) forever,
            # because each click wiggled the axtree (dropdown/toggle) and reset the
            # streak while the page never actually advanced. A legitimate multi-step
            # flow uses DIFFERENT targets (so the same-target guard never groups it)
            # or genuinely changes the URL, so url-only progress is safe here.
            progressed.append(obs["url"] != pre_url)
            # C3: track whether this action reached a genuinely new observation
            key = (obs["url"], obs["axtree"])
            if key in seen_obs:
                novelty_streak += 1
            else:
                seen_obs.add(key)
                novelty_streak = 0
            # C2: auto-advance a subgoal the solver is stuck on (never past the last)
            if sg is not None:
                sg_steps += 1
                if sg_steps >= self._SUBGOAL_CAP and sg_idx < len(sg) - 1:
                    sg_idx += 1
                    sg_steps = 0
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
                           + f"\n\nURL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}"
                           + f"\n\n{self._STOP_REASONS[stop_reason]} If the goal has "
                             "ALREADY been achieved (e.g. you are on the requested "
                             "page), call send_msg_to_user('done: ...') NOW. If the "
                             "goal cannot be achieved, call report_infeasible('why') "
                             "-- state the REAL obstacle, not the fact that you "
                             "stopped. Answer with one of those two actions only.")
            out = self.llm.complete_json(SOLVER_SYS, wrap_prompt)
            action = (out.get("action") or "").strip()
            if action.startswith("send_msg_to_user") or action.startswith("report_infeasible"):
                steps.append(Step(action=action, url=obs["url"],
                                  obs_summary=str(out.get("thought", "")),
                                  axtree=obs["axtree"]))
                obs_texts.append(obs["axtree"])
                obs_screenshots.append(None)

        infeasible = bool(steps) and steps[-1].action.startswith("report_infeasible")
        # success for non-predicate goals = agent declared done without error
        if goal_predicate is None and steps and steps[-1].action.startswith("send_msg_to_user"):
            success = True
            # ...but a task that CHANGES the site cannot have been done if nothing
            # on the page ever changed, whatever the model declares. A real
            # shopping_admin episode declared "[MOD] Send an email confirmation for
            # order #000000299" done in one step, zero browser actions, on the
            # grounds that it "was already sent". `outcomes` only holds actions that
            # actually executed, so an errored or terminal action can't satisfy this.
            if (goal.strip().startswith(_STATE_CHANGING_TAGS)
                    and not any(o != "no change" for o in outcomes)):
                print("    [solver] declared done but no action ever changed the "
                      "page -- not a success for a state-changing task")
                success = False
        return (steps, obs_texts, obs_screenshots, obs, success, infeasible,
                stop_reason if exhausted else "")
