"""Dynamic typed predicates, ontology canonicalization, and LLM extraction.

Embeddings are deliberately used only to retrieve ontology candidates.  Every
fact used by the typed planner is identified by a canonical predicate ID, and
non-exact matches require a verified directional ontology relation.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlparse

import numpy as np

from .llm import Embedder, LLM


PREDICATE_STATUSES = {"provisional", "detector_verified", "promoted", "rejected", "deprecated"}
RELATION_KINDS = {"equivalent", "implies", "implied_by", "contradicts", "related", "unrelated"}
PREDICATE_SCOPES = {"page", "session", "global"}
PREDICATE_PERSISTENCE = {"persistent", "transient"}
PREDICATE_KINDS = {"state", "event", "affordance", "location", "terminal"}


def _slug(value: str) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", (value or "").lower()))[:64]


def _stable_id(prefix: str, payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


@dataclass(frozen=True, order=True)
class PredicateArgument:
    name: str
    arg_type: str

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.arg_type}


@dataclass(frozen=True, order=True)
class EntityRef:
    entity_type: str
    key: str
    scope: str = "session"
    evidence: str = field(default="", compare=False)

    def to_dict(self) -> dict:
        return {
            "type": self.entity_type,
            "key": self.key,
            "scope": self.scope,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "EntityRef":
        return cls(
            entity_type=str(value.get("type", "entity")),
            key=str(value.get("key", "")),
            scope=str(value.get("scope", "session")),
            evidence=str(value.get("evidence", "")),
        )


@dataclass(frozen=True, order=True)
class PredicateFact:
    predicate_id: str
    arguments: tuple[EntityRef, ...] = ()

    def to_dict(self) -> dict:
        return {
            "predicate_id": self.predicate_id,
            "arguments": [argument.to_dict() for argument in self.arguments],
        }

    @classmethod
    def from_dict(cls, value: dict) -> "PredicateFact":
        return cls(
            predicate_id=str(value.get("predicate_id", "")),
            arguments=tuple(EntityRef.from_dict(v) for v in value.get("arguments", [])),
        )


@dataclass(frozen=True, order=True)
class FactPattern:
    predicate_id: str
    terms: tuple[str, ...] = ()
    argument_types: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "predicate_id": self.predicate_id,
            "terms": list(self.terms),
            "argument_types": list(self.argument_types),
        }

    @classmethod
    def from_dict(cls, value: dict) -> "FactPattern":
        return cls(
            predicate_id=str(value.get("predicate_id", "")),
            terms=tuple(str(v) for v in value.get("terms", [])),
            argument_types=tuple(str(v) for v in value.get("argument_types", [])),
        )


@dataclass(frozen=True)
class PredicateDefinition:
    predicate_id: str
    canonical_name: str
    description: str
    arguments: tuple[PredicateArgument, ...] = ()
    scope: str = "page"
    persistence: str = "persistent"
    kind: str = "state"
    detector_instruction: str = ""
    aliases: tuple[str, ...] = ()
    status: str = "provisional"
    source: str = "llm"

    def __post_init__(self) -> None:
        if self.status not in PREDICATE_STATUSES:
            raise ValueError(f"invalid predicate status: {self.status}")

    @property
    def arity(self) -> int:
        return len(self.arguments)

    def embedding_text(self) -> str:
        signature = ", ".join(arg.arg_type for arg in self.arguments)
        return (
            f"{self.canonical_name}({signature}): {self.description}; "
            f"kind={self.kind}; scope={self.scope}; persistence={self.persistence}"
        )

    def to_dict(self) -> dict:
        return {
            "predicate_id": self.predicate_id,
            "canonical_name": self.canonical_name,
            "description": self.description,
            "arguments": [argument.to_dict() for argument in self.arguments],
            "scope": self.scope,
            "persistence": self.persistence,
            "kind": self.kind,
            "detector_instruction": self.detector_instruction,
            "aliases": list(self.aliases),
            "status": self.status,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "PredicateDefinition":
        return cls(
            predicate_id=str(value["predicate_id"]),
            canonical_name=str(value.get("canonical_name", "")),
            description=str(value.get("description", "")),
            arguments=tuple(
                PredicateArgument(str(arg.get("name", "arg")), str(arg.get("type", "entity")))
                for arg in value.get("arguments", [])
            ),
            scope=str(value.get("scope", "page")),
            persistence=str(value.get("persistence", "persistent")),
            kind=str(value.get("kind", "state")),
            detector_instruction=str(value.get("detector_instruction", "")),
            aliases=tuple(str(alias) for alias in value.get("aliases", [])),
            status=str(value.get("status", "provisional")),
            source=str(value.get("source", "llm")),
        )


@dataclass(frozen=True)
class PredicateRelation:
    source_id: str
    target_id: str
    relation: str
    confidence: float
    verified: bool = False

    def __post_init__(self) -> None:
        if self.relation not in RELATION_KINDS:
            raise ValueError(f"invalid predicate relation: {self.relation}")

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "confidence": self.confidence,
            "verified": self.verified,
        }


@dataclass(frozen=True)
class PredicateSnapshot:
    facts: frozenset[PredicateFact]
    confidences: tuple[tuple[PredicateFact, float], ...] = ()
    evidence: tuple[tuple[PredicateFact, str], ...] = ()
    registry_revision: str = ""
    source: str = "kernel"

    def confidence_for(self, fact: PredicateFact) -> float:
        return dict(self.confidences).get(fact, 0.0)

    def to_dict(self) -> dict:
        confidence = dict(self.confidences)
        evidence = dict(self.evidence)
        return {
            "facts": [
                {
                    **fact.to_dict(),
                    "confidence": confidence.get(fact, 0.0),
                    "evidence": evidence.get(fact, ""),
                }
                for fact in sorted(self.facts)
            ],
            "registry_revision": self.registry_revision,
            "source": self.source,
        }


@dataclass(frozen=True)
class TypedActionModel:
    parameters: tuple[PredicateArgument, ...] = ()
    required_preconditions: frozenset[FactPattern] = frozenset()
    optional_context: frozenset[FactPattern] = frozenset()
    add_effects: frozenset[FactPattern] = frozenset()
    delete_effects: frozenset[FactPattern] = frozenset()
    confidence: float = 0.0
    evidence_ids: tuple[str, ...] = ()
    verified_effect_contexts: int = 0

    def to_dict(self) -> dict:
        return {
            "parameters": [p.to_dict() for p in self.parameters],
            "required_preconditions": [p.to_dict() for p in sorted(self.required_preconditions)],
            "optional_context": [p.to_dict() for p in sorted(self.optional_context)],
            "add_effects": [p.to_dict() for p in sorted(self.add_effects)],
            "delete_effects": [p.to_dict() for p in sorted(self.delete_effects)],
            "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
            "verified_effect_contexts": self.verified_effect_contexts,
        }

    @classmethod
    def from_dict(cls, value: dict | None) -> "TypedActionModel | None":
        if not value:
            return None
        patterns = lambda name: frozenset(FactPattern.from_dict(v) for v in value.get(name, []))
        return cls(
            parameters=tuple(
                PredicateArgument(str(v.get("name", "arg")), str(v.get("type", "entity")))
                for v in value.get("parameters", [])
            ),
            required_preconditions=patterns("required_preconditions"),
            optional_context=patterns("optional_context"),
            add_effects=patterns("add_effects"),
            delete_effects=patterns("delete_effects"),
            confidence=float(value.get("confidence", 0.0)),
            evidence_ids=tuple(str(v) for v in value.get("evidence_ids", [])),
            verified_effect_contexts=int(value.get("verified_effect_contexts", 0)),
        )


@dataclass
class PredicateStats:
    episode_ids: set[int] = field(default_factory=set)
    entity_keys: set[str] = field(default_factory=set)
    detector_tp: int = 0
    detector_fp: int = 0
    detector_fn: int = 0
    contradictions: int = 0
    observations: int = 0
    effect_verifications: int = 0
    effect_context_ids: set[str] = field(default_factory=set)
    held_out_tp: int = 0
    held_out_fp: int = 0
    held_out_fn: int = 0

    @property
    def precision(self) -> float:
        total = self.held_out_tp + self.held_out_fp
        return self.held_out_tp / total if total else 0.0

    @property
    def recall(self) -> float:
        total = self.held_out_tp + self.held_out_fn
        return self.held_out_tp / total if total else 0.0

    @property
    def contradiction_rate(self) -> float:
        return self.contradictions / self.observations if self.observations else 0.0

    def to_dict(self) -> dict:
        return {
            "episode_ids": sorted(self.episode_ids),
            "entity_keys": sorted(self.entity_keys),
            "detector_tp": self.detector_tp,
            "detector_fp": self.detector_fp,
            "detector_fn": self.detector_fn,
            "contradictions": self.contradictions,
            "observations": self.observations,
            "effect_verifications": self.effect_verifications,
            "effect_context_ids": sorted(self.effect_context_ids),
            "held_out_tp": self.held_out_tp,
            "held_out_fp": self.held_out_fp,
            "held_out_fn": self.held_out_fn,
            "precision": self.precision,
            "recall": self.recall,
            "contradiction_rate": self.contradiction_rate,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "PredicateStats":
        return cls(
            episode_ids={int(v) for v in value.get("episode_ids", [])},
            entity_keys={str(v) for v in value.get("entity_keys", [])},
            detector_tp=int(value.get("detector_tp", 0)),
            detector_fp=int(value.get("detector_fp", 0)),
            detector_fn=int(value.get("detector_fn", 0)),
            contradictions=int(value.get("contradictions", 0)),
            observations=int(value.get("observations", 0)),
            effect_verifications=int(value.get("effect_verifications", 0)),
            effect_context_ids={str(v) for v in value.get("effect_context_ids", [])},
            held_out_tp=int(value.get("held_out_tp", value.get("detector_tp", 0))),
            held_out_fp=int(value.get("held_out_fp", value.get("detector_fp", 0))),
            held_out_fn=int(value.get("held_out_fn", value.get("detector_fn", 0))),
        )


class EntityResolver:
    """Create stable entity keys without accepting arbitrary LLM IDs."""

    _ID_KEYS = ("sku", "id", "item", "product", "order", "issue", "ticket")

    def resolve(self, entity_type: str, value: str, *, url: str = "", scope: str = "session") -> EntityRef:
        parsed = urlparse(url or "")
        query = parse_qs(parsed.query)
        for key in self._ID_KEYS:
            if query.get(key):
                return EntityRef(entity_type, f"{key}:{_slug(query[key][0])}", scope, value)
        path_parts = [part for part in parsed.path.split("/") if part]
        if path_parts and re.search(r"[0-9]", path_parts[-1]):
            return EntityRef(entity_type, f"path:{_slug(path_parts[-1])}", scope, value)
        normalized = _slug(value)
        if normalized:
            page_scope = _stable_id("page", [parsed.netloc, parsed.path])[:21]
            return EntityRef(entity_type, f"name:{normalized}@{page_scope}", scope, value)
        return EntityRef(entity_type, _stable_id("anonymous", [entity_type, parsed.path]), "page", value)


class PredicateRegistry:
    def __init__(
        self,
        embedder: Embedder,
        *,
        top_k: int = 5,
        similarity_floor: float = 0.55,
        equivalence_confidence: float = 0.90,
        entailment_confidence: float = 0.85,
        min_contexts: int = 3,
        min_entities: int = 2,
        min_precision: float = 0.85,
        min_recall: float = 0.75,
        max_contradiction_rate: float = 0.10,
        effect_verify_k: int = 2,
    ):
        self.embedder = embedder
        self.top_k = max(1, top_k)
        self.similarity_floor = similarity_floor
        self.equivalence_confidence = equivalence_confidence
        self.entailment_confidence = entailment_confidence
        self.min_contexts = min_contexts
        self.min_entities = min_entities
        self.min_precision = min_precision
        self.min_recall = min_recall
        self.max_contradiction_rate = max_contradiction_rate
        self.effect_verify_k = effect_verify_k
        self.definitions: dict[str, PredicateDefinition] = {}
        self.aliases: dict[str, str] = {}
        self.relations: list[PredicateRelation] = []
        self.stats: dict[str, PredicateStats] = defaultdict(PredicateStats)
        self._embeddings: dict[str, np.ndarray] = {}

    @property
    def revision(self) -> str:
        payload = {
            "definitions": [self.definitions[key].to_dict() for key in sorted(self.definitions)],
            "relations": [r.to_dict() for r in sorted(self.relations, key=lambda r: (r.source_id, r.target_id, r.relation))],
        }
        return _stable_id("ontology", payload)

    def _embed(self, definition: PredicateDefinition) -> np.ndarray:
        vector = self._embeddings.get(definition.predicate_id)
        if vector is None:
            vector = self.embedder.encode([definition.embedding_text()])[0]
            self._embeddings[definition.predicate_id] = vector
        return vector

    @staticmethod
    def _opposite_names(first: str, second: str) -> bool:
        pairs = (
            ("empty", "nonempty"), ("enabled", "disabled"),
            ("selected", "unselected"), ("visible", "hidden"),
            ("authenticated", "unauthenticated"), ("open", "closed"),
        )
        a, b = set(_slug(first).split("_")), set(_slug(second).split("_"))
        return any((x in a and y in b) or (y in a and x in b) for x, y in pairs)

    @classmethod
    def structurally_compatible(cls, a: PredicateDefinition, b: PredicateDefinition) -> bool:
        return (
            a.arity == b.arity
            and tuple(arg.arg_type for arg in a.arguments) == tuple(arg.arg_type for arg in b.arguments)
            and a.scope == b.scope
            and a.persistence == b.persistence
            and not cls._opposite_names(a.canonical_name, b.canonical_name)
        )

    def nearest(self, candidate: PredicateDefinition) -> list[tuple[float, PredicateDefinition]]:
        if not self.definitions:
            return []
        query = self.embedder.encode([candidate.embedding_text()])[0]
        scored = [
            (float(self._embed(definition) @ query), definition)
            for definition in self.definitions.values()
            if self.structurally_compatible(candidate, definition)
        ]
        scored.sort(key=lambda item: (-item[0], item[1].predicate_id))
        return [item for item in scored[:self.top_k] if item[0] >= self.similarity_floor]

    def relevant_definitions(
        self, state_text: str, *, status: str = "promoted", limit: int = 50
    ) -> list[PredicateDefinition]:
        """Rank extraction candidates; ranking never establishes semantics."""
        candidates = [
            definition for definition in self.definitions.values()
            if definition.status == status
        ]
        if not candidates:
            return []
        query = self.embedder.encode([state_text or "web state"])[0]
        scored = sorted(
            ((float(self._embed(definition) @ query), definition) for definition in candidates),
            key=lambda item: (-item[0], item[1].predicate_id),
        )
        return [definition for _score, definition in scored[:max(1, limit)]]

    def add_definition(self, definition: PredicateDefinition) -> PredicateDefinition:
        self.definitions[definition.predicate_id] = definition
        self.aliases[_slug(definition.canonical_name)] = definition.predicate_id
        for alias in definition.aliases:
            self.aliases[_slug(alias)] = definition.predicate_id
        self._embeddings.pop(definition.predicate_id, None)
        return definition

    def create_definition(self, proposal: dict, *, source: str = "llm") -> PredicateDefinition:
        arguments = tuple(
            PredicateArgument(_slug(arg.get("name", "arg")) or "arg", _slug(arg.get("type", "entity")) or "entity")
            for arg in proposal.get("arguments", [])
            if isinstance(arg, dict)
        )
        signature = {
            "name": _slug(proposal.get("name", "predicate")) or "predicate",
            "types": [arg.arg_type for arg in arguments],
            "scope": proposal.get("scope", "page"),
            "persistence": proposal.get("persistence", "persistent"),
        }
        return PredicateDefinition(
            predicate_id=_stable_id("pred", signature),
            canonical_name=signature["name"],
            description=str(proposal.get("description", ""))[:500],
            arguments=arguments,
            scope=str(proposal.get("scope", "page")),
            persistence=str(proposal.get("persistence", "persistent")),
            kind=str(proposal.get("kind", "state")),
            detector_instruction=str(proposal.get("detector_instruction", ""))[:1000],
            aliases=tuple(str(v) for v in proposal.get("aliases", [])),
            status=str(proposal.get("status", "provisional")),
            source=source,
        )

    def canonicalize(
        self,
        proposal: dict,
        relation_judge: Callable[[PredicateDefinition, PredicateDefinition], tuple[str, float]] | None = None,
    ) -> tuple[PredicateDefinition, str]:
        candidate = self.create_definition(proposal)
        exact = self.aliases.get(_slug(candidate.canonical_name))
        if exact:
            return self.definitions[exact], "exact_alias"
        for _score, existing in self.nearest(candidate):
            relation, confidence = (
                relation_judge(candidate, existing) if relation_judge else ("related", 0.0)
            )
            if relation == "equivalent" and confidence >= self.equivalence_confidence:
                aliases = tuple(sorted(set(existing.aliases) | {candidate.canonical_name}))
                updated = replace(existing, aliases=aliases)
                self.add_definition(updated)
                self.aliases[_slug(candidate.canonical_name)] = existing.predicate_id
                self.relations.append(PredicateRelation(
                    candidate.predicate_id, existing.predicate_id, "equivalent", confidence, True
                ))
                return updated, "equivalent"
            if relation in {"implies", "implied_by", "contradicts"}:
                threshold = self.entailment_confidence
                if confidence >= threshold:
                    self.relations.append(PredicateRelation(
                        candidate.predicate_id, existing.predicate_id, relation, confidence, True
                    ))
        self.add_definition(candidate)
        return candidate, "created"

    def entails(self, source_id: str, target_id: str) -> bool:
        if source_id == target_id:
            return True
        adjacency: dict[str, set[str]] = defaultdict(set)
        for relation in self.relations:
            if not relation.verified:
                continue
            if relation.relation == "implies":
                adjacency[relation.source_id].add(relation.target_id)
            elif relation.relation == "implied_by":
                adjacency[relation.target_id].add(relation.source_id)
            elif relation.relation == "equivalent":
                adjacency[relation.source_id].add(relation.target_id)
                adjacency[relation.target_id].add(relation.source_id)
        seen = {source_id}
        frontier = [source_id]
        while frontier:
            current = frontier.pop()
            for nxt in adjacency.get(current, set()):
                if nxt == target_id:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        return False

    def record_evidence(
        self,
        predicate_id: str,
        *,
        episode_id: int,
        facts: Iterable[PredicateFact] = (),
        detector_tp: int = 1,
        detector_fp: int = 0,
        detector_fn: int = 0,
        contradiction: bool = False,
        effect_verified: bool = False,
        effect_context_id: str = "",
        held_out: bool = False,
        allow_promotion: bool = True,
    ) -> None:
        stats = self.stats[predicate_id]
        stats.episode_ids.add(episode_id)
        for fact in facts:
            stats.entity_keys.update(arg.key for arg in fact.arguments)
        stats.detector_tp += detector_tp
        stats.detector_fp += detector_fp
        stats.detector_fn += detector_fn
        stats.observations += detector_tp + detector_fp + detector_fn
        stats.contradictions += int(contradiction)
        stats.effect_verifications += int(effect_verified)
        if effect_verified and effect_context_id:
            stats.effect_context_ids.add(effect_context_id)
        if held_out:
            stats.held_out_tp += detector_tp
            stats.held_out_fp += detector_fp
            stats.held_out_fn += detector_fn
        if allow_promotion:
            self.maybe_promote(predicate_id)

    def maybe_promote(self, predicate_id: str) -> bool:
        definition = self.definitions[predicate_id]
        stats = self.stats[predicate_id]
        enough_entities = definition.arity == 0 or len(stats.entity_keys) >= self.min_entities
        ready = (
            len(stats.episode_ids) >= self.min_contexts
            and enough_entities
            and stats.precision >= self.min_precision
            and stats.recall >= self.min_recall
            and stats.contradiction_rate <= self.max_contradiction_rate
            and (
                len(stats.effect_context_ids)
                if stats.effect_context_ids else stats.effect_verifications
            ) >= self.effect_verify_k
        )
        detector_ready = (
            stats.precision >= self.min_precision
            and stats.recall >= self.min_recall
            and stats.contradiction_rate <= self.max_contradiction_rate
        )
        if detector_ready and definition.status == "provisional":
            definition = replace(definition, status="detector_verified")
            self.add_definition(definition)
        if ready and definition.status != "promoted":
            self.add_definition(replace(definition, status="promoted"))
            return True
        return False

    def all_promoted(self, predicate_ids: Iterable[str]) -> bool:
        ids = set(predicate_ids)
        return bool(ids) and all(
            predicate_id in self.definitions
            and self.definitions[predicate_id].status == "promoted"
            for predicate_id in ids
        )

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "revision": self.revision,
            "config": {
                "top_k": self.top_k,
                "similarity_floor": self.similarity_floor,
                "equivalence_confidence": self.equivalence_confidence,
                "entailment_confidence": self.entailment_confidence,
                "min_contexts": self.min_contexts,
                "min_entities": self.min_entities,
                "min_precision": self.min_precision,
                "min_recall": self.min_recall,
                "max_contradiction_rate": self.max_contradiction_rate,
                "effect_verify_k": self.effect_verify_k,
            },
            "definitions": [self.definitions[key].to_dict() for key in sorted(self.definitions)],
            "aliases": dict(sorted(self.aliases.items())),
            "relations": [relation.to_dict() for relation in self.relations],
            "stats": {key: value.to_dict() for key, value in sorted(self.stats.items())},
        }

    @classmethod
    def from_dict(cls, value: dict, embedder: Embedder) -> "PredicateRegistry":
        registry = cls(embedder, **value.get("config", {}))
        for raw in value.get("definitions", []):
            registry.add_definition(PredicateDefinition.from_dict(raw))
        registry.aliases.update({str(k): str(v) for k, v in value.get("aliases", {}).items()})
        registry.relations = [PredicateRelation(**raw) for raw in value.get("relations", [])]
        registry.stats.update({
            str(key): PredicateStats.from_dict(raw)
            for key, raw in value.get("stats", {}).items()
        })
        return registry


class PredicateEngine:
    """Hybrid kernel + dynamic predicate engine with state-signature caching."""

    def __init__(
        self,
        registry: PredicateRegistry,
        llm: LLM | None,
        *,
        kernel_extractor=None,
        cache_size: int = 5000,
        mode: str = "shadow_promote",
    ):
        self.registry = registry
        self.llm = llm
        self.kernel_extractor = kernel_extractor
        self.cache_size = max(1, cache_size)
        self.mode = mode
        self.entity_resolver = EntityResolver()
        self._cache: OrderedDict[str, PredicateSnapshot] = OrderedDict()
        self.metrics = Counter()
        self.proposal_log: list[dict] = []
        self.observation_log: list[dict] = []
        self._seed_kernel_definitions()

    @property
    def schema_version(self) -> str:
        return f"typed-v1+{self.registry.revision}"

    @property
    def terminal_predicates(self) -> frozenset[str]:
        return frozenset(
            definition.predicate_id
            for definition in self.registry.definitions.values()
            if definition.kind == "terminal" and definition.status == "promoted"
        )

    def _seed_kernel_definitions(self) -> None:
        names = sorted(getattr(self.kernel_extractor, "terminal_predicates", frozenset()))
        for name in names:
            definition = PredicateDefinition(
                predicate_id=f"kernel:{name}",
                canonical_name=name,
                description=f"Deterministic kernel fact: {name}",
                kind="terminal",
                status="promoted",
                source="kernel",
            )
            self.registry.add_definition(definition)

    @staticmethod
    def _state_signature(url: str, axtree: str, revision: str) -> str:
        normalized_ax = re.sub(r"\s+", " ", (axtree or "").strip())
        return _stable_id("state", [url, normalized_ax, revision])

    def _cache_put(self, key: str, snapshot: PredicateSnapshot) -> None:
        self._cache[key] = snapshot
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def extract(self, url: str, axtree: str = "") -> set[str]:
        """Compatibility view used by legacy planning and episode artifacts."""
        if self.kernel_extractor is None:
            return set()
        return set(self.kernel_extractor.extract(url, axtree))

    def snapshot(self, url: str, axtree: str = "", context: dict | None = None) -> PredicateSnapshot:
        key = self._state_signature(url, axtree, self.registry.revision)
        if key in self._cache:
            self.metrics["cache_hits"] += 1
            self._cache.move_to_end(key)
            return self._cache[key]
        self.metrics["cache_misses"] += 1
        facts: set[PredicateFact] = set()
        confidence: dict[PredicateFact, float] = {}
        evidence: dict[PredicateFact, str] = {}
        for name in self.extract(url, axtree):
            predicate_id = self.registry.aliases.get(_slug(name))
            if not predicate_id:
                definition = PredicateDefinition(
                    predicate_id=f"kernel:{name}", canonical_name=name,
                    description=f"Deterministic kernel fact: {name}",
                    status="promoted", source="kernel",
                )
                self.registry.add_definition(definition)
                predicate_id = definition.predicate_id
            fact = PredicateFact(predicate_id)
            facts.add(fact)
            confidence[fact] = 1.0
            evidence[fact] = "deterministic kernel"

        promoted = self.registry.relevant_definitions(
            f"{url}\n{axtree}", status="promoted", limit=100
        )
        if promoted and self.llm is not None:
            payload = {
                "url": url,
                "axtree": (axtree or "")[:8000],
                "context": context or {},
                "predicates": [definition.to_dict() for definition in promoted[:100]],
                "contract": "Use only listed predicate IDs and quote exact page evidence.",
            }
            try:
                self.metrics["fact_llm_calls"] += 1
                output = self.llm.complete_json(
                    "Extract grounded canonical predicate facts from a web state.",
                    json.dumps(payload, ensure_ascii=False),
                )
                for raw in output.get("facts", []) if isinstance(output, dict) else []:
                    fact, fact_confidence, fact_evidence = self._validated_fact(raw, url, axtree)
                    if fact is not None:
                        facts.add(fact)
                        confidence[fact] = fact_confidence
                        evidence[fact] = fact_evidence
            except Exception:
                self.metrics["fact_llm_errors"] += 1
        snapshot = PredicateSnapshot(
            facts=frozenset(facts),
            confidences=tuple(sorted(confidence.items(), key=lambda item: item[0])),
            evidence=tuple(sorted(evidence.items(), key=lambda item: item[0])),
            registry_revision=self.registry.revision,
            source="hybrid" if promoted else "kernel",
        )
        self._cache_put(key, snapshot)
        self.observation_log.append({"state_id": key, "url": url, **snapshot.to_dict()})
        return snapshot

    def _validated_fact(self, raw: dict, url: str, axtree: str) -> tuple[PredicateFact | None, float, str]:
        predicate_id = str(raw.get("predicate_id", ""))
        definition = self.registry.definitions.get(predicate_id)
        if definition is None or definition.status != "promoted":
            self.metrics["rejected_unknown_fact"] += 1
            return None, 0.0, ""
        evidence = str(raw.get("evidence", ""))
        if not evidence or evidence.lower() not in f"{url}\n{axtree}".lower():
            self.metrics["rejected_hallucinated_evidence"] += 1
            return None, 0.0, ""
        arguments = raw.get("arguments", [])
        if len(arguments) != definition.arity:
            self.metrics["rejected_fact_arity"] += 1
            return None, 0.0, ""
        for spec, value in zip(definition.arguments, arguments):
            if isinstance(value, dict) and value.get("type") not in {None, spec.arg_type}:
                self.metrics["rejected_fact_type"] += 1
                return None, 0.0, ""
        entities = tuple(
            self.entity_resolver.resolve(
                spec.arg_type,
                str(value.get("value", value.get("key", ""))) if isinstance(value, dict) else str(value),
                url=url,
                scope=definition.scope,
            )
            for spec, value in zip(definition.arguments, arguments)
        )
        return PredicateFact(predicate_id, entities), float(raw.get("confidence", 0.0)), evidence

    def relation_judge(self, candidate: PredicateDefinition, existing: PredicateDefinition) -> tuple[str, float]:
        if self.llm is None:
            return "related", 0.0
        payload = {"candidate": candidate.to_dict(), "existing": existing.to_dict()}
        try:
            self.metrics["relation_llm_calls"] += 1
            output = self.llm.complete_json(
                "Classify the directional semantic relation between two typed predicates.",
                json.dumps(payload, ensure_ascii=False),
            )
            relation = str(output.get("relation", "unrelated"))
            confidence = float(output.get("confidence", 0.0))
            return (relation, confidence) if relation in RELATION_KINDS else ("unrelated", 0.0)
        except Exception:
            self.metrics["relation_llm_errors"] += 1
            return "unrelated", 0.0

    def induce_episode(
        self,
        *,
        episode_id: int,
        task: str,
        success: bool,
        steps: list,
        obs_texts: list[str],
        final_obs: dict,
    ) -> list[dict]:
        if self.llm is None or not steps:
            return []
        transitions = []
        for index, step in enumerate(steps[:20]):
            planning = ((getattr(step, "misc", None) or {}).get("planning", {}) or {})
            before_ax = obs_texts[index] if index < len(obs_texts) else ""
            after_ax = (
                obs_texts[index + 1]
                if index + 1 < len(obs_texts)
                else str(final_obs.get("axtree", ""))
            )
            before_lines = {line.strip() for line in before_ax.splitlines() if line.strip()}
            after_lines = {line.strip() for line in after_ax.splitlines() if line.strip()}
            transitions.append({
                "step_index": index,
                "action": getattr(step, "action", ""),
                "target": {
                    "role": planning.get("target_role", ""),
                    "name": planning.get("target_name", ""),
                    "fingerprint": planning.get("target_fingerprint", ""),
                },
                "before": {
                    "url": planning.get("pre_url", getattr(step, "url", "")),
                    "axtree": before_ax[:3500],
                },
                "after": {
                    "url": planning.get("post_url", final_obs.get("url", "")),
                    "axtree": after_ax[:3500],
                },
                "dom_diff": {
                    "added": sorted(after_lines - before_lines)[:40],
                    "removed": sorted(before_lines - after_lines)[:40],
                },
                "transient_messages": [
                    line for line in sorted(after_lines - before_lines)
                    if re.search(r"success|error|added|removed|saved|failed", line, re.I)
                ][:10],
                "rule_baseline_before": sorted(self.extract(
                    planning.get("pre_url", getattr(step, "url", "")), before_ax
                )),
                "rule_baseline_after": sorted(self.extract(
                    planning.get("post_url", final_obs.get("url", "")), after_ax
                )),
            })
        payload = {
            "task": task,
            "episode_id": episode_id,
            "success": success,
            "transitions": transitions,
            "ontology": [d.to_dict() for d in list(self.registry.definitions.values())[:100]],
            "output_contract": {
                "predicates": [{
                    "name": "snake_case", "description": "state meaning",
                    "arguments": [{"name": "item", "type": "product"}],
                    "scope": "page|session|global", "persistence": "persistent|transient",
                    "kind": "state|event|affordance|location|terminal",
                    "detector_instruction": "how to observe it",
                    "observations": [{
                        "step_index": 0, "truth_before": False, "truth_after": True,
                        "evidence_before": "", "evidence_after": "exact visible text",
                        "argument_values": ["visible entity"],
                        "required_precondition": False,
                    }],
                }],
            },
        }
        try:
            self.metrics["invention_llm_calls"] += 1
            output = self.llm.complete_json(
                "Induce minimal reusable typed predicates from web action transitions.",
                json.dumps(payload, ensure_ascii=False),
            )
        except Exception:
            self.metrics["invention_llm_errors"] += 1
            return []
        accepted: list[dict] = []
        for proposal in output.get("predicates", []) if isinstance(output, dict) else []:
            if not isinstance(proposal, dict) or not proposal.get("name"):
                self.metrics["rejected_malformed_proposal"] += 1
                continue
            supplied_id = str(proposal.get("predicate_id", ""))
            invalid_schema = (
                proposal.get("scope", "page") not in PREDICATE_SCOPES
                or proposal.get("persistence", "persistent") not in PREDICATE_PERSISTENCE
                or proposal.get("kind", "state") not in PREDICATE_KINDS
                or (supplied_id and supplied_id not in self.registry.definitions)
            )
            if invalid_schema:
                self.metrics["rejected_invalid_proposal_schema"] += 1
                self.proposal_log.append({
                    "episode_id": episode_id,
                    "proposal": proposal,
                    "disposition": "rejected_invalid_schema",
                })
                continue
            candidate = self.registry.create_definition(proposal)
            nearest_candidates = [
                {"predicate_id": definition.predicate_id, "score": score}
                for score, definition in self.registry.nearest(candidate)
            ]
            grounded = []
            for observation in proposal.get("observations", []):
                index = int(observation.get("step_index", -1))
                if not 0 <= index < len(transitions):
                    continue
                transition = transitions[index]
                before_evidence = str(observation.get("evidence_before", ""))
                after_evidence = str(observation.get("evidence_after", ""))
                before_text = transition["before"]["url"] + "\n" + transition["before"]["axtree"]
                after_text = transition["after"]["url"] + "\n" + transition["after"]["axtree"]
                evidence_valid = (
                    bool(before_evidence or after_evidence)
                    and (not before_evidence or before_evidence.lower() in before_text.lower())
                    and (not after_evidence or after_evidence.lower() in after_text.lower())
                )
                values = list(observation.get("argument_values", []))
                if evidence_valid and len(values) == candidate.arity:
                    grounded.append((observation, index, transition))
            if not grounded:
                self.metrics["rejected_no_grounded_evidence"] += 1
                self.proposal_log.append({
                    "episode_id": episode_id,
                    "proposal": proposal,
                    "nearest_candidates": nearest_candidates,
                    "disposition": "rejected_no_grounded_evidence",
                })
                continue
            existing_before = candidate.predicate_id in self.registry.definitions or bool(
                self.registry.aliases.get(_slug(candidate.canonical_name))
            )
            definition, disposition = self.registry.canonicalize(proposal, self.relation_judge)
            proposal_record = {
                "episode_id": episode_id,
                "predicate_id": definition.predicate_id,
                "proposal": proposal,
                "nearest_candidates": nearest_candidates,
                "disposition": disposition,
            }
            valid_observations = []
            for observation, index, transition in grounded:
                before_evidence = str(observation.get("evidence_before", ""))
                after_evidence = str(observation.get("evidence_after", ""))
                before_text = transition["before"]["url"] + "\n" + transition["before"]["axtree"]
                after_text = transition["after"]["url"] + "\n" + transition["after"]["axtree"]
                values = list(observation.get("argument_values", []))
                entities = tuple(
                    self.entity_resolver.resolve(
                        argument.arg_type, str(value),
                        url=transition["after"]["url"] or transition["before"]["url"],
                        scope=definition.scope,
                    )
                    for argument, value in zip(definition.arguments, values)
                )
                fact = PredicateFact(definition.predicate_id, entities)
                truth_before = bool(observation.get("truth_before", False))
                truth_after = bool(observation.get("truth_after", False))
                effect = truth_before != truth_after
                self.registry.record_evidence(
                    definition.predicate_id,
                    episode_id=episode_id,
                    facts=[fact],
                    detector_tp=int(bool(before_evidence or after_evidence)),
                    detector_fn=int(not bool(before_evidence or after_evidence)),
                    effect_verified=bool(success and effect),
                    effect_context_id=_stable_id("context", [
                        transition["before"]["url"],
                        re.sub(r"\s+", " ", transition["before"]["axtree"]),
                    ]),
                    held_out=existing_before,
                    allow_promotion=self.mode == "shadow_promote",
                )
                valid_observations.append({
                    "step_index": index,
                    "fact": fact.to_dict(),
                    "truth_before": truth_before,
                    "truth_after": truth_after,
                    "required_precondition": bool(observation.get("required_precondition", False)),
                })
                planning = ((getattr(steps[index], "misc", None) or {}).setdefault("planning", {}))
                key = "typed_pre_facts" if truth_before else "typed_pre_absent"
                planning.setdefault(key, []).append(fact.to_dict())
                key = "typed_post_facts" if truth_after else "typed_post_absent"
                planning.setdefault(key, []).append(fact.to_dict())
                if observation.get("required_precondition") and truth_before:
                    # LLM co-occurrence is optional context. Required admission is
                    # intentionally reserved for an external failure/replay verifier.
                    planning.setdefault("typed_optional_context", []).append(fact.to_dict())
            proposal_record["observations"] = valid_observations
            self.proposal_log.append(proposal_record)
            if valid_observations:
                accepted.append(proposal_record)
                self.metrics["accepted_proposals"] += 1
        return accepted

    def diagnostics(self) -> dict:
        return {
            "mode": self.mode,
            "schema_version": self.schema_version,
            "registry_revision": self.registry.revision,
            "metrics": dict(sorted(self.metrics.items())),
            "definitions": len(self.registry.definitions),
            "promoted": sum(d.status == "promoted" for d in self.registry.definitions.values()),
            "provisional": sum(d.status == "provisional" for d in self.registry.definitions.values()),
            "cache_entries": len(self._cache),
        }

    def reached(self, goal: FactPattern, snapshot: PredicateSnapshot) -> bool:
        for fact in snapshot.facts:
            if not self.registry.entails(fact.predicate_id, goal.predicate_id):
                continue
            if len(fact.arguments) != len(goal.terms):
                continue
            bindings: dict[str, EntityRef] = {}
            matched = True
            for index, (term, entity) in enumerate(zip(goal.terms, fact.arguments)):
                expected_type = goal.argument_types[index] if index < len(goal.argument_types) else ""
                if expected_type and entity.entity_type != expected_type:
                    matched = False
                    break
                if term.startswith("?"):
                    if term in bindings and bindings[term] != entity:
                        matched = False
                        break
                    bindings[term] = entity
                elif term != entity.key:
                    matched = False
                    break
            if matched:
                return True
        return False


def lift_facts_to_patterns(facts: Iterable[PredicateFact]) -> frozenset[FactPattern]:
    """Lift grounded facts while preserving repeated-entity identity."""
    variables: dict[tuple[str, str], str] = {}
    counters: dict[str, int] = defaultdict(int)
    patterns = set()
    for fact in sorted(facts):
        terms = []
        types = []
        for entity in fact.arguments:
            identity = (entity.entity_type, entity.key)
            if identity not in variables:
                index = counters[entity.entity_type]
                counters[entity.entity_type] += 1
                variables[identity] = f"?{entity.entity_type}_{index}"
            terms.append(variables[identity])
            types.append(entity.entity_type)
        patterns.add(FactPattern(fact.predicate_id, tuple(terms), tuple(types)))
    return frozenset(patterns)


def lift_transition_to_model(
    before: Iterable[PredicateFact],
    after: Iterable[PredicateFact],
    required: Iterable[PredicateFact] = (),
    *,
    evidence_id: str = "",
) -> TypedActionModel:
    """Lift one grounded transition with one shared variable environment."""
    before_set, after_set, required_set = set(before), set(after), set(required)
    variables: dict[tuple[str, str], str] = {}
    counters: dict[str, int] = defaultdict(int)

    def lift(facts: Iterable[PredicateFact]) -> frozenset[FactPattern]:
        patterns = set()
        for fact in sorted(facts):
            terms, types = [], []
            for entity in fact.arguments:
                identity = (entity.entity_type, entity.key)
                if identity not in variables:
                    index = counters[entity.entity_type]
                    counters[entity.entity_type] += 1
                    variables[identity] = f"?{entity.entity_type}_{index}"
                terms.append(variables[identity])
                types.append(entity.entity_type)
            patterns.add(FactPattern(fact.predicate_id, tuple(terms), tuple(types)))
        return frozenset(patterns)

    required_patterns = lift(required_set)
    optional_patterns = lift(before_set - required_set)
    add_patterns = lift(after_set - before_set)
    delete_patterns = lift(before_set - after_set)
    parameters = tuple(
        PredicateArgument(variable.lstrip("?"), entity_type)
        for (entity_type, _key), variable in sorted(variables.items(), key=lambda item: item[1])
    )
    return TypedActionModel(
        parameters=parameters,
        required_preconditions=required_patterns,
        optional_context=optional_patterns,
        add_effects=add_patterns,
        delete_effects=delete_patterns,
        confidence=1.0 if add_patterns or delete_patterns else 0.0,
        evidence_ids=(evidence_id,) if evidence_id else (),
        verified_effect_contexts=1 if add_patterns or delete_patterns else 0,
    )
