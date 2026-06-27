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
                 api_key: str | None = None, temperature: float = 0.2):
        from openai import OpenAI                       # lazy
        self.model = model or os.environ.get("HSGE_MODEL", "gpt-4o-mini")
        self.client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
        )
        self.temperature = temperature

    def complete_json(self, system: str, prompt: str) -> dict:
        msg = self.client.chat.completions.create(
            model=self.model, temperature=self.temperature,
            messages=[{"role": "system", "content": system + "\nReturn ONLY valid JSON."},
                      {"role": "user", "content": prompt}],
        )
        txt = msg.choices[0].message.content.strip()
        txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", txt, re.S)          # salvage first JSON object
            return json.loads(m.group(0)) if m else {}

    def complete_text(self, system: str, prompt: str) -> str:
        msg = self.client.chat.completions.create(
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
