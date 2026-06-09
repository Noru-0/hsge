"""Thin BrowserGym wrapper for free-form WebArena exploration.

Uses the 'browsergym/openended' env, which starts at an arbitrary URL and accepts
free-form actions -- exactly what exploration (vs a fixed task) needs.

Requires:  pip install browsergym-core browsergym-webarena && playwright install chromium
and the WA_* env vars pointing at your hosted WebArena (see the runbook).
"""
from __future__ import annotations

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
    def __init__(self, start_url: str, headless: bool = True, timeout_ms: int = 10000):
        import gymnasium as gym
        import browsergym.core            # noqa: registers browsergym/openended
        self._gym = gym
        self.env = gym.make(
            "browsergym/openended",
            task_kwargs={"start_url": start_url},
            headless=headless,
            timeout=timeout_ms,
            wait_for_user_message=False,
        )
        self._last_obs = None

    def reset(self) -> dict:
        obs, _ = self.env.reset()
        self._last_obs = obs
        return self.observation()

    def observation(self) -> dict:
        from browsergym.utils.obs import flatten_axtree_to_str
        obs = self._last_obs or {}
        try:
            axtree = flatten_axtree_to_str(obs["axtree_object"])
        except Exception:
            axtree = ""
        return {
            "url": obs.get("url", ""),
            "axtree": axtree,
            "bids": self._extract_bids(axtree),
        }

    @staticmethod
    def _extract_bids(axtree: str) -> list[str]:
        # bids appear as [123] prefixes in the flattened axtree
        return re.findall(r"\[(\w+)\]", axtree or "")

    def act(self, action: str) -> dict:
        """action is a BrowserGym call string, e.g. click('a51') or fill('b3','x')."""
        self._last_obs, _, term, trunc, _ = self.env.step(action)
        return self.observation()

    def links(self) -> list[str]:
        """Extract all same-origin <a href> links from the current page DOM."""
        current_url = self._last_obs.get("url", "") if self._last_obs else ""
        links: set[str] = set()
        try:
            page = self.env.page  # Playwright page (undocumented but stable in BrowserGym)
            hrefs = page.evaluate("""() => {
                const links = [];
                for (const a of document.querySelectorAll('a[href]')) {
                    links.push(a.href);
                }
                return links;
            }""")
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
        except Exception:
            pass
