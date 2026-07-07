"""Minimal WebArena-style evaluators: string_match / url_match / program_html.

Verification here is what makes a phase-2 trajectory `verified` for SFT; a
task's eval spec is authored by the TaskComposer and validated against the
SiteKB before any episode runs (composer.validate_task).
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlsplit

from .digest import extract_msg

JUDGE_SYS = (
    "You judge whether a web agent's ANSWER to the given QUESTION conveys the "
    "same information as any of the REFERENCE answers. Return JSON "
    "{\"match\": true|false}. Judge meaning, not wording; a short reference "
    "(\"Yes\", a bare number) is judged as an answer to the QUESTION; numbers "
    "and names must actually agree.")


def normalize_answer(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return text.strip(" .,:;!?'\"")


def extract_answer(steps) -> str:
    for st in reversed(steps or []):
        msg = extract_msg(st.action)
        if msg:
            return msg
    return ""


def _judge_match(answer: str, references: list, judge, question: str = "") -> bool:
    if judge is None or not references or not normalize_answer(answer):
        return False
    out = judge.complete_json(JUDGE_SYS, json.dumps(
        {"question": question, "answer": answer, "references": references}))
    return bool(out.get("match"))


def string_match(answer: str, reference_answers: dict, judge=None,
                 question: str = "") -> bool:
    refs = reference_answers or {}
    na = normalize_answer(answer)
    if "exact_match" in refs:
        target = normalize_answer(str(refs["exact_match"]))
        # Solver answers are full sentences ("done: X is Y"), not bare facts,
        # so also accept the reference as a substring of the answer; when even
        # that fails, fall back to the judge -- most misses are format drift
        # ("score is 1" vs "1 point"), not wrong facts.
        if target and (na == target or target in na):
            return True
        return _judge_match(answer, [str(refs["exact_match"])], judge, question)
    if "must_include" in refs:
        items = refs["must_include"] or []
        if items and all(normalize_answer(str(x)) in na for x in items):
            return True
        # single joined reference: the answer must convey ALL items, and the
        # judge is documented to accept a match against ANY one reference
        return _judge_match(answer, ["; ".join(str(x) for x in items)] if items else [],
                            judge, question)
    if "fuzzy_match" in refs:
        return _judge_match(answer, refs["fuzzy_match"] or [], judge, question)
    return False


def url_match(final_url: str, reference_url: str) -> bool:
    def slug_blind(path: str) -> str:
        # Postmill puts a mutable slug (or '-') right after the numeric id
        # (/f/movies/15/<slug>); a retitle changes the slug, not the id, so
        # that one segment is wildcarded. Everything else compares exactly.
        segs = path.split("/")
        for i, s in enumerate(segs):
            if s.isdigit():
                if i + 1 < len(segs) and segs[i + 1]:
                    segs[i + 1] = "*"
                break
        return "/".join(segs)

    def key(u: str):
        p = urlsplit(u or "")
        return (p.netloc, slug_blind(p.path.rstrip("/") or "/"),
                tuple(sorted(parse_qsl(p.query))))
    return bool(reference_url) and key(final_url) == key(reference_url)


def program_html(browser, specs: list[dict]) -> bool:
    for spec in specs or []:
        url = spec.get("url") or "last"
        if url != "last":
            browser.act(f"goto('{url}')")
        locator = spec.get("locator") or ""
        content = browser.eval_js(locator) if locator else browser.observation()["axtree"]
        text = normalize_answer(str(content))
        required = (spec.get("required_contents") or {}).get("must_include") or []
        if not required or not all(normalize_answer(str(x)) in text for x in required):
            return False
    return bool(specs)


def evaluate(task: dict, answer: str, final_url: str, browser, judge=None) -> tuple[bool, dict]:
    """(verified, per-type details). All declared eval types must pass; a task
    with no eval types can never verify (fail-closed)."""
    ev = task.get("eval") or {}
    details: dict[str, bool] = {}
    for t in ev.get("eval_types") or []:
        if t == "string_match":
            details[t] = string_match(answer, ev.get("reference_answers") or {},
                                      judge=judge,
                                      question=str(task.get("intent") or ""))
        elif t == "url_match":
            details[t] = url_match(final_url, ev.get("reference_url") or "")
        elif t == "program_html":
            details[t] = program_html(browser, ev.get("program_html") or [])
        else:
            details[t] = False
    return bool(details) and all(details.values()), details
