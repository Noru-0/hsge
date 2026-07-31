"""OpenAILLM must cope with models (GPT-5.x / o-series) that reject a custom
temperature ("Only the default (1) value is supported"): drop the param and
retry, and remember so later calls omit it too.
Run: PYTHONPATH=. python -m pytest hsge/tests/test_backends_temperature.py -q
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
    """client.chat.completions.create raises a temperature-unsupported 400 while
    the temperature kwarg is present, and succeeds once it is dropped."""
    def __init__(self):
        self.calls = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if "temperature" in kwargs:
            resp = httpx.Response(400, request=httpx.Request("POST", "http://x"))
            raise openai.BadRequestError(
                "Unsupported value: 'temperature' does not support 0.0 with this "
                "model. Only the default (1) value is supported.",
                response=resp, body={"error": {"param": "temperature"}})
        return _Msg()


def _llm():
    llm = OpenAILLM.__new__(OpenAILLM)      # bypass __init__ (no real OpenAI client)
    llm.model = "gpt-5.6-terra"
    llm.temperature = 0.0
    llm._omit_temperature = False
    llm.client = _FakeClient()
    return llm


def test_drops_temperature_when_model_rejects_it():
    llm = _llm()
    assert llm.complete_json("sys", "hi") == {"ok": 1}
    assert "temperature" in llm.client.calls[0]      # first attempt sent it (400)
    assert "temperature" not in llm.client.calls[1]  # retried without it (ok)


def test_later_calls_omit_temperature_without_a_second_400():
    llm = _llm()
    llm.complete_json("sys", "one")     # triggers the drop + sets the flag
    llm.complete_json("sys", "two")     # must not send temperature again
    assert "temperature" not in llm.client.calls[-1]
    # exactly one rejected (400) call across both completes
    assert sum("temperature" in c for c in llm.client.calls) == 1
