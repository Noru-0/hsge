"""End-to-end dry run of the seed-conditioned GOAL curriculum: run_webarena.py
--dry-run (scripted LLM + fake browser) must derive a site seed and produce a
non-zero GOAL bucket -- the whole point of Phase A (bypass the edgeless operator
graph). No API key or live browser needed.

Run: PYTHONPATH=. python -m pytest hsge/tests/test_dry_run_seed.py -q
"""
import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_dry_run_produces_seed_and_goal_episode(tmp_path):
    out = str(tmp_path / "wa_dry")
    subprocess.run([sys.executable, "run_webarena.py", "--dry-run",
                    "--out", out, "--max-nodes", "2"],
                   check=True, cwd=REPO)

    # the seed was derived and persisted, with at least one capability
    seed = json.load(open(os.path.join(out, "seed.json"), encoding="utf-8"))
    assert seed["capabilities"], "expected at least one seed capability"

    # a GOAL episode actually ran (first-ever non-zero GOAL bucket)
    summary = json.load(open(os.path.join(out, "summary.json"), encoding="utf-8"))
    goal = summary["tasks"]["GOAL"]
    assert goal["success"] + goal["fail"] + goal["infeasible"] > 0


def test_dry_run_plans_subgoals_for_goal(tmp_path):
    """--dry-run enables plan_subgoals; the planner decomposes each GOAL and logs
    a goal_subgoals_planned event before solving."""
    out = str(tmp_path / "wa_dry")
    subprocess.run([sys.executable, "run_webarena.py", "--dry-run",
                    "--out", out, "--max-nodes", "2"], check=True, cwd=REPO)
    log = [json.loads(l) for l in open(os.path.join(out, "run_log.jsonl"), encoding="utf-8")]
    planned = [e for e in log if e.get("event") == "goal_subgoals_planned"]
    assert planned and planned[0]["n"] >= 1


def test_dry_run_verifier_demotes_false_positive_goal(tmp_path):
    """--dry-run enables verify_episodes; the scripted solver self-declares the
    checkout GOAL done without ever reaching the success page, so the grader
    FAILs it and the success is demoted to fail end-to-end. The LOCAL tasks it
    really does perform are PASSed, so the promotion path stays exercised."""
    out = str(tmp_path / "wa_dry")
    subprocess.run([sys.executable, "run_webarena.py", "--dry-run",
                    "--out", out, "--max-nodes", "2"], check=True, cwd=REPO)
    summary = json.load(open(os.path.join(out, "summary.json"), encoding="utf-8"))
    goal = summary["tasks"]["GOAL"]
    assert goal["fail"] >= 1        # the inline verifier caught the false positive
    assert goal["success"] == 0     # nothing survived the grader in the dry run
    # ...and a verified LOCAL success is still admitted, so the judge is not
    # simply vetoing everything
    assert summary["tasks"]["LOCAL"]["success"] >= 1
    assert summary["skills_discovered"] >= 1
