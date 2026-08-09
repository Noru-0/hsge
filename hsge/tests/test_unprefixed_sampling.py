"""Unprefixed sampling (Go-Browse Alg. 3, lines 24-26).

Every task HSGE collects today is "prefixed": `_solve_with_retries` resets to
the node the task was proposed on, so the agent starts already standing on the
right page. Measured on outputs/wa_eval_shopping_1: 287 of 465 successful
episodes are ONE step, 281 of those a `send_msg_to_user` on the very first LLM
call -- the model never had to navigate, so the dataset teaches it to answer at
step 1 and it stalls at step 3-4 on real eval tasks.

Go-Browse samples each feasible task twice: prefixed (from the node) AND
unprefixed (from the site root), explicitly to "instill long-horizon
task-solving". The unprefixed pass is also what feeds the skill library the
multi-step sub-trajectories it needs: with 1-step successes, segmentation
yields nothing that can recur, so clusters never reach `maturity` and the
operator graph stays empty (7 skills / 2 operators / 1 chain over 179 nodes).

Run: PYTHONPATH=. python -m pytest hsge/tests/test_unprefixed_sampling.py -q
"""
import json

from hsge.llm import HashingEmbedder, MockLLM
from hsge.schema import Step
from hsge.webarena.runtime import WebArenaExplorer

ROOT = "http://site/home"


class _Browser:
    terminated = False

    def __init__(self, url):
        self.url = url

    def reset(self):
        return self.observation()

    def observation(self):
        return {"url": self.url, "axtree": f"page {self.url}", "bids": []}

    def act(self, action):
        return self.observation()

    def screenshot_b64(self, som=False):
        return None

    def links(self):
        return []

    def page_hrefs(self, limit=100):
        return []

    def close(self):
        pass


class _Factory:
    """Records the start URL of every browser the run creates."""

    def __init__(self, fail_on=None):
        self.urls = []
        self.fail_on = fail_on

    def __call__(self, url):
        self.urls.append(url)
        if self.fail_on is not None and url == self.fail_on:
            raise RuntimeError("Page.goto: Timeout 30000ms exceeded")
        return _Browser(url)


class _TaskProposer:
    vision = False
    som = False
    llm = None          # detached like a real backend when checkpointing

    def __init__(self, tasks):
        self.tasks = tasks

    def propose(self, obs, screenshot_b64=None, site_seed=None):
        return list(self.tasks)


class _ScriptedSolver:
    """Succeeds on the tasks named in `wins`, fails on everything else.
    Produces a 3-step trajectory so segmentation has something to work with."""

    def __init__(self, wins):
        self.wins = set(wins)
        self.calls = []            # (task, max_steps) per solve

    def solve(self, browser, task, goal_predicate=None, max_steps=None, subgoals=None):
        self.calls.append((task, max_steps))
        success = task in self.wins
        url = browser.url
        steps = [Step(action="click('1')", url=url, obs_summary="open", axtree="ax1"),
                 Step(action="click('2')", url=url + "/x", obs_summary="filter", axtree="ax2"),
                 Step(action=("send_msg_to_user('done')" if success else "click('3')"),
                      url=url + "/y", obs_summary="answer", axtree="ax3")]
        return (steps, ["ax1", "ax2", "ax3"], [None, None, None],
                {"url": url + "/y", "axtree": "ax3"}, success, False, "")


def _run(tmp_path, tasks, wins, factory=None, **kw):
    factory = factory or _Factory()
    ex = WebArenaExplorer(
        browser_factory=factory, llm=MockLLM(), embedder=HashingEmbedder(),
        out_dir=str(tmp_path), allow_pattern=r"http://site", max_nodes=1,
        terminal_goal=None, goal_max_steps=25, **kw)
    ex.explorer = _TaskProposer(tasks)
    ex.solver = _ScriptedSolver(wins)
    ex.run(ROOT)
    nodes = json.load(open(tmp_path / "nodes.json"))
    return ex, factory, nodes


def test_unprefixed_reruns_only_the_successful_tasks_from_the_root(tmp_path):
    ex, factory, nodes = _run(tmp_path, ["A", "B"], wins=["A"],
                              unprefixed_sampling=True)

    tagged = [(t["tag"], t["task"]) for t in nodes[0]["tasks"]]
    assert tagged == [("LOCAL", "A"), ("LOCAL", "B"), ("UNPREFIXED", "A")]
    # a second browser was opened, at the SITE ROOT -- that is the whole point
    assert factory.urls == [ROOT, ROOT]
    # ...and the rerun got the larger (GOAL-sized) step budget, since it now has
    # to navigate to the page before doing the task
    assert ex.solver.calls[-1] == ("A", 25)


def test_unprefixed_is_off_by_default(tmp_path):
    ex, factory, nodes = _run(tmp_path, ["A", "B"], wins=["A"])

    assert [t["tag"] for t in nodes[0]["tasks"]] == ["LOCAL", "LOCAL"]
    assert factory.urls == [ROOT]           # only the node's own browser


def test_unprefixed_episodes_are_recorded_at_a_higher_difficulty(tmp_path):
    ex, _, nodes = _run(tmp_path, ["A"], wins=["A"], unprefixed_sampling=True)

    rec = next(t for t in nodes[0]["tasks"] if t["tag"] == "UNPREFIXED")
    meta = json.load(open(tmp_path / "episodes" / rec["episode"] / "episode_meta.json"))
    assert meta["metadata"]["difficulty"] == 2      # curriculum: harder than LOCAL
    assert meta["metadata"]["tags"] == ["UNPREFIXED"]


def test_unprefixed_success_feeds_the_skill_library_a_second_time(tmp_path):
    """The starvation chain this fixes: 1-step successes -> no recurring
    sub-trajectory -> no cluster reaches `maturity` -> no operators -> no
    chains. Solving the same task twice from two starting points is what makes
    a cluster recur at all."""
    ex, _, _ = _run(tmp_path, ["A"], wins=["A"], unprefixed_sampling=True)

    from_task_a = [s for s in ex.library.subtrajs.values() if s.source_task == "A"]
    assert len(from_task_a) >= 2      # prefixed pass + unprefixed pass


def test_unprefixed_stats_are_counted_in_their_own_bucket(tmp_path):
    ex, _, _ = _run(tmp_path, ["A", "B"], wins=["A"], unprefixed_sampling=True)

    summary = json.load(open(ex.out_dir + "/summary.json"))
    assert summary["tasks"]["LOCAL"] == {"success": 1, "fail": 1, "infeasible": 0}
    assert summary["tasks"]["UNPREFIXED"] == {"success": 1, "fail": 0, "infeasible": 0}


def test_a_root_browser_that_fails_to_load_skips_the_pass_without_crashing(tmp_path):
    """Same fail-soft contract as node_error: a flaky root URL costs the
    unprefixed pass, never the run."""

    class _FailSecond(_Factory):
        def __call__(self, url):
            self.urls.append(url)
            if len(self.urls) > 1:          # the root browser of the rerun pass
                raise RuntimeError("Page.goto: Timeout 30000ms exceeded")
            return _Browser(url)

    ex, factory, nodes = _run(tmp_path, ["A"], wins=["A"], factory=_FailSecond(),
                              unprefixed_sampling=True)

    assert [t["tag"] for t in nodes[0]["tasks"]] == ["LOCAL"]     # rerun skipped
    events = [json.loads(l)["event"] for l in open(ex.out_dir + "/run_log.jsonl")]
    assert "unprefixed_error" in events
    assert "run_summary" in events                                # run finished
