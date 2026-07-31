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


def test_dry_run_verifier_demotes_false_positive_goal(tmp_path):
    """--dry-run enables verify_goals; the scripted solver self-declares done but
    the grader FAILs it, so the GOAL success is demoted to fail end-to-end."""
    out = str(tmp_path / "wa_dry")
    subprocess.run([sys.executable, "run_webarena.py", "--dry-run",
                    "--out", out, "--max-nodes", "2"], check=True, cwd=REPO)
    summary = json.load(open(os.path.join(out, "summary.json"), encoding="utf-8"))
    goal = summary["tasks"]["GOAL"]
    assert goal["fail"] >= 1        # the inline verifier caught the false positive
    assert goal["success"] == 0     # nothing survived the grader in the dry run
