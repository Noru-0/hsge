"""TaskComposer gates are code: INFO answers must be backed by grounded SiteKB
refs, NAV targets must be known URLs, MOD intents pass a denylist and must not
collide on program_html targets. Rejected tasks carry a reason."""
import random

from hsge.webarena.composer import TaskComposer, sample_bundles, validate_task
from hsge.webarena.digest import SiteKB


def _kb():
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 0, "url": "http://s", "page_type": "home",
                 "title": "home", "outlinks": ["http://s/f/gaming", "http://s/f/movies"],
                 "entities": [], "facts": []})
    kb.add_node({"node_index": 1, "url": "http://s/f/gaming",
                 "page_type": "forum", "title": "gaming",
                 "outlinks": ["http://s/f/gaming/post1", "http://s",
                              "http://s/f/gaming/15/a-slug"],
                 "entities": [{"type": "post", "name": "Best budget GPU",
                               "attrs": {"author": "hlz0"}, "grounded": True,
                               "evidence": "Best budget GPU submitted by hlz0"}],
                 "facts": [{"q": "top post?", "a": "Best budget GPU",
                            "grounded": True,
                            "evidence": "top post 'Best budget GPU'"},
                           {"q": "mods?", "a": "bob", "grounded": False,
                            "evidence": "moderated by bob"}]})
    kb.add_node({"node_index": 2, "url": "http://s/f/movies", "page_type": "forum",
                 "title": "movies", "outlinks": [],
                 "entities": [{"type": "post", "name": "Dune review",
                               "attrs": {}, "grounded": True,
                               "evidence": "Dune review"}], "facts": []})
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


def test_info_reference_must_be_inside_cited_evidence():
    kb = _kb()
    # run_04 gen_0064: score "-1" backed by the fact value but absent from
    # the evidence quote -- _is_stale re-grounding can never protect it
    kb.add_node({"node_index": 3, "url": "http://s/f/movies/9/re",
                 "outlinks": [], "entities": [],
                 "facts": [{"q": "score?", "a": "-1", "grounded": True,
                            "evidence": "Re: Your Comment"}]})
    bad = _info(["n3.f0"], {"exact_match": "-1"})
    assert "not inside cited evidence" in validate_task(bad, kb, [])
    # value quoted inside its evidence still passes
    good = _info(["n1.e0.attrs.author"], {"exact_match": "hlz0"})
    assert validate_task(good, kb, []) is None


def test_build_link_graph_and_real_hops():
    from hsge.webarena.composer import build_link_graph, real_hops
    kb = _kb()
    graph = build_link_graph(kb)
    assert graph["http://s"] == {"http://s/f/gaming", "http://s/f/movies"}
    info = _info(["n1.e0.attrs.author"], {"exact_match": "hlz0"})  # start_url "http://s"
    assert real_hops(info, kb, graph) == 1        # http://s -> http://s/f/gaming
    nav = {"type": "NAV", "start_url": "http://s",
           "eval": {"reference_url": "http://s/f/gaming/post1"}}
    assert real_hops(nav, kb, graph) == 2          # http://s -> gaming -> post1
    mod_last = {"type": "MOD", "start_url": "http://s",
                "eval": {"program_html": [{"url": "last"}]}}
    assert real_hops(mod_last, kb, graph) == 0     # no real target -> trivially 0
    unreachable = {"type": "NAV", "start_url": "http://s",
                   "eval": {"reference_url": "http://s/f/movies/9/re"}}
    assert real_hops(unreachable, kb, graph) is None


def test_validate_task_rejects_unreachable_target():
    kb = _kb()
    nav = {"intent": "go to a page nothing links to", "type": "NAV",
           "start_url": "http://s", "hops": 1, "source_nodes": [1],
           "answer_fact_refs": [],
           "eval": {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/f/movies", "program_html": []}}
    kb.add_node({"node_index": 3, "url": "http://s/f/movies/9/re",
                 "outlinks": [], "entities": [], "facts": [
                     {"q": "?", "a": "x", "grounded": True, "evidence": "x here"}]})
    unreachable = dict(nav, eval=dict(nav["eval"], reference_url="http://s/f/movies/9/re"))
    # not linked from anywhere in the KB -> unreachable
    assert "unreachable" in validate_task(unreachable, kb, [])


def test_validate_task_rejects_info_zero_hop_start():
    kb = _kb()
    info = _info(["n1.e0.attrs.author"], {"exact_match": "hlz0"})
    # start_url IS the answer page itself -> 0 real hops, must be rejected
    zero_hop = dict(info, start_url="http://s/f/gaming")
    assert "0 real hops" in validate_task(zero_hop, kb, [])
    # start_url = site root (kb.site) -> 1 real hop, passes
    assert validate_task(info, kb, []) is None


def test_generate_forces_info_start_url_to_site_root_and_sets_real_hops():
    class _LLM:
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            return {"tasks": [
                dict(_info_task("find the author of the top gaming post"),
                     start_url="http://s/f/gaming"),      # LLM proposed the answer page itself
            ]}
    comp = TaskComposer(_LLM(), _kb(), quota={"INFO": 5, "NAV": 0, "MOD": 0})
    accepted, rejected = comp.generate()
    # the override happens BEFORE validation, so start_url is forced back to
    # "http://s" (the site root) regardless of what the LLM proposed, giving
    # a real BFS distance of 1 hop (http://s -> http://s/f/gaming) instead of
    # the LLM's claimed 2 -- and instead of the 0-hop rejection it would have
    # gotten had the LLM's own start_url been trusted
    assert len(accepted) == 1
    assert accepted[0]["start_url"] == "http://s"
    assert accepted[0]["hops"] == 1


def test_single_hop_depth_budget_rejects_surplus_after_share_met():
    # 1 comparable pair setup: 4 nodes total; force a scenario where 3 of 4
    # candidate INFO tasks are 1-hop (same page as start after override is
    # impossible since INFO is always forced to site root -- so use NAV
    # candidates, which can be 1-hop from the root, to fill the single-hop
    # budget, then confirm a further 1-hop NAV gets the new rejection reason).
    kb = _kb()   # http://s -[1 hop]-> gaming, movies; gaming -[1 hop]-> post1 (2 hops)

    def nav(url):
        return {"intent": f"go to {url}", "type": "NAV", "start_url": "http://s",
                "hops": 1, "source_nodes": [1], "answer_fact_refs": [],
                "eval": {"eval_types": ["url_match"], "reference_answers": None,
                         "reference_url": url, "program_html": []}}

    class _LLM:
        def __init__(self):
            self.calls = 0
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            self.calls += 1
            if self.calls == 1:
                return {"tasks": [nav("http://s/f/gaming"), nav("http://s/f/movies")]}
            return {"tasks": [dict(nav("http://s/f/gaming"),
                                    intent="go to gaming forum again")]}

    # total_quota=2 -> min_hops2_share=0.5 -> max_single_hop = round(2*0.5) = 1
    comp = TaskComposer(_LLM(), kb, quota={"INFO": 0, "NAV": 2, "MOD": 0},
                        min_hops2_share=0.5)
    accepted, rejected = comp.generate()
    assert len(accepted) == 1                       # only the budget-allowed 1-hop task
    assert accepted[0]["hops"] == 1
    reasons = [r["reason"] for r in rejected]
    assert "single-hop budget exhausted" in reasons


def test_find_comparable_pairs_across_different_nodes():
    from hsge.webarena.composer import find_comparable_pairs
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 1, "url": "http://s/f/gaming/1", "outlinks": [],
                 "entities": [{"type": "post", "name": "Post A",
                               "attrs": {"comments": "45"}, "grounded": True,
                               "evidence": "Post A has 45 comments"}], "facts": []})
    kb.add_node({"node_index": 2, "url": "http://s/f/gaming/2", "outlinks": [],
                 "entities": [{"type": "post", "name": "Post B",
                               "attrs": {"comments": "10"}, "grounded": True,
                               "evidence": "Post B has 10 comments"}], "facts": []})
    pairs = find_comparable_pairs(kb)
    assert len(pairs) == 1
    assert pairs[0]["attr"] == "comments"
    assert pairs[0]["winner"]["entity"]["name"] == "Post A"
    assert pairs[0]["loser"]["entity"]["name"] == "Post B"


def test_find_comparable_pairs_skips_same_node_and_ungrounded():
    from hsge.webarena.composer import find_comparable_pairs
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 1, "url": "http://s/x", "outlinks": [],
                 "entities": [
                     {"type": "post", "name": "A", "attrs": {"n": "5"}, "grounded": True},
                     {"type": "post", "name": "B", "attrs": {"n": "1"}, "grounded": True}],
                 "facts": []})
    kb.add_node({"node_index": 2, "url": "http://s/y", "outlinks": [],
                 "entities": [{"type": "post", "name": "C", "attrs": {"n": "9"},
                               "grounded": False}], "facts": []})
    pairs = find_comparable_pairs(kb)
    assert pairs == []   # A/B share a node (skipped); C is ungrounded (skipped)


def test_comparison_task_generated_and_verified_by_existing_gates():
    kb = _kb()
    kb.add_node({"node_index": 3, "url": "http://s/f/movies/2", "outlinks": [],
                 "entities": [{"type": "post", "name": "Dune review 2",
                               "attrs": {"comments": "50"}, "grounded": True,
                               "evidence": "Dune review 2 has 50 comments"}], "facts": []})
    # give node 2's "Dune review" a comparable, lower attr value too
    kb.nodes[2]["entities"][0]["attrs"] = {"comments": "10"}
    kb.nodes[2]["entities"][0]["evidence"] = "Dune review has 10 comments"
    # link the movies forum to its new post, like gaming already links to
    # post1/15 -- otherwise node 3 is unreachable and the existing real_hops
    # gate rejects the comparison task outright
    kb.nodes[2]["outlinks"].append("http://s/f/movies/2")

    class _LLM:
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            if system.startswith("Phrase"):
                return {"intent": "Which movie post has more comments, "
                                  "'Dune review' or 'Dune review 2'?"}
            return {"tasks": []}

    comp = TaskComposer(_LLM(), kb, quota={"INFO": 5, "NAV": 0, "MOD": 0})
    accepted, rejected = comp.generate()
    assert len(accepted) == 1
    task = accepted[0]
    assert task["type"] == "INFO"
    assert task["eval"]["reference_answers"] == {"exact_match": "Dune review 2"}
    assert sorted(task["source_nodes"]) == [2, 3]
    assert task["start_url"] == "http://s"
    assert task["hops"] >= 1


def test_comparison_task_falls_back_to_template_when_llm_phrasing_fails_gates():
    kb = _kb()
    kb.add_node({"node_index": 3, "url": "http://s/f/movies/2", "outlinks": [],
                 "entities": [{"type": "post", "name": "Dune review 2",
                               "attrs": {"comments": "50"}, "grounded": True,
                               "evidence": "Dune review 2 has 50 comments"}], "facts": []})
    kb.nodes[2]["entities"][0]["attrs"] = {"comments": "10"}
    kb.nodes[2]["entities"][0]["evidence"] = "Dune review has 10 comments"
    kb.nodes[2]["outlinks"].append("http://s/f/movies/2")

    class _BadLLM:
        """Phrases the comparison with a relative-time reference, which
        RELATIVE_TIME_RE rejects -- the composer must fall back to the
        code-generated template intent instead of dropping the task."""
        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            if system.startswith("Phrase"):
                return {"intent": "Which had more comments 5 minutes ago, "
                                  "'Dune review' or 'Dune review 2'?"}
            return {"tasks": []}

    comp = TaskComposer(_BadLLM(), kb, quota={"INFO": 5, "NAV": 0, "MOD": 0})
    accepted, rejected = comp.generate()
    assert len(accepted) == 1
    assert "minutes ago" not in accepted[0]["intent"]   # template used instead
    assert accepted[0]["intent"].startswith("Which has a higher comments")
