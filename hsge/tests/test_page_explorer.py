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
