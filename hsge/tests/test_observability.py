import json
import re

from hsge.webarena.observability import ExploreEventLogger, redact
from hsge.schema import Step
from hsge.webarena.runtime import RunMetrics, WebArenaExplorer


def test_event_logger_writes_correlated_redacted_jsonl(tmp_path):
    logger = ExploreEventLogger(str(tmp_path), run_id="run-test")
    logger.emit(
        "solver",
        "url_discovered",
        node_id=3,
        task_id="n3-local-1",
        episode_id=7,
        data={
            "url": "https://example.test/path?q=shoe&token=secret",
            "password": "hunter2",
        },
    )
    logger.close()

    record = json.loads((tmp_path / "events.jsonl").read_text().strip())
    assert record["run_id"] == "run-test"
    assert record["component"] == "solver"
    assert record["node_id"] == 3
    assert "secret" not in record["data"]["url"]
    assert record["data"]["password"] == "<redacted>"


def test_event_logger_level_filters_lower_priority_events(tmp_path):
    logger = ExploreEventLogger(str(tmp_path), level="summary")
    assert logger.emit("solver", "step", level="debug") is None
    assert logger.emit("node", "completed", level="summary") is not None
    logger.close()

    records = (tmp_path / "events.jsonl").read_text().splitlines()
    assert len(records) == 1


def test_redact_preserves_non_sensitive_payload():
    assert redact({"goal": "find shoes", "count": 2}) == {
        "goal": "find shoes",
        "count": 2,
    }


def test_solver_url_funnel_counts_each_rejection_reason():
    explorer = WebArenaExplorer.__new__(WebArenaExplorer)
    explorer.metrics = RunMetrics()
    explorer._node_url_stats = {}
    explorer._node_solver_urls = set()
    explorer._discovered_urls = {}
    explorer._active_visited = {"https://example.test/visited"}
    explorer._active_queued = {"https://example.test/queued"}
    explorer._denylist = [re.compile(r"/logout")]
    explorer.allow = re.compile(r"https://example\.test.*")
    steps = [Step("click('1')", "https://example.test/start")]

    transitions = [
        "https://example.test/new",
        "https://example.test/new",
        "https://example.test/visited",
        "https://example.test/queued",
        "https://example.test/logout",
        "https://other.test/outside",
    ]
    for target in transitions:
        explorer._on_step_completed(
            "click('1')", "https://example.test/start", target, steps
        )

    assert explorer.metrics.solver_navigation_events == 6
    assert explorer.metrics.solver_unique_urls_discovered == 5
    assert explorer.metrics.solver_urls_duplicate == 1
    assert explorer.metrics.solver_urls_already_visited == 1
    assert explorer.metrics.solver_urls_already_queued == 1
    assert explorer.metrics.solver_urls_denied == 1
    assert explorer.metrics.solver_urls_cross_origin == 1
    assert explorer.metrics.solver_urls_frontier_eligible == 1
    assert list(explorer._discovered_urls) == ["https://example.test/new"]
