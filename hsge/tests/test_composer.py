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
                 "outlinks": ["http://s/f/gaming/post1"],
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
    assert validate_task(
        dict(mod, intent="Check the 'notify me' box under Dune review"), kb, []) is None
    mod2 = dict(mod, intent="post another comment under Dune review")
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
