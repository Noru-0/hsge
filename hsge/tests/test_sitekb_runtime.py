"""Phase-1 wiring: every visited node gets its axtree persisted and a digest
added to sitekb.json; a digester crash logs digest_error and does not kill
the run."""
import json

from hsge.llm import HashingEmbedder
from hsge.webarena.runtime import WebArenaExplorer


class _LLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        if system.startswith("PROPOSE"):
            return {"tasks": []}          # no episodes; isolates digest wiring
        if system.startswith("DIGEST"):
            return {"page_type": "page", "title": "home",
                    "entities": [{"type": "link", "name": "next", "attrs": {},
                                  "evidence": "link 'next'"}],
                    "facts": [{"q": "main link?", "a": "next", "evidence": "link 'next'"},
                              {"q": "made up?", "a": "x", "evidence": "absent"}]}
        return {}


class _BoomLLM(_LLM):
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        if system.startswith("DIGEST"):
            raise RuntimeError("digester down")
        return super().complete_json(system, prompt, image_b64, image_detail)


class _Browser:
    def __init__(self, url): self.url = url
    def reset(self): return {"url": self.url, "axtree": "[1] link 'next'", "bids": ["1"]}
    def links(self): return []
    def page_hrefs(self, limit=100): return ["http://site/a"]
    def close(self): pass


def _run(tmp_path, llm):
    WebArenaExplorer(
        browser_factory=_Browser, llm=llm, embedder=HashingEmbedder(),
        out_dir=str(tmp_path), allow_pattern=r"http://site",
        max_nodes=1, max_depth=3, terminal_goal=None,
        agent_llms={"node_digester": llm},
    ).run("http://site/home")


def test_node_digest_lands_in_sitekb_and_axtree_persisted(tmp_path):
    _run(tmp_path, _LLM())
    kb = json.load(open(tmp_path / "sitekb.json"))
    assert kb["site"] == "http://site/home"
    (node,) = kb["nodes"]
    assert node["node_index"] == 1 and node["url"] == "http://site/home"
    assert node["url_template"] == "site/home"
    assert "http://site/a" in node["outlinks"]
    assert [f["grounded"] for f in node["facts"]] == [True, False]
    axp = tmp_path / node["axtree_path"]
    assert axp.read_text() == "[1] link 'next'"


def test_digester_crash_logs_and_run_survives(tmp_path):
    _run(tmp_path, _BoomLLM())
    kb = json.load(open(tmp_path / "sitekb.json"))
    assert kb["nodes"] == []            # no digest, but the KB file still exists
    events = [json.loads(l)["event"] for l in open(tmp_path / "run_log.jsonl")]
    assert "digest_error" in events and "run_summary" in events
