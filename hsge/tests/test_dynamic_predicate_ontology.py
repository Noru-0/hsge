import json
from types import SimpleNamespace

import numpy as np

from hsge.llm import Embedder, LLM, HashingEmbedder, MockLLM
from hsge.abstraction import _typed_planning_evidence
from hsge.library import SkillLibrary
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
    KERNEL_CURRENT_ROUTE,
    route_fact,
)
from hsge.relational_operators import RelationalOperator, RelationalOperatorGraph
from hsge.graph import HierarchicalGraph
from hsge.schema import SkillCard, Step, SubTrajectory
from hsge.segmentation import _attach_planning_evidence
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


def test_route_kernel_backfills_reddit_navigation_and_aggregates_effects():
    subs = []
    transitions = [
        ("https://reddit.test/", "https://reddit.test/"),
        ("https://reddit.test/", "https://reddit.test/forums"),
        ("https://reddit.test/", "https://reddit.test/wiki"),
    ]
    for episode_id, (before_url, after_url) in enumerate(transitions, 1):
        step = Step("click('1')", before_url, misc={"planning": {
            "pre_url": before_url,
            "post_url": after_url,
            "pre_predicates": [],
            "post_predicates": [],
        }})
        sub = SubTrajectory(
            [step], "open visible item", "reddit",
            source_episode_id=episode_id,
        )
        _attach_planning_evidence(
            [sub], [step], ["[1] link 'target'"],
            {"url": after_url, "axtree": "target page"},
        )
        subs.append(sub)

    model = _typed_planning_evidence(subs)
    assert {pattern.predicate_id for pattern in model.add_effects} == {
        KERNEL_CURRENT_ROUTE
    }
    assert {pattern.predicate_id for pattern in model.delete_effects} == {
        KERNEL_CURRENT_ROUTE
    }
    assert model.verified_effect_contexts == 2


class WrappedEvidenceLLM(LLM):
    def complete_json(self, system: str, _prompt: str) -> dict:
        if system.startswith("Induce minimal"):
            return {"predicates": [{
                "name": "filter_menu_open",
                "description": "the filter menu is expanded",
                "arguments": [{"name": "filter", "type": "string"}],
                "scope": "page",
                "persistence": "persistent",
                "kind": "state",
                "observations": [{
                    "step_index": 0,
                    "truth_before": False,
                    "truth_after": True,
                    "evidence_before": "Button 'Filter on: Featured' has expanded=False",
                    "evidence_after": "Button 'Filter on: Featured' has expanded=True",
                    "argument_values": ["Featured"],
                }],
            }]}
        return {"relation": "unrelated", "confidence": 1.0}


def test_wrapped_literal_evidence_is_grounded_without_accepting_paraphrases():
    registry = PredicateRegistry(HashingEmbedder())
    engine = PredicateEngine(registry, WrappedEvidenceLLM())
    accepted = engine.induce_episode(
        episode_id=1,
        task="open filter",
        success=True,
        steps=[Step("click('122')", "https://reddit.test", misc={"planning": {
            "pre_url": "https://reddit.test",
            "post_url": "https://reddit.test",
        }})],
        obs_texts=["[122] button 'Filter on: Featured' expanded=false"],
        final_obs={
            "url": "https://reddit.test",
            "axtree": "[122] button 'Filter on: Featured' expanded=true",
        },
    )
    assert len(accepted) == 1
    predicate_id = accepted[0]["predicate_id"]
    assert registry.stats[predicate_id].effect_verifications == 1
    assert PredicateEngine._observation_evidence_valid({
        "truth_before": False,
        "truth_after": True,
        "evidence_after_refs": ["s0_after_l0"],
    }, {
        "before": {"url": "", "axtree": "", "evidence_lines": []},
        "after": {
            "url": "https://reddit.test",
            "axtree": "menu",
            "evidence_lines": [{"id": "s0_after_l0", "text": "menu"}],
        },
    })


def test_effectful_candidate_upgrades_execution_only_skill(monkeypatch):
    route_before = FactPattern(
        KERNEL_CURRENT_ROUTE, ("?route_0",), ("route",)
    )
    route_after = FactPattern(
        KERNEL_CURRENT_ROUTE, ("?route_1",), ("route",)
    )
    model = TypedActionModel(
        parameters=(
            PredicateArgument("route_0", "route"),
            PredicateArgument("route_1", "route"),
        ),
        optional_context=frozenset({route_before}),
        add_effects=frozenset({route_after}),
        delete_effects=frozenset({route_before}),
        evidence_ids=("ep1", "ep2"),
        verified_effect_contexts=2,
    )
    old = SkillCard(
        name="open_visible_item", description="old", slots=[],
        action_template=["click('1')"], precondition="visible",
        success_predicate="opened", cluster_id="99", verified=True,
        skill_id="stable_skill",
    )
    candidate = SkillCard(
        name="open_visible_item", description="upgraded", slots=[],
        action_template=["click('1')"], precondition="visible",
        success_predicate="opened", cluster_id="0",
        typed_action_model=model,
    )
    library = SkillLibrary(
        MockLLM(), HashingEmbedder(), lambda: [], maturity=3, verify_k=0
    )
    library.skills[99] = old
    members = []
    for index in range(3):
        sub = SubTrajectory(
            [Step("click('1')", "https://reddit.test")],
            "open visible item", "reddit", sub_id=f"member_{index}",
            typed_action_model=model,
        )
        library.subtrajs[sub.sub_id] = sub
        members.append(sub.sub_id)
    library.cluster_to_members[0] = members
    monkeypatch.setattr("hsge.library.abstract_cluster", lambda *_args: candidate)

    admitted = library._try_admit(0)
    assert admitted == "stable_skill"
    assert 99 not in library.skills
    assert library.skills[0].typed_action_model.add_effects == frozenset({route_after})
    assert getattr(library.skills[0], "_upgraded_existing") is True


def test_route_operator_can_plan_existential_and_concrete_destination():
    registry = PredicateRegistry(HashingEmbedder(), effect_verify_k=2)
    engine = PredicateEngine(registry, None)
    before = FactPattern(KERNEL_CURRENT_ROUTE, ("?from",), ("route",))
    after = FactPattern(KERNEL_CURRENT_ROUTE, ("?to",), ("route",))
    model = TypedActionModel(
        optional_context=frozenset({before}),
        add_effects=frozenset({after}),
        delete_effects=frozenset({before}),
        evidence_ids=("ep1", "ep2"),
        verified_effect_contexts=2,
    )
    graph = RelationalOperatorGraph(registry)
    graph.add(RelationalOperator("open", model, "open"))
    initial = frozenset({route_fact("https://reddit.test/")})

    existential = graph.plan(
        initial, FactPattern(KERNEL_CURRENT_ROUTE, ("?destination",), ("route",)),
        require_action=True,
    )
    concrete = graph.plan(
        initial, FactPattern(KERNEL_CURRENT_ROUTE, ("route:/comments",), ("route",))
    )
    assert [step.operator_id for step in existential] == ["open"]
    assert [step.operator_id for step in concrete] == ["open"]


def test_episode_replay_preserves_transition_metadata_for_route_migration(tmp_path):
    episode = tmp_path / "episodes" / "ep_0000"
    (episode / "page_state").mkdir(parents=True)
    (episode / "page_state" / "step.txt").write_text("home", encoding="utf-8")
    (episode / "page_state" / "final.txt").write_text("forums", encoding="utf-8")
    (episode / "episode_meta.json").write_text(json.dumps({
        "goal": "open forums",
        "outcome": {"success": True},
        "metadata": {"tags": ["LOCAL"], "task_origin": "local"},
        "final_state": {
            "url": "https://reddit.test/forums",
            "axtree_txt": {"path": "page_state/final.txt"},
        },
    }), encoding="utf-8")
    (episode / "episode.jsonl").write_text(json.dumps({
        "parsed_action": "click('1')",
        "thought": "open forums",
        "observation": {
            "url": "https://reddit.test/",
            "axtree_txt": {"path": "page_state/step.txt"},
        },
        "misc": {"planning": {
            "pre_url": "https://reddit.test/",
            "post_url": "https://reddit.test/forums",
            "pre_predicates": [],
            "post_predicates": [],
        }},
    }) + "\n", encoding="utf-8")

    captured = []
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.out_dir = str(tmp_path)
    explorer._full_state_restored = False
    explorer._discovered_urls = {}
    explorer.discovery = SimpleNamespace(
        on_trajectory=lambda *args, **kwargs: captured.append((args, kwargs))
    )
    explorer.library = SimpleNamespace(all_skills=lambda: [])
    explorer.graph = HierarchicalGraph()
    explorer.typed_opgraph = SimpleNamespace(ops={})

    explorer._replay_episodes()
    steps = captured[0][0][0]
    assert steps[0].url == "https://reddit.test/"
    assert steps[0].misc["planning"]["post_url"] == "https://reddit.test/forums"
    assert captured[0][1]["final_obs"]["axtree"] == "forums"
