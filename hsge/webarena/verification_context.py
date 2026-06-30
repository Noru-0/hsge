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
    successful episode.  Deduplication is by start URL so different
    episodes on the same site produce distinct contexts.
    """
    ep_dir = os.path.join(out_dir, "episodes")
    if not os.path.isdir(ep_dir):
        return []

    contexts: list[WebEnv] = []
    seen_start_urls: set[str] = set()

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

        # Dedup by start URL — episodes starting from different pages
        # are valid contexts even on the same site.
        if urls_seen[0] in seen_start_urls:
            continue
        seen_start_urls.add(urls_seen[0])

        # Build a WebEnv from the trajectory URLs
        env = _build_env_from_urls(urls_seen[0], urls_seen)
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


def make_verify_contexts_fn(out_dir: str, browser_factory=None) -> Callable[..., list[WebEnv]]:
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
        return lambda skill=None: _build_browser_contexts(
            out_dir, browser_factory, skill=skill
        )
    return lambda skill=None: build_verify_contexts_from_episodes(out_dir)


def _build_browser_contexts(out_dir: str, browser_factory, skill=None) -> list[WebEnv]:
    """Build effect-compatible browser contexts from successful transitions.

    A context starts at the pre-action URL of one successful transition, not at
    the first URL of the whole episode.  The transition's target metadata is
    retained so verification can ground a generic skill onto the same semantic
    kind of control.  Candidates with planning effects only receive contexts
    whose observed predicate delta contains all declared effects.
    """
    ep_dir = os.path.join(out_dir, "episodes")
    if not os.path.isdir(ep_dir):
        return []

    contexts: list[WebEnv] = []
    seen_transitions: set[str] = set()
    required_effects = set(getattr(skill, "planning_effects", set()) or set())

    episodes = sorted(
        [d for d in os.listdir(ep_dir) if d.startswith("ep_")],
        key=lambda x: int(x.split("_")[1]),
    )

    for ep_name in episodes:
        if len(contexts) >= 10:
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

        # One episode can provide several distinct verification contexts.
        with open(traj_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                action = str(rec.get("parsed_action", "") or "").strip()
                if not action or action.startswith(("send_msg_to_user(", "goto(")):
                    continue
                obs = rec.get("observation", {})
                observed_url = obs.get("url", "") if isinstance(obs, dict) else ""
                planning = (rec.get("misc", {}) or {}).get("planning", {}) or {}
                pre_url = str(planning.get("pre_url") or observed_url or "")
                post_url = str(planning.get("post_url") or "")
                if not pre_url or not post_url:
                    continue
                pre_predicates = set(planning.get("pre_predicates", []) or [])
                post_predicates = set(planning.get("post_predicates", []) or [])
                transition_effects = post_predicates - pre_predicates
                if required_effects and not required_effects.issubset(transition_effects):
                    continue

                target_role = str(planning.get("target_role") or "").lower()
                target_name = str(planning.get("target_name") or "")
                target_fingerprint = str(planning.get("target_fingerprint") or "")
                identity = "|".join((
                    pre_url, post_url, action.split("(", 1)[0],
                    target_fingerprint or f"{target_role}:{target_name}",
                    ",".join(sorted(transition_effects)),
                ))
                if identity in seen_transitions:
                    continue
                seen_transitions.add(identity)

                pages = {
                    "start": PageState(url=pre_url, affordances=[], goto={}),
                    "goal": PageState(url=post_url, affordances=[], goto={}),
                }
                env = WebEnv(
                    site=_origin_key(pre_url), pages=pages,
                    start="start", goal_pages={"goal"},
                )
                env.browser_factory = browser_factory
                env.verification_context_id = identity
                env.verification_action_kind = action.split("(", 1)[0].lower()
                env.verification_target_role = target_role
                env.verification_target_name = target_name
                env.verification_target_fingerprint = target_fingerprint
                env.verification_pre_predicates = pre_predicates
                env.verification_effects = transition_effects
                contexts.append(env)
                if len(contexts) >= 10:
                    return contexts

    return contexts
