"""Thin BrowserGym wrapper for free-form WebArena exploration.

Uses the 'browsergym/openended' env, which starts at an arbitrary URL and accepts
free-form actions -- exactly what exploration (vs a fixed task) needs.

Requires:  pip install browsergym-core browsergym-webarena && playwright install chromium
and the WA_* env vars pointing at your hosted WebArena (see the runbook).
"""
from __future__ import annotations

import asyncio
import os
import re
from urllib.parse import urljoin, urlparse


def _is_same_origin(base: str, url: str) -> bool:
    """True if `url` has the same scheme+host as `base` (or is relative)."""
    if not url or url.startswith("javascript:") or url.startswith("mailto:"):
        return False
    if url.startswith("/") or not url.startswith("http"):
        return True  # relative URL — resolve later
    try:
        return urlparse(base).netloc == urlparse(url).netloc
    except Exception:
        return False


class WebArenaBrowser:
    def __init__(self, start_url: str, headless: bool = True, timeout_ms: int = 10000,
                 screenshot: bool = False, storage_state: str | None = None):
        import logging
        # Tắt log "Overriding the task's timeout parameter" từ browsergym
        logging.getLogger("browsergym").setLevel(logging.WARNING)
        logging.getLogger("browsergym.core").setLevel(logging.WARNING)
        logging.getLogger("browsergym.core.task").setLevel(logging.ERROR)
        logging.getLogger("gymnasium").setLevel(logging.WARNING)
        import gymnasium as gym
        import browsergym.core            # noqa: registers browsergym/openended
        self._gym = gym
        self.start_url = start_url
        self.timeout_ms = timeout_ms
        self.screenshot_enabled = screenshot
        # Build pw_context_kwargs with storage_state if provided.
        # We pass it BOTH via gym.make() (for initial context creation)
        # AND directly on env.unwrapped.pw_context_kwargs (so env.reset()
        # re-applies it when creating new Playwright contexts).
        pw_context_kwargs = {}
        if storage_state:
            if os.path.isfile(storage_state):
                pw_context_kwargs["storage_state"] = storage_state
                logging.getLogger(__name__).info(
                    f"Using storage_state: {storage_state}"
                )
            else:
                logging.getLogger(__name__).warning(
                    f"storage_state file not found: {storage_state}. "
                    "Proceeding without pre-loaded login state."
                )
        self.env = gym.make(
            "browsergym/openended",
            # OpenEndedTask hardcodes a 10s timeout for its setup goto. Start on
            # a local blank page and navigate ourselves in reset() so the YAML
            # browser.timeout_ms value is actually respected.
            task_kwargs={"start_url": "about:blank"},
            headless=headless,
            timeout=timeout_ms,
            wait_for_user_message=False,
            pw_context_kwargs=pw_context_kwargs,
        )
        # Also set pw_context_kwargs directly on the unwrapped BrowserEnv,
        # matching Go-Browse's pattern (web_explore.py line 696).
        # This ensures storage_state is re-applied every time env.reset()
        # creates a new Playwright context.
        if pw_context_kwargs:
            self.env.unwrapped.pw_context_kwargs.update(pw_context_kwargs)
        self._last_obs = None

    def reset(self) -> dict:
        try:
            self.env.reset()
            page = self.env.unwrapped.page
            page.goto(
                self.start_url,
                timeout=self.timeout_ms,
                wait_until="domcontentloaded",
            )
            obs = self.env.unwrapped._get_obs()
        except Exception as e:
            # Page.goto timeout or other reset failure — return safe fallback
            return {"url": "", "axtree": "", "bids": [], "screenshot_base64": None,
                    "_reset_error": str(e), "_start_url": self.start_url}
        self._last_obs = obs
        return self.observation()

    def observation(self) -> dict:
        from browsergym.utils.obs import flatten_axtree_to_str
        obs = self._last_obs or {}
        try:
            axtree = flatten_axtree_to_str(obs["axtree_object"])
        except Exception:
            axtree = ""
        result = {
            "url": obs.get("url", ""),
            "axtree": axtree,
            "bids": self._extract_bids(axtree),
            "screenshot_base64": None,
        }
        if self.screenshot_enabled:
            try:
                result["screenshot_base64"] = self.env.unwrapped.page.screenshot(
                    type="png", full_page=False,
                )
            except Exception:
                pass
        return result

    def _safe_page_evaluate(self, js: str, default=None):
        """Run page.evaluate with protection against closed browser/page."""
        try:
            page = self.env.unwrapped.page
            if page.is_closed():
                return default
            return page.evaluate(js)
        except Exception:
            return default

    @staticmethod
    def _extract_bids(axtree: str) -> list[str]:
        # bids appear as [123] prefixes in the flattened axtree
        return re.findall(r"\[(\w+)\]", axtree or "")

    def act(self, action: str) -> dict:
        """action is a BrowserGym call string, e.g. click('a51') or fill('b3','x')."""
        try:
            self._last_obs, _, term, trunc, _ = self.env.step(action)
        except Exception:
            # If the browser was closed mid-step (e.g. TargetClosedError),
            # return a safe fallback observation so the caller can exit gracefully.
            return {"url": "", "axtree": "", "bids": [], "screenshot_base64": None}
        return self.observation()

    def links(self) -> list[str]:
        """Extract all same-origin <a href> links from the current page DOM."""
        current_url = self._last_obs.get("url", "") if self._last_obs else ""
        links: set[str] = set()
        try:
            hrefs = self._safe_page_evaluate("""() => {
                const links = [];
                for (const a of document.querySelectorAll('a[href]')) {
                    links.push(a.href);
                }
                return links;
            }""", default=[])
            for href in (hrefs or []):
                if _is_same_origin(current_url, href):
                    # Normalize: strip fragment & trailing slash
                    u = href.split("#")[0].rstrip("/")
                    links.add(u)
        except Exception:
            pass
        # Also include open_pages_urls as fallback
        obs = self._last_obs or {}
        for u in (obs.get("open_pages_urls", []) or []):
            if _is_same_origin(current_url, u):
                links.add(u.rstrip("/"))
        return sorted(links)

    def close(self):
        try:
            self.env.close()
        except (Exception, asyncio.CancelledError):
            pass
