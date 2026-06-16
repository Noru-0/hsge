"""Frontier scoring for HSGE — matches Go-Browse's UVD implementation.

Implements the composite scoring function from Go-Browse:
    S = α·U + β·V + θ·D

Where:
    U (Uncertainty) = σ / (μ + ε)  — variance/mean of lookahead confidences
    V (Value)       = SR · (1 / log(n + 1))  — parent success rate with sibling penalty
    D (Diversity)   = mean cosine distance between consecutive state embeddings

Reference: go-browse/webexp/explore/core/scoring.py
"""
from __future__ import annotations

import json
import math
import os
import re
from textwrap import dedent
from typing import Any
from urllib.parse import urlparse


# ------------------------------------------------------------------
# Lightweight LLM-based confidence predictor for task candidates
# ------------------------------------------------------------------

class LookaheadPredictor:
    """Zero-shot lookahead: uses a small/cheap LLM to propose plausible
    exploration tasks on a page *before* any agent runs.

    Each candidate has a task description, type, and confidence score (0-1).
    The *variance* of these confidence scores becomes the Uncertainty (U)
    component of the frontier score.

    Matches Go-Browse's LookaheadPredictor implementation.
    """

    def __init__(
        self,
        llm=None,
        num_candidates: int = 6,
    ):
        """If `llm` is provided, use it for completions (HSGE's LLM interface).
        If None, falls back to no lookahead (U=1.0 for all nodes).
        """
        self.llm = llm
        self.num_candidates = num_candidates

    _LOGIN_KEYWORDS = [
        "login", "sign in", "signin", "sign up", "signup",
        "register", "create account", "log in", "log into",
        "authenticate", "forgot password", "reset password",
    ]

    @staticmethod
    def _is_login_task(task: str) -> bool:
        """Check if a task is login/registration related."""
        task_lower = task.lower()
        return any(kw in task_lower for kw in LookaheadPredictor._LOGIN_KEYWORDS)

    def propose(self, axtree_snippet: str) -> list[dict]:
        """Propose {num_candidates} useful frontier exploration tasks with
        feasibility confidence scores, based on the page's accessibility tree.

        Returns:
            list[dict]: Each dict has keys "task" (str), "type" (str),
            and "confidence" (float).
        """
        return self._propose_with_prompt(f"""\
Propose {self.num_candidates} diverse candidate tasks.

Each task should be:
- local to the current page state, or a direct navigation action visible from this page
- concrete and executable
- useful for discovering website functionality or new states
- not dependent on hidden information

IMPORTANT: Do NOT propose any login, sign in, sign up, register,
or account creation tasks — the agent is already logged in.

For each task, provide:
- "task": a short natural-language goal
- "type": one of ["local", "navigation", "search", "form", "unknown"]
- "confidence": a number from 0.0 to 1.0 estimating how likely the task is feasible from this page state

Use confidence as FEASIBILITY confidence, not user-intent probability.

Page accessibility tree:
{axtree_snippet[:3500]}
""")

    def propose_from_url(self, url: str) -> list[dict]:
        """Propose tasks for a URL in the frontier that hasn't been visited yet.
        
        Dùng URL làm thông tin duy nhất (không có axtree vì chưa visit).
        Returns fallback nếu LLM không available.
        """
        if self.llm is None:
            return self._fallback()
        return self._propose_with_prompt(f"""\
Propose {self.num_candidates} diverse candidate tasks for a web page.

The page URL is: {url}

Based ONLY on the URL, propose tasks that a user could likely do on this page.
Consider what type of page it is (category listing, product detail, cart, checkout, etc.)
and what actions would be feasible.

IMPORTANT: Do NOT propose any login, sign in, sign up, register,
or account creation tasks — the agent is already logged in.

For each task, provide:
- "task": a short natural-language goal
- "type": one of ["local", "navigation", "search", "form", "unknown"]
- "confidence": a number from 0.0 to 1.0 estimating how likely the task is feasible from this page state

Use confidence as FEASIBILITY confidence, not user-intent probability.
""")

    def _propose_with_prompt(self, prompt_body: str) -> list[dict]:
        """Shared implementation for propose and propose_from_url."""
        if self.llm is None:
            return self._fallback()

        system = (
            "You are evaluating a web page state for autonomous web exploration. "
            "Given the page information, propose diverse candidate tasks "
            "that an agent could attempt from this exact page state. "
            "Return ONLY valid JSON."
        )
        prompt = dedent(prompt_body) + (
            '\n\nRespond with ONLY valid JSON in this exact format:\n'
            '{{\n'
            '  "candidates": [\n'
            '    {{"task": "...", "type": "local", "confidence": 0.80}}\n'
            '  ]\n'
            '}}'
        )

        try:
            out = self.llm.complete_json(system, prompt)
            # Handle both array and {"candidates": [...]} wrappers
            data = out
            if isinstance(data, dict):
                for key in ("candidates", "actions", "predictions"):
                    if key in data and isinstance(data[key], list):
                        data = data[key]
                        break
            if not isinstance(data, list):
                return self._fallback()
            results = []
            for item in data[:self.num_candidates]:
                if isinstance(item, dict) and ("task" in item or "action" in item):
                    conf = float(item.get("confidence", 0.5))
                    task = str(item.get("task") or item.get("action"))
                    task_type = str(item.get("type", "unknown"))
                    if task_type not in {"local", "navigation", "search", "form", "unknown"}:
                        task_type = "unknown"
                    if self._is_login_task(task):
                        continue
                    results.append({
                        "task": task,
                        "type": task_type,
                        "confidence": max(0.0, min(1.0, conf)),
                    })
            if results:
                return results
        except Exception:
            pass
        return self._fallback()

    def _fallback(self) -> list[dict]:
        """Return neutral candidates when prediction fails."""
        return [
            {"task": f"generic_interaction_{i}", "type": "unknown", "confidence": 0.5}
            for i in range(self.num_candidates)
        ]


# ------------------------------------------------------------------
# Frontier Scorer  S = α·U + β·V + θ·D
# ------------------------------------------------------------------

class FrontierScorer:
    """Computes frontier scores for unexplored URLs.

    Usage:
        scorer = FrontierScorer(alpha=1.0, beta=1.0, theta=1.0)
        score = scorer.compute(url, url_info, explored_urls)

    Matches Go-Browse's FrontierScorer implementation exactly.
    """

    def __init__(
        self,
        alpha: float = 1.0,
        beta: float = 1.0,
        theta: float = 0.0,
        epsilon: float = 1e-5,
    ):
        self.alpha = alpha
        self.beta = beta
        self.theta = theta
        self.epsilon = epsilon

        # Per-URL stats (stored externally, updated by runtime)
        self._lookahead: dict[str, list[dict]] = {}        # url -> lookahead candidates
        self._parent_url: dict[str, str] = {}               # url -> parent url
        self._success_rate: dict[str, float] = {}           # url -> success rate (0..1)
        self._total_trajs: dict[str, int] = {}              # url -> total trajectories
        self._selected_child_count: dict[str, int] = {}     # url -> children selected count
        self._embeddings: dict[str, list[list[float]]] = {} # url -> list of embedding vectors

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(self, url: str, explored_urls: set[str] | None = None) -> float:
        """Compute composite frontier score S = α·U + β·V for a URL.

        D (Diversity) is removed — only U (Uncertainty) and V (Value) are used.
        """
        U = self.uncertainty(url)
        V = self.value(url)
        return self.alpha * U + self.beta * V

    def breakdown(self, url: str, explored_urls: set[str] | None = None) -> dict:
        """Return a dict with the score and its components (for logging/debugging)."""
        explored = explored_urls or set()
        U = self.uncertainty(url)
        V_sr, V_sr_source = self._estimate_parent_success_rate_with_source(url)
        V_n, V_n_source = self._parent_selected_child_count_with_source(url)
        V = V_sr * (1.0 / math.log(V_n + 2))
        S = self.alpha * U + self.beta * V
        return {
            "score": S,
            "U": U,
            "V": V,
            "V_sr": V_sr,
            "V_sr_source": V_sr_source,
            "V_n": V_n,
            "V_n_source": V_n_source,
            "D": 0.0,
            "alpha": self.alpha,
            "beta": self.beta,
            "theta": 0.0,
        }

    # ------------------------------------------------------------------
    # Component: Uncertainty  U = σ / (μ + ε)
    # ------------------------------------------------------------------

    def uncertainty(self, url: str) -> float:
        """Uncertainty — higher means more potential for novel tasks.

        U = σ / (μ + ε)

        σ: variance of lookahead confidence scores at this URL.
        μ: mean of those confidence scores.
        ε: small constant.

        Data source: `self._lookahead[url]` — a list of
        {"task": str, "type": str, "confidence": float} produced by the
        LookaheadPredictor when the URL first entered the frontier.

        Fresh URLs (no lookahead data yet) get U = 1.0 to encourage
        initial exploration.
        """
        candidates = self._lookahead.get(url)
        if not candidates:
            return 1.0

        confidences = [c["confidence"] for c in candidates if isinstance(c, dict)]
        if not confidences:
            return 1.0

        n = len(confidences)
        mu = sum(confidences) / n
        sigma = sum((c - mu) ** 2 for c in confidences) / n  # variance
        return sigma / (mu + self.epsilon)

    # ------------------------------------------------------------------
    # Component: Value  V = SR · (1 / log(n + 1))
    # ------------------------------------------------------------------

    def value(self, url: str) -> float:
        """Value (exploitation) — higher means the parent branch is fruitful.

        V = SR · (1 / log(n + 2))

        SR: success rate of the parent URL.
        n:  number of child URLs selected for exploration from that parent (V_n).
        Sibling URLs share the same SR and n, so they share the same V.
        Dùng n+2 thay vì n+1 để V_n=0 và V_n=1 có giá trị khác nhau.
        """
        sr, _ = self._estimate_parent_success_rate_with_source(url)
        n, _ = self._parent_selected_child_count_with_source(url)
        penalty = 1.0 / math.log(n + 2)
        return sr * penalty

    def _estimate_parent_success_rate_with_source(self, url: str) -> tuple[float, str]:
        """Estimate parent SR and report its source for value scoring.

        Child URLs use their direct parent's observed success_rate.
        Root URLs use their own observed success_rate.
        If the required URL has no trajectories yet, use the neutral prior 0.5.
        """
        parent_url = self._parent_url.get(url)
        if parent_url is not None:
            n = self._total_trajs.get(parent_url, 0)
            if n > 0:
                return self._success_rate.get(parent_url, 0.5), f"parent:{parent_url}"
            return 0.5, f"parent_prior:{parent_url}"

        if self._total_trajs.get(url, 0) > 0:
            return self._success_rate.get(url, 0.5), "self"

        return 0.5, "prior"

    def _parent_selected_child_count_with_source(self, url: str) -> tuple[int, str]:
        """Return n for V: selected child count on the direct parent."""
        parent_url = self._parent_url.get(url)
        if parent_url is not None:
            return max(self._selected_child_count.get(parent_url, 0), 0), f"parent:{parent_url}"
        return max(self._selected_child_count.get(url, 0), 0), "self"

    # ------------------------------------------------------------------
    # Component: Diversity  D = mean cosine distance between embeddings
    # ------------------------------------------------------------------

    @staticmethod
    def cosine_distance(a: list[float], b: list[float], eps: float = 1e-10) -> float:
        """Cosine distance between two vectors: 1 - cos_sim(a, b)."""
        dot = sum(ai * bi for ai, bi in zip(a, b))
        norm_a = math.sqrt(sum(ai * ai for ai in a))
        norm_b = math.sqrt(sum(bi * bi for bi in b))
        cos_sim = dot / (norm_a * norm_b + eps)
        return 1.0 - cos_sim

    def diversity(self, url: str, explored_urls: set[str]) -> float:
        """Diversity — higher means more UI/DOM state change during interaction.

        D = mean cosine distance between consecutive embedding vectors.

        Returns 0.5 when no embeddings are available (neutral tiebreaker).
        """
        embeddings = self._embeddings.get(url)
        if embeddings is None or len(embeddings) < 2:
            return 0.5

        distances = []
        for i in range(len(embeddings) - 1):
            dist = self.cosine_distance(embeddings[i], embeddings[i + 1])
            distances.append(dist)
        return sum(distances) / len(distances) if distances else 0.5

    # ------------------------------------------------------------------
    # Scoring multiple candidates
    # ------------------------------------------------------------------

    def score_all(
        self,
        candidates: list[tuple[str, int]],
        explored_urls: set[str],
    ) -> list[tuple[float, str, int]]:
        """Score all candidate (url, depth) pairs and return sorted list.

        Returns list of (score, url, depth) sorted descending by score.
        """
        scored = []
        for url, depth in candidates:
            score = self.compute(url, explored_urls)
            scored.append((score, url, depth))
        scored.sort(key=lambda x: -x[0])
        return scored

    # ------------------------------------------------------------------
    # State setters (called by runtime)
    # ------------------------------------------------------------------

    def set_lookahead(self, url: str, candidates: list[dict]) -> None:
        """Store lookahead candidates for a URL."""
        self._lookahead[url] = candidates

    def set_parent(self, url: str, parent_url: str | None) -> None:
        """Record the parent relationship for a URL."""
        if parent_url:
            self._parent_url[url] = parent_url

    def record_exploration(
        self, url: str, success: bool,
        parent_url: str | None = None,
        total_trajs: int | None = None,
        successful_trajs: int | None = None,
    ) -> None:
        """Record the outcome of exploring a URL and update stats."""
        if parent_url:
            self._parent_url[url] = parent_url
        if total_trajs is not None and total_trajs > 0:
            self._total_trajs[url] = total_trajs
            self._success_rate[url] = (successful_trajs or 0) / total_trajs

    def record_child_selection(self, parent_url: str) -> None:
        """Increment the selected child count for a parent URL.
        
        Được gọi khi một child URL được thêm vào frontier (từ callback discovery)
        hoặc khi một URL được chọn để visit. V_n = số child đã được chọn từ parent.
        """
        self._selected_child_count[parent_url] = self._selected_child_count.get(parent_url, 0) + 1

    def set_embeddings(self, url: str, embeddings: list[list[float]]) -> None:
        """Store embedding vectors for a URL (for diversity computation)."""
        self._embeddings[url] = embeddings

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "alpha": self.alpha,
            "beta": self.beta,
            "theta": self.theta,
            "epsilon": self.epsilon,
            "_lookahead": self._lookahead,
            "_parent_url": self._parent_url,
            "_success_rate": self._success_rate,
            "_total_trajs": self._total_trajs,
            "_selected_child_count": self._selected_child_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FrontierScorer":
        scorer = cls(
            alpha=d.get("alpha", 1.0),
            beta=d.get("beta", 1.0),
            theta=d.get("theta", 1.0),
            epsilon=d.get("epsilon", 1e-5),
        )
        scorer._lookahead = d.get("_lookahead", {})
        scorer._parent_url = d.get("_parent_url", {})
        scorer._success_rate = d.get("_success_rate", {})
        scorer._total_trajs = d.get("_total_trajs", {})
        scorer._selected_child_count = d.get("_selected_child_count", {})
        return scorer
