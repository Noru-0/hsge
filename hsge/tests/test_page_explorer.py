"""PageExplorer must always return task strings, even when the LLM doesn't
follow the requested {"tasks": ["...", ...]} schema exactly.

Regression: gpt-4o (unlike DeepSeek) sometimes wraps a task in an object
(e.g. {"task": "...", "type": "NAV"}) instead of a flat string, despite
EXPLORER_SYS asking for one. propose() used to pass such dicts straight
through, which crashed downstream code (runtime.py did `task[:50]`,
str-only operations) with a KeyError on a slice.
"""

from hsge.webarena.agents import EXPLORER_SYS, PageExplorer


class _StubLLM:
    def __init__(self, tasks):
        self._tasks = tasks

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"tasks": self._tasks}


def test_propose_returns_only_strings_when_llm_mixes_shapes():
    llm = _StubLLM([
        {"task": "[NAV] Click X", "type": "NAV"},
        "[INFO] plain string task",
        {"description": "[MOD] uses a different key"},
        {"unrelated": "no usable text field"},
        42,
    ])
    explorer = PageExplorer(llm)

    tasks = explorer.propose({"url": "http://x", "axtree": "irrelevant"})

    assert all(isinstance(t, str) for t in tasks)
    assert tasks == ["[NAV] Click X", "[INFO] plain string task", "[MOD] uses a different key"]


def test_propose_all_strings_unaffected():
    llm = _StubLLM(["[NAV] a", "[INFO] b"])
    explorer = PageExplorer(llm)

    assert explorer.propose({"url": "http://x", "axtree": ""}) == ["[NAV] a", "[INFO] b"]


class _RefusesWithImageLLM:
    """Simulates a vision model that refuses (empty response) only when an
    image is attached, succeeding on a plain text-only retry."""

    def __init__(self):
        self.calls = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls.append(image_b64)
        if image_b64:
            return {}
        return {"tasks": ["[INFO] text-only fallback task"]}


def test_propose_retries_without_image_when_vision_call_is_refused():
    llm = _RefusesWithImageLLM()
    explorer = PageExplorer(llm, vision=True)

    tasks = explorer.propose({"url": "http://x", "axtree": "irrelevant"},
                              screenshot_b64="ZmFrZQ==")

    assert tasks == ["[INFO] text-only fallback task"]
    assert llm.calls == ["ZmFrZQ==", None]  # first with image, then retried without


def test_propose_does_not_retry_when_vision_is_off():
    llm = _RefusesWithImageLLM()
    explorer = PageExplorer(llm, vision=False)

    tasks = explorer.propose({"url": "http://x", "axtree": "irrelevant"},
                              screenshot_b64="ZmFrZQ==")

    assert tasks == ["[INFO] text-only fallback task"]
    assert llm.calls == [None]  # vision off -> never sent the image in the first place


def test_explorer_sys_forbids_leaking_the_answer_in_info_tasks():
    """Regression guard: a real run showed [INFO] tasks like 'Read the number
    of submissions for X (5,718 submissions)' -- the goal already contains the
    answer, so solving it requires zero real navigation/reading and the
    resulting trajectory is useless as training data. Can't unit-test that an
    LLM actually complies with a prompt, but this guards against the explicit
    anti-leak instruction being accidentally removed later."""
    assert "must never state the value/answer itself" in EXPLORER_SYS.lower()


def test_propose_keeps_nav_mod_over_info_when_truncating():
    """Regression: a real run on a forum-listing page got back 4 [INFO] tasks
    and frontier growth was 0 that node. EXPLORER_SYS asks the model to list
    INFO tasks first, then NAV, then MOD; naively slicing to max_tasks after
    that ordering silently drops every NAV/MOD task whenever a page offers
    more INFO candidates than max_tasks -- exactly the tasks that would have
    grown the frontier. INFO must be what gets dropped, not NAV/MOD."""
    llm = _StubLLM([
        "[INFO] a", "[INFO] b", "[INFO] c", "[INFO] d", "[INFO] e",
        "[NAV] open the AskReddit forum",
    ])
    explorer = PageExplorer(llm, max_tasks=4)

    tasks = explorer.propose({"url": "http://x", "axtree": "irrelevant"})

    assert "[NAV] open the AskReddit forum" in tasks
    assert len(tasks) == 4


def test_propose_preserves_order_when_nothing_is_dropped():
    llm = _StubLLM(["[INFO] a", "[NAV] b", "[MOD] c"])
    explorer = PageExplorer(llm, max_tasks=4)

    assert explorer.propose({"url": "http://x", "axtree": ""}) == ["[INFO] a", "[NAV] b", "[MOD] c"]


def test_explorer_sys_forbids_navigating_to_the_current_page():
    """Regression guard: a real run showed a [NAV] "Go to the Wiki page" task
    proposed while the axtree/URL already WAS the wiki page -- the Solver
    then clicked the same link 15 times and burned the whole episode without
    ever reaching send_msg_to_user. Can't unit-test LLM compliance, but this
    guards against the instruction being accidentally removed later."""
    assert "already on" in EXPLORER_SYS.lower()


class _RecordingStubLLM:
    """Like _StubLLM but records every prompt it was called with, and can
    serve a different batch of tasks per call (one per simulated page)."""

    def __init__(self, batches):
        self._batches = list(batches)
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        return {"tasks": self._batches.pop(0)}


def test_propose_drops_near_duplicate_tasks_seen_at_earlier_pages():
    """Regression: a real 11-page run had 26/57 (46%) of all proposed tasks be
    near-identical 'Go to the Forums/Wiki/Home page' boilerplate, re-proposed
    at almost every page because the sitewide nav menu appears everywhere.
    One PageExplorer instance lives for the whole run (see runtime.py), so it
    must remember what it already proposed and drop repeats -- even across
    trivial punctuation/case differences."""
    llm = _RecordingStubLLM([
        ["[NAV] Go to the 'Forums' page.", "[INFO] Find the number of notifications."],
        ["[NAV] Go to the Forums page", "[INFO] Find the number of messages."],
    ])
    explorer = PageExplorer(llm)

    first = explorer.propose({"url": "http://x/a", "axtree": ""})
    second = explorer.propose({"url": "http://x/b", "axtree": ""})

    assert first == ["[NAV] Go to the 'Forums' page.", "[INFO] Find the number of notifications."]
    # the near-duplicate "Go to the Forums page" is dropped the second time;
    # the genuinely new INFO task survives
    assert second == ["[INFO] Find the number of messages."]


def test_propose_includes_already_proposed_tasks_as_negative_context():
    """The prompt for a later page should tell the model what's already been
    proposed so it can avoid re-proposing sitewide nav boilerplate in the
    first place, rather than relying only on the after-the-fact code dedup."""
    llm = _RecordingStubLLM([["[NAV] Go to the Forums page"], ["[INFO] Find something else."]])
    explorer = PageExplorer(llm)

    explorer.propose({"url": "http://x/a", "axtree": ""})
    explorer.propose({"url": "http://x/b", "axtree": ""})

    assert "Go to the Forums page" not in llm.prompts[0]
    assert "Go to the Forums page" in llm.prompts[1]


def test_propose_accepts_structured_type_field_without_a_bracket():
    """Regression: a real run showed 89% (51/57) of returned tasks had no
    [INFO]/[NAV]/[MOD] bracket at all, despite EXPLORER_SYS asking for one --
    gpt-4o's natural tendency is to put the classification in a `type` field
    on an object instead (already handled for text salvage, but the `type`
    field itself used to be discarded). It must now be read and used."""
    llm = _StubLLM([
        {"text": "Find the total number of posts.", "type": "INFO"},
        {"text": "Create a new post.", "type": "MOD"},
    ])
    explorer = PageExplorer(llm)

    tasks = explorer.propose({"url": "http://x", "axtree": ""})

    assert tasks == ["[INFO] Find the total number of posts.", "[MOD] Create a new post."]


def test_readonly_drops_mod_task_classified_only_via_type_field():
    llm = _StubLLM([{"text": "Create a new post.", "type": "MOD"}])
    explorer = PageExplorer(llm, read_only=True)

    assert explorer.propose({"url": "http://x", "axtree": ""}) == []


def test_readonly_drops_untagged_task_fail_closed():
    """Regression: ep_0050 in a real run was "Click the 'Save' button to
    create the new page." with NO bracket and NO type field at all -- a real
    [MOD] action that the old substring-only filter (`"[MOD]" not in text`)
    would NOT have caught in --read-only mode. An unclassifiable task must be
    dropped under read_only, not assumed safe."""
    llm = _StubLLM(["Click the 'Save' button to create the new page."])
    explorer = PageExplorer(llm, read_only=True)

    assert explorer.propose({"url": "http://x", "axtree": ""}) == []


def test_untagged_task_passes_through_unchanged_when_not_read_only():
    llm = _StubLLM(["Click the 'Save' button to create the new page."])
    explorer = PageExplorer(llm)

    assert explorer.propose({"url": "http://x", "axtree": ""}) == [
        "Click the 'Save' button to create the new page."]


class _PromptCapturingLLM:
    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        return {"tasks": []}


def test_propose_truncates_long_axtree_with_marker():
    llm = _PromptCapturingLLM()
    explorer = PageExplorer(llm)
    long_axtree = "y" * 7000

    explorer.propose({"url": "http://x", "axtree": long_axtree})

    assert "TRUNCATED" in llm.prompts[0]
    assert len(llm.prompts[0]) < 7000 + 200   # not the raw 7000 chars plus a small prompt overhead


def test_parse_task_accepts_composite_type_and_bracket():
    assert PageExplorer._parse_task(
        {"text": "open post then reply", "type": "COMPOSITE"}
    ) == ("open post then reply", "COMPOSITE")
    assert PageExplorer._parse_task(
        "[COMPOSITE] open post then reply"
    ) == ("open post then reply", "COMPOSITE")


def test_read_only_drops_composite_task():
    llm = _StubLLM([
        {"text": "read the count", "type": "INFO"},
        {"text": "go to forums", "type": "NAV"},
        {"text": "open post then reply", "type": "COMPOSITE"},
    ])
    explorer = PageExplorer(llm, read_only=True)
    tasks = explorer.propose({"url": "http://x", "axtree": ""})
    assert tasks == ["[INFO] read the count", "[NAV] go to forums"]


def test_truncation_keeps_composite_over_info():
    llm = _StubLLM([
        {"text": "info one", "type": "INFO"},
        {"text": "info two", "type": "INFO"},
        {"text": "open post then reply", "type": "COMPOSITE"},
    ])
    explorer = PageExplorer(llm, max_tasks=1)
    tasks = explorer.propose({"url": "http://x", "axtree": ""})
    assert tasks == ["[COMPOSITE] open post then reply"]


def test_truncation_reserves_composite_against_a_flood_of_mod():
    """COMPOSITE reserve must survive overflow even when MOD floods the page
    (COMPOSITE used to sit last in the non-INFO bucket and get dropped first).
    At least _COMPOSITE_RESERVE COMPOSITE must survive. (NAV no longer floods:
    it is capped to _NAV_CAP unconditionally -- see the NAV-cap tests below.)"""
    tasks_in = (
        [{"text": f"mod {i}", "type": "MOD"} for i in range(6)]
        + [{"text": "buy the cheapest mouse", "type": "COMPOSITE"},
           {"text": "reply to the top comment on the newest post", "type": "COMPOSITE"}]
    )
    explorer = PageExplorer(_StubLLM(tasks_in), max_tasks=4)

    tasks = explorer.propose({"url": "http://x", "axtree": ""})

    assert len(tasks) == 4
    composite = [t for t in tasks if t.startswith("[COMPOSITE]")]
    assert composite == ["[COMPOSITE] buy the cheapest mouse",
                         "[COMPOSITE] reply to the top comment on the newest post"]
    # MOD isn't fully starved either -- it fills the remaining slots
    assert any(t.startswith("[MOD]") for t in tasks)


def test_nav_capped_to_one_even_when_composite_is_scarce():
    """NAV is a thin reserve (_NAV_CAP=1): a page flooding NAV keeps at most one,
    and the single COMPOSITE still survives."""
    tasks_in = (
        [{"text": "the one composite", "type": "COMPOSITE"}]
        + [{"text": f"nav {i}", "type": "NAV"} for i in range(6)]
    )
    explorer = PageExplorer(_StubLLM(tasks_in), max_tasks=4)

    tasks = explorer.propose({"url": "http://x", "axtree": ""})

    assert "[COMPOSITE] the one composite" in tasks
    assert len([t for t in tasks if t.startswith("[NAV]")]) == 1


def test_explorer_sys_forbids_account_auth_tasks():
    """Guard: login/logout/sign-up/register/change-password tasks are useless
    here (the session is already authenticated, and the account is shared
    across runs) and risk locking the run out. This guards the anti-auth
    instruction against accidental removal."""
    lower = EXPLORER_SYS.lower()
    assert "account/authentication task" in lower
    for word in ("log in", "log out", "sign in", "sign up", "register", "password"):
        assert word in lower


def test_explorer_sys_asks_to_fill_whole_form_not_single_field():
    """Guard: on a multi-field form page the model should propose one task that
    completes the whole form, not a task per field."""
    lower = EXPLORER_SYS.lower()
    assert "multiple input fields" in lower
    assert "whole form" in lower


def test_explorer_sys_uses_intent_phrasing_and_lists_composite_first():
    """Guard the two prompt requirements this change introduced: tasks phrased
    as user intents (WebArena-style) rather than click-by-click scripts, and
    COMPOSITE listed first so a front-loading model emits more of them."""
    lower = EXPLORER_SYS.lower()
    assert "intent" in lower
    assert "list composite tasks first" in lower


# --- Task 2: NAV/INFO rebalance + seed-conditioned proposals -----------------

class _SeedCapturingLLM:
    """Records the last user prompt and serves a fixed task list."""

    def __init__(self, tasks=None):
        self.prompt = None
        self._tasks = tasks if tasks is not None else ["[NAV] a"]

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompt = prompt
        return {"tasks": self._tasks}


def test_explorer_sys_demotes_nav_to_one_reserve():
    # generation-side: ask for at most one NAV, listed last
    assert "at most one nav" in EXPLORER_SYS.lower()
    # the old "then NAV, then INFO" ordering must be gone
    assert "then nav, then info" not in EXPLORER_SYS.lower()


def test_propose_caps_nav_to_one_even_under_budget():
    # 3 NAV proposed, max_tasks high enough that overflow truncation does NOT fire
    llm = _StubLLM(["[NAV] a", "[NAV] b", "[NAV] c", "[MOD] m", "[COMPOSITE] c1"])
    tasks = PageExplorer(llm, max_tasks=10).propose({"url": "http://x", "axtree": ""})
    assert sum(t.startswith("[NAV]") for t in tasks) == 1
    assert "[MOD] m" in tasks and "[COMPOSITE] c1" in tasks


def test_propose_keep_order_reserves_info_and_one_nav_on_overflow():
    # 2 COMPOSITE, 1 MOD, 2 NAV, 4 INFO; max_tasks=6.
    # NAV cap -> 1 NAV. keep-order: COMPOSITE[:3] + MOD + INFO[:2] + NAV[:1] + ...
    llm = _StubLLM([
        "[COMPOSITE] c1", "[COMPOSITE] c2", "[MOD] m1",
        "[NAV] n1", "[NAV] n2",
        "[INFO] i1", "[INFO] i2", "[INFO] i3", "[INFO] i4"])
    tasks = PageExplorer(llm, max_tasks=6).propose({"url": "http://x", "axtree": ""})
    assert len(tasks) == 6
    assert sum(t.startswith("[COMPOSITE]") for t in tasks) == 2
    assert sum(t.startswith("[MOD]") for t in tasks) == 1
    assert sum(t.startswith("[INFO]") for t in tasks) == 2   # INFO reserve honored
    assert sum(t.startswith("[NAV]") for t in tasks) == 1    # NAV capped to reserve


def test_info_reserve_survives_a_composite_heavy_page():
    # INFO reserve is placed before extra COMPOSITE, so a page with lots of
    # COMPOSITE still keeps >=1 INFO for training data.
    llm = _StubLLM([
        "[COMPOSITE] c1", "[COMPOSITE] c2", "[COMPOSITE] c3", "[COMPOSITE] c4",
        "[MOD] m1", "[INFO] i1", "[INFO] i2"])
    tasks = PageExplorer(llm, max_tasks=6).propose({"url": "http://x", "axtree": ""})
    assert sum(t.startswith("[INFO]") for t in tasks) >= 1


def test_propose_injects_site_goals_when_seed_present():
    llm = _SeedCapturingLLM(["[NAV] a"])
    seed = {"description": "A shop for gadgets.",
            "capabilities": [{"name": "checkout", "goal": "Buy a gadget and confirm the order."}]}
    PageExplorer(llm).propose({"url": "http://x", "axtree": "tree"}, site_seed=seed)
    assert "SITE GOALS" in llm.prompt
    assert "A shop for gadgets." in llm.prompt
    assert "Buy a gadget and confirm the order." in llm.prompt
    # additive, not suppressive
    assert "crowd out" in llm.prompt


def test_propose_omits_site_goals_when_seed_absent_or_empty():
    for seed in (None, {"description": "", "capabilities": []}):
        llm = _SeedCapturingLLM(["[NAV] a"])
        PageExplorer(llm).propose({"url": "http://x", "axtree": "tree"}, site_seed=seed)
        assert "SITE GOALS" not in llm.prompt
