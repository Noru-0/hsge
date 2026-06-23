"""Domain-neutral state abstraction for WebArena pages.

The exploration loop mines operators from differences between start/end
predicates. Keep this vocabulary generic: predicates should describe reusable web
state cues rather than one site's object model.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

PREDICATES = frozenset({
    "has_search_input", "has_form_input", "has_filter_or_sort",
    "has_menu", "has_feedback", "has_numeric_content", "has_record_status",
    "has_progress_control", "has_confirmation_cue",
})

_STOP_SEGMENTS = {
    "www", "app", "home", "index", "main", "page", "pages", "view", "site",
}


def _page_tokens(url: str) -> set[str]:
    """Extract stable, generic path tokens without preserving domain names."""
    parsed = urlparse(url or "")
    raw_segments = [s for s in parsed.path.split("/") if s]
    tokens: set[str] = set()
    for segment in raw_segments[:4]:
        stem = re.sub(r"\.(html?|php|aspx?|jsp)$", "", segment.lower())
        if not stem or stem in _STOP_SEGMENTS:
            continue
        if re.fullmatch(r"\d+|[a-f0-9]{16,}|[a-f0-9-]{24,}", stem):
            tokens.add("page_id")
            continue
        for token in re.findall(r"[a-z][a-z0-9]{2,}", stem):
            if token not in _STOP_SEGMENTS:
                tokens.add(f"path:{token[:32]}")
    return tokens


def predicates_from(url: str, axtree: str = "") -> set[str]:
    p: set[str] = set(_page_tokens(url))
    ax = (axtree or "").lower()
    if re.search(r"\b(searchbox|search)\b", ax):
        p.add("has_search_input")
    if re.search(r"\b(textbox|combobox|checkbox|radio)\b", ax):
        p.add("has_form_input")
    if re.search(r"\b(sort|filter|facet|refine)\b", ax):
        p.add("has_filter_or_sort")
    if re.search(r"\b(menuitem|haspopup|expanded=true|submenu)\b", ax):
        p.add("has_menu")
    if re.search(r"\b(review|rating|feedback|comment|discussion|stars?)\b", ax):
        p.add("has_feedback")
    if re.search(r"\$|amount|cost|total|date|percent|%|\b\d+(?:[.,]\d+)?\b", ax):
        p.add("has_numeric_content")
    if re.search(r"\b(status|history|record|request|case|incident|ticket|order)\b", ax):
        p.add("has_record_status")
    if re.search(r"\b(next|continue|confirm|finish|complete|submit|save|apply)\b", ax):
        p.add("has_progress_control")
    if re.search(r"\b(success|successful|saved|submitted|confirmed|completed|thank you)\b", ax):
        p.add("has_confirmation_cue")
    return p


TERMINALS: dict[str, dict[str, str | None]] = {}


def reached(goal: str, url: str, axtree: str = "") -> bool:
    if not goal:
        return False
    spec = TERMINALS.get(goal)
    if not spec:
        return goal in predicates_from(url, axtree)
    ok = bool(re.search(spec["url"], url))
    if spec["text"]:
        ok = ok and spec["text"] in (axtree or "").lower()
    return ok
