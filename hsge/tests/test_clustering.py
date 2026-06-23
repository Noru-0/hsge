"""Tests for the core online clustering and the discovery pipeline.

Run:  python -m pytest tests/ -q     (or)     python tests/test_clustering.py
"""
import numpy as np

from hsge import (
    Discovery, HashingEmbedder, HierarchicalGraph, MockLLM, OnlineClusterer,
    SkillLibrary, Step, demo_sites,
)
from hsge.env import WebEnv, PageState
from hsge.schema import ParamSlot, SkillCard, SubTrajectory
from hsge.abstraction import abstract_cluster, validate_skill_card
from hsge.segmentation import segment_trajectory
from hsge.verification import verify_skill


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_similar_vectors_share_cluster():
    c = OnlineClusterer(sim_threshold=0.6)
    a = _unit([1, 0, 0])
    b = _unit([0.95, 0.05, 0])      # very close to a
    assert c.partial_fit(a, "a") == c.partial_fit(b, "b")
    assert len(c) == 1


def test_dissimilar_vectors_spawn_clusters():
    c = OnlineClusterer(sim_threshold=0.6)
    c.partial_fit(_unit([1, 0, 0]), "a")
    c.partial_fit(_unit([0, 1, 0]), "b")   # orthogonal -> new cluster
    assert len(c) == 2


def test_clusterer_grows_online():
    c = OnlineClusterer(sim_threshold=0.8)
    rng = np.random.default_rng(0)
    for i in range(20):
        c.partial_fit(_unit(rng.normal(size=8)), f"x{i}")
    # nonparametric: cluster count is data-driven, strictly between 1 and 20
    assert 1 < len(c) <= 20


def test_pipeline_admits_two_verified_skills():
    IDS = {
        "shop": dict(user="email", pwd="pwd", submit="signin", box="q", go="search_btn"),
        "forum": dict(user="username", pwd="password", submit="login_btn", box="searchbox", go="go_btn"),
        "gitlab": dict(user="login_field", pwd="pass_field", submit="submit", box="search_input", go="find"),
    }
    sites = demo_sites()
    train = ["shop", "forum", "gitlab"]

    def traj(s):
        e = IDS[s]; lu = f"/{s}/login"; hu = f"/{s}/home"
        return [Step(f"type [{e['user']}] a", lu), Step(f"type [{e['pwd']}] b", lu),
                Step(f"click [{e['submit']}]", lu), Step(f"type [{e['box']}] q", hu),
                Step(f"click [{e['go']}]", hu)]

    def vctx():
        out = []
        for s in train:
            out += [sites[s]["login"], sites[s]["home"]]
        return out

    lib = SkillLibrary(MockLLM(), HashingEmbedder(), vctx, maturity=3, verify_k=2)
    g = HierarchicalGraph()
    d = Discovery(lib, g)
    for s in train:
        d.on_trajectory(traj(s), s, "task", ["log in with credentials", "search the catalog"])

    names = {c.name for c in lib.all_skills()}
    assert {"fill_visible_field", "submit_search_query"} <= names
    assert all(c.verified for c in lib.all_skills())


def test_verification_rejects_ungroundable_skill():
    env = WebEnv(
        "empty",
        {"start": PageState("/empty", affordances=[], goto={})},
        start="start",
        goal_pages={"done"},
    )
    card = SkillCard(
        name="Click Missing",
        description="Click a missing control.",
        slots=[ParamSlot("target", "selector")],
        action_template=["click({target})"],
        precondition="target is visible",
        success_predicate="done",
        cluster_id="c0",
    )

    assert not verify_skill(MockLLM(), card, [env], k=1)
    assert not card.verified
    assert card.stats.n_verify_attempts == 1
    assert card.stats.n_verify_success == 0


def test_action_kind_parses_canonical_hsge_actions():
    assert Step("click('101')", "/").action_kind() == "click"
    assert Step("fill('102','query')", "/").action_kind() == "fill"
    assert Step("click [submit]", "/").action_kind() == "click"


def test_segmentation_adds_reusable_action_level_segments():
    steps = [
        Step("fill('102','ginger')", "/search", obs_summary="Filled Search."),
        Step("click('103')", "/search", obs_summary="Clicked Search."),
        Step("click('201')", "/detail", obs_summary="Opened visible item."),
    ]

    subs = segment_trajectory(MockLLM(), steps, "site", "Search for ginger and open product detail")
    subgoals = {s.subgoal for s in subs}

    assert "submit search query" in subgoals
    assert "open visible item" in subgoals


class _OverfitSkillLLM(MockLLM):
    def complete_json(self, system, prompt):
        if "ABSTRACT" in system:
            return {
                "name": "Locate Gingerbread House Kit",
                "description": "Find the Pre-baked Gingerbread House Kit on the webpage.",
                "slots": [{"name": "product_name", "slot_type": "value"}],
                "action_template": "click('{product_name}')",
                "precondition": "The webpage is loaded.",
                "success_predicate": (
                    "Locate the 'Pre-baked Gingerbread House Kit Value Pack, "
                    "17 oz., Pack of 2, Total 34 oz.' on the webpage. completed"
                ),
            }
        return super().complete_json(system, prompt)


def test_abstraction_rejects_long_entity_literals():
    member = SubTrajectory(
        steps=[Step("click [101]", "/product")],
        subgoal="Locate product detail",
        source_site="site",
        source_task="task",
    )

    assert abstract_cluster(_OverfitSkillLLM(), 1, [member, member, member]) is None


class _OverfitCanonicalSkillLLM(MockLLM):
    def complete_json(self, system, prompt):
        if "ABSTRACT" in system:
            return {
                "name": "LocateGingerbreadProduct",
                "description": "Open the product page for the Pre-baked Gingerbread House Kit.",
                "slots": [{"name": "item_selector", "slot_type": "selector"}],
                "action_template": ["click({item_selector})"],
                "precondition": "The product link is visible.",
                "success_predicate": "product page loaded",
            }
        return super().complete_json(system, prompt)


def test_abstraction_fallback_accepts_canonical_overfit_skill():
    member = SubTrajectory(
        steps=[Step("click('101')", "/product")],
        subgoal="open product detail",
        source_site="site",
        source_task="Open product detail",
    )

    card = abstract_cluster(_OverfitCanonicalSkillLLM(), 7, [member, member, member])

    assert card is not None
    assert card.name == "open_visible_item"
    assert card.stats.bootstrap_verified


class _FixedSkillLLM(MockLLM):
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, system, prompt):
        if "ABSTRACT" in system:
            return self.payload
        return super().complete_json(system, prompt)


def _member(subgoal="open visible item", task="Open item"):
    return SubTrajectory(
        steps=[Step("click('101')", "/detail", obs_summary="Clicked a visible link.")],
        subgoal=subgoal,
        source_site="site",
        source_task=task,
    )


def test_abstraction_rejects_value_slot_click_target():
    out = {
        "name": "ClickProductLink",
        "description": "Clicks on a specified product link.",
        "slots": [{"name": "product_name", "slot_type": "value"}],
        "action_template": ["click('{product_name}')"],
        "precondition": "The product link is visible.",
        "success_predicate": "product page loaded",
    }

    assert abstract_cluster(_FixedSkillLLM(out), 2, [_member(), _member(), _member()]) is None


def test_abstraction_rejects_natural_language_template():
    out = {
        "name": "save_visible_item",
        "description": "Save a visible item for later.",
        "slots": [{"name": "item_name", "slot_type": "value"}],
        "action_template": ["Add {item_name} to your wish list."],
        "precondition": "A save control is visible.",
        "success_predicate": "item saved",
    }

    assert abstract_cluster(_FixedSkillLLM(out), 3, [_member(), _member(), _member()]) is None


def test_abstraction_accepts_canonical_open_visible_item():
    out = {
        "name": "open_visible_item",
        "description": "Open a visible item or record.",
        "slots": [{"name": "item_selector", "slot_type": "selector"}],
        "action_template": ["click({item_selector})"],
        "precondition": "A target item is visible.",
        "success_predicate": "item detail is visible",
    }

    card = abstract_cluster(_FixedSkillLLM(out), 4, [_member(), _member(), _member()])

    assert card is not None
    assert card.name == "open_visible_item"
    assert not validate_skill_card(card)


def test_abstraction_accepts_canonical_submit_search_query():
    out = {
        "name": "submit_search_query",
        "description": "Submit a query through a visible search field.",
        "slots": [
            {"name": "search_selector", "slot_type": "selector"},
            {"name": "query_value", "slot_type": "value"},
        ],
        "action_template": ["fill({search_selector}, {query_value})", "press('Enter')"],
        "precondition": "A search field is visible.",
        "success_predicate": "query results are visible",
    }

    card = abstract_cluster(_FixedSkillLLM(out), 5, [_member("search visible records")] * 3)

    assert card is not None
    assert card.name == "submit_search_query"
    assert not validate_skill_card(card)


def test_duplicate_normalized_skill_is_detected():
    lib = SkillLibrary(MockLLM(), HashingEmbedder(), lambda: [], maturity=3, verify_k=1)
    existing = SkillCard(
        name="open_visible_item",
        description="Open a visible item or record.",
        slots=[ParamSlot("item_selector", "selector")],
        action_template=["click({item_selector})"],
        precondition="item visible",
        success_predicate="detail visible",
        cluster_id="0",
    )
    candidate = SkillCard(
        name="open_visible_item",
        description="Open another visible item or record.",
        slots=[ParamSlot("record_selector", "selector")],
        action_template=["click({record_selector})"],
        precondition="record visible",
        success_predicate="detail visible",
        cluster_id="1",
    )
    lib.skills[0] = existing

    assert lib._duplicate_skill(candidate) is existing


def test_domain_examples_share_open_visible_item_abstraction():
    out = {
        "name": "ClickProductLink",
        "description": "Open a visible item or record.",
        "slots": [{"name": "item_selector", "slot_type": "selector"}],
        "action_template": ["click({item_selector})"],
        "precondition": "A target item is visible.",
        "success_predicate": "item detail is visible",
    }
    members = [
        _member("open issue detail", "Open issue #42"),
        _member("open article detail", "Open API reference article"),
        _member("open item detail", "Open listed item"),
    ]

    card = abstract_cluster(_FixedSkillLLM(out), 6, members)

    assert card is not None
    assert card.name == "open_visible_item"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
