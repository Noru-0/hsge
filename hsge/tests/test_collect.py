"""GenerationRunner: INFO/NAV run before MOD, verdicts gate `verified`, resume
skips task_ids already on disk, stats land in summary.json['gen'], and the
(expensive) instance reset runs once after the MOD batch."""
import json

from hsge.llm import HashingEmbedder
from hsge.schema import Step
from hsge.webarena.collect import GenerationRunner, top_k_skill_hints
from hsge.webarena.digest import SiteKB


class _Browser:
    def __init__(self, url): self.url = url
    def reset(self): return self.observation()
    def observation(self): return {"url": self.url, "axtree": "comment 'hello world'"}
    def act(self, action): return self.observation()
    def eval_js(self, expr): return ""
    def close(self): pass


class _Solver:
    """Answers '42' to everything; the eval spec decides pass/fail."""
    def solve(self, browser, goal, goal_predicate=None, hints=None):
        steps = [Step(action="send_msg_to_user('the answer is 42')",
                      url=browser.url, axtree="ax")]
        return steps, ["ax"], [None], browser.observation(), True


def _task(tid, ttype="INFO", ra=None, ph=None):
    return {"task_id": tid, "intent": f"task {tid}", "type": ttype,
            "start_url": "http://s/home", "hops": 2, "source_nodes": [1],
            "answer_fact_refs": [],
            "eval": {"eval_types": ["string_match"] if ttype == "INFO" else ["program_html"],
                     "reference_answers": ra, "reference_url": None,
                     "program_html": ph or []}}


def test_runner_verifies_orders_and_resets(tmp_path):
    resets = []
    tasks = [_task("gen_0002", "MOD",
                   ph=[{"url": "last", "locator": "",
                        "required_contents": {"must_include": ["hello world"]}}]),
             _task("gen_0000", ra={"must_include": ["42"]}),
             _task("gen_0001", ra={"exact_match": "not this"})]
    runner = GenerationRunner(_Browser, _Solver(), str(tmp_path), HashingEmbedder(),
                              SiteKB(), reset_fn=lambda: resets.append(1),
                              skill_hints=False)
    stats = runner.run(tasks)
    assert stats["attempted"] == 3 and stats["verified"] == 2 and stats["failed"] == 1
    assert resets == [1]                       # once, after the MOD batch
    metas = sorted(
        (json.load(open(p)) for p in tmp_path.glob("episodes/*/episode_meta.json")),
        key=lambda m: m["task_id"])
    assert [(m["task_id"], m["verified"]) for m in metas] == [
        ("gen_0000", True), ("gen_0001", False), ("gen_0002", True)]
    # MOD ran last despite being listed first
    assert metas[2]["task_id"] == "gen_0002"
    ep_dirs = sorted(p.name for p in (tmp_path / "episodes").iterdir())
    mod_meta = json.load(open(tmp_path / "episodes" / ep_dirs[-1] / "episode_meta.json"))
    assert mod_meta["task_id"] == "gen_0002"
    assert json.load(open(tmp_path / "summary.json"))["gen"]["verified"] == 2


def test_runner_resumes_and_skips_done(tmp_path):
    t = _task("gen_0000", ra={"must_include": ["42"]})
    runner = GenerationRunner(_Browser, _Solver(), str(tmp_path), HashingEmbedder(),
                              SiteKB(), skill_hints=False)
    runner.run([t])
    n_eps = len(list((tmp_path / "episodes").iterdir()))
    runner2 = GenerationRunner(_Browser, _Solver(), str(tmp_path), HashingEmbedder(),
                               SiteKB(), skill_hints=False)
    stats = runner2.run([t])
    assert stats["attempted"] == 0
    assert len(list((tmp_path / "episodes").iterdir())) == n_eps


def test_dump_stats_does_not_clobber_existing_summary_keys(tmp_path):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({"nodes_visited": 7, "skills_discovered": 2}))
    t = _task("gen_0000", ra={"must_include": ["42"]})
    GenerationRunner(_Browser, _Solver(), str(tmp_path), HashingEmbedder(),
                     SiteKB(), skill_hints=False).run([t])
    summary = json.load(open(summary_path))
    assert summary["nodes_visited"] == 7 and summary["skills_discovered"] == 2
    assert summary["gen"]["verified"] == 1


def test_top_k_skill_hints():
    skills = [{"name": "open_forum", "description": "open a forum page"},
              {"name": "checkout", "description": "complete a purchase"}]
    hints = top_k_skill_hints(HashingEmbedder(), skills, "go to the gaming forum", k=1)
    assert hints and hints.count("\n") == 0     # exactly one hint line
    assert top_k_skill_hints(HashingEmbedder(), [], "x") is None
