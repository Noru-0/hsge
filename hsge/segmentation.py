"""Segment a full trajectory into candidate sub-trajectories.

Strategy from the plan: seed boundaries at URL transitions (free from the
flat-graph exploration graph), then let the LLM name the sub-goal of each segment. The mock
LLM just echoes the seeded segments with a provided sub-goal label.
"""
from __future__ import annotations

import json

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
    return subs
