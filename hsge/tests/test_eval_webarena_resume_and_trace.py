"""training/eval_webarena.py: errored tasks are requeued (not treated as done),
results.jsonl keeps one row per task, the LLM-judge key check counts only tasks
that actually reach the judge, and the trace records raw model output.

Every one of these guards a SILENT failure — the kind that produces a plausible
number instead of an error:
  - an errored row counted as done turns one tunnel blip into a permanent 0;
  - a duplicate row for a retried task corrupts the success denominator;
  - a missing OPENAI_API_KEY makes llm_fuzzy_match tasks score 0 with no symptom;
  - an unparseable model response ends the episode looking like a deliberate stop.

Run:  python -m pytest hsge/tests/test_eval_webarena_resume_and_trace.py -q
 (or) PYTHONPATH=. python hsge/tests/test_eval_webarena_resume_and_trace.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from training.eval_webarena import (n_llm_judged_tasks, prune_errored,  # noqa: E402
                                   write_summary, write_trace)


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_errored_rows_are_requeued_and_clean_rows_are_kept():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "results.jsonl"
        _write(p, [
            {"task_id": 1, "success": True, "reward": 1.0},
            {"task_id": 2, "error": "APIConnectionError: boom"},
            {"task_id": 3, "success": False, "reward": 0.0},
        ])
        done, n_requeued = prune_errored(p)

        assert done == {1, 3}, "task 2 errored, so it must be retried"
        assert n_requeued == 1
        kept = [json.loads(l) for l in p.read_text().splitlines()]
        assert [r["task_id"] for r in kept] == [1, 3]
        # the original file is preserved, since rewriting is destructive
        assert (Path(tmp) / "results.jsonl.bak").exists()


def test_a_retried_task_does_not_leave_two_rows():
    """results.jsonl is append-only, so retrying without rewriting would leave
    the errored row AND the new one, and the summary counts rows."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "results.jsonl"
        _write(p, [
            {"task_id": 7, "error": "Timeout"},
            {"task_id": 7, "success": True, "reward": 1.0},   # the retry landed
        ])
        done, n_requeued = prune_errored(p)

        assert done == {7}
        rows = [json.loads(l) for l in p.read_text().splitlines()]
        assert len(rows) == 1 and rows[0]["success"] is True


def test_an_error_after_a_success_requeues_the_task():
    """Order matters: a later error means the last attempt did not score."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "results.jsonl"
        _write(p, [
            {"task_id": 9, "success": True, "reward": 1.0},
            {"task_id": 9, "error": "vLLM restarted mid-task"},
        ])
        done, n_requeued = prune_errored(p)

        assert done == set() and n_requeued == 1
        assert p.read_text().strip() == ""


def test_no_rewrite_when_nothing_errored():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "results.jsonl"
        _write(p, [{"task_id": 1, "success": True}])
        before = p.read_text()
        done, n_requeued = prune_errored(p)

        assert done == {1} and n_requeued == 0
        assert p.read_text() == before
        assert not (Path(tmp) / "results.jsonl.bak").exists()


def test_judge_key_check_ignores_the_na_special_case():
    """`fuzzy_match: "N/A"` is exact-matched by WebArena and never calls the
    model — 70 of the 655 tasks carry the key but only 40 reach the judge, so
    counting the key would demand a key for sites that do not need one."""
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "test.raw.json"
        cache.write_text(json.dumps([
            {"task_id": 1, "sites": ["shopping"],
             "eval": {"reference_answers": {"fuzzy_match": ["a real answer"]}}},
            {"task_id": 2, "sites": ["shopping"],
             "eval": {"reference_answers": {"fuzzy_match": "N/A"}}},
            {"task_id": 3, "sites": ["shopping"],
             "eval": {"reference_answers": {"exact_match": "5"}}},
            {"task_id": 4, "sites": ["shopping"],
             "eval": {"reference_answers": {"fuzzy_match": ["N/A"]}}},
        ]))
        assert n_llm_judged_tasks("shopping", cache, [1, 2, 3, 4]) == 1
        # and it respects the selected subset
        assert n_llm_judged_tasks("shopping", cache, [2, 3, 4]) == 0


def test_trace_records_raw_output_and_keeps_the_three_records_separate():
    class _Step:
        def __init__(self, action, url, thought, axtree):
            self.action, self.url = action, url
            self.obs_summary, self.axtree = thought, axtree

    steps = [_Step("click('12')", "/p", "opening the product", "x" * 100)]
    llm_calls = [
        {"raw": '{"thought": "t", "action": "click(\'12\')"}', "parsed_ok": True},
        # the failure this whole record exists for: JSON has no \x escape
        {"raw": '{"thought": "t", "action": "click(\'12\\xa0 Reviews\')"}',
         "parsed_ok": False},
    ]
    act_trace = [{"action": "click('12')", "step_reward": 0.0,
                  "action_error": "Timeout 500ms exceeded"}]

    with tempfile.TemporaryDirectory() as tmp:
        write_trace(Path(tmp), 42, "find the price", steps, 0.0, "budget",
                    llm_calls=llm_calls, act_trace=act_trace)
        tr = json.loads((Path(tmp) / "traces" / "42.json").read_text())

    assert tr["n_steps"] == 1 and tr["n_llm_calls"] == 2 and tr["n_acts"] == 1
    assert not tr["llm_calls"][1]["parsed_ok"]
    assert "\\xa0" in tr["llm_calls"][1]["raw"]
    assert tr["act_trace"][0]["action_error"].startswith("Timeout")
    # axtree is opt-in; its size is always recorded so its absence is visible
    assert "axtree" not in tr["steps"][0] and tr["steps"][0]["axtree_chars"] == 100


def test_trace_stores_the_axtree_when_asked():
    class _Step:
        def __init__(self):
            self.action, self.url = "noop()", "/"
            self.obs_summary, self.axtree = "waiting", "RootWebArea 'x'"

    with tempfile.TemporaryDirectory() as tmp:
        write_trace(Path(tmp), 1, "g", [_Step()], 0.0, "", with_axtree=True)
        tr = json.loads((Path(tmp) / "traces" / "1.json").read_text())
    assert tr["steps"][0]["axtree"] == "RootWebArea 'x'"




class _Args:
    """Minimal stand-in for argparse.Namespace in write_summary()."""
    site = "shopping"
    model = "qwen35-9b"
    base_url = "http://127.0.0.1:8000/v1"


def test_summary_reports_the_full_site_denominator_not_the_attempted_one():
    """An interrupted sweep must not look better than a finished one."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        p = out / "results.jsonl"
        _write(p, [
            {"task_id": 1, "success": True},
            {"task_id": 2, "success": False},
            {"task_id": 3, "error": "Timeout"},
        ])
        # the site has 10 tasks; this sweep touched 3, one of which errored
        s = write_summary(out, p, _Args(), task_ids=list(range(1, 11)))

        assert s["n_site_tasks"] == 10
        assert (s["n_scored"], s["n_errored"], s["n_success"]) == (2, 1, 1)
        assert s["success_rate"] == 0.1            # 1/10, the comparable figure
        assert s["success_rate_attempted"] == 0.5  # 1/2, flattering, labelled as such
        assert s["complete"] is False
        # and it is persisted, not just returned
        assert json.loads((out / "summary.json").read_text())["n_site_tasks"] == 10


def test_summary_marks_a_finished_sweep_complete():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        p = out / "results.jsonl"
        _write(p, [{"task_id": 1, "success": True}, {"task_id": 2, "success": False}])
        s = write_summary(out, p, _Args(), task_ids=[1, 2])
    assert s["complete"] is True and s["success_rate"] == 0.5


def test_summary_aggregates_the_unparsed_and_action_error_counters():
    """Sweep-wide health signals: a rising unparsed count means the endpoint or
    chat template regressed, not that the model got worse."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        p = out / "results.jsonl"
        _write(p, [
            {"task_id": 1, "success": False, "n_unparsed_llm": 2, "n_action_errors": 3},
            {"task_id": 2, "success": True, "n_unparsed_llm": 0, "n_action_errors": 1},
            {"task_id": 3, "error": "boom"},                      # no counters at all
        ])
        s = write_summary(out, p, _Args(), task_ids=[1, 2, 3])
    assert s["n_unparsed_llm"] == 2 and s["n_action_errors"] == 4


def test_summary_is_written_on_the_abort_path():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        p = out / "results.jsonl"
        _write(p, [{"task_id": 1, "error": "tunnel gone"}])
        s = write_summary(out, p, _Args(), task_ids=[1, 2, 3], aborted=True)
    assert s["aborted_on_consecutive_errors"] is True
    assert s["complete"] is False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
