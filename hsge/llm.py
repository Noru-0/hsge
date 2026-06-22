"""Pluggable backends: LLM (for segmentation/abstraction/grounding) and Embedder
(for clustering). Ship with deterministic mocks so the full pipeline runs with no
network/keys; swap in real backends by subclassing.
"""
from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod

import numpy as np


# --------------------------------------------------------------------------- #
# Embedder
# --------------------------------------------------------------------------- #
class Embedder(ABC):
    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) L2-normalized float32 array."""


class HashingEmbedder(Embedder):
    """Deterministic bag-of-token hashing embedder. No deps, reproducible.

    Good enough to demonstrate that semantically similar action-signatures land
    near each other. In the paper, replace with sentence-transformers:

        from sentence_transformers import SentenceTransformer
        class STEmbedder(Embedder):
            def __init__(self): self.m = SentenceTransformer("all-MiniLM-L6-v2")
            def encode(self, texts): return self.m.encode(texts, normalize_embeddings=True)
    """
    def __init__(self, dim: int = 256):
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._vec(t) for t in texts]).astype(np.float32)


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #
class LLM(ABC):
    @abstractmethod
    def complete_json(self, system: str, prompt: str) -> dict:
        """Return a parsed JSON object. Real impls should strip code fences."""

    def complete_vision_json(self, system: str, prompt: str,
                             screenshot_base64: bytes | None = None) -> dict:
        """Return parsed JSON, optionally with a screenshot. Falls back to
        complete_json if the backend doesn't support vision."""
        return self.complete_json(system, prompt)

    def complete_with_tools(
        self,
        system: str,
        prompt: str,
        tools: list[dict] | None = None,
    ) -> dict:
        """Send a completion with tool/function definitions.

        Default implementation falls back to complete_json (ignoring tools).
        Real backends (OpenAILLM) override this to use function-calling API.
        """
        return self.complete_json(system, prompt)


class MockLLM(LLM):
    """Heuristic stand-in that returns structured outputs for the three calls the
    pipeline makes: segment / abstract / ground. Deterministic, offline.

    Real backend (Anthropic shown; OpenAI analogous):

        import anthropic, json
        class ClaudeLLM(LLM):
            def __init__(self): self.c = anthropic.Anthropic()
            def complete_json(self, system, prompt):
                msg = self.c.messages.create(
                    model="claude-opus-4-8", max_tokens=2000,
                    system=system, messages=[{"role":"user","content":prompt}])
                txt = msg.content[0].text
                txt = txt.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
                return json.loads(txt)
    """

    def complete_json(self, system: str, prompt: str) -> dict:
        if "SEGMENT" in system:
            return self._segment(prompt)
        if "ABSTRACT" in system:
            return self._abstract(prompt)
        if "GROUND" in system:
            return self._ground(prompt)
        return {}

    # The mock cheats by reading hints we pass in the prompt as JSON. A real LLM
    # would read the raw trajectory/DOM instead.
    @staticmethod
    def _payload(prompt: str) -> dict:
        m = re.search(r"<payload>(.*)</payload>", prompt, re.S)
        return json.loads(m.group(1)) if m else {}

    def _segment(self, prompt: str) -> dict:
        # Echo back the pre-marked segments (URL-boundary seeds) with subgoals.
        p = self._payload(prompt)
        return {"segments": p.get("segments", [])}

    def _abstract(self, prompt: str) -> dict:
        p = self._payload(prompt)
        subgoal = p.get("dominant_subgoal", "perform action")
        verbs = p.get("action_verbs", [])
        # Lift: any 'type'/'fill' verb implies a value slot + a selector slot.
        slots, template = [], []
        for i, v in enumerate(verbs):
            if v in ("type", "fill"):
                slots.append({"name": f"value_{i}", "slot_type": "value",
                              "description": f"value entered at step {i}", "example": ""})
                slots.append({"name": f"sel_{i}", "slot_type": "selector",
                              "description": f"target field at step {i}", "example": ""})
                template.append(f"type({{sel_{i}}}, {{value_{i}}}, '0')")
            elif v == "click":
                slots.append({"name": f"sel_{i}", "slot_type": "selector",
                              "description": f"element clicked at step {i}", "example": ""})
                template.append(f"click({{sel_{i}}})")
            else:
                template.append(v)
        if any(v in ("type", "fill") for v in verbs):
            skill_name = "submit_search_query" if "search" in subgoal.lower() else "fill_visible_field"
        elif any(v == "click" for v in verbs):
            skill_name = "open_visible_item"
        else:
            skill_name = "activate_named_control"
        return {
            "name": skill_name,
            "description": f"Reusable routine for a generic page interaction.",
            "slots": slots,
            "action_template": template,
            "precondition": "required controls are visible",
            "success_predicate": "interaction completed",
        }

    def _ground(self, prompt: str) -> dict:
        # On a new page, bind each selector slot, in order, to the next available
        # element id advertised by the DOM. Value slots get a placeholder value.
        # A real LLM would match by semantics; order-binding suffices for the mock.
        p = self._payload(prompt)
        affs = list(p.get("affordances", []))
        bindings, ok = {}, True
        for slot in p.get("slots", []):
            if slot["slot_type"] == "selector":
                if affs:
                    bindings[slot["name"]] = affs.pop(0)
                else:
                    ok = False
            elif slot["slot_type"] == "value":
                bindings[slot["name"]] = "auto_value"
        return {"groundable": ok, "bindings": bindings}
