"""SiteKB + NodeDigester: the grounding gate is code (evidence must be a literal
substring of the axtree), not LLM self-report; refs resolve to (value, grounded)."""
import json

from hsge.webarena.digest import (NodeDigester, SiteKB, evidence_grounded,
                                  extract_msg, normalize_ws)


def test_evidence_grounded_is_whitespace_insensitive_substring():
    ax = "[1] link 'Best budget GPU'\n\ttext '183 upvotes'"
    assert evidence_grounded("link 'Best budget GPU'", ax)
    assert evidence_grounded("text  '183   upvotes'", ax)   # ws-normalized
    assert not evidence_grounded("text '999 upvotes'", ax)  # not on the page
    assert not evidence_grounded("", ax)                    # empty evidence


def test_extract_msg():
    assert extract_msg("send_msg_to_user('done: the author is hlz0')") == "done: the author is hlz0"
    assert extract_msg('send_msg_to_user("45")') == "45"
    assert extract_msg("click('1')") == ""


class _DigestLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        assert system.startswith("DIGEST")
        return {"page_type": "forum_listing", "title": "gaming",
                "entities": [
                    {"type": "post", "name": "Best budget GPU",
                     "attrs": {"upvotes": "183"}, "evidence": "link 'Best budget GPU'"},
                    {"type": "post", "name": "Fake post", "attrs": {},
                     "evidence": "link 'not on page'"}],
                "facts": [
                    {"q": "upvotes of Best budget GPU?", "a": "183",
                     "evidence": "text '183 upvotes'"},
                    {"q": "hallucinated?", "a": "yes", "evidence": "nope"}]}


def test_digester_grounds_entities_and_facts_by_code():
    obs = {"url": "http://s/f/gaming",
           "axtree": "[1] link 'Best budget GPU'\n\ttext '183 upvotes'"}
    solved = [{"task": "[INFO] Find the upvote count", "success": True,
               "answer": "183", "final_axtree": "text '183 upvotes'"},
              {"task": "[INFO] Find the moderator", "success": True,
               "answer": "bob", "final_axtree": "text 'nothing here'"}]
    d = NodeDigester(_DigestLLM()).digest(obs, solved)
    assert d["page_type"] == "forum_listing"
    assert [e["grounded"] for e in d["entities"]] == [True, False]
    ax_facts = [f for f in d["facts"] if f["source"] == "axtree"]
    assert [f["grounded"] for f in ax_facts] == [True, False]
    # episode-sourced facts are grounded iff the answer appears in the episode's
    # final axtree
    ep_facts = [f for f in d["facts"] if f["source"] == "episode"]
    assert [(f["a"], f["grounded"]) for f in ep_facts] == [("183", True), ("bob", False)]


def test_sitekb_resolve_ref_and_known_urls(tmp_path):
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 3, "url": "http://s/f/gaming", "outlinks": ["http://s/f/gaming/1"],
                 "entities": [{"type": "post", "name": "Best budget GPU",
                               "attrs": {"author": "hlz0"}, "grounded": True}],
                 "facts": [{"q": "q", "a": "183", "grounded": False}]})
    assert kb.resolve_ref("n3.e0") == ("Best budget GPU", True)
    assert kb.resolve_ref("n3.e0.attrs.author") == ("hlz0", True)
    assert kb.resolve_ref("n3.f0") == ("183", False)
    assert kb.resolve_ref("n3.f9") is None and kb.resolve_ref("bogus") is None
    assert kb.known_urls() == {"http://s/f/gaming", "http://s/f/gaming/1"}
    kb.dump(tmp_path / "kb.json")
    kb2 = SiteKB.load(tmp_path / "kb.json")
    assert kb2.site == "http://s" and kb2.resolve_ref("n3.f0") == ("183", False)
