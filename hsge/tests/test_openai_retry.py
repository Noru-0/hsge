"""OpenAILLM retry/backoff on transient API errors."""

import httpx
import openai
import pytest

from hsge.backends import OpenAILLM


def _response(status_code):
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return httpx.Response(status_code, request=req)


def _make_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = OpenAILLM(model="gpt-4o-mini")
    monkeypatch.setattr("hsge.backends.time.sleep", lambda s: None)
    return llm


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeResponse:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": _FakeMessage(content)})()]


def test_retries_transient_error_then_succeeds(monkeypatch):
    llm = _make_llm(monkeypatch)
    calls = {"n": 0}

    def fake_create(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise openai.RateLimitError("rate limited", response=_response(429), body=None)
        return _FakeResponse('{"ok": true}')

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)
    result = llm.complete_json("SYS", "PROMPT")

    assert result == {"ok": True}
    assert calls["n"] == 3


def test_gives_up_after_max_retries(monkeypatch):
    llm = _make_llm(monkeypatch)
    calls = {"n": 0}

    def fake_create(**kwargs):
        calls["n"] += 1
        raise openai.APIConnectionError(
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    with pytest.raises(openai.APIConnectionError):
        llm.complete_json("SYS", "PROMPT")
    assert calls["n"] == 4  # 1 initial attempt + 3 retries


def test_non_retryable_error_raises_immediately(monkeypatch):
    llm = _make_llm(monkeypatch)
    calls = {"n": 0}

    def fake_create(**kwargs):
        calls["n"] += 1
        raise openai.AuthenticationError("bad key", response=_response(401), body=None)

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    with pytest.raises(openai.AuthenticationError):
        llm.complete_json("SYS", "PROMPT")
    assert calls["n"] == 1  # no retries for a non-transient error


def test_image_b64_builds_multimodal_content(monkeypatch):
    llm = _make_llm(monkeypatch)
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeResponse('{"ok": true}')

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)
    llm.complete_json("SYS", "PROMPT", image_b64="ZmFrZQ==", image_detail="high")

    user_content = captured["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0] == {"type": "text", "text": "PROMPT"}
    assert user_content[1]["image_url"]["url"] == "data:image/jpeg;base64,ZmFrZQ=="
    assert user_content[1]["image_url"]["detail"] == "high"


def test_no_image_keeps_plain_string_content(monkeypatch):
    llm = _make_llm(monkeypatch)
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeResponse('{"ok": true}')

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)
    llm.complete_json("SYS", "PROMPT")

    assert captured["messages"][1]["content"] == "PROMPT"
