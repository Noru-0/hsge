import json

from hsge.abstraction import abstract_cluster
from hsge.env import PageState, WebEnv
from hsge.llm import HashingEmbedder, MockLLM
from hsge.library import SkillLibrary
from hsge.schema import ParamSlot, SkillCard, Step, SubTrajectory
from hsge.verification import verify_skill
from hsge.webarena.predicates import build_predicate_extractor
from hsge.webarena.verification_context import _build_browser_contexts


def _write_episode(root, index, transitions):
    episode = root / "episodes" / f"ep_{index:04d}"
    episode.mkdir(parents=True)
    (episode / "episode_meta.json").write_text(
        json.dumps({"outcome": {"success": True}}), encoding="utf-8"
    )
    records = []
    for transition in transitions:
        records.append({
            "parsed_action": transition.get("action", "click('1')"),
            "observation": {"url": transition["pre_url"]},
            "misc": {"planning": {
                "pre_url": transition["pre_url"],
                "post_url": transition["post_url"],
                "pre_predicates": transition.get("pre_predicates", []),
                "post_predicates": transition.get("post_predicates", []),
                "target_role": transition.get("target_role", "link"),
                "target_name": transition.get("target_name", "Target"),
                "target_fingerprint": transition.get(
                    "target_fingerprint", "link|target"
                ),
            }},
        })
    (episode / "episode.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_browser_contexts_use_effect_compatible_transitions_not_episode_start(tmp_path):
    root = "https://shop.test/"
    _write_episode(tmp_path, 0, [
        {
            "pre_url": root,
            "post_url": root + "electronics",
            "post_predicates": ["has_filter_or_sort", "results_shown"],
            "target_name": "Electronics",
            "target_fingerprint": "link|electronics",
        },
        {
            "pre_url": root,
            "post_url": root + "item/1",
            "post_predicates": ["view:detail"],
            "target_name": "Example item",
            "target_fingerprint": "link|example item",
        },
    ])
    _write_episode(tmp_path, 1, [{
        "pre_url": root,
        "post_url": root + "grocery",
        "post_predicates": ["has_filter_or_sort", "results_shown"],
        "target_name": "Grocery",
        "target_fingerprint": "link|grocery",
    }])
    card = SkillCard(
        name="activate_named_control",
        description="Activate a named control.",
        slots=[ParamSlot("control_selector", "selector")],
        action_template=["click({control_selector})"],
        precondition="control visible",
        success_predicate="collection visible",
        cluster_id="1",
        planning_effects={"has_filter_or_sort", "results_shown"},
    )

    contexts = _build_browser_contexts(str(tmp_path), lambda _url: None, skill=card)

    assert len(contexts) == 2
    assert {context.verification_target_name for context in contexts} == {
        "Electronics", "Grocery",
    }
    assert len({context.verification_context_id for context in contexts}) == 2
    assert {context.pages[context.start].url for context in contexts} == {root}


def test_verifier_keeps_distinct_transitions_with_the_same_start_url():
    contexts = []
    for identity in ("category-a", "category-b"):
        env = WebEnv(
            "site",
            {
                "start": PageState("https://shop.test/", ["next"], {"next": "done"}),
                "done": PageState("https://shop.test/category", [], {}),
            },
            start="start",
            goal_pages={"done"},
        )
        env.verification_context_id = identity
        contexts.append(env)
    card = SkillCard(
        name="activate_named_control",
        description="Activate a named control.",
        slots=[ParamSlot("control_selector", "selector")],
        action_template=["click({control_selector})"],
        precondition="control visible",
        success_predicate="control activated",
        cluster_id="2",
    )

    assert verify_skill(MockLLM(), card, contexts, k=2)
    assert card.stats.n_verify_success == 2


def test_semantic_transition_target_overrides_generic_llm_binding():
    class Browser:
        def reset(self):
            return {
                "url": "https://shop.test/",
                "axtree": "[1] link 'Example item'\n[2] link 'Electronics'\n",
            }

        def act(self, action):
            if action == "click('2')":
                return {
                    "url": "https://shop.test/electronics",
                    "axtree": (
                        "[10] combobox 'Sort By'\n"
                        "[11] link 'First result'\n[12] link 'Second result'\n"
                    ),
                }
            return {
                "url": "https://shop.test/item/1",
                "axtree": "[20] heading 'Product Details'\n",
            }

        def close(self):
            pass

    env = WebEnv(
        "site",
        {"start": PageState("https://shop.test/", [], {})},
        start="start",
        goal_pages={"done"},
    )
    env.browser_factory = lambda _url: Browser()
    env.verification_context_id = "electronics-transition"
    env.verification_target_role = "link"
    env.verification_target_name = "Electronics"
    env.verification_target_fingerprint = "link|electronics"
    card = SkillCard(
        name="activate_named_control",
        description="Activate a named control.",
        slots=[ParamSlot("control_selector", "selector")],
        action_template=["click({control_selector})"],
        precondition="control visible",
        success_predicate="collection visible",
        cluster_id="3",
        planning_effects={"has_filter_or_sort", "results_shown"},
    )

    assert verify_skill(
        MockLLM(), card, [env], k=1,
        predicate_extractor=build_predicate_extractor(["commerce"]),
    )


def test_cart_effects_override_an_overly_generic_llm_skill_name():
    members = [
        SubTrajectory(
            steps=[Step("click('7')", "https://shop.test/item")],
            subgoal="add item to cart",
            source_site="shop",
            planning_effects={"cart_nonempty", "on_cart"},
        )
        for _ in range(3)
    ]

    card = abstract_cluster(MockLLM(), 4, members)

    assert card is not None
    assert card.name == "activate_state_change_control"


def test_mature_cluster_splits_navigation_from_state_changes():
    library = SkillLibrary(
        MockLLM(), HashingEmbedder(), lambda: [],
        sim_threshold=-1.0, maturity=4, verify_k=1,
    )
    members = [
        SubTrajectory(
            steps=[Step("click('1')", "https://shop.test/")],
            subgoal="open a collection",
            source_site="shop",
            planning_effects={"has_filter_or_sort", "results_shown"},
        ),
        SubTrajectory(
            steps=[Step("click('2')", "https://shop.test/")],
            subgoal="open another collection",
            source_site="shop",
            planning_effects={"has_filter_or_sort", "results_shown"},
        ),
        SubTrajectory(
            steps=[Step("click('3')", "https://shop.test/item")],
            subgoal="add item to cart",
            source_site="shop",
            planning_effects={"cart_nonempty", "on_cart"},
        ),
        SubTrajectory(
            steps=[Step("click('4')", "https://shop.test/item")],
            subgoal="add another item to cart",
            source_site="shop",
            planning_effects={"cart_nonempty", "on_cart"},
        ),
    ]

    for member in members:
        library.observe(member)

    families = [
        {library._behavior_family(library.subtrajs[mid]) for mid in mids}
        for mids in library.cluster_to_members.values()
    ]
    assert len(families) == 2
    assert all(len(family) == 1 for family in families)
    assert {next(iter(family)) for family in families} == {
        "open_collection", "state_change",
    }
