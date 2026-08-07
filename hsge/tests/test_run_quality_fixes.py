"""Regression tests for the five data-quality defects found by auditing the
158-node reddit run (outputs/wa_eval_reddit, 887 episodes).

Each test encodes the measured symptom, not just the mechanism:
  1. tier-0 frontier URLs bypassed the per-template cap  -> 58/158 nodes were one
     forum's comment threads;
  2. a seed capability was attempted once per RUN         -> 7 GOAL tasks total;
  3. INFO was only capped when a page overflowed max_tasks-> 272/560 successes
     were INFO, 237 of them with zero browser actions;
  4. verify_skill claimed verified=True with 0 attempts;
  5. build_sft_dataset kept answer-only episodes.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hsge.schema import ParamSlot, SkillCard, Step, SubTrajectory
from hsge.verification import verify_skill
from hsge.webarena.agents import PageExplorer
from hsge.webarena.runtime import WebArenaExplorer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _StubLLM:
    def __init__(self, reply=None):
        self.reply = reply or {}
        self.prompts = []

    def complete_json(self, system, prompt, **kw):
        self.prompts.append((system, prompt))
        return self.reply


def _explorer(**kw) -> WebArenaExplorer:
    """A runtime instance with every backend stubbed -- we only poke pure logic."""
    return WebArenaExplorer(
        browser_factory=lambda url: None, llm=_StubLLM(), embedder=None,
        out_dir=tempfile.mkdtemp(), allow_pattern=".*", **kw)


# --------------------------------------------------------------- 1. tier-0 cap
def test_tier0_urls_are_template_capped_not_exempt():
    ex = _explorer(per_template_cap=3, reached_template_cap=5)
    assert ex.reached_template_cap == 5
    # Same shape for every comment of one thread: the cap has something to bite on.
    urls = [f"http://h/f/AskReddit/10224/-/comment/{i}" for i in range(20)]
    templates = {ex._url_template(u) for u in urls}
    assert len(templates) == 1, f"expected one template, got {templates}"


def test_reached_cap_defaults_looser_than_mined_cap():
    """Tier 0 is still privileged -- reaching a page while solving is evidence."""
    ex = _explorer()
    assert ex.reached_template_cap > ex.per_template_cap


# ------------------------------------------------- 2. seed capability repeats
def _seeded(explorer, n=2):
    explorer.site_seed = {"description": "", "capabilities": [
        {"name": f"cap{i}", "goal": f"do thing {i}"} for i in range(n)]}
    return explorer


def test_seed_capability_reoffered_on_a_different_page_template():
    ex = _seeded(_explorer(use_site_seed=True, goal_chains_per_node=1,
                           seed_capability_repeats=3))
    first = ex._goal_task("http://h/f/AskReddit")
    again = ex._goal_task("http://h/wiki")
    assert [t["goal"] for t in first] == ["do thing 0"]
    assert [t["goal"] for t in again] == ["do thing 0"], (
        "the same capability must be retryable from a different kind of page")


def test_seed_capability_not_repeated_on_the_same_page_template():
    ex = _seeded(_explorer(use_site_seed=True, goal_chains_per_node=1,
                           seed_capability_repeats=3))
    ex._goal_task("http://h/f/AskReddit/1/-/comment/2")
    # different ids, same shape -> same template -> capability already spent here
    again = ex._goal_task("http://h/f/AskReddit/9/-/comment/8")
    assert [t["goal"] for t in again] == ["do thing 1"]


def test_seed_capability_repeat_cap_is_enforced():
    ex = _seeded(_explorer(use_site_seed=True, goal_chains_per_node=1,
                           seed_capability_repeats=2), n=1)
    goals = []
    # distinct, digit-free paths so each really is a different url template
    for page in ("alpha", "beta", "gamma", "delta", "epsilon"):
        goals += [t["goal"] for t in ex._goal_task(f"http://h/{page}")]
    assert goals == ["do thing 0", "do thing 0"], goals


# --------------------------------------------------------------- 3. INFO cap
def _propose(tasks, max_tasks=9):
    pe = PageExplorer(_StubLLM({"tasks": tasks}), max_tasks=max_tasks)
    return pe.propose({"url": "http://h/", "axtree": "RootWebArea"})


def test_info_capped_even_when_page_is_under_max_tasks():
    """The bug: no overflow -> no truncation -> every INFO proposal survived."""
    tasks = [{"text": f"read fact {i}", "type": "INFO"} for i in range(6)]
    out = _propose(tasks)
    assert len(out) == PageExplorer._INFO_CAP, out


def test_info_cap_does_not_touch_composite_or_mod():
    tasks = ([{"text": f"read fact {i}", "type": "INFO"} for i in range(5)]
             + [{"text": f"do multi {i}", "type": "COMPOSITE"} for i in range(3)]
             + [{"text": f"change {i}", "type": "MOD"} for i in range(2)])
    out = _propose(tasks)
    assert sum(t.startswith("[INFO]") for t in out) == PageExplorer._INFO_CAP
    assert sum(t.startswith("[COMPOSITE]") for t in out) == 3
    assert sum(t.startswith("[MOD]") for t in out) == 2


# ------------------------------------------------------------- 4. verified flag
def _card():
    return SkillCard(name="s", description="d",
                     slots=[ParamSlot(name="b", slot_type="selector")],
                     action_template=["click('{b}')"], precondition="p",
                     success_predicate="q", cluster_id="0", member_ids=[])


def test_skill_not_marked_verified_when_verification_never_ran():
    card = _card()
    admitted = verify_skill(_StubLLM(), card, contexts=[], k=0)
    assert admitted is True, "k=0 must still ADMIT -- WebArena verifies by outcome"
    assert card.verified is False, "but it was never executed, so not 'verified'"
    assert card.stats.n_verify_attempts == 0


# ------------------------------------------------ 5. answer-only episode filter
def _write_episode(root, name, actions, success=True, infeasible=False):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    json.dump({"goal": "[INFO] g", "outcome": {"success": success, "infeasible": infeasible},
               "metadata": {"difficulty": 1}, "step_count": len(actions)},
              open(os.path.join(d, "episode_meta.json"), "w"))
    with open(os.path.join(d, "episode.jsonl"), "w") as f:
        for i, a in enumerate(actions):
            f.write(json.dumps({"record_type": "step", "index": i, "url": "http://h/",
                                "parsed_action": a, "thought": "t",
                                "observation": {}}) + "\n")
    return d


def _build(src, *extra):
    out = os.path.join(src, "train.jsonl")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "build_sft_dataset.py"),
                        src, out, *extra],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    ids = {json.loads(l)["trajectory_id"] for l in open(out) if l.strip()}
    return ids, r.stdout


def test_min_actions_drops_answer_only_episodes():
    with tempfile.TemporaryDirectory() as tmp:
        _write_episode(tmp, "ep_answer", ["send_msg_to_user('42')"])
        _write_episode(tmp, "ep_acting", ["click('68')", "send_msg_to_user('done')"])
        kept, _ = _build(tmp, "--min-actions", "1")
        assert kept == {"ep_acting"}


def test_min_actions_keeps_report_infeasible_episodes():
    with tempfile.TemporaryDirectory() as tmp:
        _write_episode(tmp, "ep_infeasible", ["report_infeasible('nope')"],
                       success=False, infeasible=True)
        kept, _ = _build(tmp, "--min-actions", "1")
        assert kept == {"ep_infeasible"}, "refusing IS the training target here"


def test_min_actions_defaults_to_keeping_everything():
    with tempfile.TemporaryDirectory() as tmp:
        _write_episode(tmp, "ep_answer", ["send_msg_to_user('42')"])
        kept, _ = _build(tmp)
        assert kept == {"ep_answer"}
