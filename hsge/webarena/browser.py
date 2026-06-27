"""Thin BrowserGym wrapper for free-form WebArena exploration.

Uses the 'browsergym/openended' env, which starts at an arbitrary URL and accepts
free-form actions -- exactly what exploration (vs a fixed task) needs.

Requires:  pip install browsergym-core browsergym-webarena && playwright install chromium
and the WA_* env vars pointing at your hosted WebArena (see the runbook).
"""
from __future__ import annotations

import re


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
        obs = self._last_obs or {}
        urls = obs.get("open_pages_urls", []) or []
        return list(urls)

    def close(self):
        try:
            self.env.close()
        except Exception:
            pass
