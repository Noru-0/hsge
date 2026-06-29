import inspect
import re
from collections import Counter
from types import SimpleNamespace

import pytest

from hsge.abstraction import _planning_evidence
from hsge.env import PageState, WebEnv
from hsge.graph import HierarchicalGraph
from hsge.llm import MockLLM
from hsge.operators import Operator, OperatorGraph, plan
from hsge.schema import ParamSlot, SkillCard, Step, SubTrajectory
from hsge.webarena.agents import PageExplorer, Solver
from hsge.webarena.runtime import RunMetrics, WebArenaExplorer, _normalize_trace_url
from hsge.verification import verify_skill


def _card(**overrides):
    values = {
        "name": "activate_named_control",
        "description": "Activate a visible control.",
        "slots": [ParamSlot("control_selector", "selector")],
        "action_template": ["click({control_selector})"],
        "precondition": "a control is visible",
        "success_predicate": "the control is activated",
        "cluster_id": "1",
        "verified": True,
        "skill_id": "skill_control",
        "planning_preconditions": set(),
        "planning_effects": {"has_confirmation_cue"},
        "planning_ready": True,
        "predicate_schema_version": "test-v1",
        "terminal": True,
    }
    values.update(overrides)
    return SkillCard(**values)


def test_operator_is_only_derived_from_verified_skill_and_keeps_identity():
    with pytest.raises(ValueError, match="unverified"):
        Operator.from_skill(_card(verified=False))

    card = _card()
    op = Operator.from_skill(card)
    graph = OperatorGraph()
    graph.add(op)

    assert op.skill_id == card.skill_id
    assert list(graph.ops) == [card.skill_id]
    assert plan(graph, frozenset(), "has_confirmation_cue") == [card.skill_id]


def test_node_identity_preserves_semantic_query_and_drops_tracking_params():
    first = _normalize_trace_url(
        "HTTPS://Example.Test/search?utm_source=x&q=shoe&page=2#results"
    )
    same = _normalize_trace_url(
        "https://example.test/search?page=2&q=shoe&utm_medium=email"
    )
    different = _normalize_trace_url("https://example.test/search?q=phone&page=2")

    assert first == "https://example.test/search?page=2&q=shoe"
    assert same == first
    assert different != first


def test_successful_node_marks_redirect_aliases_visited_and_releases_queue():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer._discovered_urls = {
        "https://example.test/requested?q=1": object(),
        "https://example.test/actual?q=1": object(),
    }
    explorer._prefix_retry_counts = {"https://example.test/requested?q=1": 1}
    explorer._load_retry_counts = {"https://example.test/requested?q=1": 1}
    visited = set()
    queued = {
        "https://example.test/requested?q=1",
        "https://example.test/actual?q=1",
    }

    explorer._mark_node_visited(
        "https://example.test/requested?q=1",
        "https://example.test/actual?q=1",
        visited,
        queued,
    )

    assert visited == {
        "https://example.test/requested?q=1",
        "https://example.test/actual?q=1",
    }
    assert queued == set()
    assert explorer._discovered_urls == {}


def test_planning_evidence_requires_two_thirds_support():
    members = []
    for index in range(3):
        members.append(SubTrajectory(
            steps=[Step("click('1')", "/start")],
            subgoal="activate control",
            source_site=str(index),
            planning_preconditions={"has_form_input", "has_menu"} if index < 2 else {"has_menu"},
            planning_effects={"has_confirmation_cue", "has_feedback"} if index < 2 else {"has_feedback"},
        ))

    preconditions, effects = _planning_evidence(members)

    assert preconditions == {"has_form_input", "has_menu"}
    assert effects == {"has_confirmation_cue", "has_feedback"}


def test_explorer_and_solver_public_apis_do_not_accept_learned_skills():
    explorer_params = inspect.signature(PageExplorer.propose).parameters
    solver_params = inspect.signature(Solver.solve).parameters

    assert "skill_hints" not in explorer_params
    assert "skill_hints" not in solver_params
    assert "tools" not in solver_params
    assert "context_hints" in solver_params


def test_browser_verification_requires_declared_planning_effects():
    class Browser:
        def reset(self):
            return {"url": "http://example.test/start", "axtree": "[1] button 'Open'"}

        def act(self, _action):
            return {"url": "http://example.test/detail", "axtree": "[2] heading 'Detail'"}

        def close(self):
            pass

    env = WebEnv(
        "site",
        {"start": PageState("http://example.test/start", affordances=[], goto={})},
        start="start",
        goal_pages={"done"},
    )
    env.browser_factory = lambda _url: Browser()
    card = _card(planning_effects={"has_confirmation_cue"})

    assert not verify_skill(MockLLM(), card, [env], k=1)
    assert not card.verified


def test_goal_composer_rejects_wrong_chain_and_uses_deterministic_fallback():
    class WrongChainLLM:
        def complete_json(self, _system, _prompt):
            return {"instruction": "Wrong", "skill_ids": ["another_skill"]}

    card = _card()
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.goal_composer_llm = WrongChainLLM()
    explorer.library = SimpleNamespace(all_skills=lambda: [card])

    instruction = explorer._compose_goal_instruction(
        [card.skill_id], "has_confirmation_cue", {"url": "/start", "axtree": "page"}
    )

    assert "activate named control" in instruction
    assert "has_confirmation_cue" in instruction


def test_old_checkpoint_is_rejected(tmp_path):
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.out_dir = str(tmp_path)
    with pytest.raises(ValueError, match="requires version 4"):
        explorer._resume_from_checkpoint({"version": 3})


def test_restored_verified_skill_rebuilds_operator_graph():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.terminal_goal = "has_confirmation_cue"
    explorer.opgraph = OperatorGraph()
    explorer.graph = HierarchicalGraph()
    explorer.library = SimpleNamespace(skills={}, _abstracted=set())

    explorer._restore_skills([{
        "skill_id": "skill_restored",
        "name": "activate_named_control",
        "description": "Activate a control.",
        "slots": [],
        "action_template": ["click('1')"],
        "precondition": "control visible",
        "success_predicate": "confirmation visible",
        "cluster_id": "4",
        "verified": True,
        "planning_preconditions": [],
        "planning_effects": ["has_confirmation_cue"],
    }])

    assert "skill_restored" in explorer.opgraph.ops
    assert explorer.opgraph.ops["skill_restored"].terminal
    assert explorer.graph.skills["skill_restored"] is explorer.library.skills[4]


def test_composed_goal_retries_three_full_attempts_and_records_each(tmp_path):
    class FakePageExplorer:
        domain_type = "generic"
        common_tasks = []
        common_actions = []

        def detect_domain(self, _obs):
            pass

        def propose(self, _obs):
            return []

    class FakeBrowser:
        def reset(self):
            return {"url": "http://example.test", "axtree": "[1] button 'Continue'"}

        def links(self):
            return []

        def close(self):
            pass

    class FakeSolver:
        def __init__(self):
            self.outcomes = [False, False, True]
            self.calls = 0

        def solve(self, _browser, _goal, **_kwargs):
            success = self.outcomes[self.calls]
            self.calls += 1
            final = {
                "url": "http://example.test/success" if success else "http://example.test",
                "axtree": "successful" if success else "not complete",
            }
            return [Step("click('1')", "http://example.test")], ["[1] button 'Continue'"], final, success, []

    class FakeScorer:
        _selected_child_count = {}
        _lookahead = {}

        def record_exploration(self, *_args, **_kwargs):
            pass

        def breakdown(self, _url, _visited):
            return {
                "score": 1.0, "U": 0.0, "V": 0.0,
                "V_sr": 0.0, "V_sr_source": "none",
                "V_n": 0, "V_n_source": "none",
            }

    card = _card()
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.out_dir = str(tmp_path)
    explorer._log_file = None
    explorer._frontier_file = open(tmp_path / "frontier.jsonl", "w", encoding="utf-8")
    explorer.browser_factory = lambda _url: FakeBrowser()
    explorer.explorer = FakePageExplorer()
    explorer.solver = FakeSolver()
    explorer.graph = HierarchicalGraph()
    explorer.graph.add_skill(card, init_states=[], effect_states=[])
    explorer.opgraph = explorer.graph.operator_graph
    explorer.library = SimpleNamespace(all_skills=lambda: [card])
    explorer.terminal_goal = "has_confirmation_cue"
    explorer.goal_instruction = "Complete the full workflow."
    explorer.auto_terminal_goals = False
    explorer.max_goal_attempts = 3
    explorer._discovered_urls = {}
    explorer._denylist = []
    explorer.allow = re.compile(r"http://example\.test.*")
    explorer.max_depth = 2
    explorer._frontier_max_size = 10
    explorer._frontier_scorer = FakeScorer()
    explorer._lookahead_predictor = SimpleNamespace(propose=lambda _ax: [])
    explorer._url_attempts = {}
    explorer._url_successes = {}
    explorer._axtree_cache = {}
    explorer.metrics = RunMetrics()
    explorer.episode = 0
    explorer._account_info = ""
    explorer.checkout_mode = "safe"
    explorer.place_order_allowed = False
    explorer._task_attempt_counts = Counter()
    explorer._task_success_counts = Counter()
    explorer._task_failure_counts = Counter()
    explorer._task_error_counts = Counter()
    explorer._task_family_failure_counts = Counter()
    explorer._skill_family_counts = Counter()
    explorer._coverage = {"successful_task_family": Counter()}
    explorer._reset_browser_to_node = lambda *_args: {
        "url": "http://example.test", "axtree": "[1] button 'Continue'"
    }
    recorded = []

    def record(_goal, _steps, _obs, success, **_kwargs):
        recorded.append(success)
        explorer.episode += 1

    explorer._record = record

    processed = explorer._process_node(
        "http://example.test", 0, "http://example.test",
        frontier=[], visited=set(), queued={"http://example.test"}, node_num=1,
    )
    explorer._frontier_file.close()

    assert processed == "http://example.test"
    assert explorer.solver.calls == 3
    assert recorded == [False, False, True]
    assert explorer.metrics.goal_tasks_solved == 1
