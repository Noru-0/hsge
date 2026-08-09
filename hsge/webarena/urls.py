"""Host-independent URLs, shared by the prompt builders and the executor.

A WebArena deployment's host is an accident of where it is running: data was
collected against 192.168.1.31:8080/8023/8081 and evaluated against a
completely different host. Absolute URLs in the prompt (the `URL:` field) and
in `goto` targets therefore teach the model a host it will never see again --
93% of train_all.jsonl's prompts carried the collection host.

The fix is symmetric, which is the only way it stays correct:
  * `site_relative` / `relativize_goto` strip the origin everywhere a URL is
    SHOWN or IMITATED -- used identically by the live Solver prompt
    (agents.py), the offline SFT builder (build_sft_dataset.py) and the thought
    re-annotator, so training and inference see the same shape.
  * `absolutize_goto` puts the CURRENT origin back just before the action is
    executed (browser.py), because Playwright's page.goto needs an absolute URL
    -- BrowserGym configures no baseURL.

Net effect: a `goto` learned on one instance runs unchanged on another.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_GOTO_RE = re.compile(r"^goto\(\s*(['\"])(?P<url>.*?)\1\s*,?\s*\)$", re.DOTALL)


def site_relative(url: str) -> str:
    """`http://host:8080/f/pics?x=1#y` -> `/f/pics?x=1#y`.

    Anything without a scheme+host (already relative, empty, `about:blank`,
    `chrome-error:...`) is returned unchanged -- those are not site URLs and
    rewriting them would destroy information.
    """
    if not url:
        return url
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url
    return urlunsplit(("", "", parts.path or "/", parts.query, parts.fragment))


def _goto_target(action: str) -> str | None:
    m = _GOTO_RE.match((action or "").strip())
    return m.group("url") if m else None


def relativize_goto(action: str, page_url: str) -> str:
    """Rewrite a SAME-ORIGIN `goto('http://host/p')` to `goto('/p')`.

    An off-origin target is left exactly as it is: it ends a WebArena episode
    at reward 0 and is dropped as a training target upstream, so quietly
    rewriting it into a legal same-site action would hide the defect instead of
    removing it.
    """
    target = _goto_target(action)
    if target is None:
        return action
    t, base = urlsplit(target), urlsplit(page_url or "")
    if not t.netloc or t.netloc != base.netloc:
        return action
    return f"goto('{site_relative(target)}')"


def absolutize_goto(action: str, page_url: str) -> str:
    """Inverse of `relativize_goto`, applied at execution time: resolve
    `goto('/p')` against the origin of the page the agent is currently on."""
    target = _goto_target(action)
    if target is None or not page_url:
        return action
    if urlsplit(target).netloc:
        return action
    base = urlsplit(page_url)
    if not base.scheme or not base.netloc:
        return action
    t = urlsplit(target)
    return f"goto('{urlunsplit((base.scheme, base.netloc, t.path, t.query, t.fragment))}')"
