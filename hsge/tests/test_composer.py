"""TaskComposer gates are code: INFO answers must be backed by grounded SiteKB
refs, NAV targets must be known URLs, MOD intents pass a denylist and must not
collide on program_html targets. Rejected tasks carry a reason."""
import random

from hsge.webarena.composer import TaskComposer, sample_bundles, validate_task
from hsge.webarena.digest import SiteKB


def _kb():
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 1, "url": "http://s/f/gaming",
                 "page_type": "forum", "title": "gaming",
                 "outlinks": ["http://s/f/gaming/post1", "http://s",
                              "http://s/f/gaming/15/a-slug"],
                 "entities": [{"type": "post", "name": "Best budget GPU",
                               "attrs": {"author": "hlz0"}, "grounded": True}],
                 "facts": [{"q": "top post?", "a": "Best budget GPU", "grounded": True},
                           {"q": "mods?", "a": "bob", "grounded": False}]})
    kb.add_node({"node_index": 2, "url": "http://s/f/movies", "page_type": "forum",
                 "title": "movies", "outlinks": [],
                 "entities": [{"type": "post", "name": "Dune review",
                               "attrs": {}, "grounded": True}], "facts": []})
    return kb


def _info(refs, ra):
    return {"intent": "find the author of the top post in gaming", "type": "INFO",
            "start_url": "http://s", "hops": 2, "source_nodes": [1],
            "answer_fact_refs": refs,
            "eval": {"eval_types": ["string_match"], "reference_answers": ra,
                     "reference_url": None, "program_html": []}}


def test_validate_info_gates():
    kb = _kb()
    assert validate_task(_info(["n1.e0.attrs.author"], {"exact_match": "hlz0"}), kb, []) is None
    assert "ungrounded" in validate_task(_info(["n1.f1"], {"exact_match": "bob"}), kb, [])
    assert "unknown ref" in validate_task(_info(["n9.f0"], {"exact_match": "x"}), kb, [])
    assert "not backed" in validate_task(
        _info(["n1.e0.attrs.author"], {"exact_match": "someone else"}), kb, [])
    assert "without answer_fact_refs" in validate_task(_info([], {"exact_match": "x"}), kb, [])


def test_validate_nav_mod_and_dedup():
    kb = _kb()
    nav = {"intent": "go to the first gaming post", "type": "NAV", "start_url": "http://s",
           "hops": 2, "source_nodes": [1], "answer_fact_refs": [],
           "eval": {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/f/gaming/post1", "program_html": []}}
    assert validate_task(nav, kb, []) is None
    nav_bad = dict(nav, eval=dict(nav["eval"], reference_url="http://elsewhere"))
    assert "not in SiteKB" in validate_task(nav_bad, kb, [])

    mod = {"intent": "post a comment saying hello under Dune review", "type": "MOD",
           "start_url": "http://s", "hops": 2, "source_nodes": [2], "answer_fact_refs": [],
           "eval": {"eval_types": ["program_html"], "reference_answers": None,
                    "reference_url": None,
                    "program_html": [{"url": "http://s/f/movies", "locator": "",
                                      "required_contents": {"must_include": ["hello"]}}]}}
    assert validate_task(mod, kb, []) is None
    assert "destructive" in validate_task(dict(mod, intent="delete the Dune review"), kb, [])
    # read-only phrasings typed as MOD are rejected (they mutate nothing) ...
    assert "read-only" in validate_task(
        dict(mod, intent="Check if the 'Formatting help' checkbox is unchecked"), kb, [])
    assert "read-only" in validate_task(
        dict(mod, intent="Verify whether there is an RSS link"), kb, [])
    # ... but an imperative "Check the X box" is a real MOD and still passes
    mod_check = dict(mod, intent="Check the 'notify me' box under Dune review",
                     eval={"eval_types": ["program_html"], "reference_answers": None,
                           "reference_url": None,
                           "program_html": [{"url": "http://s/f/movies", "locator": "",
                                             "required_contents":
                                                 {"must_include": ["notify me"]}}]})
    assert validate_task(mod_check, kb, []) is None
    mod2 = dict(mod, intent="post another comment saying hello under the Dune thread")
    assert "collides" in validate_task(mod2, kb, [dict(mod, task_id="gen_0000")])
    assert "duplicate" in validate_task(dict(mod), kb, [dict(mod, task_id="gen_0000")])


def test_sample_bundles_links_and_types():
    bundles = sample_bundles(_kb(), random.Random(0))
    # link-neighborhood bundles + one same-entity-type ("post") bundle
    assert any(len(b) == 2 and {n["node_index"] for n in b} == {1, 2} for b in bundles)


class _ComposerLLM:
    def __init__(self): self.calls = 0
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        assert system.startswith("COMPOSE")
        self.calls += 1
        return {"tasks": [
            _info_task("find the author of the top gaming post"),
            _info_task("find the author of the top gaming post"),      # dup -> rejected
            dict(_info_task("tell me the moderator"),
                 answer_fact_refs=["n1.f1"]),                           # ungrounded -> rejected
        ]}


def _info_task(intent):
    return {"intent": intent, "type": "INFO", "start_url": "http://s", "hops": 2,
            "source_nodes": [1], "answer_fact_refs": ["n1.e0.attrs.author"],
            "eval": {"eval_types": ["string_match"],
                     "reference_answers": {"exact_match": "hlz0"},
                     "reference_url": None, "program_html": []}}


def test_generate_assigns_ids_and_collects_rejections():
    comp = TaskComposer(_ComposerLLM(), _kb(), quota={"INFO": 5, "NAV": 0, "MOD": 0})
    accepted, rejected = comp.generate()
    assert [t["task_id"] for t in accepted] == ["gen_0000"]
    assert len(rejected) >= 2
    assert all(r["reason"] for r in rejected)


def test_validate_mod_self_verifying_gates():
    kb = _kb()
    def mod(intent, ph):
        return {"intent": intent, "type": "MOD", "start_url": "http://s", "hops": 2,
                "source_nodes": [2], "answer_fact_refs": [],
                "eval": {"eval_types": ["program_html"], "reference_answers": None,
                         "reference_url": None, "program_html": ph}}
    good = mod('post a comment saying "great movie" under Dune review',
               [{"url": "http://s/f/movies", "locator": "",
                 "required_contents": {"must_include": ["great movie"]}}])
    assert validate_task(good, kb, []) is None
    # run_03 gen_0091: prose assertion the DOM will never contain
    prose = mod("post a new comment on the Dune review",
                [{"url": "last", "locator": "",
                  "required_contents": {"must_include": ["comment posted successfully"]}}])
    assert "not quoted in intent" in validate_task(prose, kb, [])
    # run_03 gen_0099: jQuery pseudo-selector locator
    jq = mod('add a comment saying "nice" under Dune review',
             [{"url": "last", "locator": "a:contains('Create forum')",
               "required_contents": {"must_include": ["nice"]}}])
    assert "locator" in validate_task(jq, kb, [])
    unknown = mod('post a comment saying "nice" under Dune review',
                  [{"url": "http://elsewhere/x", "locator": "",
                    "required_contents": {"must_include": ["nice"]}}])
    assert "not in SiteKB" in validate_task(unknown, kb, [])
    empty = mod('post a comment saying "nice" under Dune review',
                [{"url": "last", "locator": "",
                  "required_contents": {"must_include": []}}])
    assert "without must_include" in validate_task(empty, kb, [])


def test_validate_nav_rejects_self_referential_target():
    kb = _kb()
    # run_04 gen_0004: "Go to the Messages page from the notifications page"
    # with reference_url == start_url -- unwinnable as specified
    nav = {"intent": "Go to the Messages page from the notifications page.",
           "type": "NAV", "start_url": "http://s/f/gaming", "hops": 1,
           "source_nodes": [1], "answer_fact_refs": [],
           "eval": {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/f/gaming", "program_html": []}}
    assert "equals start_url" in validate_task(nav, kb, [])
    # slug drift must not hide the self-reference (slug-blind compare)
    slugged = dict(nav, start_url="http://s/f/gaming/15/b-slug",
                   eval=dict(nav["eval"],
                             reference_url="http://s/f/gaming/15/a-slug"))
    assert "equals start_url" in validate_task(slugged, kb, [])
    # missing start_url falls back to kb.site
    rootless = dict(nav, eval=dict(nav["eval"], reference_url="http://s"))
    del rootless["start_url"]
    assert "equals start_url" in validate_task(rootless, kb, [])
    # a genuine target elsewhere still passes
    ok = dict(nav, eval=dict(nav["eval"],
                             reference_url="http://s/f/gaming/post1"))
    assert validate_task(ok, kb, []) is None


def test_relative_time_and_site_mechanics_gates():
    kb = _kb()
    info = _info(["n1.e0.attrs.author"], {"exact_match": "hlz0"})
    # run_04 gen_0074: intent goes stale the moment it is written
    assert "relative-time" in validate_task(
        dict(info, intent="Find the text of the comment by MarvelsGrantMan136 "
                          "written 17 minutes ago"), kb, [])
    nav = {"intent": "Go to the post submitted yesterday", "type": "NAV",
           "start_url": "http://s", "hops": 2, "source_nodes": [1],
           "answer_fact_refs": [],
           "eval": {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/f/gaming/post1",
                    "program_html": []}}
    assert "relative-time" in validate_task(nav, kb, [])
    # run_04 gen_0014/0048/0082: Postmill UI trivia the solver misreads
    assert "site-mechanics" in validate_task(
        dict(info, intent="Find the short URL for the post titled "
                          "'New Edited Title Here'"), kb, [])
    assert "site-mechanics" in validate_task(
        dict(info, intent="Is there an RSS link on the gaming forum page"),
        kb, [])
    # content questions with absolute wording still pass
    assert validate_task(
        dict(info, intent="Find the author of the top gaming post"),
        kb, []) is None
