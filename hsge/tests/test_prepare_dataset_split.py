"""training/prepare_dataset.py: the train/val split holds out whole *tasks*,
and same-goal same-difficulty repeats are dropped while LOCAL/UNPREFIXED pairs
are kept.

Both invariants come from a real defect: `unprefixed_sampling` records every
solved task twice (LOCAL from its node, UNPREFIXED from the site root), so a
trajectory-level split leaked 50% of val examples' goals into train in
`training_data/`.

Run:  python -m pytest hsge/tests/test_prepare_dataset_split.py -q
 (or) PYTHONPATH=. python hsge/tests/test_prepare_dataset_split.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from training.prepare_dataset import drop_redundant, task_key  # noqa: E402

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _example(site, goal, difficulty, tid, step_index):
    user = (f"# Goal\n{goal}\n\n# Current Page\nURL: /x\n\nRootWebArea 'x'\n\n"
            f"# Error Message from Last Action\n(none)\n\n"
            f"# History of Past Actions\n(none)\n\n# Next Action\n")
    return {"messages": [{"role": "system", "content": "sys"},
                         {"role": "user", "content": user},
                         {"role": "assistant",
                          "content": json.dumps({"thought": "t", "action": "click('1')"})}],
            "site": site, "difficulty": difficulty, "trajectory_id": tid,
            "step_index": step_index, "total_steps": step_index + 1}


def _traj(site, goal, difficulty, tid, n_steps):
    return [_example(site, goal, difficulty, tid, i) for i in range(n_steps)]


def test_task_key_reads_the_goal_out_of_the_prompt():
    rows = _traj("reddit", "Open the wiki page.", 1, "reddit__ep_0001", 2)
    assert task_key(rows) == ("reddit", "Open the wiki page.")


def test_task_key_falls_back_to_trajectory_id_on_the_old_prompt_format():
    rows = _traj("reddit", "g", 1, "reddit__ep_0001", 1)
    rows[0]["messages"][1]["content"] = "GOAL: legacy format\n\nURL: /x\n\nPAGE:\n"
    # without the fallback every legacy trajectory would key to the same
    # empty goal and end up in one group
    assert task_key(rows) == ("reddit", "reddit__ep_0001")


def test_local_unprefixed_pair_is_kept_but_a_same_difficulty_repeat_is_not():
    trajs = {
        # the intended pair: same goal, difficulty 1 + 2 -> both kept
        "reddit__ep_0001": _traj("reddit", "Open the wiki page.", 1, "reddit__ep_0001", 2),
        "reddit__ep_0002": _traj("reddit", "Open the wiki page.", 2, "reddit__ep_0002", 5),
        # a genuine repeat: same goal, both difficulty 2 -> longest kept
        "reddit__ep_0003": _traj("reddit", "Submit a post.", 2, "reddit__ep_0003", 3),
        "reddit__ep_0004": _traj("reddit", "Submit a post.", 2, "reddit__ep_0004", 9),
        # same wording on another site is a different task
        "gitlab__ep_0001": _traj("gitlab", "Open the wiki page.", 1, "gitlab__ep_0001", 4),
    }
    dropped, report = drop_redundant(trajs)
    assert dropped == {"reddit__ep_0003"}
    assert len(report) == 1
    site, goal, diff, kept, gone = report[0]
    assert (site, goal, diff, kept, gone) == (
        "reddit", "Submit a post.", 2, "reddit__ep_0004", ["reddit__ep_0003"])


def test_split_holds_out_whole_tasks_so_no_val_goal_appears_in_train():
    rows = []
    for i in range(40):
        goal = f"Task number {i}."
        rows += _traj("reddit", goal, 1, f"reddit__ep_{i:04d}a", 2)
        rows += _traj("reddit", goal, 2, f"reddit__ep_{i:04d}b", 3)

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "pool.jsonl")
        with open(src, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        out = os.path.join(tmp, "data")
        # the script asserts the no-leak invariant itself, so a non-zero exit
        # is already a failure; check the split explicitly anyway
        subprocess.run([sys.executable, "training/prepare_dataset.py", src,
                        "--out-dir", out, "--keep-all-fields"],
                       cwd=_REPO, check=True, capture_output=True)
        train = [json.loads(l) for l in open(os.path.join(out, "train.jsonl"))]
        val = [json.loads(l) for l in open(os.path.join(out, "val.jsonl"))]

    def goals(part):
        by_traj = {}
        for r in part:
            by_traj.setdefault(r["trajectory_id"], []).append(r)
        return {task_key(v) for v in by_traj.values()}

    assert val, "val split is empty"
    assert not (goals(val) & goals(train))
    # and the pair itself never straddles: a held-out goal takes both its
    # trajectories with it
    val_ids = {r["trajectory_id"] for r in val}
    for tid in val_ids:
        twin = tid[:-1] + ("b" if tid.endswith("a") else "a")
        assert twin in val_ids, f"{tid} held out without its twin {twin}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
