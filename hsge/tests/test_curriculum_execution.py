import json
from collections import Counter
from types import SimpleNamespace

from hsge.graph import HierarchicalGraph
from hsge.schema import SkillCard, Step, Task
from hsge.webarena.runtime import RunMetrics, WebArenaExplorer


def _card() -> SkillCard:
    return SkillCard(
        name="finish_workflow",
        description="Finish the workflow.",
        slots=[],
        action_template=["click('1')"],
        precondition="ready",
        success_predicate="done",
        cluster_id="1",
        verified=True,
        skill_id="skill_finish",
        planning_preconditions={"ready"},
        planning_effects={"done"},
        planning_ready=True,
        predicate_schema_version="test-v1",
        terminal=True,
    )


class _Extractor:
    schema_version = "test-v1"

    def extract(self, _url, _axtree=""):
        return {"ready"}


class _Composer:
    def complete_json(self, _system, prompt):
        payload = json.loads(prompt)
        return {
            "instruction": "Finish the visible workflow.",
            "skill_ids": payload["skill_ids"],
        }


class _Solver:
    def __init__(self, success=True):
        self.success = success
        self.calls = []

    def solve(self, _browser, goal, **kwargs):
        self.calls.append((goal, kwargs))
        return (
            [Step("click('1')", "http://example.test")],
            ["[1] button 'Finish'"],
            {"url": "http://example.test", "axtree": "done"},
            self.success,
            [],
        )


def _explorer(tmp_path, *, success=True):
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.out_dir = str(tmp_path)
    explorer.graph = HierarchicalGraph()
    card = _card()
    explorer.graph.add_skill(card, [], [])
    explorer.opgraph = explorer.graph.operator_graph
    explorer.library = SimpleNamespace(all_skills=lambda: [card])
    explorer.predicate_extractor = _Extractor()
    explorer.goal_composer_llm = _Composer()
    explorer.solver = _Solver(success=success)
    explorer.discovery = SimpleNamespace(on_trajectory=lambda *args, **kwargs: None)
    explorer.metrics = RunMetrics()
    explorer.episode = 0
    explorer.execute_curriculum_tasks = True
    explorer.curriculum_max_tasks_per_node = 3
    explorer.curriculum_max_attempts = 1
    explorer.curriculum_feed_success_to_discovery = True
    explorer._curriculum_task_attempt_counts = Counter()
    explorer._curriculum_task_success_counts = Counter()
    explorer._account_info = ""
    explorer.checkout_mode = "safe"
    explorer.place_order_allowed = False
    explorer._active_task_id = None
    explorer._active_episode_id = None
    explorer._reset_browser_to_node = lambda *_args: {
        "url": "http://example.test", "axtree": "ready"
    }
    return explorer


def test_curriculum_scheduler_prefers_least_attempted_then_difficulty(tmp_path):
    explorer = _explorer(tmp_path)
    tasks = [
        Task("a", ["a"], 1, task_id="a", goal_predicate="a"),
        Task("b", ["b1", "b2"], 2, task_id="b", goal_predicate="b"),
        Task("c", ["c"], 1, task_id="c", goal_predicate="c"),
        Task("d", ["d"], 1, task_id="d", goal_predicate="d"),
    ]
    explorer._curriculum_task_attempt_counts.update({"a": 2, "c": 1})

    selected = explorer._select_curriculum_tasks(tasks)

    assert [task.task_id for task in selected] == ["d", "b", "c"]


def test_curriculum_runner_records_provenance_and_feeds_success(tmp_path):
    explorer = _explorer(tmp_path)
    recorded = []
    discovered = []

    def record(goal, _steps, _obs, success, **kwargs):
        recorded.append((goal, success, kwargs))
        explorer.episode += 1

    explorer._record = record
    explorer.discovery = SimpleNamespace(
        on_trajectory=lambda *args, **kwargs: discovered.append((args, kwargs))
    )
    task_records = []

    success = explorer._run_curriculum_tasks(
        browser=object(),
        requested_url="http://example.test",
        actual_url="http://example.test",
        root_url="http://example.test",
        node_num=7,
        task_records=task_records,
    )

    assert success is True
    assert len(explorer.solver.calls) == 1
    assert explorer.solver.calls[0][1]["goal_predicate"] == "done"
    assert recorded[0][2]["tag"] == "CURRICULUM"
    metadata = recorded[0][2]["task_metadata"]
    assert metadata["generated_by_curriculum"] is True
    assert metadata["node_id"] == 7
    assert metadata["goal_predicate"] == "done"
    assert metadata["skill_chain"] == ["skill_finish"]
    assert task_records[0]["task_origin"] == "curriculum"
    assert len(discovered) == 1
    assert discovered[0][1]["provenance"]["source_kind"] == "curriculum"
    ledger = [
        json.loads(line)
        for line in (tmp_path / "curriculum_executions.jsonl").read_text().splitlines()
    ]
    assert ledger[0]["status"] == "solved"
    assert ledger[0]["episode_id"] == 0


def test_curriculum_reset_failure_still_records_marked_episode(tmp_path):
    explorer = _explorer(tmp_path)
    resets = iter([
        {"url": "http://example.test", "axtree": "ready"},
        {"url": "", "axtree": ""},
    ])
    explorer._reset_browser_to_node = lambda *_args: next(resets)
    recorded = []

    def record(_goal, steps, _obs, success, **kwargs):
        recorded.append((steps, success, kwargs))
        explorer.episode += 1

    explorer._record = record

    explorer._run_curriculum_tasks(
        browser=object(),
        requested_url="http://example.test",
        actual_url="http://example.test",
        root_url="http://example.test",
        node_num=2,
        task_records=[],
    )

    assert recorded[0][0] == []
    assert recorded[0][1] is False
    assert recorded[0][2]["tag"] == "CURRICULUM"
    assert recorded[0][2]["task_metadata"]["skip_reason"] == "node_reset_failed"
    assert explorer.metrics.curriculum_tasks_skipped == 1


def test_record_writes_curriculum_provenance_to_episode_meta(tmp_path):
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.out_dir = str(tmp_path)
    (tmp_path / "episodes").mkdir()
    explorer.episode = 0
    explorer.predicate_extractor = _Extractor()
    explorer._coverage = {
        "task_family": Counter(),
        "action_family": Counter(),
        "successful_task_family": Counter(),
        "failed_task_family": Counter(),
        "successful_action_family": Counter(),
        "invalid_or_empty_episodes": 0,
    }

    explorer._record(
        "Finish the workflow",
        [Step("click('1')", "http://example.test")],
        ["[1] button 'Finish'"],
        True,
        difficulty=2,
        tag="CURRICULUM",
        final_obs={"url": "http://example.test", "axtree": "done"},
        task_metadata={
            "generated_by_curriculum": True,
            "curriculum_task_id": "curriculum_123",
            "goal_predicate": "done",
            "skill_chain": ["open", "finish"],
        },
    )

    meta = json.loads(
        (tmp_path / "episodes" / "ep_0000" / "episode_meta.json").read_text()
    )
    assert meta["metadata"]["tags"] == ["CURRICULUM"]
    assert meta["metadata"]["task_origin"] == "curriculum"
    assert meta["metadata"]["generated_by_curriculum"] is True
    assert meta["metadata"]["curriculum_task_id"] == "curriculum_123"


def test_checkpoint_v6_persists_scheduler_and_v5_is_not_resumable(tmp_path):
    explorer = _explorer(tmp_path)
    explorer._curriculum_task_attempt_counts.update({"curriculum_a": 3})
    explorer._curriculum_task_success_counts.update({"curriculum_a": 2})
    explorer._discovered_urls = {}
    explorer._frontier_scorer = SimpleNamespace(to_dict=lambda: {})
    explorer._url_attempts = {}
    explorer._url_successes = {}
    explorer._frontier_selection_counts = {}
    explorer._prefix_retry_counts = {}
    explorer._load_retry_counts = {}
    explorer._curriculum_initial_predicates = {"ready"}
    explorer.graph = HierarchicalGraph()
    explorer.library = SimpleNamespace(
        all_skills=lambda: [],
        clusterer=SimpleNamespace(clusters={}, sim_threshold=0.6),
        cluster_to_members={},
    )
    explorer._write_graph = lambda: None
    explorer._write_curriculum = lambda: None
    explorer._write_metrics_snapshot = lambda: None

    explorer.save_checkpoint([], set(), set())

    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert checkpoint["version"] == 6
    assert checkpoint["predicate_kernel_revision"] == 2
    assert checkpoint["curriculum_task_attempt_counts"] == {"curriculum_a": 3}
    assert checkpoint["curriculum_task_success_counts"] == {"curriculum_a": 2}

    restored = WebArenaExplorer.__new__(WebArenaExplorer)
    restored.out_dir = str(tmp_path / "v5")
    import pytest
    with pytest.raises(ValueError, match="import-legacy-run"):
        restored._resume_from_checkpoint({"version": 5})
