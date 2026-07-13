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


def _axtree_similarity(a: str, b: str) -> float | None:
    """Line-set Jaccard between two axtrees; None when either side is empty
    (mock pipeline / missing observation -> the signal is unavailable)."""
    la = {ln.strip() for ln in (a or "").splitlines() if ln.strip()}
    lb = {ln.strip() for ln in (b or "").splitlines() if ln.strip()}
    if not la or not lb:
        return None
    return len(la & lb) / len(la | lb)


def _candidate_boundaries(steps: list[Step], axtree_sim: float) -> list[int]:
    """Candidate cut indices (0 < i < n): URL changes, plus same-URL step pairs
    whose axtrees changed substantially (similarity below the threshold)."""
    cuts = []
    for i in range(1, len(steps)):
        if steps[i].url != steps[i - 1].url:
            cuts.append(i)
            continue
        sim = _axtree_similarity(steps[i - 1].axtree, steps[i].axtree)
        if sim is not None and sim < axtree_sim:
            cuts.append(i)
    return cuts


def _spans_from_cuts(cuts: list[int], n: int) -> list[tuple[int, int]]:
    """[c1, c2, ...] -> [(0, c1), (c1, c2), ..., (ck, n)]."""
    bounds = [0] + list(cuts) + [n]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


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
    # Spans are code-computed (URL boundaries) and authoritative; the LLM only
    # supplies subgoal labels. Never trust it to echo spans back correctly.
    llm_segs = out.get("segments") or []
    subs: list[SubTrajectory] = []
    for i, (a, b) in enumerate(spans):
        subgoal = hints[i] if i < len(hints) else f"segment {i}"
        if i < len(llm_segs) and isinstance(llm_segs[i], dict):
            subgoal = llm_segs[i].get("subgoal") or subgoal
        subs.append(SubTrajectory(
            steps=steps[a:b], subgoal=subgoal,
            source_site=site, source_task=task, success=True,
        ))
    return subs
