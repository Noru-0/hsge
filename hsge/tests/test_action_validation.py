from hsge.webarena.action_validation import (
    answer_has_evidence,
    repair_thought,
    task_family,
    validate_hsge_action,
)
from hsge.webarena.agents import PageExplorer, Solver


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
