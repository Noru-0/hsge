"""Verification context builders for HSGE.

Provides the `verify_contexts_fn` callable used by SkillLibrary to obtain
WebEnv instances for grounding-and-execution verification of candidate skills.

Two strategies:
  1. **Episode-based contexts**: Replay successful episodes from the run directory,
     constructing lightweight WebEnv mocks that simulate the page transitions seen
     during exploration. This is the primary strategy for real runs.
  2. **Browser-based contexts** (optional): Use a real browser on known-stable pages.
     Requires additional browser instances.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable

from ..env import WebEnv, PageState


def build_verify_contexts_from_episodes(
    out_dir: str,
    max_contexts: int = 5,
) -> list[WebEnv]:
    """Build verification contexts from successful episodes.

    Each context is a WebEnv that simulates the page transitions of one
    successful episode. Different episodes from different URL origins are
    selected to ensure diversity.

    Returns a list of WebEnv instances (may be empty if no episodes exist).
    """
    ep_dir = os.path.join(out_dir, "episodes")
    if not os.path.isdir(ep_dir):
        return []

    contexts: list[WebEnv] = []
    seen_urls: set[str] = set()

    episodes = sorted(
        [d for d in os.listdir(ep_dir) if d.startswith("ep_")],
        key=lambda x: int(x.split("_")[1]),
    )

    for ep_name in episodes:
        if len(contexts) >= max_contexts:
            break

        ep_path = os.path.join(ep_dir, ep_name)
        meta_path = os.path.join(ep_path, "episode_meta.json")
        traj_path = os.path.join(ep_path, "episode.jsonl")

        if not os.path.isfile(meta_path) or not os.path.isfile(traj_path):
            continue

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        if not meta.get("outcome", {}).get("success"):
            continue

        # Extract unique URLs from the trajectory
        urls_seen: list[str] = []
        with open(traj_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                obs = rec.get("observation", {})
                if isinstance(obs, dict):
                    # Ưu tiên lấy URL từ observation.url (đã được lưu từ _record)
                    url = obs.get("url", "")
                    if url:
                        urls_seen.append(url)
                    else:
                        # Fallback: parse từ axtree text
                        ax_path = obs.get("axtree_txt", {}).get("path", "")
                        if ax_path:
                            ax_full = os.path.join(ep_path, ax_path)
                            if os.path.isfile(ax_full):
                                with open(ax_full, encoding="utf-8") as af:
                                    obs_text = af.read()
                                url_match = re.search(r'URL:\s*(\S+)', obs_text)
                                if url_match:
                                    urls_seen.append(url_match.group(1))

        if not urls_seen:
            continue

        # Use the first URL as the origin identifier
        origin = urls_seen[0]
        # Skip if we already have a context from this origin
        origin_key = _origin_key(origin)
        if origin_key in seen_urls:
            continue
        seen_urls.add(origin_key)

        # Build a WebEnv from the trajectory URLs
        env = _build_env_from_urls(origin, urls_seen)
        if env is not None:
            contexts.append(env)

    return contexts


def _origin_key(url: str) -> str:
    """Extract a coarse origin key from a URL (scheme + host + first path segment)."""
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
        path_seg = p.path.strip("/").split("/")[0] if p.path else ""
        return f"{p.scheme}://{p.netloc}/{path_seg}"
    except Exception:
        return url


def _build_env_from_urls(start_url: str, urls: list[str]) -> WebEnv | None:
    """Build a minimal WebEnv from a list of URLs visited in a trajectory.

    Each unique URL becomes a PageState. Transitions between consecutive URLs
    become goto edges. The start page is the first URL, and the goal page is
    the last URL.

    Returns None if there are fewer than 2 unique URLs (not enough for a
    meaningful verification context).
    """
    unique_urls = list(dict.fromkeys(urls))  # preserve order, deduplicate
    if len(unique_urls) < 2:
        return None

    pages: dict[str, PageState] = {}
    for i, url in enumerate(unique_urls):
        # Create a page key from the URL
        page_key = f"p{i}"
        affordances: list[str] = []
        goto: dict[str, str] = {}

        # Add a "next" affordance if there's a next page
        if i + 1 < len(unique_urls):
            next_key = f"p{i + 1}"
            # Use a generic affordance name
            affordances.append("next")
            goto["next"] = next_key

        pages[page_key] = PageState(
            url=url,
            affordances=affordances,
            goto=goto,
        )

    # The first page is the start, the last page is the goal
    start_key = "p0"
    goal_keys = {f"p{len(unique_urls) - 1}"}

    return WebEnv(
        site=_origin_key(start_url),
        pages=pages,
        start=start_key,
        goal_pages=goal_keys,
    )


def make_verify_contexts_fn(out_dir: str, browser_factory=None) -> Callable[[], list[WebEnv]]:
    """Create the verify_contexts_fn callable for SkillLibrary.

    Nếu có browser_factory, dùng browser thật để verify (mở từng URL, lấy axtree).
    Nếu không, fallback về mock WebEnv từ episodes.

    Usage:
        library = SkillLibrary(
            llm, embedder,
            verify_contexts_fn=make_verify_contexts_fn(out_dir, browser_factory),
            ...
        )
    """
    if browser_factory:
        return lambda: _build_browser_contexts(out_dir, browser_factory)
    return lambda: build_verify_contexts_from_episodes(out_dir)


def _build_browser_contexts(out_dir: str, browser_factory) -> list[WebEnv]:
    """Build verification contexts using real browser from successful episodes.

    Mỗi context là một WebEnv với browser_factory để ground_and_execute
    có thể dùng browser thật để verify skill.
    """
    from .browser import WebArenaBrowser
    
    ep_dir = os.path.join(out_dir, "episodes")
    if not os.path.isdir(ep_dir):
        return []

    contexts: list[WebEnv] = []
    seen_urls: set[str] = set()

    episodes = sorted(
        [d for d in os.listdir(ep_dir) if d.startswith("ep_")],
        key=lambda x: int(x.split("_")[1]),
    )

    for ep_name in episodes:
        if len(contexts) >= 3:
            break

        ep_path = os.path.join(ep_dir, ep_name)
        meta_path = os.path.join(ep_path, "episode_meta.json")
        traj_path = os.path.join(ep_path, "episode.jsonl")

        if not os.path.isfile(meta_path) or not os.path.isfile(traj_path):
            continue

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        if not meta.get("outcome", {}).get("success"):
            continue

        # Lấy URL đầu tiên và cuối cùng từ trajectory
        first_url = ""
        last_url = ""
        with open(traj_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                obs = rec.get("observation", {})
                url = obs.get("url", "") if isinstance(obs, dict) else ""
                if url:
                    if not first_url:
                        first_url = url
                    last_url = url

        if not first_url or not last_url or first_url == last_url:
            continue

        origin = _origin_key(first_url)
        if origin in seen_urls:
            continue
        seen_urls.add(origin)

        # Tạo WebEnv với browser_factory để verify dùng browser thật
        pages = {
            "start": PageState(url=first_url, affordances=[], goto={}),
            "goal": PageState(url=last_url, affordances=[], goto={}),
        }
        env = WebEnv(site=origin, pages=pages, start="start", goal_pages={"goal"})
        env.browser_factory = browser_factory  # gắn browser_factory để ground_and_execute dùng
        contexts.append(env)

    return contexts
