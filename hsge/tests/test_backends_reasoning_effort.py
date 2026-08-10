"""OpenAILLM's `reasoning_effort` param (GPT-5.x).

It is a cost knob, not just a quality one: reasoning tokens bill at the OUTPUT
rate and the Solver makes one call per step, so `none` on the hot path is what
keeps a Luna run cheap. It must be sent only when configured, and a model that
has no such param must degrade the same way an unsupported temperature does.
Run: PYTHONPATH=. python -m pytest hsge/tests/test_backends_reasoning_effort.py -q
"""
import pytest

openai = pytest.importorskip("openai")
httpx = pytest.importorskip("httpx")

from hsge.backends import OpenAILLM


class _Msg:
    class _Choice:
        class _M:
            content = '{"ok": 1}'
            refusal = None
        message = _M()
        finish_reason = "stop"
    choices = [_Choice()]


class _FakeClient:
    def __init__(self, reject=()):
        self.calls = []
        self.reject = reject
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        for param in self.reject:
            if param in kwargs:
                resp = httpx.Response(400, request=httpx.Request("POST", "http://x"))
                raise openai.BadRequestError(
                    f"Unrecognized request argument supplied: {param}",
                    response=resp, body={"error": {"param": param}})
        return _Msg()


def _llm(effort, reject=(), verbosity=None):
    llm = OpenAILLM.__new__(OpenAILLM)      # bypass __init__ (no real OpenAI client)
    llm.model = "gpt-5.6-luna"
    llm.temperature = 1.0
    llm._omit_temperature = False
    llm.reasoning_effort = effort
    llm.verbosity = verbosity
    llm._dropped_params = set()
    llm.client = _FakeClient(reject)
    return llm


def test_sends_reasoning_effort_and_verbosity_when_configured():
    llm = _llm("medium", verbosity="medium")
    assert llm.complete_json("sys", "hi") == {"ok": 1}
    assert llm.client.calls[0]["reasoning_effort"] == "medium"
    assert llm.client.calls[0]["verbosity"] == "medium"


def test_omits_gpt5_params_when_unset():
    """gpt-4o / deepseek have no such params -- never send them unasked. The
    request must also stay format=text (no response_format), since complete_json
    parses prompt-instructed JSON out of a plain-text answer."""
    llm = _llm(None)
    llm.complete_json("sys", "hi")
    assert "reasoning_effort" not in llm.client.calls[0]
    assert "verbosity" not in llm.client.calls[0]
    assert "response_format" not in llm.client.calls[0]


def test_drops_verbosity_but_keeps_reasoning_effort():
    """Dropping one rejected param must not disable the other."""
    llm = _llm("medium", reject=("verbosity",), verbosity="medium")
    assert llm.complete_json("sys", "hi") == {"ok": 1}
    assert llm.client.calls[-1]["reasoning_effort"] == "medium"
    assert "verbosity" not in llm.client.calls[-1]


def test_drops_reasoning_effort_when_model_rejects_it():
    llm = _llm("low", reject=("reasoning_effort",))
    assert llm.complete_json("sys", "one") == {"ok": 1}
    assert "reasoning_effort" in llm.client.calls[0]      # first attempt (400)
    assert "reasoning_effort" not in llm.client.calls[1]  # retried without it
    llm.complete_json("sys", "two")                       # flag remembered
    assert "reasoning_effort" not in llm.client.calls[-1]
    assert sum("reasoning_effort" in c for c in llm.client.calls) == 1
