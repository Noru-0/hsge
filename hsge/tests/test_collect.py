"""GenerationRunner: INFO/NAV run before MOD, verdicts gate `verified`, resume
skips task_ids already on disk, stats land in summary.json['gen'], and the
(expensive) instance reset runs once after the MOD batch."""
import json
import re

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


class _SiteBrowser:
    """URL-addressed fake: per-page axtrees, goto() switches pages; a URL not
    in `pages` renders a not-found page (dead link)."""
    def __init__(self, url, pages):
        self.url, self.pages, self.gotos = url, pages, []
    def reset(self): return self.observation()
    def observation(self):
        return {"url": self.url,
                "axtree": self.pages.get(self.url, "404 Not Found")}
    def act(self, action):
        m = re.match(r"goto\('([^']+)'\)", action or "")
        if m:
            self.url = m.group(1)
            self.gotos.append(self.url)
        return self.observation()
    def eval_js(self, expr): return ""
    def close(self): pass


def _kb_two_pages():
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 1, "url": "http://s/home",
                 "outlinks": ["http://s/page2"], "entities": [], "facts": []})
    kb.add_node({"node_index": 2, "url": "http://s/page2", "outlinks": [],
                 "entities": [],
                 "facts": [{"q": "fact?", "a": "42", "grounded": True,
                            "evidence": "old fact"}]})
    return kb


def test_multihop_info_stale_evidence_on_linked_node_skips(tmp_path):
    # evidence "old fact" no longer on page2 -> stale skip, no solve spent
    pages = {"http://s/home": "home page", "http://s/page2": "fresh content only"}
    task = dict(_task("gen_0000", ra={"must_include": ["42"]}),
                hops=3, answer_fact_refs=["n2.f0"])
    runner = GenerationRunner(lambda url: _SiteBrowser(url, pages), _Solver(),
                              str(tmp_path), HashingEmbedder(), _kb_two_pages(),
                              skill_hints=False)
    stats = runner.run([task])
    assert stats["stale_skipped"] == 1 and stats["attempted"] == 0


def test_multihop_info_live_evidence_solves_from_start_url(tmp_path):
    pages = {"http://s/home": "home page",
             "http://s/page2": "page still shows old fact here"}
    browsers = []
    def factory(url):
        b = _SiteBrowser(url, pages); browsers.append(b); return b
    task = dict(_task("gen_0000", ra={"must_include": ["42"]}),
                hops=3, answer_fact_refs=["n2.f0"])
    runner = GenerationRunner(factory, _Solver(), str(tmp_path),
                              HashingEmbedder(), _kb_two_pages(),
                              skill_hints=False)
    stats = runner.run([task])
    assert stats["attempted"] == 1 and stats["verified"] == 1
    # stale check visited the evidence node, then restored start_url pre-solve
    assert browsers[0].gotos == ["http://s/page2", "http://s/home"]


def test_nav_dead_reference_url_skips_as_stale(tmp_path):
    task = dict(_task("gen_0000", "NAV"), hops=2)
    task["eval"] = {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/gone", "program_html": []}
    runner = GenerationRunner(
        lambda url: _SiteBrowser(url, {"http://s/home": "home page"}), _Solver(),
        str(tmp_path), HashingEmbedder(), _kb_two_pages(), skill_hints=False)
    stats = runner.run([task])
    assert stats["stale_skipped"] == 1 and stats["attempted"] == 0


def test_nav_live_reference_url_still_attempted(tmp_path):
    pages = {"http://s/home": "home page", "http://s/target": "target page"}
    browsers = []
    def factory(url):
        b = _SiteBrowser(url, pages); browsers.append(b); return b
    task = dict(_task("gen_0000", "NAV"), hops=2)
    task["eval"] = {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/target", "program_html": []}
    stats = GenerationRunner(factory, _Solver(), str(tmp_path),
                             HashingEmbedder(), _kb_two_pages(),
                             skill_hints=False).run([task])
    assert stats["attempted"] == 1
    assert browsers[0].gotos == ["http://s/target", "http://s/home"]


class _RedirectBrowser(_SiteBrowser):
    """goto() lands on redirects[target] when mapped (login bounce)."""
    def __init__(self, url, pages, redirects):
        super().__init__(url, pages)
        self.redirects = redirects
    def act(self, action):
        m = re.match(r"goto\('([^']+)'\)", action or "")
        if m:
            self.url = self.redirects.get(m.group(1), m.group(1))
            self.gotos.append(self.url)
        return self.observation()


def test_nav_redirected_reference_url_skips_as_stale(tmp_path):
    # run_04 class: another user's comment-edit page bounces to /login --
    # page exists (no 404 copy), but is unreachable for this account
    pages = {"http://s/home": "home page", "http://s/login": "log in please"}
    redirects = {"http://s/secret/edit": "http://s/login"}
    task = dict(_task("gen_0000", "NAV"), hops=2)
    task["eval"] = {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/secret/edit", "program_html": []}
    runner = GenerationRunner(
        lambda url: _RedirectBrowser(url, pages, redirects), _Solver(),
        str(tmp_path), HashingEmbedder(), _kb_two_pages(), skill_hints=False)
    stats = runner.run([task])
    assert stats["stale_skipped"] == 1 and stats["attempted"] == 0


def test_nav_slug_redirect_is_not_stale(tmp_path):
    # Postmill redirects a stale slug to the canonical one -- same page,
    # slug-blind equal -> must still be attempted
    pages = {"http://s/home": "home page",
             "http://s/f/m/15/real-slug": "target page"}
    redirects = {"http://s/f/m/15/-": "http://s/f/m/15/real-slug"}
    task = dict(_task("gen_0000", "NAV"), hops=2)
    task["eval"] = {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/f/m/15/-", "program_html": []}
    stats = GenerationRunner(
        lambda url: _RedirectBrowser(url, pages, redirects), _Solver(),
        str(tmp_path), HashingEmbedder(), _kb_two_pages(),
        skill_hints=False).run([task])
    assert stats["attempted"] == 1 and stats["stale_skipped"] == 0
