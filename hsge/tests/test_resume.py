"""Accurate resume of an interrupted WebArena run: atomic per-node pickle
checkpoint of the loop state + discovery objects (backends detached/re-injected),
and a --resume overwrite guard.

Run:  python -m pytest hsge/tests/test_resume.py -q
 (or) PYTHONPATH=. python hsge/tests/test_resume.py
"""
import heapq
import os
import pickle
import tempfile
from collections import Counter
from unittest import mock

from hsge.llm import HashingEmbedder, MockLLM
from hsge.operators import Operator
from hsge.schema import SkillCard, Step, SubTrajectory
from hsge.webarena.runtime import WebArenaExplorer


def _explorer(out_dir=None, browser_factory=None):
    return WebArenaExplorer(
        browser_factory=browser_factory or (lambda url: None),
        llm=MockLLM(), embedder=HashingEmbedder(),
        out_dir=out_dir or tempfile.mkdtemp(),
        allow_pattern=".*", terminal_goal=None)


def _install_skill(ex, name="AddToCart"):
    steps = [Step(action="click('1')", url="http://shop/item.html", axtree="before ax"),
             Step(action="click('2')", url="http://shop/cart", axtree="after ax")]
    sub = SubTrajectory(steps=steps, subgoal=name, source_site="shop")
    card = SkillCard(name=name, description="add an item", slots=[],
                     action_template=["click {btn}"], precondition="",
                     success_predicate="", cluster_id=0, member_ids=[sub.sub_id])
    ex.library.skills[0] = card
    ex.library.subtrajs[sub.sub_id] = sub
    return card


def _populate_discovery(ex):
    """Give the explorer some non-trivial discovery state to preserve."""
    ex.registry.canonical("the cart is empty")
    ex.registry.canonical("search results are shown")
    ex.opgraph.add(Operator("search", frozenset(), frozenset({"p0"})))
    ex.opgraph.add(Operator("checkout", frozenset({"p0"}), frozenset({"p1"})))
    _install_skill(ex)
    ex.episode = 5
    ex.explorer._seen["go to the forums page"] = "Go to the Forums page"


def _loop_state():
    frontier = []
    for key in [(1, 2, 3, 7, "http://shop/c"), (0, 0, 1, 3, "http://shop/a"),
                (1, 0, 2, 5, "http://shop/b")]:
        heapq.heappush(frontier, key)
    return {
        "frontier": frontier,
        "visited": {"http://shop/home", "http://shop/item.html"},
        "queued": {"http://shop/home", "http://shop/item.html", "http://shop/a",
                   "http://shop/b", "http://shop/c"},
        "template_counts": Counter({"shop/item_html": 1, "shop/home": 1}),
        "seen_content": {"deadbeef", "cafef00d"},
        "seq": 8,
        "duplicate_nodes": 1,
        "node_errors": 2,
        "task_stats": {"LOCAL": {"success": 3, "fail": 1, "infeasible": 0},
                       "GOAL": {"success": 0, "fail": 0, "infeasible": 0}},
        "nodes_log": [{"index": 1, "url": "http://shop/home", "tasks": []}],
    }


# --------------------------------------------------------------------------- #
# Checkpoint round-trip.
# --------------------------------------------------------------------------- #
def test_checkpoint_roundtrip_restores_loop_and_discovery_state():
    out = tempfile.mkdtemp()
    ex = _explorer(out_dir=out)
    ex.run_started_epoch, ex.run_started_iso = 111.0, "2026-07-22T00:00:00"
    _populate_discovery(ex)
    loop = _loop_state()

    ex._write_checkpoint(loop)

    ex2 = _explorer(out_dir=out)                 # fresh backends, same out_dir
    ex2.load_checkpoint(os.path.join(out, "checkpoint.pkl"))

    # discovery state preserved exactly
    assert len(ex2.library.all_skills()) == len(ex.library.all_skills())
    assert ex2.registry.counts == ex.registry.counts
    assert set(ex2.opgraph.ops) == {"search", "checkout"}
    assert ex2.episode == 5
    assert ex2.explorer._seen == {"go to the forums page": "Go to the Forums page"}

    # loop state preserved: same visited/queued/counters and same frontier pop order
    st = ex2._resume_loop_state
    assert st["visited"] == loop["visited"]
    assert st["queued"] == loop["queued"]
    assert st["template_counts"] == loop["template_counts"]
    assert st["seen_content"] == loop["seen_content"]
    assert st["seq"] == 8
    assert st["duplicate_nodes"] == 1 and st["node_errors"] == 2
    assert st["task_stats"] == loop["task_stats"]
    popped = [heapq.heappop(st["frontier"]) for _ in range(3)]
    assert [k[4] for k in popped] == ["http://shop/a", "http://shop/b", "http://shop/c"]


def test_checkpoint_round_trips_site_seed():
    out = tempfile.mkdtemp()
    ex = _explorer(out_dir=out)
    ex.run_started_epoch, ex.run_started_iso = 1.0, "x"
    ex.site_seed = {"description": "d", "capabilities": [{"name": "c", "goal": "g"}]}
    ex._attempted_capabilities = {"c"}

    ex._write_checkpoint(_loop_state())

    ex2 = _explorer(out_dir=out)
    ex2.load_checkpoint(os.path.join(out, "checkpoint.pkl"))

    assert ex2.site_seed == {"description": "d", "capabilities": [{"name": "c", "goal": "g"}]}
    assert ex2._attempted_capabilities == {"c"}


def test_backends_reattached_after_load():
    out = tempfile.mkdtemp()
    ex = _explorer(out_dir=out)
    ex.run_started_epoch, ex.run_started_iso = 1.0, "x"
    _populate_discovery(ex)
    ex._write_checkpoint(_loop_state())

    ex2 = _explorer(out_dir=out)
    ex2.load_checkpoint(os.path.join(out, "checkpoint.pkl"))

    assert ex2.library.llm is not None
    assert ex2.library.abstraction_llm is not None
    assert ex2.library.verification_llm is not None
    assert ex2.library.embedder is not None
    assert ex2.registry.llm is not None
    assert ex2.registry.embedder is not None
    assert ex2.discovery.segmentation_llm is not None
    assert ex2.explorer.llm is not None


def test_write_checkpoint_restores_live_backends():
    """Detaching backends for pickling must be reversed even on the running
    explorer, so the current run keeps working after a checkpoint."""
    out = tempfile.mkdtemp()
    ex = _explorer(out_dir=out)
    ex.run_started_epoch, ex.run_started_iso = 1.0, "x"
    _populate_discovery(ex)
    before = (ex.library.llm, ex.library.embedder, ex.registry.llm,
              ex.registry.embedder, ex.discovery.segmentation_llm, ex.explorer.llm)

    ex._write_checkpoint(_loop_state())

    after = (ex.library.llm, ex.library.embedder, ex.registry.llm,
             ex.registry.embedder, ex.discovery.segmentation_llm, ex.explorer.llm)
    assert all(a is b for a, b in zip(before, after))
    assert all(x is not None for x in after)


# --------------------------------------------------------------------------- #
# Atomic write.
# --------------------------------------------------------------------------- #
def test_atomic_write_leaves_previous_checkpoint_intact_on_failure():
    out = tempfile.mkdtemp()
    ex = _explorer(out_dir=out)
    ex.run_started_epoch, ex.run_started_iso = 1.0, "x"
    _populate_discovery(ex)
    ex._write_checkpoint(_loop_state())                 # a valid checkpoint exists
    good = open(os.path.join(out, "checkpoint.pkl"), "rb").read()

    with mock.patch("hsge.webarena.runtime.pickle.dump", side_effect=RuntimeError("disk full")):
        try:
            ex._write_checkpoint(_loop_state())
            assert False, "expected the failing dump to propagate"
        except RuntimeError:
            pass

    # previous checkpoint untouched, no stray .tmp left behind
    assert open(os.path.join(out, "checkpoint.pkl"), "rb").read() == good
    assert not os.path.exists(os.path.join(out, "checkpoint.pkl.tmp"))


# --------------------------------------------------------------------------- #
# Resume does not re-process an already-visited node.
# --------------------------------------------------------------------------- #
def test_resume_skips_already_visited_node():
    out = tempfile.mkdtemp()
    called = []
    ex = _explorer(out_dir=out, browser_factory=lambda url: called.append(url))
    ex.run_started_epoch, ex.run_started_iso = 1.0, "x"
    ex._resume_loop_state = {
        "frontier": [(0, 0, 0, 0, "http://shop/seen")],
        "visited": {"http://shop/seen"},
        "queued": {"http://shop/seen"},
        "template_counts": Counter(),
        "seen_content": set(),
        "seq": 1,
        "duplicate_nodes": 0,
        "node_errors": 0,
        "task_stats": {"LOCAL": {"success": 0, "fail": 0, "infeasible": 0},
                       "GOAL": {"success": 0, "fail": 0, "infeasible": 0}},
        "nodes_log": [],
    }

    ex.run("http://shop/seen")

    assert called == []          # already-visited node skipped before browser build
    assert ex.episode == 0       # no episode produced


# --------------------------------------------------------------------------- #
# Overwrite guard (run_webarena helper).
# --------------------------------------------------------------------------- #
def test_resume_guard_rejects_and_accepts():
    from run_webarena import _check_resume_precondition
    out = tempfile.mkdtemp()
    ckpt = os.path.join(out, "checkpoint.pkl")

    # --resume with no checkpoint -> error
    try:
        _check_resume_precondition(out, resume=True)
        assert False
    except ValueError:
        pass

    # no checkpoint, no --resume -> fine (fresh run)
    assert _check_resume_precondition(out, resume=False) is None

    open(ckpt, "wb").write(b"x")

    # checkpoint present but no --resume -> error (don't clobber)
    try:
        _check_resume_precondition(out, resume=False)
        assert False
    except ValueError:
        pass

    # checkpoint present + --resume -> returns the path
    assert _check_resume_precondition(out, resume=True) == ckpt


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
