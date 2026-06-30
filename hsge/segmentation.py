"""Segment a full trajectory into candidate sub-trajectories.

Strategy from the plan: seed boundaries at URL transitions (free from the
flat-graph exploration graph), then let the LLM name the sub-goal of each segment. The mock
LLM just echoes the seeded segments with a provided sub-goal label.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .llm import LLM
from .schema import Step, SubTrajectory
from .webarena.predicates import PredicateExtractor, predicates_from

_SYS = "You SEGMENT a web trajectory into coherent sub-goals. Return JSON."


def _url_boundary_segments(steps: list[Step]) -> list[tuple[int, int]]:
    """Split where the URL changes; each run of same-URL steps is one segment."""
    if not steps:
        return []
    bounds, start = [], 0
    for i in range(1, len(steps)):
        if steps[i].url != steps[i - 1].url:
            bounds.append((start, i))
            start = i
    bounds.append((start, len(steps)))
    return bounds


def segment_trajectory(
    llm: LLM,
    steps: list[Step],
    site: str,
    task: str,
    subgoal_hints: list[str] | None = None,
    obs_texts: list[str] | None = None,
    final_obs: dict[str, Any] | None = None,
    predicate_extractor: PredicateExtractor | None = None,
) -> list[SubTrajectory]:
    spans = _url_boundary_segments(steps)
    hints = subgoal_hints or [f"segment {i}" for i in range(len(spans))]
    # Hand the LLM the seeded spans; it returns sub-goal labels.
    payload = {"segments": [
        {"span": [a, b], "subgoal": hints[i] if i < len(hints) else f"segment {i}"}
        for i, (a, b) in enumerate(spans)
    ]}
    prompt = f"Task: {task}\n<payload>{json.dumps(payload)}</payload>"
    out = llm.complete_json(_SYS, prompt)
    # Defensive: if out is a list, treat it as the segments array directly.
    segments = out if isinstance(out, list) else out.get("segments", [])
    subs: list[SubTrajectory] = []
    for seg in segments:
        if not isinstance(seg, dict) or "span" not in seg:
            continue
        try:
            span = seg["span"]
            if not isinstance(span, (list, tuple)) or len(span) != 2:
                continue
            a, b = int(span[0]), int(span[1])
            if not (0 <= a < b <= len(steps)):
                continue
            subs.append(SubTrajectory(
                steps=steps[a:b], subgoal=seg.get("subgoal", ""),
                source_site=site, source_task=task, success=True,
            ))
        except (TypeError, ValueError):
            continue
    # Fallback: if LLM returned unusable output, use the seeded spans directly.
    if not subs and spans:
        subs = [
            SubTrajectory(
                steps=steps[a:b],
                subgoal=hints[i] if i < len(hints) else f"segment {i}",
                source_site=site, source_task=task, success=True,
            )
            for i, (a, b) in enumerate(spans)
        ]
    result = _dedupe_subtrajectories(subs + _action_level_segments(steps, site, task))
    _attach_planning_evidence(
        result, steps, obs_texts or [], final_obs or {}, predicate_extractor
    )
    return result


def _attach_planning_evidence(
    subs: list[SubTrajectory],
    full_steps: list[Step],
    obs_texts: list[str],
    final_obs: dict[str, Any],
    predicate_extractor: PredicateExtractor | None = None,
) -> None:
    """Attach observed symbolic deltas to each candidate skill segment."""
    by_identity = {id(step): i for i, step in enumerate(full_steps)}
    for sub in subs:
        if not sub.steps:
            continue
        start_idx = by_identity.get(id(sub.steps[0]))
        end_idx = by_identity.get(id(sub.steps[-1]))
        if start_idx is None or end_idx is None:
            continue
        first_planning = (full_steps[start_idx].misc or {}).get("planning", {})
        last_planning = (full_steps[end_idx].misc or {}).get("planning", {})
        sub.predicate_schema_version = (
            first_planning.get("schema_version")
            or getattr(predicate_extractor, "schema_version", "core-v2")
        )
        if first_planning.get("pre_predicates") is not None and last_planning.get(
            "post_predicates"
        ) is not None:
            before = set(first_planning["pre_predicates"])
            after = set(last_planning["post_predicates"])
            sub.planning_preconditions = before
            sub.planning_effects = after - before
            continue

        start_url = full_steps[start_idx].url
        start_ax = obs_texts[start_idx] if start_idx < len(obs_texts) else ""
        if end_idx + 1 < len(full_steps):
            end_url = full_steps[end_idx + 1].url
            end_ax = obs_texts[end_idx + 1] if end_idx + 1 < len(obs_texts) else ""
        else:
            end_url = final_obs.get("url", full_steps[end_idx].url)
            end_ax = final_obs.get("axtree", "")
        before = predicates_from(start_url, start_ax, predicate_extractor)
        after = predicates_from(end_url, end_ax, predicate_extractor)
        sub.planning_preconditions = before
        sub.planning_effects = after - before


def _action_level_segments(steps: list[Step], site: str, task: str) -> list[SubTrajectory]:
    """Add compact reusable action-pattern segments alongside URL spans.

    Commerce-triggering actions (add to cart, checkout, etc.) get
    context windows (preceding fill/type/select + the click itself) so the
    segment captures the full causal sequence — not just a bare click.
    """
    out: list[SubTrajectory] = []
    i = 0
    while i < len(steps):
        kind = steps[i].action_kind()
        if kind == "send_msg_to_user":
            i += 1
            continue
        if kind in {"fill", "type"}:
            j = i + 1
            if j < len(steps) and steps[j].action_kind() in {"click", "press"}:
                out.append(SubTrajectory(
                    steps=steps[i:j + 1],
                    subgoal=_form_subgoal(task),
                    source_site=site,
                    source_task=task,
                    success=True,
                ))
                i = j + 1
                continue
            out.append(SubTrajectory(
                steps=[steps[i]],
                subgoal="fill visible field",
                source_site=site,
                source_task=task,
                success=True,
            ))
        elif kind == "click":
            subgoal = _click_subgoal(task, steps[i])
            # Commerce-triggering clicks: include preceding fill/type/select
            # for context (e.g. quantity fill → Add to Cart click)
            if subgoal in {"add item to cart", "save visible item", "advance transaction flow"}:
                start = i
                if i > 0 and steps[i - 1].action_kind() in {"fill", "type", "select_option"}:
                    start = i - 1
                out.append(SubTrajectory(
                    steps=steps[start:i + 1],
                    subgoal=subgoal,
                    source_site=site,
                    source_task=task,
                    success=True,
                ))
            else:
                out.append(SubTrajectory(
                    steps=[steps[i]],
                    subgoal=subgoal,
                    source_site=site,
                    source_task=task,
                    success=True,
                ))
        elif kind == "hover":
            out.append(SubTrajectory(
                steps=[steps[i]],
                subgoal="inspect menu options",
                source_site=site,
                source_task=task,
                success=True,
            ))
        i += 1
    return out


def _form_subgoal(task: str) -> str:
    g = (task or "").lower()
    if re.search(r"\b(search|find|sku|query)\b", g):
        return "submit search query"
    if re.search(r"\b(message|contact|comment|reply|email)\b", g):
        return "fill communication form"
    return "fill visible field"


def _click_subgoal(task: str, step: Step) -> str:
    g = f"{task or ''} {step.obs_summary or ''}".lower()
    if re.search(r"\b(review|rating|feedback|comment)\b", g):
        return "inspect feedback indicator"
    # Commerce-specific subgoals — must NOT fall into generic "activate state change control"
    # because that would lump add-to-cart, wishlist, checkout, and pagination together.
    if re.search(r"\b(add to (?:cart|basket)|add (?:item|product) to|add this (?:item|product))\b", g):
        return "add item to cart"
    if re.search(r"\b(add to (?:wish ?list|wishlist|favorites|saved)|save (?:item|this|product))\b", g):
        return "save visible item"
    if re.search(r"\b(proceed to checkout|checkout now|secure checkout|go to checkout|begin checkout)\b", g):
        return "advance transaction flow"
    if re.search(r"\b(continue to (?:payment|shipping|billing)|place order|review order|confirm (?:order|payment))\b", g):
        return "advance transaction flow"
    # Generic state-change controls (submit, apply, confirm, compare, sort filter, etc.)
    if re.search(r"\b(add|save|apply|submit|confirm|continue|next|compare|remove|delete|reorder)\b", g):
        return "activate state change control"
    if re.search(r"\b(detail|details|image|product|article|issue|record|link|view|open)\b", g):
        return "open visible item"
    return "activate named control"


def _dedupe_subtrajectories(subs: list[SubTrajectory]) -> list[SubTrajectory]:
    seen: set[tuple[tuple[str, ...], str]] = set()
    out: list[SubTrajectory] = []
    for sub in subs:
        kinds = {s.action_kind() for s in sub.steps}
        if not sub.steps or "send_msg_to_user" in kinds or "goto" in kinds:
            continue
        key = (tuple(s.action for s in sub.steps), sub.subgoal)
        if key in seen:
            continue
        seen.add(key)
        out.append(sub)
    return out
