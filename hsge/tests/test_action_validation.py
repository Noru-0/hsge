from hsge.webarena.action_validation import (
    answer_has_evidence,
    repair_thought,
    task_family,
    validate_hsge_action,
)
from hsge.webarena.agents import PageExplorer, Solver
from hsge.webarena.runtime import (
    PrefixTraceStep,
    RunMetrics,
    WebArenaExplorer,
    _name_from_goal,
    desired_skill_family_for_task,
    skill_family,
)
from hsge.graph import HierarchicalGraph
from hsge.operators import OperatorGraph
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
    assert not validate_hsge_action("unknown_action('102','Blue')", AXTREE).ok
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
    # Go-Browse style narrative: no template markers
    assert "I can see" in thought or "need to" in thought.lower()
    assert "Evidence:" not in thought
    assert "In summary" not in thought.lower()


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

    assert "[INFO] Read visible review information and answer one detail." in tasks
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

    assert "[MOD] Add the visible item to the cart." in tasks
    assert "[NAV] Open the visible My Orders record-status page." in tasks
    assert "[MOD] Add the visible item to the wish list." in tasks


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

    assert "[INFO] Read the visible status for issue #42." in tasks
    assert all("publish" not in task.lower() for task in tasks)
    assert all("delete" not in task.lower() for task in tasks)


def test_page_explorer_hover_seed_has_report_stop_condition():
    obs = {
        "url": "http://example.test",
        "axtree": "[301] menuitem 'More', hasPopup='menu'",
    }
    tasks = PageExplorer(_TaskLLM([]), max_tasks=20).propose(obs)

    hover_tasks = [task for task in tasks if "hover over" in task.lower()]
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

    assert "[INFO] Read the visible status shown on this page." in tasks
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

    assert "[INFO] Report the visible feedback count shown by '12 Reviews'." in tasks
    assert "[INFO] Open the visible 'Sort By' sort or filter control and report one available option." in tasks
    assert "[NAV] Open the visible 'My Account' account or settings control and report one visible option." in tasks


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


def test_prefix_trace_checkpoint_roundtrip_uses_versioned_schema(tmp_path):
    from types import SimpleNamespace
    import json

    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.out_dir = str(tmp_path)
    explorer.episode = 7
    explorer.opgraph = OperatorGraph()
    explorer.graph = HierarchicalGraph()
    explorer.library = SimpleNamespace(
        clusterer=SimpleNamespace(clusters={}, sim_threshold=0.6),
        cluster_to_members={},
    )
    explorer._frontier_scorer = SimpleNamespace(to_dict=lambda: {})
    explorer._url_attempts = {}
    explorer._url_successes = {}
    explorer._discovered_urls = {}

    target = "http://example.test/detail"
    explorer._on_step_completed(
        "click('2')",
        "http://example.test/list",
        target,
        [
            Step("click('1')", "http://example.test/", "Open the list."),
            Step("click('2')", "http://example.test/list", "Open the detail."),
        ],
    )
    explorer.save_checkpoint(frontier=[(target, 1)], visited=set(), queued={target})

    ckpt = json.load(open(tmp_path / "checkpoint.json", encoding="utf-8"))
    saved = ckpt["discovered_urls"][target]
    assert saved["schema_version"] == 2
    assert saved["source_url"] == "http://example.test"
    assert saved["target_url"] == target
    assert saved["discovered_by_action"] == "click('2')"
    assert [s["action"] for s in saved["steps"]] == ["click('1')", "click('2')"]

    resumed = WebArenaExplorer.__new__(WebArenaExplorer)
    resumed.out_dir = str(tmp_path)
    resumed.opgraph = OperatorGraph()
    resumed.graph = HierarchicalGraph()
    resumed.library = SimpleNamespace(
        clusterer=SimpleNamespace(clusters={}, sim_threshold=0.6),
        cluster_to_members={},
    )
    resumed._resume_from_checkpoint(ckpt)
    trace = resumed._coerce_prefix_trace(target, resumed._discovered_urls[target])
    assert trace.source_url == "http://example.test"
    assert trace.target_url == target
    assert len(trace.steps) == 2


def test_legacy_prefix_trace_dict_migrates_to_versioned_trace():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    target = "http://example.test/cart"

    trace = explorer._coerce_prefix_trace(target, {
        "source_url": "http://example.test/",
        "action": "click('101')",
        "prefix_steps": [
            {"action": "click('101')", "url": "http://example.test/", "obs_summary": "Add item to cart."},
        ],
    })

    assert trace.schema_version == 2
    assert trace.source_url == "http://example.test"
    assert trace.target_url == target
    assert trace.discovered_by_action == "click('101')"
    assert trace.steps[0].thought == "Add item to cart."
    assert trace.steps[0].stateful_hint is True


def test_loose_frontier_selection_uses_top_band_not_always_top_score():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.max_depth = 3
    explorer._frontier_select_pool = 3
    explorer._frontier_score_band = 0.98
    explorer._frontier_selection_counts = {
        "http://example.test/a": 2,
    }
    explorer._prefix_retry_counts = {}

    selected = explorer._select_frontier_node([
        (10.0, "http://example.test/a", 1),
        (9.9, "http://example.test/b", 1),
        (9.7, "http://example.test/c", 1),
    ])

    assert selected == (9.9, "http://example.test/b", 1)
    assert explorer._frontier_selection_counts["http://example.test/b"] == 1


def test_stale_prefix_requeues_then_releases_for_fresh_discovery():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer._log_file = None
    explorer._prefix_retry_counts = {}
    explorer._prefix_retry_limit = 1
    target = "http://example.test/detail"
    explorer._discovered_urls = {
        target: {
            "source_url": "http://example.test",
            "prefix_steps": [{"action": "click('101')", "url": "http://example.test"}],
        }
    }
    explorer._last_prefix_replay_status = {
        "attempted": True,
        "stateful": True,
        "reason": "stale_action:bid 101 is not present in current AXTree",
    }
    frontier = []
    queued = {target}

    assert explorer._recover_unprocessed_prefix_url(target, 1, frontier, queued) is True
    assert frontier == [(target, 1)]
    assert queued == {target}
    assert explorer._discovered_urls[target]

    frontier.clear()
    assert explorer._recover_unprocessed_prefix_url(target, 1, frontier, queued) is False
    assert frontier == []
    assert target not in queued
    assert target not in explorer._discovered_urls
    assert target not in explorer._prefix_retry_counts


def test_empty_direct_load_requeues_then_releases():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer._log_file = None
    explorer._load_retry_counts = {}
    explorer._load_retry_limit = 1
    explorer.metrics = RunMetrics()
    target = "http://example.test"
    explorer._last_node_load_status = {
        "reason": "empty_observation",
        "detail": "Timeout 30000ms exceeded",
        "prefix_attempted": False,
    }
    frontier = []
    queued = {target}

    assert explorer._recover_empty_observation_url(target, 0, frontier, queued) is True
    assert frontier == [(target, 0)]
    assert queued == {target}
    assert explorer._load_retry_counts[target] == 1
    assert explorer.metrics.nodes_error == 0

    frontier.clear()
    assert explorer._recover_empty_observation_url(target, 0, frontier, queued) is False
    assert frontier == []
    assert target not in queued
    assert target not in explorer._load_retry_counts
    assert explorer.metrics.nodes_error == 1


def test_load_error_requeues_then_releases():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer._log_file = None
    explorer._load_retry_counts = {}
    explorer._load_retry_limit = 1
    explorer._discovered_urls = {}
    explorer.metrics = RunMetrics()
    target = "http://example.test/catalog?q=shoe"
    explorer._last_node_load_status = {
        "reason": "load_error",
        "detail": "temporary browser failure",
        "prefix_attempted": False,
    }
    frontier = []
    queued = {target}

    assert explorer._recover_empty_observation_url(target, 1, frontier, queued)
    assert frontier == [(target, 1)]

    frontier.clear()
    assert not explorer._recover_empty_observation_url(target, 1, frontier, queued)
    assert target not in queued
    assert explorer.metrics.nodes_error == 1


def test_redirect_to_visited_releases_requested_alias():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer._discovered_urls = {"http://example.test/private": object()}
    explorer._last_node_load_status = {
        "reason": "redirect_visited",
        "actual_url": "http://example.test/login",
    }
    queued = {"http://example.test/private"}

    assert not explorer._recover_empty_observation_url(
        "http://example.test/private", 1, [], queued
    )
    assert not queued
    assert not explorer._discovered_urls


def test_browser_reset_uses_configured_navigation_timeout(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    from hsge.webarena.browser import WebArenaBrowser

    calls = {}

    class Page:
        def goto(self, url, **kwargs):
            calls["goto"] = (url, kwargs)

    class Env:
        def __init__(self):
            self.unwrapped = SimpleNamespace(
                page=Page(),
                _get_obs=lambda: {"url": "https://example.test", "axtree_object": {}},
            )

        def reset(self):
            calls["reset"] = True

    obs_module = ModuleType("browsergym.utils.obs")
    obs_module.flatten_axtree_to_str = lambda _tree: "[1] heading 'Ready'"
    monkeypatch.setitem(sys.modules, "browsergym.utils.obs", obs_module)

    browser = WebArenaBrowser.__new__(WebArenaBrowser)
    browser.env = Env()
    browser.start_url = "https://example.test"
    browser.timeout_ms = 45000
    browser.screenshot_enabled = False
    browser._last_obs = None

    obs = browser.reset()

    assert calls["reset"]
    assert calls["goto"] == (
        "https://example.test",
        {"timeout": 45000, "wait_until": "domcontentloaded"},
    )
    assert obs["url"] == "https://example.test"


def test_browser_act_surfaces_browsergym_action_timeout(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    from hsge.webarena.browser import WebArenaBrowser

    class Env:
        unwrapped = SimpleNamespace(
            last_action_error="TimeoutError: Timeout 500ms exceeded."
        )

        def step(self, _action):
            return (
                {
                    "url": "https://example.test",
                    "axtree_object": {},
                    "last_action_error": "TimeoutError: Timeout 500ms exceeded.",
                },
                0.0,
                False,
                False,
                {"action_exec_timeout": 0.5},
            )

    obs_module = ModuleType("browsergym.utils.obs")
    obs_module.flatten_axtree_to_str = lambda _tree: "[1] button 'Ready'"
    monkeypatch.setitem(sys.modules, "browsergym.utils.obs", obs_module)

    browser = WebArenaBrowser.__new__(WebArenaBrowser)
    browser.env = Env()
    browser.screenshot_enabled = False
    browser._last_obs = None

    obs = browser.act("hover('1')")

    assert obs["url"] == "https://example.test"
    assert obs["_action_timed_out"] is True
    assert obs["_action_error_type"] == "TimeoutError"
    assert "500ms" in obs["_action_error"]


def test_solver_stops_immediately_when_browser_reports_action_error():
    from hsge.webarena.agents import Solver

    class LLM:
        supports_vision = False

        def complete_json(self, _system, _prompt):
            return {"thought": "Reveal the menu.", "action": "hover('1')"}

    class Browser:
        calls = 0

        def observation(self):
            return {
                "url": "https://example.test",
                "axtree": "[1] button 'Menu' haspopup=menu",
                "screenshot_base64": None,
            }

        def act(self, _action):
            self.calls += 1
            return {
                **self.observation(),
                "_action_error": "TimeoutError: Timeout 500ms exceeded.",
                "_action_timed_out": True,
                "_action_elapsed_ms": 501,
            }

    browser = Browser()
    steps, _, final_obs, success, _ = Solver(LLM(), max_steps=3).solve(
        browser, "Hover over Menu and report a submenu option."
    )

    assert browser.calls == 1
    assert len(steps) == 1
    assert "action error" in steps[0].obs_summary
    assert final_obs["_action_timed_out"] is True
    assert success is False


def test_empty_prefix_load_is_left_to_prefix_recovery():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer._load_retry_counts = {}
    explorer.metrics = RunMetrics()
    explorer._last_node_load_status = {
        "reason": "empty_observation",
        "detail": "stale prefix",
        "prefix_attempted": True,
    }

    assert explorer._recover_empty_observation_url(
        "http://example.test/detail", 1, [], set()
    ) is False
    assert explorer._load_retry_counts == {}
    assert explorer.metrics.nodes_error == 0


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


def test_prefix_replay_semantically_regrounds_changed_bid():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer._log_file = None
    target = "http://example.test/detail"
    explorer._discovered_urls = {
        target: {
            "source_url": "http://example.test",
            "steps": [PrefixTraceStep(
                action="click('101')",
                source_url="http://example.test",
                target_url=target,
                target_bid="101",
                target_role="link",
                target_name="'Result'",
                target_fingerprint="link|'result'",
            ).to_dict()],
        }
    }

    class Browser:
        def __init__(self):
            self.url = "http://example.test"
            self.actions = []

        def act(self, action):
            self.actions.append(action)
            if action.startswith("goto("):
                self.url = "http://example.test"
            elif action == "click('909')":
                self.url = target
            return self.observation()

        def observation(self):
            return {"url": self.url, "axtree": "[909] link 'Result'"}

    browser = Browser()
    assert explorer._navigate_via_prefix(browser, target)["url"] == target
    assert "click('909')" in browser.actions
    assert "semantic_reground" in explorer._last_prefix_replay_status["outcomes"]


def test_failed_stateful_reset_is_attempted_once_per_node():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer._log_file = None
    explorer._node_reset_unavailable = False
    explorer._discovered_urls = {"http://example.test/cart": {}}
    attempts = []

    def fail_once(_browser, _url):
        attempts.append(1)
        explorer._last_prefix_replay_status = {
            "attempted": True, "stateful": True, "reason": "target_not_found"
        }
        return None

    explorer._navigate_via_prefix = fail_once
    first = explorer._reset_browser_to_node(object(), "http://example.test/cart", "http://example.test/cart")
    second = explorer._reset_browser_to_node(object(), "http://example.test/cart", "http://example.test/cart")

    assert not first["url"] and not second["url"]
    assert len(attempts) == 1
    assert explorer._node_reset_short_circuits == 1


def test_process_node_falls_back_to_dom_links_when_callbacks_find_none(tmp_path):
    import re
    from collections import Counter
    from types import SimpleNamespace

    class FakePageExplorer:
        domain_type = "generic"
        common_tasks = []
        common_actions = []

        def detect_domain(self, obs):
            self.detected = obs["url"]

        def propose(self, obs, skill_hints=""):
            return []

    class FakeBrowser:
        def reset(self):
            return {
                "url": "http://example.test",
                "axtree": "[1] link 'Detail'\n[2] link 'Logout'",
            }

        def links(self):
            return [
                "http://example.test/detail",
                "http://example.test/logout",
                "http://other.test/outside",
            ]

        def close(self):
            pass

    class FakeScorer:
        def __init__(self):
            self._selected_child_count = {}
            self._lookahead = {}
            self.parents = {}

        def record_exploration(self, *args, **kwargs):
            pass

        def set_parent(self, link, parent):
            self.parents[link] = parent

        def set_lookahead(self, link, lookahead):
            self._lookahead[link] = lookahead

        def breakdown(self, url, visited):
            return {
                "score": 1.0,
                "U": 0.0,
                "V": 0.0,
                "V_sr": 0.0,
                "V_sr_source": "none",
                "V_n": 0.0,
                "V_n_source": "none",
            }

    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.out_dir = str(tmp_path)
    explorer._log_file = None
    explorer._frontier_file = open(tmp_path / "frontier.jsonl", "w", encoding="utf-8")
    explorer.browser_factory = lambda _url: FakeBrowser()
    explorer.explorer = FakePageExplorer()
    explorer.solver = SimpleNamespace()
    explorer.opgraph = OperatorGraph()
    explorer.terminal_goal = None
    explorer.goal_instruction = None
    explorer.auto_terminal_goals = False
    explorer._discovered_urls = {}
    explorer._denylist = [re.compile(r"/logout")]
    explorer.allow = re.compile(r"http://example\.test.*")
    explorer.max_depth = 2
    explorer._frontier_max_size = 10
    explorer._frontier_scorer = FakeScorer()
    explorer._lookahead_predictor = SimpleNamespace(propose=lambda _axtree: [{"task": "open detail"}])
    explorer._url_attempts = {}
    explorer._url_successes = {}
    explorer._axtree_cache = {}
    explorer.metrics = RunMetrics()
    explorer.library = SimpleNamespace(all_skills=lambda: [])
    explorer.episode = 0
    explorer._account_info = ""
    explorer._task_attempt_counts = {}
    explorer._task_success_counts = {}
    explorer._task_failure_counts = {}
    explorer._task_error_counts = {}
    explorer._task_family_failure_counts = {}
    explorer._skill_family_counts = Counter()
    explorer._coverage = {"successful_task_family": {}}

    frontier = []
    queued = {"http://example.test"}
    processed = explorer._process_node(
        "http://example.test",
        0,
        "http://example.test",
        frontier,
        visited=set(),
        queued=queued,
        node_num=1,
    )
    explorer._frontier_file.close()

    assert processed == "http://example.test"
    assert frontier == [("http://example.test/detail", 1)]
    assert queued == {"http://example.test", "http://example.test/detail"}
    assert "http://example.test/logout" not in queued
    assert "http://other.test/outside" not in queued


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
