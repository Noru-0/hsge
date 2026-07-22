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
