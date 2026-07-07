"""Node digests and the Site Knowledge Base (SiteKB).

Phase 1 distills every visited node into a digest (page_type, entities, facts,
outlinks). The load-bearing anti-hallucination layer is CODE, not the LLM:
every entity/fact must quote `evidence`, and evidence_grounded() checks it is a
literal (whitespace-normalized) substring of the page's axtree. Only
`grounded: true` items may back a generated task's reference answer
(see composer.validate_task). Spec:
docs/superpowers/specs/2026-07-07-semantic-trajectory-two-phase-design.md
"""
from __future__ import annotations

import json
import re

_WS_RE = re.compile(r"\s+")
_MSG_RE = re.compile(r"send_msg_to_user\(\s*['\"](.*?)['\"]\s*\)", re.S)
_REF_RE = re.compile(r"^n(\d+)\.(?:f(\d+)|e(\d+)(?:\.attrs\.([\w-]+))?)$")

DIGEST_SYS = (
    "DIGEST this web page into structured site knowledge. Return JSON "
    '{"page_type": str, "title": str, '
    '"entities": [{"type": str, "name": str, "attrs": {str: str}, "evidence": str}], '
    '"facts": [{"q": str, "a": str, "evidence": str}]}.\n'
    "Rules:\n"
    "- page_type and entity type are short snake_case labels you choose "
    "(e.g. forum_listing, post, user, product).\n"
    "- evidence is REQUIRED for every entity and fact: quote the exact axtree text "
    "(a contiguous snippet) that supports it. Items whose evidence is not literally "
    "on the page get discarded, so never paraphrase.\n"
    "- facts are question/answer pairs a user could ask about THIS page; the answer "
    "must be visible on the page and must appear inside the evidence.\n"
    "- The solved-task results below are hints only; repeat one as a fact only if "
    "its answer is visible in the axtree.")


def normalize_ws(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def evidence_grounded(evidence: str, axtree: str) -> bool:
    ev = normalize_ws(evidence)
    return bool(ev) and ev in normalize_ws(axtree)


def extract_msg(action: str) -> str:
    m = _MSG_RE.search(action or "")
    return m.group(1) if m else ""


class SiteKB:
    def __init__(self, site: str = ""):
        self.site = site
        self.nodes: list[dict] = []
        self.skills: list[dict] = []

    def add_node(self, node: dict):
        self.nodes.append(node)

    def node_by_index(self, idx: int) -> dict | None:
        return next((n for n in self.nodes if n.get("node_index") == idx), None)

    def resolve_ref(self, ref: str) -> tuple[str, bool] | None:
        """(value, grounded) for a ref like n12.f3 / n13.e1 / n13.e1.attrs.author."""
        m = _REF_RE.match(ref or "")
        if not m:
            return None
        node = self.node_by_index(int(m.group(1)))
        if node is None:
            return None
        if m.group(2) is not None:
            facts = node.get("facts") or []
            i = int(m.group(2))
            if i >= len(facts):
                return None
            return str(facts[i].get("a", "")), bool(facts[i].get("grounded"))
        ents = node.get("entities") or []
        i = int(m.group(3))
        if i >= len(ents):
            return None
        ent = ents[i]
        if m.group(4):
            val = (ent.get("attrs") or {}).get(m.group(4))
            if val is None:
                return None
            return str(val), bool(ent.get("grounded"))
        return str(ent.get("name", "")), bool(ent.get("grounded"))

    def known_urls(self) -> set[str]:
        urls: set[str] = set()
        for n in self.nodes:
            urls.add(n.get("url") or "")
            urls.update(n.get("outlinks") or [])
        urls.discard("")
        return urls

    def to_dict(self) -> dict:
        return {"site": self.site, "nodes": self.nodes, "skills": self.skills}

    def dump(self, path):
        json.dump(self.to_dict(), open(path, "w"), indent=2)

    @classmethod
    def load(cls, path) -> "SiteKB":
        d = json.load(open(path))
        kb = cls(d.get("site", ""))
        kb.nodes = d.get("nodes") or []
        kb.skills = d.get("skills") or []
        return kb


class NodeDigester:
    def __init__(self, llm, max_entities: int = 20, max_facts: int = 10):
        self.llm = llm
        self.max_entities = max_entities
        self.max_facts = max_facts

    def digest(self, obs: dict, solved: list[dict]) -> dict:
        """One LLM call -> digest with code-checked `grounded` flags.

        solved items ({"task","success","answer","final_axtree"}) become
        episode-sourced facts; those are grounded iff the answer text appears
        in that episode's FINAL axtree (the page the answer was read from),
        never on the LLM's say-so.
        """
        solved_txt = "\n".join(
            f"- task: {s['task']!r} success={s['success']} answer={s['answer']!r}"
            for s in solved) or "(none)"
        prompt = (f"URL: {obs['url']}\n\nSOLVED TASKS ON THIS PAGE:\n{solved_txt}"
                  f"\n\nPAGE (accessibility tree):\n{obs['axtree'][:8000]}")
        out = self.llm.complete_json(DIGEST_SYS, prompt) or {}
        axtree = obs.get("axtree", "")
        entities = []
        for e in (out.get("entities") or [])[: self.max_entities]:
            if not isinstance(e, dict) or not e.get("name"):
                continue
            ev = str(e.get("evidence") or "")
            entities.append({
                "type": str(e.get("type") or "unknown"), "name": str(e["name"]),
                "attrs": {str(k): str(v) for k, v in (e.get("attrs") or {}).items()},
                "evidence": ev, "grounded": evidence_grounded(ev, axtree)})
        facts = []
        for f in (out.get("facts") or [])[: self.max_facts]:
            if not isinstance(f, dict) or not f.get("q"):
                continue
            ev = str(f.get("evidence") or "")
            facts.append({"q": str(f["q"]), "a": str(f.get("a", "")), "source": "axtree",
                          "evidence": ev, "grounded": evidence_grounded(ev, axtree)})
        for s in solved:
            if s.get("success") and s.get("answer"):
                facts.append({"q": s["task"], "a": s["answer"], "source": "episode",
                              "evidence": s["answer"],
                              "grounded": evidence_grounded(s["answer"],
                                                            s.get("final_axtree", ""))})
        return {"url": obs.get("url", ""), "page_type": str(out.get("page_type") or "unknown"),
                "title": str(out.get("title") or ""), "entities": entities, "facts": facts}
