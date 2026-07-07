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
    "You judge whether a web agent's ANSWER conveys the same information as any "
    "of the REFERENCE answers. Return JSON {\"match\": true|false}. Judge meaning, "
    "not wording; numbers and names must actually agree.")


def normalize_answer(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return text.strip(" .,:;!?'\"")


def extract_answer(steps) -> str:
    for st in reversed(steps or []):
        msg = extract_msg(st.action)
        if msg:
            return msg
    return ""


def string_match(answer: str, reference_answers: dict, judge=None) -> bool:
    refs = reference_answers or {}
    na = normalize_answer(answer)
    if "exact_match" in refs:
        return na == normalize_answer(str(refs["exact_match"]))
    if "must_include" in refs:
        items = refs["must_include"] or []
        return bool(items) and all(normalize_answer(str(x)) in na for x in items)
    if "fuzzy_match" in refs and judge is not None:
        out = judge.complete_json(JUDGE_SYS, json.dumps(
            {"answer": answer, "references": refs["fuzzy_match"]}))
        return bool(out.get("match"))
    return False


def url_match(final_url: str, reference_url: str) -> bool:
    def key(u: str):
        p = urlsplit(u or "")
        return (p.netloc, (p.path.rstrip("/") or "/"), tuple(sorted(parse_qsl(p.query))))
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
            details[t] = string_match(answer, ev.get("reference_answers") or {}, judge=judge)
        elif t == "url_match":
            details[t] = url_match(final_url, ev.get("reference_url") or "")
        elif t == "program_html":
            details[t] = program_html(browser, ev.get("program_html") or [])
        else:
            details[t] = False
    return bool(details) and all(details.values()), details
