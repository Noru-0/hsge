"""Real backends for HSGE: an OpenAI-compatible LLM and a sentence-transformers
embedder. Imports are lazy so the rest of the package still runs without these
installed. Configure via env vars: OPENAI_API_KEY, OPENAI_BASE_URL, HSGE_MODEL.
"""
from __future__ import annotations

import json
import os
import re

import numpy as np

from .llm import LLM, Embedder


class OpenAILLM(LLM):
    """OpenAI-compatible chat-completions backend returning parsed JSON."""

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, temperature: float = 0.2,
                 supports_vision: bool = True,
                 timeout_seconds: float = 60.0,
                 max_retries: int = 2):
        from openai import OpenAI                       # lazy
        self.model = model or os.environ.get("HSGE_MODEL", "gpt-4o-mini")
        self.client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
        self.temperature = temperature
        self.supports_vision = supports_vision

    @staticmethod
    def _fix_json(txt: str) -> str:
        """Apply common LLM JSON fixups (trailing commas, single quotes, etc.)."""
        # Remove trailing commas before ] or }
        txt = re.sub(r",\s*([}\]])", r"\1", txt)
        # Replace single quotes used as string delimiters (but not inside strings)
        # This is a simple heuristic: replace ' with " around property names/values
        txt = re.sub(r"(?<=[{,])\s*'([^']+)'\s*:", r'"\1":', txt)
        txt = re.sub(r":\s*'([^']*)'\s*([,}])", r': "\1"\2', txt)
        return txt

    def _parse_json(self, txt: str | None) -> dict:
        if not txt:
            return {}
        txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
        txt = self._fix_json(txt)
        try:
            result = json.loads(txt)
            # The LLM may return a JSON array instead of an object;
            # wrap it so callers always receive a dict.
            if isinstance(result, list):
                return {"segments": result}
            if isinstance(result, dict):
                return result
            return {}
        except json.JSONDecodeError:
            # Try to extract a JSON object or array from the text
            m = re.search(r"[\[\{].*[\]\}]", txt, re.S)
            if m:
                raw = self._fix_json(m.group(0))
                try:
                    result = json.loads(raw)
                    if isinstance(result, list):
                        return {"segments": result}
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass
            return {}

    def _get_content(self, msg) -> str | None:
        """Safely extract text content from an OpenAI response."""
        try:
            choice = msg.choices[0]
            content = choice.message.content
            if content is not None:
                return content.strip()
            # Some models return content as a list of content blocks
            if hasattr(choice.message, 'content') and isinstance(choice.message.content, list):
                parts = [p.get('text', '') for p in choice.message.content if isinstance(p, dict)]
                return '\n'.join(parts).strip()
        except (IndexError, AttributeError):
            pass
        return None

    def complete_json(self, system: str, prompt: str) -> dict:
        msg = self.client.chat.completions.create(
            model=self.model, temperature=self.temperature,
            messages=[{"role": "system", "content": system + "\nReturn ONLY valid JSON."},
                      {"role": "user", "content": prompt}],
        )
        return self._parse_json(self._get_content(msg))

    def complete_vision_json(self, system: str, prompt: str,
                             screenshot_base64: bytes | None = None) -> dict:
        """Multimodal completion with optional screenshot."""
        if screenshot_base64 is None:
            return self.complete_json(system, prompt)
        import base64
        img_b64 = base64.b64encode(screenshot_base64).decode("utf-8")
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{img_b64}",
                           "detail": "auto"}},
        ]
        msg = self.client.chat.completions.create(
            model=self.model, temperature=self.temperature,
            messages=[{"role": "system", "content": system + "\nReturn ONLY valid JSON."},
                      {"role": "user", "content": user_content}],
        )
        return self._parse_json(self._get_content(msg))

    def complete_text(self, system: str, prompt: str) -> str:
        msg = self.client.chat.completions.create(
            model=self.model, temperature=self.temperature,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
        )
        return self._get_content(msg) or ""

    def complete_with_tools(
        self,
        system: str,
        prompt: str,
        tools: list[dict] | None = None,
    ) -> dict:
        """Send a completion with tool/function definitions.

        Returns a dict with either:
          - {"type": "text", "content": "...", "thought": "..."} for text responses
          - {"type": "tool_call", "name": "...", "arguments": {...}} for tool calls

        Tools are registered as 'functions' in the OpenAI API format.
        """
        kwargs = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        msg = self.client.chat.completions.create(**kwargs)
        choice = msg.choices[0]

        # Check for tool calls first
        if choice.message.tool_calls:
            tc = choice.message.tool_calls[0]
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            return {
                "type": "tool_call",
                "name": tc.function.name,
                "arguments": args,
            }

        # Fall back to text response (parse as JSON action)
        content = self._get_content(msg) or ""
        parsed = self._parse_json(content)
        return {
            "type": "text",
            "content": content,
            "thought": parsed.get("thought", ""),
            "action": parsed.get("action", content),
        }


class STEmbedder(Embedder):
    """sentence-transformers embedder (L2-normalized)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer   # lazy
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        v = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(v, dtype=np.float32)
