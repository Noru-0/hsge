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
from .webarena.predicates import PredicateExtractor


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
        predicate_extractor: PredicateExtractor | None = None,
    ):
        self.llm = llm
        self.embedder = embedder
        self.verify_contexts_fn = verify_contexts_fn
        self.maturity = maturity
        self.verify_k = verify_k
        self.prune_min_rate = prune_min_rate
        self.predicate_extractor = predicate_extractor

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

        # Re-abstraction: an already-admitted execution-only skill (empty
        # planning_effects) that now has new members with actual effects
        # should be re-evaluated.  Clear the abstracted flag so the next
        # maturity trigger will re-abstract.
        if cid in self._abstracted and cid in self.skills:
            admitted_card = self.skills[cid]
            if (
                not admitted_card.planning_effects
                and sub.planning_effects
            ):
                print(
                    f"  [library] cluster {cid}: new effect evidence "
                    f"arrived for execution-only skill "
                    f"\"{admitted_card.name}\" — will re-abstract on "
                    f"next maturity cycle"
                )
                self._diag(
                    "reabstract_scheduled",
                    cluster_id=cid,
                    skill_name=admitted_card.name,
                    old_effects=list(admitted_card.planning_effects),
                    new_effects=list(sub.planning_effects),
                )
                # Do not clear _abstracted immediately; wait until next
                # maturity threshold to batch the re-abstraction.
                if n >= self.maturity:
                    self._abstracted.discard(cid)
                    return self._try_admit(cid)

        return None

    def _try_admit(self, cid: int) -> int | None:
        # --- split heterogeneous clusters before abstraction ---
        split_cids = self._split_incompatible_cluster(cid)
        if split_cids:
            self._diag(
                "cluster_split",
                original_cluster_id=cid,
                new_cluster_ids=split_cids,
                reason="incompatible_effect_signatures",
            )
            # Recurse: each new cluster may now be mature on its own.
            admitted = []
            for new_cid in split_cids:
                new_members = self.cluster_to_members.get(new_cid, [])
                if len(new_members) >= self.maturity and new_cid not in self._abstracted:
                    result = self._try_admit(new_cid)
                    if result:
                        admitted.append(result)
            return admitted[0] if admitted else None

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
        ok = verify_skill(
            self.llm,
            card,
            contexts,
            k=effective_k,
            predicate_extractor=self.predicate_extractor,
        )
        if ok:
            planning_successes = int(
                getattr(card, "_planning_verify_successes", 0)
            )
            card.planning_ready = bool(card.planning_effects) and (
                planning_successes >= effective_k
            )
            if not card.planning_effects:
                card.planning_rejection_reason = "empty_planning_effects"
            elif not card.planning_ready:
                card.planning_rejection_reason = "planning_effects_unverified"
            else:
                card.planning_rejection_reason = ""
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
                planning_ready=card.planning_ready,
                planning_rejection_reason=card.planning_rejection_reason,
                planning_verify_success=planning_successes,
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
            failure_reasons=dict(Counter(getattr(card, "_verify_failures", []))),
        )
        return None

    def _effective_verify_k(self, card: SkillCard, contexts: list) -> int:
        if card.stats.bootstrap_verified and contexts:
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
        """Detect duplicates by planning semantics, not just name.

        Two skills with the same generic name but different planning effects
        are NOT duplicates — they serve different roles in the operator graph.
        """
        for card in self.skills.values():
            if card.name != candidate.name:
                continue
            # Same name + overlapping effects → true duplicate (same role)
            if card.planning_effects and candidate.planning_effects:
                if card.planning_effects & candidate.planning_effects:
                    return card
                # Different effects → different roles, keep both
                continue
            # One has empty effects → ambiguous; check if same action signature
            if not card.planning_effects or not candidate.planning_effects:
                return card
        return None

    # --------------------------------------------------- cluster splitting ---
    def _effect_signature(
        self, member_ids: list[str]
    ) -> dict[frozenset[str], list[str]]:
        """Group member IDs by their planning_effects set."""
        groups: dict[frozenset[str], list[str]] = {}
        for mid in member_ids:
            sub = self.subtrajs.get(mid)
            if sub is None:
                continue
            key = frozenset(sub.planning_effects)
            groups.setdefault(key, []).append(mid)
        return groups

    def _split_incompatible_cluster(self, cid: int) -> list[int]:
        """Split a mature cluster whose members have incompatible effect
        signatures.  Returns new cluster IDs if a split occurred, or empty
        list if the cluster is already effect-coherent."""
        from .webarena.predicates import MILESTONE_COMMERCE

        member_ids = self.cluster_to_members.get(cid, [])
        if len(member_ids) < self.maturity:
            return []

        groups = self._effect_signature(member_ids)
        # Single effect group → already coherent
        if len(groups) <= 1:
            return []

        # A split is only warranted when commerce-milestone effects differ.
        milestone_groups: dict[frozenset[str], list[str]] = {}
        for eff_key, mids in groups.items():
            milestone_key = frozenset(eff_key & MILESTONE_COMMERCE)
            milestone_groups.setdefault(milestone_key, []).extend(mids)

        if len(milestone_groups) <= 1:
            return []

        # Require at least 2 members per group to avoid noise splits.
        viable = [
            (mkey, mids)
            for mkey, mids in milestone_groups.items()
            if len(mids) >= 2
        ]
        if len(viable) < 2:
            return []

        print(
            f"  [library] cluster {cid}: splitting by incompatible commerce "
            f"effects: {[(list(k), len(v)) for k, v in viable]}"
        )
        # Build new centroids: average of member vectors per group
        member_groups: list[tuple[list[str], np.ndarray]] = []
        for _mkey, mids in viable:
            vectors = []
            for mid in mids:
                sub = self.subtrajs.get(mid)
                if sub is not None:
                    vectors.append(self.embedder.encode([sub.text_for_embedding()])[0])
            if not vectors:
                continue
            centroid = np.mean(vectors, axis=0)
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm
            member_groups.append((mids, centroid))

        if len(member_groups) < 2:
            return []

        new_cids = self.clusterer.split_cluster(cid, member_groups)
        # Update cluster_to_members mapping
        if cid in self.cluster_to_members:
            del self.cluster_to_members[cid]
        for (mids, _centroid), new_cid in zip(
            [g for g in member_groups if g[0]], new_cids
        ):
            self.cluster_to_members[new_cid] = mids
        # Clear abstracted flag for the old cluster so new ones can mature
        self._abstracted.discard(cid)
        return new_cids
