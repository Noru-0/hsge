"""Segment a full trajectory into candidate sub-trajectories.

Strategy from the plan: seed boundaries at URL transitions (free from the
flat-graph exploration graph), then let the LLM name the sub-goal of each segment. The mock
LLM just echoes the seeded segments with a provided sub-goal label.
"""
from __future__ import annotations

import json
import re

from .llm import LLM
from .schema import Step, SubTrajectory

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
    return _dedupe_subtrajectories(subs + _action_level_segments(steps, site, task))


def _action_level_segments(steps: list[Step], site: str, task: str) -> list[SubTrajectory]:
    """Add compact reusable action-pattern segments alongside URL spans."""
    out: list[SubTrajectory] = []
    i = 0
    while i < len(steps):
        kind = steps[i].action_kind()
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
            out.append(SubTrajectory(
                steps=[steps[i]],
                subgoal=_click_subgoal(task, steps[i]),
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
    if re.search(r"\b(add|save|apply|submit|confirm|continue|next|compare|remove|delete|checkout|proceed|reorder|wish\s*list|cart)\b", g):
        return "activate state change control"
    if re.search(r"\b(detail|details|image|product|article|issue|record|link|view|open)\b", g):
        return "open visible item"
    return "activate named control"


def _dedupe_subtrajectories(subs: list[SubTrajectory]) -> list[SubTrajectory]:
    seen: set[tuple[tuple[str, ...], str]] = set()
    out: list[SubTrajectory] = []
    for sub in subs:
        key = (tuple(s.action for s in sub.steps), sub.subgoal)
        if key in seen:
            continue
        seen.add(key)
        out.append(sub)
    return out
