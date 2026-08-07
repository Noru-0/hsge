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


def test_client_has_bounded_request_timeout(monkeypatch):
    """A real run stalled silently for tens of minutes with no error and no
    log line: the OpenAI SDK's client, constructed with no explicit timeout,
    defaults to a 600s read/write/pool timeout, and our own retry wrapper
    multiplies that across up to 4 attempts. The client must be constructed
    with a much shorter, explicit timeout so a slow/unresponsive API raises
    (and gets retried/logged like any other transient error) instead of
    blocking silently for a long time.

    The bound must still leave room for a reasoning model (solver_goal): at 60s
    every GOAL task stalled, because one non-streaming gpt-5.x call over a
    6000-char axtree + screenshot routinely runs longer than that.

    max_retries=0 matters just as much: the SDK retries internally by default,
    which silently multiplied each of _create_with_retry's 4 attempts by 3."""
    llm = _make_llm(monkeypatch)

    assert llm.client.timeout == 180.0
    assert llm.client.max_retries == 0


class _FakeMessage:
    def __init__(self, content, refusal=None):
        self.content = content
        self.refusal = refusal


class _FakeResponse:
    def __init__(self, content, refusal=None, finish_reason="stop"):
        message = _FakeMessage(content, refusal=refusal)
        self.choices = [type("C", (), {"message": message, "finish_reason": finish_reason})()]


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


def test_none_content_returns_empty_dict_instead_of_crashing(monkeypatch):
    """message.content can be None (safety refusal, content filter, ...);
    this must degrade gracefully like a malformed-JSON response does, not
    crash with AttributeError: 'NoneType' object has no attribute 'strip'."""
    llm = _make_llm(monkeypatch)

    def fake_create(**kwargs):
        return _FakeResponse(None, refusal="I can't help with that.",
                              finish_reason="content_filter")

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    assert llm.complete_json("SYS", "PROMPT") == {}


def test_non_dict_json_response_returns_empty_dict_instead_of_crashing(monkeypatch):
    """Some models return a bare JSON array/scalar as the top-level response
    (e.g. '[{"segments": [...]}]' instead of '{"segments": [...]}'). All
    complete_json callers rely on the dict contract (see LLM.complete_json
    docstring); a non-dict must degrade the same way malformed JSON does,
    not propagate an AttributeError from the first caller that does .get()."""
    llm = _make_llm(monkeypatch)

    def fake_create(**kwargs):
        return _FakeResponse('[{"segments": []}]')

    monkeypatch.setattr(llm.client.chat.completions, "create", fake_create)

    assert llm.complete_json("SYS", "PROMPT") == {}
