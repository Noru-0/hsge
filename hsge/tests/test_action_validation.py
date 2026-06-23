from hsge.webarena.action_validation import (
    answer_has_evidence,
    repair_thought,
    task_family,
    validate_hsge_action,
)
from hsge.webarena.agents import PageExplorer, Solver
from hsge.webarena.runtime import (
    WebArenaExplorer,
    _name_from_goal,
    desired_skill_family_for_task,
    skill_family,
)
from hsge.schema import Step


AXTREE = """
[101] button 'Add to Cart'
[102] textbox 'Search'
[103] StaticText 'Tweezers For Succulents Duo'
[104] link 'Reviews'
"""


def test_validate_canonical_actions():
    assert validate_hsge_action("click('101')", AXTREE).ok
    assert validate_hsge_action("fill('102','laptop')", AXTREE).ok
    assert validate_hsge_action("scroll('down')", AXTREE).ok
    assert validate_hsge_action("send_msg_to_user('The price is $12.99')", AXTREE).ok
    assert validate_hsge_action("goto('http://example.com')", AXTREE).ok
    assert not validate_hsge_action(
        "goto('http://example.com')", AXTREE, allow_goto=False
    ).ok


def test_reject_invalid_action_and_hallucinated_bid():
    assert not validate_hsge_action("select_option('102','Blue')", AXTREE).ok
    assert not validate_hsge_action("functions.GatherProductInfo('x')", AXTREE).ok
    assert not validate_hsge_action("click('Tweezers For Succulents Duo')", AXTREE).ok
    assert not validate_hsge_action("click('999')", AXTREE).ok
    assert not validate_hsge_action("click('103')", AXTREE).ok
    assert not validate_hsge_action(
        "click('105')",
        AXTREE + "\n[105] button 'Submit', disabled=True",
    ).ok


def test_repair_thought_mentions_action_and_target():
    thought, repaired = repair_thought(
        "I need to add the item to the cart.",
        "click('101')",
        AXTREE,
    )
    assert repaired
    assert "click" in thought.lower()
    assert "[101]" in thought
    assert "Add to Cart" in thought
    assert "I need to" in thought
    assert "The next action is to" in thought
    assert "Evidence:" in thought


def test_answer_evidence_gate_for_review_tasks():
    assert not answer_has_evidence(
        "Who complained about this product in the reviews?",
        "No reviewers complained.",
        [AXTREE],
        ["click('101')"],
    )
    assert answer_has_evidence(
        "Who complained about this product in the reviews?",
        "Alice complained about battery life.",
        [AXTREE + "\n[200] StaticText 'Alice complained about battery life'"],
        ["click('104')"],
    )


class _TaskLLM:
    def __init__(self, tasks):
        self.tasks = tasks

    def complete_json(self, _sys, _prompt):
        return {"tasks": self.tasks}


def test_page_explorer_filters_ungrounded_action_chain_tasks():
    obs = {
        "url": "http://example.test",
        "axtree": "\n".join([
            "[101] link 'V8 +Energy, Healthy Energy Drink'",
            "[102] textbox 'Search'",
            "[103] link 'Reviews'",
        ]),
    }
    explorer = PageExplorer(_TaskLLM([
        "Search for 'Energy Drink' -> Select product 'V8 +Energy' -> Add to cart",
        "Open wish list -> Add item 'Pre-baked Gingerbread House Kit' -> View item details",
        "Read visible review information and answer one detail.",
        "Proceed to checkout with the selected product.",
    ]), max_tasks=20)

    tasks = explorer.propose(obs)

    assert "Read visible review information and answer one detail." in tasks
    assert all("->" not in task for task in tasks)
    assert all("Pre-baked Gingerbread" not in task for task in tasks)
    assert all("checkout" not in task.lower() for task in tasks)


def test_page_explorer_allows_grounded_domain_specific_tasks():
    obs = {
        "url": "http://example.test",
        "axtree": "\n".join([
            "[101] link 'V8 +Energy, Healthy Energy Drink'",
            "[102] button 'Add to Cart'",
            "[103] link 'My Orders'",
            "[104] link 'Add to Wish List'",
        ]),
    }
    explorer = PageExplorer(_TaskLLM([
        "Add the visible item to the cart.",
        "Open the visible My Orders record-status page.",
        "Add the visible item to the wish list.",
    ]), max_tasks=20)

    tasks = explorer.propose(obs)

    assert "Add the visible item to the cart." in tasks
    assert "Open the visible My Orders record-status page." in tasks
    assert "Add the visible item to the wish list." in tasks


def test_page_explorer_risky_controls_are_domain_neutral():
    obs = {
        "url": "http://example.test/issues",
        "axtree": "\n".join([
            "[201] textbox 'Search issues'",
            "[202] link 'Open issue #42'",
            "[203] StaticText 'Status: pending review'",
        ]),
    }
    explorer = PageExplorer(_TaskLLM([
        "Publish a reply to issue #42.",
        "Delete issue #42.",
        "Read the visible status for issue #42.",
    ]), max_tasks=20)

    tasks = explorer.propose(obs)

    assert "Read the visible status for issue #42." in tasks
    assert all("publish" not in task.lower() for task in tasks)
    assert all("delete" not in task.lower() for task in tasks)


def test_page_explorer_hover_seed_has_report_stop_condition():
    obs = {
        "url": "http://example.test",
        "axtree": "[301] menuitem 'More', hasPopup='menu'",
    }
    tasks = PageExplorer(_TaskLLM([]), max_tasks=20).propose(obs)

    hover_tasks = [task for task in tasks if task.lower().startswith("hover over")]
    assert hover_tasks
    assert "report one submenu option" in hover_tasks[0]


def test_page_explorer_seeds_only_visible_affordances():
    obs = {
        "url": "http://example.test/article",
        "axtree": "\n".join([
            "[401] link 'Article title'",
            "StaticText 'Status: published on 2026-06-22'",
        ]),
    }
    tasks = PageExplorer(_TaskLLM([
        "Open a communication form and identify its required fields.",
        "Use a visible sort or filter control to narrow the current list.",
        "Read the visible status shown on this page.",
    ]), max_tasks=20).propose(obs)

    assert "Read the visible status shown on this page." in tasks
    assert all("communication form" not in task.lower() for task in tasks)
    assert all("sort or filter" not in task.lower() for task in tasks)
    assert any("numeric or dated" in task.lower() for task in tasks)


def test_page_explorer_adds_deep_progression_task_from_visible_control():
    obs = {
        "url": "http://example.test/flow",
        "axtree": "\n".join([
            "[501] button 'Continue to payment'",
            "[502] textbox 'Search'",
        ]),
    }
    tasks = PageExplorer(_TaskLLM([]), max_tasks=20).propose(obs)

    assert any("Continue to payment" in task for task in tasks)
    assert any("next required step or confirmation" in task for task in tasks)


def test_search_control_does_not_create_progression_seed():
    obs = {
        "url": "http://example.test",
        "axtree": "\n".join([
            "[501] button '\\ue615 Search'",
            "[502] textbox 'Search'",
        ]),
    }
    tasks = PageExplorer(_TaskLLM([]), max_tasks=20).propose(obs)

    assert not any("progression control" in task for task in tasks)


def test_checkout_seed_respects_safe_final_order_policy():
    obs = {
        "url": "http://example.test/checkout",
        "axtree": "\n".join([
            "[601] button 'Place Order'",
            "[602] StaticText 'Order Summary'",
        ]),
    }
    tasks = PageExplorer(_TaskLLM([]), max_tasks=20).propose(obs)

    assert any("final order control" in task for task in tasks)
    assert not any(task.startswith("Use the visible 'Place Order'") for task in tasks)


def test_page_explorer_seed_tasks_have_concrete_report_targets():
    obs = {
        "url": "http://example.test/list",
        "axtree": "\n".join([
            "[601] link '12 Reviews'",
            "[602] combobox 'Sort By'",
            "[603] link 'My Account'",
        ]),
    }
    tasks = PageExplorer(_TaskLLM([]), max_tasks=20).propose(obs)

    assert "Report the visible feedback count shown by '12 Reviews'." in tasks
    assert "Open the visible 'Sort By' sort or filter control and report one available option." in tasks
    assert "Open the visible 'My Account' account or settings control and report one visible option." in tasks


def test_task_family_uses_generic_state_change_labels():
    assert task_family("Save the visible settings form") == "state_change"
    assert task_family("Delete the selected issue") == "destructive_change"
    assert task_family("Open order history and report the status") == "records_status"
    assert task_family("Add the item to your wish list") == "state_change"
    assert task_family("Click Proceed to Checkout") == "state_change"
    assert task_family("View recent orders") == "records_status"


def test_node_task_records_expose_task_success_rate(tmp_path):
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.out_dir = str(tmp_path)

    explorer._save_node_info(
        node_num=1,
        url="http://example.test",
        depth=0,
        children=[],
        visited=True,
        total_trajs=1,
        successful_trajs=1,
        selected_child_count=0,
        frontier_score=0.0,
        frontier_breakdown={},
        lookahead_candidates=[],
        tasks=[
            {"goal": "Search for Alpha", "status": "solved", "episode_id": 0},
            {"goal": "Add the visible item to the cart.", "status": "failed", "episode_id": 1},
            {"goal": "Open stale page", "status": "skipped", "episode_id": None},
            {"goal": "Read record", "status": "error", "episode_id": None},
        ],
    )

    import json
    info = json.load(open(tmp_path / "nodes" / "node_1" / "node_info.json"))
    assert info["success_rate"] == 1.0
    assert info["node_success_rate"] == 1.0
    assert info["tasks_attempted"] == 3
    assert info["tasks_solved"] == 1
    assert info["tasks_failed"] == 1
    assert info["tasks_error"] == 1
    assert info["tasks_skipped"] == 1
    assert info["task_success_rate"] == 0.333333


def test_prefix_replay_rejects_stale_action_and_stateful_direct_goto():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer._log_file = None
    target = "http://example.test/cart"
    explorer._discovered_urls = {
        target: {
            "source_url": "http://example.test",
            "prefix_steps": [Step("click('101')", "http://example.test", "I need to add the item to cart.")],
        }
    }

    class Browser:
        def __init__(self):
            self.url = "http://example.test"
        def act(self, action):
            if action.startswith("goto("):
                self.url = "http://example.test"
                return self.observation()
            raise AssertionError("stale action should not execute")
        def observation(self):
            return {"url": self.url, "axtree": "[202] button 'Different Control'"}

    assert explorer._navigate_via_prefix(Browser(), target) is None
    assert explorer._last_prefix_replay_status["reason"].startswith("stale_action")
    assert explorer._last_prefix_replay_status["stateful"] is True


def test_skill_diversity_family_mapping_is_generic():
    assert skill_family("submit_search_query") == "search_submission"
    assert skill_family("click_visible_detail") == "open_visible_item"
    assert skill_family("inspect_feedback_indicator") == "inspect_feedback"
    assert desired_skill_family_for_task("Add the visible item to the cart.") == "activate_state_change"
    assert desired_skill_family_for_task("Open issue #42 detail") == "open_visible_item"


def test_operator_names_are_generic_for_domain_specific_tasks():
    assert _name_from_goal("Add 'V8 +Energy' to your cart") == "activate_state_change_control"
    assert _name_from_goal("Click Proceed to Checkout") == "advance_transaction_flow"
    assert _name_from_goal("Enter a product name in the Search textbox") == "submit_search_query"


def test_terminal_success_gate_requires_grounded_search_and_state_change():
    obs = {"url": "http://example.test/search", "axtree": "[1] StaticText 'No records here'"}
    assert not Solver._terminal_success_gate(
        "Search for 'alpha beta'",
        "Search for alpha beta completed successfully.",
        obs,
        ["[1] StaticText 'No records here'"],
        ["fill('10','alpha beta')", "click('11')"],
    )
    assert Solver._terminal_success_gate(
        "Search for 'alpha beta'",
        "The alpha beta record is visible.",
        {"url": "http://example.test/search?q=alpha+beta", "axtree": "[1] StaticText 'Alpha beta record'"},
        ["[1] StaticText 'Alpha beta record'"],
        ["fill('10','alpha beta')", "click('11')"],
    )
    assert not Solver._terminal_success_gate(
        "Save the visible settings form",
        "Settings saved successfully.",
        {"url": "http://example.test/settings", "axtree": "[1] button 'Save'"},
        ["[1] button 'Save'"],
        ["click('1')"],
    )
    assert Solver._terminal_success_gate(
        "Save the visible settings form",
        "Settings saved successfully.",
        {"url": "http://example.test/settings", "axtree": "[1] StaticText 'Settings saved'"},
        ["[1] StaticText 'Settings saved'"],
        ["click('1')"],
    )


def test_terminal_success_gate_accepts_hover_report_with_menu_evidence():
    assert Solver._terminal_success_gate(
        "Hover over one visible menu or expandable control and report one submenu option that appears.",
        "The Reports submenu option appears.",
        {"url": "http://example.test", "axtree": "[1] menuitem 'Reports'"},
        ["[1] menuitem 'Reports'"],
        ["hover('1')"],
    )
    assert not Solver._terminal_success_gate(
        "Hover over one visible menu or expandable control and report one submenu option that appears.",
        "The Reports submenu option appears.",
        {"url": "http://example.test", "axtree": "[1] button 'Reports'"},
        ["[1] button 'Reports'"],
        ["click('1')"],
    )
