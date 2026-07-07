"""TaskComposer: generate WebArena-style tasks (with eval specs) from a SiteKB.

Generation is per "context bundle" (a few related node digests), never the
whole KB in one prompt, so multi-hop tasks are grounded in pages that really
link together. Hard gates are code: INFO reference answers must be backed by
grounded SiteKB refs, NAV targets must be known URLs, MOD intents pass a
denylist, are self-verifying (must_include quoted in the intent, empty
locator, known target URL), and must not collide on program_html targets.
"""
from __future__ import annotations

import json
import random
import re

from .evaluator import normalize_answer, url_key

MOD_DENY_RE = re.compile(
    r"\b(delete|remove|erase|logout|log\s*out|password|ban|deactivate|wipe)\b", re.I)
# Read-only phrasings the model keeps typing as MOD ("Check if the checkbox is
# unchecked..."): they mutate nothing, so program_html can only ever assert
# pre-existing state. Narrow on purpose -- "Check the 'notify me' box" is a
# legitimate MOD and must not match.
MOD_READONLY_RE = re.compile(
    r"^\s*(?:check|verify|find\s+out)\s+(?:if|whether)\b|^\s*(?:is|are|does|do)\s+there\b",
    re.I)
_PUNCT_RE = re.compile(r"[^\w\s]")

COMPOSER_SYS = (
    "COMPOSE realistic WebArena-style tasks for a web agent from the site knowledge "
    'below. Return JSON {"tasks": [{"intent": str, "type": "INFO"|"NAV"|"MOD", '
    '"start_url": str, "hops": int, "source_nodes": [int], "answer_fact_refs": [str], '
    '"eval": {"eval_types": [str], "reference_answers": object|null, '
    '"reference_url": str|null, "program_html": [object]}}]}.\n'
    "Rules:\n"
    "- intent reads like a real user request; prefer multi-hop (hops = pages the "
    "agent must traverse to solve it). Never put the answer in the intent text.\n"
    '- INFO: eval_types=["string_match"]; reference_answers is {"exact_match": str} '
    'or {"must_include": [str, ...]}; the reference must be the fact/entity VALUE '
    "copied verbatim from the knowledge -- never Yes/No, never reworded or "
    'reformatted; answer_fact_refs cites the knowledge refs the answer comes from '
    '(e.g. "n12.f3", "n13.e1.attrs.author") -- ONLY items shown with grounded=true.\n'
    '- NAV: eval_types=["url_match"]; reference_url must be a URL from the knowledge.\n'
    '- MOD: must PERFORM a state-changing action (post, edit, subscribe, vote, ...); '
    'a read-only question ("check if/whether ...") is INFO, not MOD. The intent MUST '
    'quote, verbatim, the literal text the change will leave visible on the page '
    '(the comment/reply body you choose, or the expected button/label text after '
    'the toggle). eval_types=["program_html"]; entries are {"url": <a knowledge URL '
    'where the change will be visible, or "last">, "locator": "", '
    '"required_contents": {"must_include": [<exactly that quoted text>]}}. '
    'Never destructive (no delete/remove/logout/password/ban).\n'
    "- Do not repeat or trivially rephrase ALREADY GENERATED intents.")


def _norm_intent(text: str) -> str:
    return re.sub(r"\s+", " ", _PUNCT_RE.sub("", (text or "").lower())).strip()


def _mod_target_urls(task: dict) -> set[str]:
    urls = {p.get("url") for p in (task.get("eval") or {}).get("program_html") or []}
    return {u for u in urls if u and u != "last"}


def sample_bundles(kb, rng: random.Random, max_nodes: int = 4) -> list[list[dict]]:
    """Link-neighborhood bundles (a node + KB nodes it links to) plus
    same-entity-type bundles (e.g. every node holding 'post' entities)."""
    rich = [n for n in kb.nodes if (n.get("entities") or n.get("facts"))]
    by_url = {n.get("url"): n for n in kb.nodes}
    by_idx = {n.get("node_index"): n for n in kb.nodes}
    bundles: list[list[dict]] = []
    for n in rich:
        linked = [by_url[u] for u in (n.get("outlinks") or [])
                  if u in by_url and by_url[u] is not n]
        bundles.append([n] + linked[: max_nodes - 1])
    by_type: dict[str, set[int]] = {}
    for n in rich:
        for e in n.get("entities") or []:
            by_type.setdefault(str(e.get("type") or ""), set()).add(n["node_index"])
    for _t, idxs in sorted(by_type.items()):
        if len(idxs) >= 2:
            bundles.append([by_idx[i] for i in sorted(idxs)[:max_nodes]])
    rng.shuffle(bundles)
    return bundles


def validate_task(task, kb, accepted: list[dict]) -> str | None:
    """Rejection reason, or None when the task passes every code gate."""
    if not isinstance(task, dict):
        return "not an object"
    intent = str(task.get("intent") or "")
    ttype = task.get("type")
    if ttype not in ("INFO", "NAV", "MOD"):
        return "bad type"
    if not intent.strip():
        return "empty intent"
    key = _norm_intent(intent)
    if any(_norm_intent(a.get("intent", "")) == key for a in accepted):
        return "duplicate intent"
    ev = task.get("eval") or {}
    types = ev.get("eval_types") or []
    if ttype == "INFO":
        if "string_match" not in types:
            return "INFO without string_match"
        refs = task.get("answer_fact_refs") or []
        if not refs:
            return "INFO without answer_fact_refs"
        resolved = []
        for r in refs:
            got = kb.resolve_ref(r)
            if got is None:
                return f"unknown ref {r}"
            val, grounded = got
            if not grounded:
                return f"ungrounded ref {r}"
            resolved.append(normalize_answer(val))
        ra = ev.get("reference_answers") or {}
        targets = ([ra["exact_match"]] if "exact_match" in ra
                   else ra.get("must_include") or [])
        if not targets:
            return "INFO without reference answer"
        for t in targets:
            nt = normalize_answer(str(t))
            if not any(nt == v or nt in v for v in resolved):
                return f"reference answer {t!r} not backed by refs"
    elif ttype == "NAV":
        if "url_match" not in types:
            return "NAV without url_match"
        if ev.get("reference_url") not in kb.known_urls():
            return "reference_url not in SiteKB"
        if url_key(ev.get("reference_url") or "") == url_key(
                task.get("start_url") or kb.site):
            return "NAV reference_url equals start_url"
    else:  # MOD
        if MOD_DENY_RE.search(intent):
            return "destructive MOD intent"
        if MOD_READONLY_RE.search(intent):
            return "read-only intent typed as MOD"
        if "program_html" not in types or not ev.get("program_html"):
            return "MOD without program_html"
        ni = normalize_answer(intent)
        known = kb.known_urls()
        for spec in ev.get("program_html") or []:
            if spec.get("locator"):
                return "MOD locator must be empty (whole-page check)"
            url = spec.get("url") or "last"
            if url != "last" and url not in known:
                return "MOD program_html url not in SiteKB"
            required = (spec.get("required_contents") or {}).get("must_include") or []
            if not required:
                return "MOD without must_include"
            for s in required:
                if normalize_answer(str(s)) not in ni:
                    return f"must_include {s!r} not quoted in intent"
        mine = _mod_target_urls(task)
        for a in accepted:
            if a.get("type") == "MOD" and mine & _mod_target_urls(a):
                return "MOD target collides with an accepted MOD task"
    return None


class TaskComposer:
    def __init__(self, llm, kb, quota: dict | None = None, hops: tuple = (2, 4),
                 tasks_per_call: int = 5, seed: int = 0):
        self.llm = llm
        self.kb = kb
        self.quota = dict(quota or {"INFO": 60, "NAV": 20, "MOD": 20})
        self.hops = hops
        self.tasks_per_call = tasks_per_call
        self.rng = random.Random(seed)

    def _render_bundle(self, bundle: list[dict]) -> str:
        view = []
        for n in bundle:
            view.append({
                "node_index": n["node_index"], "url": n.get("url"),
                "page_type": n.get("page_type"), "title": n.get("title"),
                "entities": [dict(e, ref=f"n{n['node_index']}.e{i}")
                             for i, e in enumerate(n.get("entities") or [])],
                "facts": [dict(f, ref=f"n{n['node_index']}.f{i}")
                          for i, f in enumerate(n.get("facts") or [])],
                "outlinks": (n.get("outlinks") or [])[:20]})
        return json.dumps(view, indent=1)

    def generate(self) -> tuple[list[dict], list[dict]]:
        accepted: list[dict] = []
        rejected: list[dict] = []
        remaining = dict(self.quota)
        for bundle in sample_bundles(self.kb, self.rng):
            if all(v <= 0 for v in remaining.values()):
                break
            prompt = (f"SITE: {self.kb.site}\nQUOTA REMAINING: {remaining}\n"
                      f"PREFERRED HOPS: {self.hops[0]}-{self.hops[1]}\n\n"
                      f"SITE KNOWLEDGE (this bundle):\n{self._render_bundle(bundle)}\n\n"
                      "ALREADY GENERATED:\n"
                      + ("\n".join(f"- {a['intent']}" for a in accepted[-30:]) or "(none)")
                      + f"\n\nGenerate up to {self.tasks_per_call} tasks from THIS bundle.")
            out = self.llm.complete_json(COMPOSER_SYS, prompt) or {}
            for t in out.get("tasks") or []:
                reason = None
                if isinstance(t, dict) and remaining.get(t.get("type"), 0) <= 0:
                    reason = "quota exhausted for type"
                reason = reason or validate_task(t, self.kb, accepted)
                if reason:
                    rejected.append({"task": t, "reason": reason})
                    continue
                t["task_id"] = f"gen_{len(accepted):04d}"
                t.setdefault("start_url", self.kb.site)
                t.setdefault("hops", 1)
                accepted.append(t)
                remaining[t["type"]] -= 1
        return accepted, rejected
