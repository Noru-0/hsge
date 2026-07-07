"""Thin BrowserGym wrapper for free-form WebArena exploration.

Uses the 'browsergym/openended' env, which starts at an arbitrary URL and accepts
free-form actions -- exactly what exploration (vs a fixed task) needs.

Requires:  pip install browsergym-core browsergym-webarena && playwright install chromium
and the WA_* env vars pointing at your hosted WebArena (see the runbook).
"""
from __future__ import annotations

import json
import os
import re


class WebArenaBrowser:
    def __init__(self, start_url: str, headless: bool = True, timeout_ms: int = 10000,
                 storage_state: str | None = None):
        import gymnasium as gym
        import browsergym.core            # noqa: registers browsergym/openended
        from browsergym.core.action.highlevel import HighLevelActionSet
        self._gym = gym
        # The Solver emits high-level actions as strings, e.g. click('a51'),
        # fill('b3','x'), goto('url'), go_back(), send_msg_to_user('done'). BrowserGym's
        # openended env executes Python in the page context, so we map each high-level
        # string to executable code via the action set (mirrors go-browse's setup).
        self.action_set = HighLevelActionSet(
            subsets=["chat", "bid", "infeas", "nav"], strict=False, multiaction=False)
        env_kwargs = {}
        pw_context_kwargs = {}
        headers_path = os.environ.get("PW_EXTRA_HEADERS")
        if headers_path and os.path.exists(headers_path):
            with open(headers_path) as f:
                pw_context_kwargs["extra_http_headers"] = json.load(f)
        # storage_state (from hsge.webarena.auth.ensure_login) starts the context
        # already logged in, so every node visit shares one cached session instead
        # of hitting a login wall.
        if storage_state:
            pw_context_kwargs["storage_state"] = storage_state
        if pw_context_kwargs:
            env_kwargs["pw_context_kwargs"] = pw_context_kwargs
        self.env = gym.make(
            "browsergym/openended",
            task_kwargs={"start_url": start_url},
            headless=headless,
            timeout=timeout_ms,
            wait_for_user_message=False,
            action_mapping=self.action_set.to_python_code,
            **env_kwargs,
        )
        self._last_obs = None
        self.terminated = False

    def reset(self) -> dict:
        obs, _ = self.env.reset()
        self._last_obs = obs
        self.terminated = False
        return self.observation()

    def observation(self) -> dict:
        from browsergym.utils.obs import flatten_axtree_to_str
        obs = self._last_obs or {}
        try:
            axtree = flatten_axtree_to_str(
                obs["axtree_object"], filter_visible_only=False,
                extra_properties=obs.get("extra_element_properties"))
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

    def screenshot_bytes(self, som: bool = False) -> bytes | None:
        """JPEG-encode the last observation's screenshot.

        If som, overlay bid-tagged bounding boxes first via BrowserGym's own
        browsergym.utils.obs.overlay_som (same extra_element_properties used
        to flatten the axtree). None on any failure, mirroring observation()'s
        try/except-to-empty-string pattern.
        """
        obs = self._last_obs or {}
        arr = obs.get("screenshot")
        if arr is None:
            return None
        try:
            import io
            from PIL import Image
            from browsergym.utils.obs import overlay_som
            if som:
                arr = overlay_som(arr, obs.get("extra_element_properties") or {})
            buf = io.BytesIO()
            Image.fromarray(arr).convert("RGB").save(buf, format="JPEG", quality=80)
            return buf.getvalue()
        except Exception:
            return None

    def screenshot_b64(self, som: bool = False) -> str | None:
        import base64
        data = self.screenshot_bytes(som=som)
        return base64.b64encode(data).decode("ascii") if data else None

    def act(self, action: str) -> dict:
        """action is a BrowserGym call string, e.g. click('a51') or fill('b3','x')."""
        self._last_obs, _, term, trunc, _ = self.env.step(action)
        self.terminated = bool(term or trunc)
        return self.observation()

    def links(self) -> list[str]:
        obs = self._last_obs or {}
        urls = obs.get("open_pages_urls", []) or []
        return list(urls)

    def page_hrefs(self, limit: int = 100) -> list[str]:
        """Every <a href> on the current page, as absolute URLs (order-deduped,
        capped at `limit`). Read straight off the Playwright page because the
        flattened axtree drops hrefs. Fail-soft to [] like observation()."""
        try:
            page = self.env.unwrapped.page
            hrefs = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href)")
        except Exception:
            return []
        seen, out = set(), []
        for h in hrefs or []:
            if h and h not in seen:
                seen.add(h)
                out.append(h)
                if len(out) >= limit:
                    break
        return out

    def close(self):
        try:
            self.env.close()
        except Exception:
            pass
