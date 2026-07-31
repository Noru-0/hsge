"""Real backends for HSGE: an OpenAI-compatible LLM and a sentence-transformers
embedder. Imports are lazy so the rest of the package still runs without these
installed. Configure via env vars: OPENAI_API_KEY, OPENAI_BASE_URL, HSGE_MODEL.
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time

import numpy as np

from .llm import LLM, Embedder


class OpenAILLM(LLM):
    """OpenAI-compatible chat-completions backend returning parsed JSON."""

    # The SDK's own default (connect=5.0, read/write/pool=600) lets a single
    # stalled request block for up to 10 minutes with no error and no log
    # line -- and _create_with_retry can multiply that across 4 attempts.
    # A much shorter, explicit timeout makes a slow/unresponsive API raise
    # (and get retried/logged like any other transient error) instead.
    _REQUEST_TIMEOUT_S = 60.0

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, temperature: float = 0.2):
        from openai import OpenAI                       # lazy
        self.model = model or os.environ.get("HSGE_MODEL", "gpt-4o-mini")
        self.client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
            timeout=self._REQUEST_TIMEOUT_S,
        )
        self.temperature = temperature
        # Set once a model rejects a custom temperature (GPT-5.x / o-series only
        # accept the default), so later calls omit the param instead of re-hitting
        # the 400 every time.
        self._omit_temperature = False

    @staticmethod
    def _is_unsupported_temperature(e) -> bool:
        """True if a 400 is specifically about a temperature the model won't accept
        (e.g. 'temperature does not support 0.0 ... Only the default (1) value is
        supported')."""
        body = getattr(e, "body", None)
        if isinstance(body, dict) and (body.get("error") or {}).get("param") == "temperature":
            return True
        msg = str(e).lower()
        return "temperature" in msg and ("does not support" in msg or "unsupported" in msg)

    def _create_with_retry(self, **kwargs):
        """chat.completions.create with retry/backoff on transient errors only.

        Rate limits, connection blips, and 5xx are retried (up to 3 times,
        exponential backoff + jitter); auth/bad-request errors are not --
        those are never going to succeed on retry, so failing fast is better.
        The one exception: a 400 that rejects a custom temperature (GPT-5.x /
        o-series) is recovered by dropping the param and retrying once.
        """
        import openai
        retryable = (openai.RateLimitError, openai.APIConnectionError,
                     openai.APITimeoutError, openai.InternalServerError)
        delay = 1.0
        for attempt in range(4):
            try:
                return self.client.chat.completions.create(**kwargs)
            except openai.BadRequestError as e:
                if "temperature" in kwargs and self._is_unsupported_temperature(e):
                    print(f"[OpenAILLM] model {self.model!r} rejects a custom "
                          "temperature; retrying without it", file=sys.stderr)
                    self._omit_temperature = True
                    kwargs.pop("temperature", None)
                    continue
                raise
            except retryable as e:
                if attempt == 3:
                    raise
                sleep_s = delay + random.uniform(0, delay * 0.25)
                print(f"[OpenAILLM] retry {attempt + 1}/3 after {type(e).__name__}, "
                      f"sleeping {sleep_s:.1f}s", file=sys.stderr)
                time.sleep(sleep_s)
                delay *= 2

    @staticmethod
    def _user_content(prompt: str, image_b64: str | None, image_detail: str):
        if not image_b64:
            return prompt
        return [{"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{image_b64}",
                               "detail": image_detail}}]

    def complete_json(self, system: str, prompt: str,
                       image_b64: str | None = None, image_detail: str = "low") -> dict:
        kwargs = dict(
            model=self.model,
            messages=[{"role": "system", "content": system + "\nReturn ONLY valid JSON."},
                      {"role": "user",
                       "content": self._user_content(prompt, image_b64, image_detail)}],
        )
        if not self._omit_temperature:
            kwargs["temperature"] = self.temperature
        msg = self._create_with_retry(**kwargs)
        choice = msg.choices[0]
        content = choice.message.content
        if content is None:
            # message.content can be None (safety refusal, content filter, ...),
            # distinct from a malformed-JSON response -- degrade the same way.
            refusal = getattr(choice.message, "refusal", None)
            print(f"[OpenAILLM] empty content (finish_reason={choice.finish_reason!r}"
                  f"{f', refusal={refusal!r}' if refusal else ''}), returning {{}}",
                  file=sys.stderr)
            return {}
        txt = content.strip()
        txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
        try:
            parsed = json.loads(txt)
        except json.JSONDecodeError:
            parsed = None
            m = re.search(r"\{.*\}", txt, re.S)          # salvage first JSON object
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        if isinstance(parsed, dict):
            return parsed
        # Callers all rely on the dict contract (see LLM.complete_json docstring);
        # a bare top-level JSON array/scalar is as unusable to them as malformed JSON.
        print(f"[OpenAILLM] non-dict JSON response, returning {{}}: {txt[:200]!r}",
              file=sys.stderr)
        return {}

    def complete_text(self, system: str, prompt: str) -> str:
        msg = self._create_with_retry(
            model=self.model, temperature=self.temperature,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
        )
        return msg.choices[0].message.content


class STEmbedder(Embedder):
    """sentence-transformers embedder (L2-normalized)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer   # lazy
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        v = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(v, dtype=np.float32)
