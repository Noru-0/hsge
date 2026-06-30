"""Typed relational operators with entity-preserving unification."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace

from .predicate_ontology import (
    EntityRef,
    FactPattern,
    PredicateFact,
    PredicateRegistry,
    TypedActionModel,
)


@dataclass(frozen=True)
class RelationalOperator:
    name: str
    model: TypedActionModel
    skill_id: str
    terminal: bool = False

    @property
    def key(self) -> str:
        return self.skill_id or self.name

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "skill_id": self.skill_id,
            "terminal": self.terminal,
            "model": self.model.to_dict(),
        }

    @classmethod
    def from_skill(cls, card) -> "RelationalOperator":
        if not getattr(card, "verified", False):
            raise ValueError("cannot create typed operator from unverified skill")
        model = getattr(card, "typed_action_model", None)
        if model is None:
            raise ValueError("skill has no typed action model")
        return cls(
            name=str(card.name), model=model,
            skill_id=str(card.skill_id), terminal=bool(card.terminal),
        )

    @classmethod
    def from_dict(cls, value: dict) -> "RelationalOperator":
        model = TypedActionModel.from_dict(value.get("model"))
        if model is None:
            raise ValueError("typed relational operator requires an action model")
        return cls(
            name=str(value.get("name", "operator")),
            model=model,
            skill_id=str(value.get("skill_id", "")),
            terminal=bool(value.get("terminal", False)),
        )


@dataclass(frozen=True)
class TypedPlanStep:
    operator_id: str
    bindings: tuple[tuple[str, EntityRef], ...] = ()

    def binding_dict(self) -> dict[str, EntityRef]:
        return dict(self.bindings)

    def to_dict(self) -> dict:
        return {
            "operator_id": self.operator_id,
            "bindings": {
                variable: entity.to_dict() for variable, entity in self.bindings
            },
        }


def _match_pattern(
    pattern: FactPattern,
    fact: PredicateFact,
    bindings: dict[str, EntityRef],
    registry: PredicateRegistry,
) -> dict[str, EntityRef] | None:
    if not registry.entails(fact.predicate_id, pattern.predicate_id):
        return None
    if len(pattern.terms) != len(fact.arguments):
        return None
    result = dict(bindings)
    for index, (term, entity) in enumerate(zip(pattern.terms, fact.arguments)):
        expected_type = pattern.argument_types[index] if index < len(pattern.argument_types) else ""
        if expected_type and entity.entity_type != expected_type:
            return None
        if term.startswith("?"):
            bound = result.get(term)
            if bound is not None and bound != entity:
                return None
            result[term] = entity
        elif term != entity.key:
            return None
    return result


def satisfying_bindings(
    patterns: frozenset[FactPattern],
    state: frozenset[PredicateFact],
    registry: PredicateRegistry,
) -> list[dict[str, EntityRef]]:
    if not patterns:
        return [{}]
    ordered = sorted(patterns, key=lambda pattern: (pattern.predicate_id, pattern.terms))
    candidates: list[dict[str, EntityRef]] = [{}]
    for pattern in ordered:
        next_candidates: list[dict[str, EntityRef]] = []
        for bindings in candidates:
            for fact in state:
                matched = _match_pattern(pattern, fact, bindings, registry)
                if matched is not None and matched not in next_candidates:
                    next_candidates.append(matched)
        candidates = next_candidates
        if not candidates:
            return []
    return candidates


def instantiate(pattern: FactPattern, bindings: dict[str, EntityRef]) -> PredicateFact | None:
    arguments = []
    for index, term in enumerate(pattern.terms):
        expected_type = pattern.argument_types[index] if index < len(pattern.argument_types) else "entity"
        if term.startswith("?"):
            entity = bindings.get(term)
            if entity is None or (expected_type and entity.entity_type != expected_type):
                return None
            arguments.append(entity)
        else:
            arguments.append(EntityRef(expected_type or "entity", term, "global"))
    return PredicateFact(pattern.predicate_id, tuple(arguments))


class RelationalOperatorGraph:
    def __init__(self, registry: PredicateRegistry):
        self.registry = registry
        self.ops: dict[str, RelationalOperator] = {}
        self.goal_patterns: set[FactPattern] = set()

    def add(self, operator: RelationalOperator) -> None:
        def persistent(pattern: FactPattern) -> bool:
            definition = self.registry.definitions.get(pattern.predicate_id)
            return bool(
                definition
                and definition.persistence == "persistent"
                and definition.kind != "event"
            )

        model = operator.model
        model = replace(
            model,
            required_preconditions=frozenset(filter(persistent, model.required_preconditions)),
            optional_context=frozenset(filter(persistent, model.optional_context)),
            add_effects=frozenset(filter(persistent, model.add_effects)),
            delete_effects=frozenset(filter(persistent, model.delete_effects)),
        )
        operator = replace(operator, model=model)
        predicate_ids = {
            pattern.predicate_id
            for pattern in (
                operator.model.required_preconditions
                | operator.model.add_effects
                | operator.model.delete_effects
            )
        }
        if not operator.model.add_effects and not operator.model.delete_effects:
            raise ValueError("typed operator requires at least one add/delete effect")
        if not self.registry.all_promoted(predicate_ids):
            raise ValueError("typed operator contains non-promoted predicates")
        if operator.model.verified_effect_contexts < self.registry.effect_verify_k:
            raise ValueError("typed operator effects are not sufficiently verified")
        self.ops[operator.key] = operator
        self.goal_patterns = {
            pattern
            for candidate in self.ops.values()
            if candidate.terminal
            for pattern in candidate.model.add_effects
        }

    def remove(self, operator_id: str) -> None:
        self.ops.pop(operator_id, None)

    @staticmethod
    def _patterns_may_unify(first: FactPattern, second: FactPattern) -> bool:
        if len(first.terms) != len(second.terms):
            return False
        if first.argument_types and second.argument_types:
            if first.argument_types != second.argument_types:
                return False
        for a, b in zip(first.terms, second.terms):
            if not a.startswith("?") and not b.startswith("?") and a != b:
                return False
        return True

    def edges(self) -> list[tuple[str, str]]:
        out = []
        for source in sorted(self.ops.values(), key=lambda op: op.key):
            for target in sorted(self.ops.values(), key=lambda op: op.key):
                if source.key == target.key:
                    continue
                compatible = any(
                    self.registry.entails(effect.predicate_id, precondition.predicate_id)
                    and self._patterns_may_unify(effect, precondition)
                    for effect in source.model.add_effects
                    for precondition in (
                        target.model.required_preconditions | target.model.optional_context
                    )
                )
                if compatible:
                    out.append((source.key, target.key))
        return out

    def applicable(
        self,
        operator: RelationalOperator,
        state: frozenset[PredicateFact],
    ) -> list[dict[str, EntityRef]]:
        required_bindings = satisfying_bindings(
            operator.model.required_preconditions, state, self.registry
        )
        candidates = list(required_bindings)
        # Optional context never blocks applicability, but may ground typed
        # parameters. This keeps co-occurrence out of the required set while
        # still preserving entity identity in forward planning.
        for pattern in sorted(operator.model.optional_context):
            expanded = list(candidates)
            for bindings in candidates:
                for fact in state:
                    matched = _match_pattern(pattern, fact, bindings, self.registry)
                    if matched is not None and matched not in expanded:
                        expanded.append(matched)
            candidates = expanded
        return candidates

    def apply(
        self,
        operator: RelationalOperator,
        state: frozenset[PredicateFact],
        bindings: dict[str, EntityRef],
    ) -> frozenset[PredicateFact] | None:
        add = {
            fact for pattern in operator.model.add_effects
            if (fact := instantiate(pattern, bindings)) is not None
        }
        delete = {
            fact for pattern in operator.model.delete_effects
            if (fact := instantiate(pattern, bindings)) is not None
        }
        if len(add) != len(operator.model.add_effects) or len(delete) != len(operator.model.delete_effects):
            return None
        return frozenset((set(state) - delete) | add)

    def goal_reached(self, state: frozenset[PredicateFact], goal: FactPattern) -> bool:
        return bool(satisfying_bindings(frozenset({goal}), state, self.registry))

    def plan(
        self,
        initial: frozenset[PredicateFact],
        goal: FactPattern,
        *,
        max_states: int = 10000,
    ) -> list[TypedPlanStep] | None:
        if self.goal_reached(initial, goal):
            return []
        queue = deque([(initial, [])])
        seen = {initial}
        while queue and len(seen) <= max_states:
            state, path = queue.popleft()
            for operator in sorted(self.ops.values(), key=lambda op: op.key):
                for bindings in self.applicable(operator, state):
                    next_state = self.apply(operator, state, bindings)
                    if next_state is None or next_state == state:
                        continue
                    step = TypedPlanStep(
                        operator.key,
                        tuple(sorted(bindings.items(), key=lambda item: item[0])),
                    )
                    next_path = path + [step]
                    if self.goal_reached(next_state, goal):
                        return next_path
                    if next_state not in seen:
                        seen.add(next_state)
                        queue.append((next_state, next_path))
        return None

    def to_dict(self) -> dict:
        return {
            "operators": {
                key: operator.to_dict() for key, operator in sorted(self.ops.items())
            },
            "edges": self.edges(),
            "goal_patterns": [pattern.to_dict() for pattern in sorted(self.goal_patterns)],
            "registry_revision": self.registry.revision,
        }

    @classmethod
    def from_dict(
        cls, value: dict, registry: PredicateRegistry
    ) -> "RelationalOperatorGraph":
        graph = cls(registry)
        for raw in value.get("operators", {}).values():
            operator = RelationalOperator.from_dict(raw)
            graph.add(operator)
        return graph
