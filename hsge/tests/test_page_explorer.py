"""PageExplorer must always return task strings, even when the LLM doesn't
follow the requested {"tasks": ["...", ...]} schema exactly.

Regression: gpt-4o (unlike DeepSeek) sometimes wraps a task in an object
(e.g. {"task": "...", "type": "NAV"}) instead of a flat string, despite
EXPLORER_SYS asking for one. propose() used to pass such dicts straight
through, which crashed downstream code (runtime.py did `task[:50]`,
str-only operations) with a KeyError on a slice.
"""

from hsge.webarena.agents import PageExplorer


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
