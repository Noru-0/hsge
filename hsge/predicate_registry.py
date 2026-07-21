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

import json

from .clustering import OnlineClusterer
from .llm import LLM, Embedder

_EQUIV_SYS = (
    "You decide whether two PLANNING PREDICATES describe the SAME world "
    "condition. They may be worded differently. Answer equivalent=true only if a "
    "planner could treat them as interchangeable (one is satisfied exactly when "
    "the other is); answer false if one is a narrower/different condition. "
    'Return JSON {"equivalent": true|false}.'
)


def predicates_equivalent(llm: LLM, a: str, b: str) -> bool:
    """Ask the LLM whether two NL predicates denote the same planning condition.
    A malformed/empty response degrades to False (don't merge unless the LLM
    explicitly says so)."""
    out = llm.complete_json(_EQUIV_SYS, f"<payload>{json.dumps({'a': a, 'b': b})}</payload>")
    return bool(out.get("equivalent", False))


class PredicateRegistry:
    def __init__(self, embedder: Embedder, llm: LLM | None = None,
                 sim_threshold: float = 0.6, adjudication_band: float = 0.15):
        self.embedder = embedder
        # Optional LLM tie-breaker for the borderline band around sim_threshold.
        # Embedding-only canonicalization can't separate synonyms from near-
        # neighbours at any single cutoff (measured on wa_run_09: a true synonym
        # pair scored 0.570 while a false pair scored 0.606, straddling 0.6). When
        # an LLM is supplied, cosine decides the confident tails and the LLM
        # adjudicates only the ambiguous middle; llm=None keeps the old single-
        # threshold behaviour exactly (deterministic mock pipeline).
        self.llm = llm
        self.sim_threshold = sim_threshold
        self._low = sim_threshold - adjudication_band
        self._high = sim_threshold + adjudication_band
        # merge_threshold > 1 disables online merging: canonical ids are append-only
        # and never reassigned, so ids already baked into operators stay valid.
        self.clusterer = OnlineClusterer(sim_threshold=sim_threshold, merge_threshold=2.0)
        self.labels: dict[int, str] = {}     # canonical cluster id -> representative NL
        self.counts: dict[int, int] = {}     # canonical cluster id -> times resolved

    def canonical(self, nl: str) -> str:
        """Map one NL predicate to a stable canonical id like 'p3'.

        Without an LLM, close predicates (cosine >= sim_threshold) collapse onto
        the same id. With an LLM, cosine still decides the confident tails
        (>= high -> merge, < low -> new id) but a borderline nearest neighbour is
        settled by an LLM equivalence check, so synonyms unify instead of each
        operator getting a private predicate vocabulary that never chains. The
        first NL seen for a cluster is kept as its human-readable label; usage is
        counted so vocabulary() can surface the most-shared predicates.
        """
        text = (nl or "").strip()
        vec = self.embedder.encode([text])[0]
        cid, sim = self.clusterer.nearest(vec)
        if cid is None:
            cid = self.clusterer.spawn(vec, text)
        elif self.llm is None:
            cid = (self.clusterer.add_to(cid, vec, text) if sim >= self.sim_threshold
                   else self.clusterer.spawn(vec, text))
        elif sim >= self._high:
            cid = self.clusterer.add_to(cid, vec, text)
        elif sim < self._low:
            cid = self.clusterer.spawn(vec, text)
        elif predicates_equivalent(self.llm, text, self.labels[cid]):
            cid = self.clusterer.add_to(cid, vec, text)
        else:
            cid = self.clusterer.spawn(vec, text)
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
