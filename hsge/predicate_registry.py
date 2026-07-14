"""Predicate registry: a vocabulary of planning predicates *learned* by embedding
similarity instead of hardcoded.

The old pipeline mapped a page to a fixed 6-word predicate vocabulary
(`webarena/predicates.py`). That does not extend to new sites/domains. Here, an
LLM emits free-form NL predicates (preconditions/effects of a skill) and this
registry canonicalizes them: an NL predicate that is close (cosine) to one seen
before collapses onto the same canonical id; otherwise it spawns a new one.

This reuses `OnlineClusterer` (the same streaming cosine-threshold mechanism the
skill library uses) so operators keep referencing a small set of stable
`frozenset` ids and the planner's set logic is untouched.
"""
from __future__ import annotations

from .clustering import OnlineClusterer
from .llm import Embedder


class PredicateRegistry:
    def __init__(self, embedder: Embedder, sim_threshold: float = 0.6):
        self.embedder = embedder
        # merge_threshold > 1 disables online merging: canonical ids are append-only
        # and never reassigned, so ids already baked into operators stay valid.
        self.clusterer = OnlineClusterer(sim_threshold=sim_threshold, merge_threshold=2.0)
        self.labels: dict[int, str] = {}     # canonical cluster id -> representative NL
        self.counts: dict[int, int] = {}     # canonical cluster id -> times resolved

    def canonical(self, nl: str) -> str:
        """Map one NL predicate to a stable canonical id like 'p3'.

        Close predicates (cosine >= sim_threshold) collapse onto the same id; the
        first NL seen for a cluster is kept as its human-readable label. Usage is
        counted so vocabulary() can surface the most-shared predicates.
        """
        text = (nl or "").strip()
        vec = self.embedder.encode([text])[0]
        cid = self.clusterer.partial_fit(vec, text)
        self.labels.setdefault(cid, text)
        self.counts[cid] = self.counts.get(cid, 0) + 1
        return f"p{cid}"

    def vocabulary(self, max_frequent: int = 25, max_recent: int = 25) -> list[str]:
        """Labels for LLM prompt context: the most-used predicates first (the
        core vocabulary foundational operators share), then the most recent
        (new concepts), deduplicated. Recent-only selection would "forget"
        foundational predicates once the vocabulary outgrows the cap."""
        by_freq = sorted(self.counts, key=lambda cid: (-self.counts[cid], cid))
        chosen = by_freq[:max_frequent]
        chosen_set = set(chosen)
        by_recent = sorted(self.counts, reverse=True)
        for cid in by_recent:
            if len(chosen) >= max_frequent + max_recent:
                break
            if cid not in chosen_set:
                chosen.append(cid)
                chosen_set.add(cid)
        return [self.labels[cid] for cid in chosen]

    def label(self, pid: str) -> str:
        """Human-readable NL for a canonical id (for printing/audit)."""
        try:
            cid = int(pid[1:])
        except (ValueError, IndexError):
            return pid
        return self.labels.get(cid, pid)
