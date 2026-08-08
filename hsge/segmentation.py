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

_SYS = (
    "You SEGMENT a web trajectory into coherent sub-goals. You are given numbered "
    "steps and candidate segments (span = [start, end) step indices). Merge "
    "candidates that serve one sub-goal; split a candidate only where a new "
    "sub-goal clearly starts. Return JSON "
    '{"segments": [{"span": [start, end], "subgoal": "short imperative name"}, ...]} '
    "covering all steps in order."
)


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


# Verbs that, alone in a 1-step segment, are pure navigation -- never a skill.
_NAV_VERBS = {"click", "goto", "go_back"}


def _action_verb(action: str) -> str:
    """Leading verb of an action, for both mock syntax ("click [go]") and real
    WebArena syntax ("click('42')")."""
    m = re.match(r"\s*([A-Za-z_]+)", action or "")
    return m.group(1).lower() if m else ""


def _merge_trivial_nav(segs: list[list], steps: list[Step]) -> list[list]:
    """Merge 1-step pure-navigation segments into the following segment (into
    the preceding one when last). Right-to-left so nav chains are absorbed.
    Runs after LLM output, so it applies to the fallback paths too."""
    out = [list(s) for s in segs]
    for i in range(len(out) - 1, -1, -1):
        if len(out) == 1:
            break
        a, b, _subgoal = out[i]
        if b - a == 1 and _action_verb(steps[a].action) in _NAV_VERBS:
            if i < len(out) - 1:
                out[i + 1][0] = a          # absorb into the following segment
            else:
                out[i - 1][1] = b          # last segment: absorb backward
            out.pop(i)
    return out


def segment_trajectory(
    llm: LLM,
    steps: list[Step],
    site: str,
    task: str,
    subgoal_hints: list[str] | None = None,
    axtree_sim: float = 0.6,
) -> list[SubTrajectory]:
    n = len(steps)
    if n == 0:
        return []
    cand_cuts = _candidate_boundaries(steps, axtree_sim)
    cand_spans = _spans_from_cuts(cand_cuts, n)
    hints = subgoal_hints or [f"segment {i}" for i in range(len(cand_spans))]
    payload = {
        # obs_summary carries the step's full thought now; cap it here so this
        # prompt stays the size it was before that change.
        "steps": [{"i": k, "action": st.action, "obs": st.obs_summary[:100]}
                  for k, st in enumerate(steps)],
        "segments": [
            {"span": [a, b], "subgoal": hints[i] if i < len(hints) else f"segment {i}"}
            for i, (a, b) in enumerate(cand_spans)
        ],
    }
    prompt = f"Task: {task}\n<payload>{json.dumps(payload)}</payload>"
    out = llm.complete_json(_SYS, prompt)

    # The LLM proposes cut points via the *start* of each returned span; each
    # start is validated independently (drop bad ones, keep good ones), and ends
    # are recomputed, so a malformed span can never corrupt the partition. An
    # empty cut set from a parseable response is a legitimate merge-everything;
    # only a response with no parseable span at all falls back to candidates.
    entries = []
    for seg in (out.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        span = seg.get("span")
        if (isinstance(span, (list, tuple)) and span
                and isinstance(span[0], int) and not isinstance(span[0], bool)
                and 0 <= span[0] < n):
            entries.append((span[0], seg.get("subgoal")))
    if entries:
        cuts = sorted({s for s, _ in entries if s > 0})
        labels = {s: g for s, g in entries if isinstance(g, str) and g}
    else:
        cuts, labels = cand_cuts, {}

    segs = []
    for i, (a, b) in enumerate(_spans_from_cuts(cuts, n)):
        subgoal = labels.get(a) or (hints[i] if i < len(hints) else f"segment {i}")
        segs.append([a, b, subgoal])
    segs = _merge_trivial_nav(segs, steps)
    return [
        SubTrajectory(steps=steps[a:b], subgoal=g, source_site=site,
                      source_task=task, success=True)
        for a, b, g in segs
    ]
