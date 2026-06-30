import json

import numpy as np

from hsge.llm import Embedder, LLM, HashingEmbedder
from hsge.predicate_ontology import (
    EntityRef,
    FactPattern,
    PredicateArgument,
    PredicateDefinition,
    PredicateEngine,
    PredicateFact,
    PredicateRegistry,
    PredicateRelation,
    TypedActionModel,
)
from hsge.relational_operators import RelationalOperator, RelationalOperatorGraph
from hsge.graph import HierarchicalGraph
from hsge.schema import SkillCard, Step
from hsge.webarena.runtime import RunMetrics, WebArenaExplorer


class ConstantEmbedder(Embedder):
    def encode(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), 4), dtype=np.float32) / 2


def _definition(name, *, arity=0, status="promoted"):
    arguments = (
        (PredicateArgument("item", "product"),) if arity else ()
    )
    return PredicateDefinition(
        predicate_id=f"pred:{name}",
        canonical_name=name,
        description=name.replace("_", " "),
        arguments=arguments,
        scope="session",
        persistence="persistent",
        status=status,
    )


def test_synonyms_merge_but_opposite_polarity_never_merges():
    registry = PredicateRegistry(ConstantEmbedder(), similarity_floor=0.0)
    selected = registry.add_definition(_definition("item_selected", arity=1))

    merged, disposition = registry.canonicalize(
        {
            "name": "product_chosen",
            "description": "the product is selected",
            "arguments": [{"name": "item", "type": "product"}],
            "scope": "session",
            "persistence": "persistent",
        },
        lambda _candidate, _existing: ("equivalent", 0.97),
    )
    assert disposition == "equivalent"
    assert merged.predicate_id == selected.predicate_id

    empty = registry.add_definition(_definition("cart_empty"))
    nonempty, disposition = registry.canonicalize(
        {
            "name": "cart_nonempty",
            "description": "the cart contains an item",
            "scope": "session",
            "persistence": "persistent",
        },
        lambda _candidate, _existing: ("equivalent", 0.99),
    )
    assert disposition == "created"
    assert nonempty.predicate_id != empty.predicate_id


def test_entailment_is_directional_and_roundtrips():
    registry = PredicateRegistry(HashingEmbedder())
    item_added = registry.add_definition(_definition("item_added", arity=1))
    nonempty = registry.add_definition(_definition("cart_nonempty"))
    registry.relations.append(PredicateRelation(
        item_added.predicate_id, nonempty.predicate_id, "implies", 0.94, True
    ))

    assert registry.entails(item_added.predicate_id, nonempty.predicate_id)
    assert not registry.entails(nonempty.predicate_id, item_added.predicate_id)

    restored = PredicateRegistry.from_dict(registry.to_dict(), HashingEmbedder())
    assert restored.entails(item_added.predicate_id, nonempty.predicate_id)
    assert restored.revision == registry.revision


def test_promotion_requires_unique_contexts_entities_detector_and_effect_replay():
    registry = PredicateRegistry(
        HashingEmbedder(), min_contexts=3, min_entities=2,
        min_precision=0.85, min_recall=0.75, effect_verify_k=2,
    )
    definition = registry.add_definition(_definition(
        "item_selected", arity=1, status="provisional"
    ))
    first = PredicateFact(definition.predicate_id, (EntityRef("product", "sku:a"),))
    second = PredicateFact(definition.predicate_id, (EntityRef("product", "sku:b"),))

    registry.record_evidence(
        definition.predicate_id, episode_id=1, facts=[first],
        effect_verified=True, held_out=False,
    )
    registry.record_evidence(
        definition.predicate_id, episode_id=2, facts=[second],
        effect_verified=True, held_out=True,
    )
    assert registry.definitions[definition.predicate_id].status != "promoted"
    registry.record_evidence(
        definition.predicate_id, episode_id=3, facts=[first],
        effect_verified=True, held_out=True,
    )
    assert registry.definitions[definition.predicate_id].status == "promoted"


class FactLLM(LLM):
    def __init__(self):
        self.fact_calls = 0

    def complete_json(self, system: str, prompt: str) -> dict:
        if system.startswith("Extract grounded"):
            self.fact_calls += 1
            predicate_id = json.loads(prompt)["predicates"][0]["predicate_id"]
            return {"facts": [{
                "predicate_id": predicate_id,
                "arguments": [],
                "evidence": "Cart",
                "confidence": 0.95,
            }]}
        return {}


def test_snapshot_cache_and_grounded_fact_validation():
    llm = FactLLM()
    registry = PredicateRegistry(HashingEmbedder())
    definition = registry.add_definition(_definition("cart_visible"))
    engine = PredicateEngine(registry, llm)

    first = engine.snapshot("https://shop.test/cart", "Cart")
    second = engine.snapshot("https://shop.test/cart", "Cart")
    assert first == second
    assert PredicateFact(definition.predicate_id) in first.facts
    assert llm.fact_calls == 1
    assert engine.metrics["cache_hits"] == 1

    invalid, _, _ = engine._validated_fact({
        "predicate_id": definition.predicate_id,
        "arguments": [],
        "evidence": "invented message",
    }, "https://shop.test/cart", "Cart")
    assert invalid is None
    assert engine.metrics["rejected_hallucinated_evidence"] == 1


class HallucinatingProposalLLM(LLM):
    def complete_json(self, system: str, _prompt: str) -> dict:
        if system.startswith("Induce minimal"):
            return {"predicates": [{
                "name": "secret_state",
                "description": "an unobserved state",
                "arguments": [],
                "scope": "page",
                "persistence": "persistent",
                "observations": [{
                    "step_index": 0,
                    "truth_before": False,
                    "truth_after": True,
                    "evidence_after": "text that is not on the page",
                    "argument_values": [],
                }],
            }]}
        return {"relation": "unrelated", "confidence": 1.0}


def test_hallucinated_proposal_is_rejected_before_registry_mutation():
    registry = PredicateRegistry(HashingEmbedder())
    engine = PredicateEngine(registry, HallucinatingProposalLLM())
    before = set(registry.definitions)
    accepted = engine.induce_episode(
        episode_id=1,
        task="change state",
        success=True,
        steps=[Step("click('1')", "https://shop.test", misc={"planning": {}})],
        obs_texts=["Button"],
        final_obs={"url": "https://shop.test/done", "axtree": "Done"},
    )
    assert accepted == []
    assert set(registry.definitions) == before


def _model(required=(), optional=(), add=(), delete=()):
    return TypedActionModel(
        parameters=(PredicateArgument("item", "product"),),
        required_preconditions=frozenset(required),
        optional_context=frozenset(optional),
        add_effects=frozenset(add),
        delete_effects=frozenset(delete),
        confidence=1.0,
        evidence_ids=("ep1", "ep2"),
        verified_effect_contexts=2,
    )


def test_typed_planner_preserves_entity_bindings_across_three_operators_and_deletes():
    registry = PredicateRegistry(HashingEmbedder(), effect_verify_k=2)
    definitions = {
        name: registry.add_definition(_definition(name, arity=arity))
        for name, arity in {
            "product_visible": 1,
            "product_open": 1,
            "item_in_cart": 1,
            "checkout_ready": 1,
        }.items()
    }
    pattern = lambda name: FactPattern(
        definitions[name].predicate_id, ("?item",), ("product",)
    )
    graph = RelationalOperatorGraph(registry)
    graph.add(RelationalOperator(
        "open product", _model(optional=[pattern("product_visible")], add=[pattern("product_open")]),
        "open_product",
    ))
    graph.add(RelationalOperator(
        "add product", _model(required=[pattern("product_open")], add=[pattern("item_in_cart")]),
        "add_to_cart",
    ))
    graph.add(RelationalOperator(
        "checkout", _model(required=[pattern("item_in_cart")], add=[pattern("checkout_ready")]),
        "checkout", terminal=True,
    ))
    item_a = EntityRef("product", "sku:a")
    initial = frozenset({PredicateFact(
        definitions["product_visible"].predicate_id, (item_a,)
    )})
    goal_a = FactPattern(
        definitions["checkout_ready"].predicate_id, ("sku:a",), ("product",)
    )
    plan = graph.plan(initial, goal_a)
    assert [step.operator_id for step in plan] == [
        "open_product", "add_to_cart", "checkout"
    ]
    assert all(dict(step.bindings)["?item"] == item_a for step in plan)

    goal_b = FactPattern(
        definitions["checkout_ready"].predicate_id, ("sku:b",), ("product",)
    )
    assert graph.plan(initial, goal_b) is None

    remove = RelationalOperator(
        "remove product",
        _model(required=[pattern("item_in_cart")], delete=[pattern("item_in_cart")]),
        "remove_from_cart",
    )
    graph.add(remove)
    in_cart = frozenset({PredicateFact(definitions["item_in_cart"].predicate_id, (item_a,))})
    bindings = graph.applicable(remove, in_cart)[0]
    assert graph.apply(remove, in_cart, bindings) == frozenset()

    restored = RelationalOperatorGraph.from_dict(graph.to_dict(), registry)
    assert [step.operator_id for step in restored.plan(initial, goal_a)] == [
        "open_product", "add_to_cart", "checkout"
    ]


def test_wrong_arity_type_and_entity_identity_do_not_form_edges():
    registry = PredicateRegistry(HashingEmbedder(), effect_verify_k=2)
    visible = registry.add_definition(_definition("visible", arity=1))
    opened = registry.add_definition(PredicateDefinition(
        predicate_id="pred:opened_order", canonical_name="opened_order",
        description="order opened",
        arguments=(PredicateArgument("order", "order"),),
        scope="session", persistence="persistent", status="promoted",
    ))
    product_effect = FactPattern(visible.predicate_id, ("?x",), ("product",))
    order_required = FactPattern(opened.predicate_id, ("?x",), ("order",))
    graph = RelationalOperatorGraph(registry)
    graph.add(RelationalOperator("show", _model(add=[product_effect]), "show"))
    graph.add(RelationalOperator("open", _model(required=[order_required], add=[order_required]), "open"))
    assert ("show", "open") not in graph.edges()


def test_typed_unreachable_falls_back_to_legacy_with_provenance():
    registry = PredicateRegistry(HashingEmbedder())
    registry.add_definition(_definition("done"))
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.terminal_goal = "done"
    explorer.goal_instruction = "Finish the flow."
    explorer.auto_terminal_goals = False
    explorer.predicate_registry = registry
    explorer.typed_opgraph = RelationalOperatorGraph(registry)
    explorer.predicate_engine = PredicateEngine(registry, None)
    explorer.metrics = RunMetrics()
    explorer.graph = HierarchicalGraph()
    card = SkillCard(
        name="finish_flow", description="finish", slots=[],
        action_template=["click('1')"], precondition="ready",
        success_predicate="done", cluster_id="1", verified=True,
        skill_id="legacy_finish", planning_preconditions={"ready"},
        planning_effects={"done"}, planning_ready=True,
    )
    explorer.graph.add_skill(card, init_states=[], effect_states=[])
    explorer.library = type("Library", (), {"all_skills": lambda self: [card]})()
    explorer._emit_event = lambda *_args, **_kwargs: None

    task = explorer._goal_task(
        {"ready"}, {"url": "https://example.test", "axtree": "Ready"}
    )
    assert task["planner_source"] == "legacy_fallback"
    assert task["chain"] == ["legacy_finish"]
    assert explorer.metrics.legacy_plan_fallbacks == 1


def test_legacy_run_imports_only_provisional_shadow_predicates(tmp_path):
    (tmp_path / "skills.json").write_text(json.dumps([{
        "planning_preconditions": ["ready"],
        "planning_effects": ["done"],
    }]), encoding="utf-8")
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.predicate_registry = PredicateRegistry(HashingEmbedder())
    imported = explorer._import_legacy_predicates(str(tmp_path))

    assert imported == 2
    assert {
        definition.source for definition in explorer.predicate_registry.definitions.values()
    } == {"legacy"}
    assert all(
        definition.status == "provisional"
        for definition in explorer.predicate_registry.definitions.values()
    )
