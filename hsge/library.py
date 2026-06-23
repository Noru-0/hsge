"""The growing, verified skill library.

Lifecycle of an incoming sub-trajectory:
    observe -> embed -> online cluster -> (cluster mature?) -> abstract
            -> verify in held-out contexts -> admit / reject -> (periodic) prune
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from .abstraction import abstract_cluster
from .clustering import OnlineClusterer
from .llm import LLM, Embedder
from .schema import SkillCard, SubTrajectory
from .verification import verify_skill


class SkillLibrary:
    def __init__(
        self,
        llm: LLM,
        embedder: Embedder,
        verify_contexts_fn,                 # callable() -> list[WebEnv] for verification
        sim_threshold: float = 0.6,
        maturity: int = 3,                  # min cluster size before abstraction
        verify_k: int = 2,
        prune_min_rate: float = 0.34,
    ):
        self.llm = llm
        self.embedder = embedder
        self.verify_contexts_fn = verify_contexts_fn
        self.maturity = maturity
        self.verify_k = verify_k
        self.prune_min_rate = prune_min_rate

        self.clusterer = OnlineClusterer(sim_threshold=sim_threshold)
        self.subtrajs: dict[str, SubTrajectory] = {}
        self.cluster_to_members: dict[int, list[str]] = {}
        self.skills: dict[int, SkillCard] = {}     # keyed by cluster id
        self._abstracted: set[int] = set()
        self._on_admit = None                       # callback(skill_card) on admission
        self._on_diagnostic = None                  # callback(event_dict)

    def _diag(self, event: str, **data) -> None:
        payload = {"event": event, **data}
        if self._on_diagnostic:
            self._on_diagnostic(payload)

    # ----------------------------------------------------------------- observe
    def observe(self, sub: SubTrajectory) -> int | None:
        """Ingest one sub-trajectory; return a skill_id if a new skill was admitted."""
        if not sub.success:
            return None
        self.subtrajs[sub.sub_id] = sub
        vec = self.embedder.encode([sub.text_for_embedding()])[0]
        cid = self.clusterer.partial_fit(vec, sub.sub_id)
        self.cluster_to_members.setdefault(cid, []).append(sub.sub_id)

        members = self.cluster_to_members[cid]
        n = len(members)
        self._diag(
            "cluster_observe",
            cluster_id=cid,
            cluster_size=n,
            subgoal=sub.subgoal,
            action_signature=sub.action_signature(),
            source_task=sub.source_task,
        )
        if n >= self.maturity and cid not in self._abstracted:
            print(f"  [library] cluster {cid} reached maturity ({n} members), "
                  f"attempting abstraction...")
            self._diag(
                "cluster_matured",
                cluster_id=cid,
                cluster_size=n,
                signatures=dict(Counter(
                    self.subtrajs[mid].action_signature()
                    for mid in members
                    if mid in self.subtrajs and self.subtrajs[mid] is not None
                )),
            )
            return self._try_admit(cid)
        elif n > 0 and n < self.maturity:
            pass  # still accumulating
        return None

    def _try_admit(self, cid: int) -> int | None:
        members = [self.subtrajs[mid] for mid in self.cluster_to_members[cid]]
        card = abstract_cluster(self.llm, cid, members)
        if card is None:                                 # LLM abstraction failed
            print(f"  [library] cluster {cid}: abstraction FAILED, will retry later")
            self._diag(
                "abstraction_rejected",
                cluster_id=cid,
                cluster_size=len(members),
                reason="abstract_cluster_returned_none",
            )
            return None                                   # don't mark abstracted; retry later
        existing = self._duplicate_skill(card)
        if existing is not None:
            self._abstracted.add(cid)
            print(f"  [library] cluster {cid}: duplicate skill \"{card.name}\" "
                  f"matches {existing.skill_id}; skipping admission")
            self._diag(
                "duplicate_skill",
                cluster_id=cid,
                skill_name=card.name,
                existing_skill_id=existing.skill_id,
            )
            return None
        card.stats.n_members = len(members)
        for m in members:
            card.stats.sites_seen.add(m.source_site)
        print(f"  [library] cluster {cid}: abstracted → \"{card.name}\", "
              f"verifying (k={self.verify_k})...")
        contexts = self.verify_contexts_fn()
        effective_k = self._effective_verify_k(card, contexts)
        self._diag(
            "skill_abstracted",
            cluster_id=cid,
            skill_name=card.name,
            cluster_size=len(members),
            verify_k=effective_k,
            contexts=len(contexts),
            bootstrap=bool(card.stats.bootstrap_verified),
        )
        ok = verify_skill(self.llm, card, contexts, k=effective_k)
        if ok:
            self._abstracted.add(cid)
            self.skills[cid] = card
            if self._on_admit:
                self._on_admit(card)
            print(f"  [library] cluster {cid}: VERIFIED → skill admitted: {card.name}")
            self._diag(
                "skill_admitted",
                cluster_id=cid,
                skill_name=card.name,
                verify_success=card.stats.n_verify_success,
                verify_attempts=card.stats.n_verify_attempts,
                bootstrap=bool(card.stats.bootstrap_verified),
            )
            return card.skill_id
        # verification failed — do NOT mark abstracted so we can retry later
        print(f"  [library] cluster {cid}: verification FAILED, will retry later")
        self._diag(
            "verification_rejected",
            cluster_id=cid,
            skill_name=card.name,
            verify_success=card.stats.n_verify_success,
            verify_attempts=card.stats.n_verify_attempts,
            required=effective_k,
            reason="insufficient_successes",
        )
        return None

    def _effective_verify_k(self, card: SkillCard, contexts: list) -> int:
        if card.stats.bootstrap_verified and contexts:
            unique = set()
            for env in contexts:
                site = getattr(env, "site", "") or repr(env)
                start = getattr(env, "start", "")
                try:
                    page_url = env.pages[start].url
                except Exception:
                    page_url = str(start)
                unique.add(f"{site}:{page_url}")
            if len(unique) < self.verify_k:
                return 1
        return self.verify_k

    # --------------------------------------------------------------- retrieval
    def retrieve(self, query: str, top_k: int = 3) -> list[SkillCard]:
        """Cosine retrieval of admitted skills against a query (used for transfer)."""
        if not self.skills:
            return []
        q = self.embedder.encode([query])[0]
        scored = []
        for cid, card in self.skills.items():
            c = self.clusterer.clusters.get(cid)
            if c is None:
                continue
            scored.append((float(c.centroid @ q), card))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [card for _, card in scored[:top_k]]

    # ------------------------------------------------------------------- prune
    def prune(self) -> list[str]:
        """Drop verified skills whose running success rate decayed below threshold."""
        dropped = []
        for cid in list(self.skills):
            card = self.skills[cid]
            if card.stats.n_verify_attempts >= 4 and card.stats.success_rate < self.prune_min_rate:
                dropped.append(card.skill_id)
                del self.skills[cid]
        return dropped

    def all_skills(self) -> list[SkillCard]:
        return list(self.skills.values())

    def _duplicate_skill(self, candidate: SkillCard) -> SkillCard | None:
        for card in self.skills.values():
            if card.name == candidate.name:
                return card
        return None
