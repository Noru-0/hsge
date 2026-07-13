# Segmentation v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace URL-only trajectory segmentation with code-computed candidate boundaries (URL change + axtree-similarity drop) that an LLM may merge/split via validated cut points, plus a safety net that absorbs 1-step navigation segments — so trivial nav skills stop reaching the library.

**Architecture:** All segmentation logic stays in `hsge/segmentation.py` (one LLM call per trajectory, same as today). `Discovery` and the WebArena runtime only gain a pass-through threshold parameter (`seg_axtree_sim`). A new root-level replay script evaluates the change offline against recorded run-02 episodes.

**Tech Stack:** Python 3.10+, numpy-only core (no new deps). Tests follow the repo's standalone-or-pytest pattern (`hsge/tests/test_clustering.py` style).

**Spec:** `docs/superpowers/specs/2026-07-14-segmentation-v2-design.md`

## Global Constraints

- Run everything from the repo root; activate the conda env first: `conda activate go-browse`.
- All code/comments/commit messages in English.
- The mock pipeline must stay deterministic; `PYTHONPATH=. python hsge/tests/test_clustering.py` must pass unchanged (analysis: its segments are 3-step and 2-step, untouched by the safety net).
- Default threshold `seg_axtree_sim = 0.6`; precedence CLI > config.yaml > DEFAULTS.
- Commit after each task; end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- After the final task, append an entry to `.claude/memory/changelog.md` (real timestamp via `date "+%Y-%m-%d %H:%M"`).

---

### Task 1: Axtree similarity + candidate boundaries

**Files:**
- Modify: `hsge/segmentation.py` (add three helpers; touch nothing else yet)
- Create: `hsge/tests/test_segmentation.py`

**Interfaces:**
- Produces: `_axtree_similarity(a: str, b: str) -> float | None`,
  `_candidate_boundaries(steps: list[Step], axtree_sim: float) -> list[int]` (cut indices, `0 < i < n`),
  `_spans_from_cuts(cuts: list[int], n: int) -> list[tuple[int, int]]`. Tasks 2/3/5 import these.

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_segmentation.py`:

```python
"""Tests for segmentation v2: candidate boundaries, LLM cut-point protocol,
trivial-nav safety net.

Run:  python -m pytest hsge/tests/test_segmentation.py -q
 (or) PYTHONPATH=. python hsge/tests/test_segmentation.py
"""
from hsge.schema import Step
from hsge.segmentation import (
    _axtree_similarity, _candidate_boundaries, _spans_from_cuts,
)

AX_A = "RootWebArea 'Home'\n[1] link 'Forums'\n[2] link 'Wiki'"
AX_B = "RootWebArea 'Forum'\n[10] heading 'AskReddit'\n[11] article 'post'"


def test_similarity_identical():
    assert _axtree_similarity(AX_A, AX_A) == 1.0


def test_similarity_disjoint():
    assert _axtree_similarity(AX_A, AX_B) == 0.0


def test_similarity_unavailable_when_empty():
    assert _axtree_similarity("", AX_A) is None
    assert _axtree_similarity(AX_A, "") is None


def test_candidates_url_change_only():
    steps = [Step("click [a]", "/login"), Step("click [b]", "/login"),
             Step("click [c]", "/home")]
    assert _candidate_boundaries(steps, 0.6) == [2]


def test_candidates_axtree_drop_same_url():
    steps = [Step("click [a]", "/app", axtree=AX_A),
             Step("click [b]", "/app", axtree=AX_A),
             Step("click [c]", "/app", axtree=AX_B)]
    assert _candidate_boundaries(steps, 0.6) == [2]


def test_candidates_axtree_signal_off_when_missing():
    steps = [Step("click [a]", "/app"), Step("click [b]", "/app")]
    assert _candidate_boundaries(steps, 0.6) == []


def test_spans_from_cuts():
    assert _spans_from_cuts([], 3) == [(0, 3)]
    assert _spans_from_cuts([1, 2], 3) == [(0, 1), (1, 2), (2, 3)]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_segmentation.py -q`
Expected: FAIL — `ImportError: cannot import name '_axtree_similarity'`

- [ ] **Step 3: Implement the helpers**

In `hsge/segmentation.py`, after `_SYS`, add (keep `_url_boundary_segments` untouched for now — Task 2 removes it):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest hsge/tests/test_segmentation.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add hsge/segmentation.py hsge/tests/test_segmentation.py
git commit -m "Add axtree-similarity candidate boundaries for segmentation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: LLM cut-point protocol (propose, validate, fallback)

**Files:**
- Modify: `hsge/segmentation.py` (`_SYS`, `segment_trajectory`; delete `_url_boundary_segments`)
- Test: `hsge/tests/test_segmentation.py` (append)

**Interfaces:**
- Consumes: `_candidate_boundaries`, `_spans_from_cuts` from Task 1.
- Produces: `segment_trajectory(llm, steps, site, task, subgoal_hints=None, axtree_sim=0.6) -> list[SubTrajectory]` — same name/behavior contract as today plus the new kwarg. Payload/response protocol: payload has `steps` (`[{"i", "action", "obs"}]`) and `segments` (`[{"span": [a, b], "subgoal": str}]`); response reuses the `segments` key, and only each returned span's **start** is trusted (as a cut point).

- [ ] **Step 1: Write the failing tests**

Append to `hsge/tests/test_segmentation.py` (and add `MockLLM` + `segment_trajectory` to the imports at the top):

```python
from hsge.llm import MockLLM
from hsge.segmentation import segment_trajectory


class ScriptedLLM:
    """Returns one canned JSON response, whatever the prompt."""
    def __init__(self, response):
        self.response = response

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return self.response


def _login_steps():
    # candidates: URL change at index 2 only (axtrees empty -> axtree signal off)
    return [Step("type [user] a", "/login"), Step("type [pwd] b", "/login"),
            Step("click [go]", "/home"), Step("type [q] x", "/home")]


def test_llm_merge_is_trusted():
    llm = ScriptedLLM({"segments": [{"span": [0, 4], "subgoal": "log in and search"}]})
    subs = segment_trajectory(llm, _login_steps(), "site", "task")
    assert len(subs) == 1
    assert subs[0].subgoal == "log in and search"
    assert len(subs[0].steps) == 4


def test_llm_split_is_trusted():
    llm = ScriptedLLM({"segments": [
        {"span": [0, 1], "subgoal": "enter username"},
        {"span": [1, 4], "subgoal": "finish login and search"},
    ]})
    subs = segment_trajectory(llm, _login_steps(), "site", "task")
    assert [len(s.steps) for s in subs] == [1, 3]
    assert subs[0].subgoal == "enter username"


def test_invalid_cuts_dropped_individually():
    llm = ScriptedLLM({"segments": [
        {"span": [0, 2], "subgoal": "log in"},
        {"span": [99, 100], "subgoal": "out of range"},      # dropped alone
        {"span": ["x", 4], "subgoal": "not an int"},         # dropped alone
        {"span": [2, 4], "subgoal": "search"},
    ]})
    subs = segment_trajectory(llm, _login_steps(), "site", "task")
    assert [len(s.steps) for s in subs] == [2, 2]
    assert [s.subgoal for s in subs] == ["log in", "search"]


def test_garbage_falls_back_to_candidates():
    subs = segment_trajectory(ScriptedLLM({}), _login_steps(), "site", "task",
                              subgoal_hints=["log in", "search"])
    assert [len(s.steps) for s in subs] == [2, 2]
    assert [s.subgoal for s in subs] == ["log in", "search"]


def test_mockllm_reproduces_old_url_boundary_behavior():
    subs = segment_trajectory(MockLLM(), _login_steps(), "site", "task",
                              subgoal_hints=["log in", "search"])
    assert [len(s.steps) for s in subs] == [2, 2]
    assert [s.subgoal for s in subs] == ["log in", "search"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_segmentation.py -q`
Expected: the 5 new tests FAIL (old `segment_trajectory` echoes URL spans and ignores LLM span edits); the 7 Task-1 tests still pass.

- [ ] **Step 3: Rewrite `_SYS` and `segment_trajectory`; delete `_url_boundary_segments`**

In `hsge/segmentation.py`, replace `_SYS` (keep the word `SEGMENT` — `MockLLM.complete_json` dispatches on it):

```python
_SYS = (
    "You SEGMENT a web trajectory into coherent sub-goals. You are given numbered "
    "steps and candidate segments (span = [start, end) step indices). Merge "
    "candidates that serve one sub-goal; split a candidate only where a new "
    "sub-goal clearly starts. Return JSON "
    '{"segments": [{"span": [start, end], "subgoal": "short imperative name"}, ...]} '
    "covering all steps in order."
)
```

Delete `_url_boundary_segments` (subsumed: `_candidate_boundaries` with empty axtrees is exactly URL-boundary). Replace `segment_trajectory` with:

```python
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
        "steps": [{"i": k, "action": st.action, "obs": st.obs_summary}
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
    return [
        SubTrajectory(steps=steps[a:b], subgoal=g, source_site=site,
                      source_task=task, success=True)
        for a, b, g in segs
    ]
```

- [ ] **Step 4: Run the segmentation tests and the existing suite**

Run: `python -m pytest hsge/tests/test_segmentation.py -q` — Expected: 12 passed
Run: `PYTHONPATH=. python hsge/tests/test_clustering.py` — Expected: `4 tests passed.` (MockLLM echoes the candidate spans → identity)

- [ ] **Step 5: Commit**

```bash
git add hsge/segmentation.py hsge/tests/test_segmentation.py
git commit -m "Let the segmenter LLM merge/split via validated cut points

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Trivial-nav safety net

**Files:**
- Modify: `hsge/segmentation.py` (add `re` import, `_NAV_VERBS`, `_action_verb`, `_merge_trivial_nav`; one call site in `segment_trajectory`)
- Test: `hsge/tests/test_segmentation.py` (append)

**Interfaces:**
- Consumes: the `segs` list of `[start, end, subgoal]` built at the end of Task 2's `segment_trajectory`.
- Produces: `_merge_trivial_nav(segs: list[list], steps: list[Step]) -> list[list]`; `_action_verb(action: str) -> str` (also used by Task 5's metrics).

- [ ] **Step 1: Write the failing tests**

Append to `hsge/tests/test_segmentation.py`:

```python
def test_one_step_nav_merges_into_following():
    # candidates: URL change at 1 -> spans (0,1)(1,3); (0,1) is a bare click
    steps = [Step("click [forums]", "/home"),
             Step("type [q] x", "/forum"), Step("click [go]", "/forum")]
    subs = segment_trajectory(ScriptedLLM({}), steps, "site", "task",
                              subgoal_hints=["open forums", "search in forum"])
    assert len(subs) == 1
    assert len(subs[0].steps) == 3
    assert subs[0].subgoal == "search in forum"   # absorbed into the following


def test_trailing_one_step_nav_merges_backward():
    steps = [Step("type [user] a", "/login"), Step("type [pwd] b", "/login"),
             Step("click [go]", "/home")]
    subs = segment_trajectory(ScriptedLLM({}), steps, "site", "task",
                              subgoal_hints=["log in", "landed"])
    assert len(subs) == 1
    assert subs[0].subgoal == "log in"            # last segment absorbed backward


def test_nav_chain_is_fully_absorbed():
    steps = [Step("click [a]", "/one"), Step("click [b]", "/two"),
             Step("type [q] x", "/three"), Step("click [go]", "/three")]
    subs = segment_trajectory(ScriptedLLM({}), steps, "site", "task")
    assert len(subs) == 1
    assert len(subs[0].steps) == 4


def test_single_segment_never_merged_away():
    subs = segment_trajectory(ScriptedLLM({}), [Step("click [x]", "/a")],
                              "site", "task")
    assert len(subs) == 1


def test_non_nav_one_step_segment_survives():
    # real WebArena action syntax: verb must parse from "click('42')" too
    steps = [Step("send_msg_to_user('done')", "/a"), Step("click('42')", "/b"),
             Step("fill('7', 'x')", "/b")]
    llm = ScriptedLLM({"segments": [
        {"span": [0, 1], "subgoal": "report answer"},
        {"span": [1, 3], "subgoal": "next task"},
    ]})
    subs = segment_trajectory(llm, steps, "site", "task")
    assert [len(s.steps) for s in subs] == [1, 2]
    assert subs[0].subgoal == "report answer"     # send_msg is not navigation
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_segmentation.py -q`
Expected: the first three new tests FAIL (nav segments not merged yet); the other two pass already — keep them as regression guards.

- [ ] **Step 3: Implement the safety net**

In `hsge/segmentation.py`: add `import re` to the imports, then:

```python
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
```

In `segment_trajectory`, insert one line between building `segs` and the return:

```python
    segs = _merge_trivial_nav(segs, steps)
```

- [ ] **Step 4: Run the full test suite and the mock demos**

Run: `python -m pytest hsge/tests/ -q` — Expected: all pass (17 in test_segmentation + existing suite; test_clustering unchanged per Global Constraints).
Run: `python explore.py && python demo.py && python compare_three_way.py` — Expected: all complete without traceback. Skill counts may legitimately shift in demo *stdout*; only assertions matter, and none should fail.

- [ ] **Step 5: Commit**

```bash
git add hsge/segmentation.py hsge/tests/test_segmentation.py
git commit -m "Merge 1-step navigation segments into their neighbor (safety net)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Wire the threshold through Discovery/runtime/CLI; persist Step.url

**Files:**
- Modify: `hsge/discovery.py:19-27` (`__init__`), `:43-45` (`on_trajectory` call)
- Modify: `hsge/webarena/runtime.py:50-58` (`__init__` signature), `:104-107` (Discovery ctor), `:129-133` (`_record` step dict)
- Modify: `run_webarena.py:27-33` (DEFAULTS), argparse block, `main()` pick + `WebArenaExplorer(...)` call
- Modify: `.claude/rules/architecture.md` (segmentation pipeline line)
- Test: `hsge/tests/test_segmentation.py` (append)

**Interfaces:**
- Consumes: `segment_trajectory(..., axtree_sim=...)` from Task 2.
- Produces: `Discovery(library, graph, segmentation_llm=None, axtree_sim=0.6)` with an `.axtree_sim` attribute; `WebArenaExplorer(..., seg_axtree_sim=0.6)`; config key `run.seg_axtree_sim`; CLI flag `--seg-axtree-sim`; episode step records now contain `"url"`.

- [ ] **Step 1: Write the failing test**

Append to `hsge/tests/test_segmentation.py`:

```python
def test_discovery_passes_axtree_sim_through():
    from hsge import Discovery, HashingEmbedder, HierarchicalGraph, SkillLibrary
    lib = SkillLibrary(MockLLM(), HashingEmbedder(), lambda: [], maturity=3)
    d = Discovery(lib, HierarchicalGraph(), axtree_sim=0.4)
    assert d.axtree_sim == 0.4
```

Run: `python -m pytest hsge/tests/test_segmentation.py -q`
Expected: FAIL — `TypeError: Discovery.__init__() got an unexpected keyword argument 'axtree_sim'`

- [ ] **Step 2: Thread the parameter through `discovery.py`**

In `Discovery.__init__`, add the parameter and store it:

```python
    def __init__(
        self,
        library: SkillLibrary,
        graph: HierarchicalGraph,
        segmentation_llm: LLM | None = None,
        axtree_sim: float = 0.6,
    ):
        self.library = library
        self.graph = graph
        self.segmentation_llm = segmentation_llm or library.llm
        self.axtree_sim = axtree_sim
```

In `on_trajectory`, pass it to the segmenter:

```python
        subs = segment_trajectory(
            self.segmentation_llm, steps, site, task, subgoal_hints,
            axtree_sim=self.axtree_sim,
        )
```

- [ ] **Step 3: Thread it through `runtime.py`; persist `Step.url`**

In `WebArenaExplorer.__init__`, add `seg_axtree_sim: float = 0.6` to the signature (after `predicate_sim: float = 0.6`), and pass it where `Discovery` is constructed:

```python
        self.discovery = Discovery(
            self.library, self.graph,
            segmentation_llm=role("trajectory_segmenter"),
            axtree_sim=seg_axtree_sim,
        )
```

In `_record`, add the step's URL to the per-step record (replay fidelity — run-02 episodes lack it):

```python
                rec = {"record_type": "step", "index": k, "url": st.url,
                       "action": json.dumps({"thought": st.obs_summary, "action": st.action}),
                       "parsed_action": st.action, "thought": st.obs_summary,
                       "observation": observation}
```

- [ ] **Step 4: Thread it through `run_webarena.py`**

DEFAULTS `run` dict — add: `"seg_axtree_sim": 0.6,` (after `"predicate_sim": 0.6,`).

Argparse — add after `--maturity`:

```python
    ap.add_argument("--seg-axtree-sim", type=float, default=None,
                    help="axtree-similarity threshold for segmentation boundary "
                         "candidates (default 0.6; lower = fewer candidate cuts)")
```

In `main()` — add with the other `_pick` lines: `seg_axtree_sim = _pick(args.seg_axtree_sim, run["seg_axtree_sim"])`, and pass `seg_axtree_sim=seg_axtree_sim,` in the `WebArenaExplorer(...)` call (next to `predicate_sim=predicate_sim`).

- [ ] **Step 5: Update the architecture rule line**

In `.claude/rules/architecture.md`, replace the pipeline line

```
  → segmentation.py    URL-boundary + LLM trajectory segmentation → SubTrajectories
```

with

```
  → segmentation.py    candidate cuts (URL change + axtree-similarity drop, run.seg_axtree_sim)
                       → LLM-arbitrated cut points (validated; 1-step nav segments
                       merged into a neighbor) → SubTrajectories
```

- [ ] **Step 6: Verify — tests + dry run + url persisted**

Run: `python -m pytest hsge/tests/ -q` — Expected: all pass.
Run: `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2` — Expected: completes; prints the usual summary.
Run: `grep -o '"url": "[^"]*"' /tmp/wa_dry/episodes/ep_0000/episode.jsonl | head -3` — Expected: three `"url": "http://shop/..."` lines (the new field).

- [ ] **Step 7: Commit**

```bash
git add hsge/discovery.py hsge/webarena/runtime.py run_webarena.py \
        hsge/tests/test_segmentation.py .claude/rules/architecture.md
git commit -m "Wire seg_axtree_sim through Discovery/runtime/CLI; persist Step.url in episodes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Offline replay harness + changelog

**Files:**
- Create: `replay_segmentation.py` (repo root)
- Modify: `.claude/memory/changelog.md`, `docs/superpowers/specs/2026-07-14-segmentation-v2-design.md` (Status line)

**Interfaces:**
- Consumes: `_candidate_boundaries`, `_spans_from_cuts`, `_action_verb`, `segment_trajectory` from Tasks 1–3; `_load_config`, `_effective_llm_config`, `_load_dotenv` from `run_webarena.py`; `MockLLM` from `hsge.llm`.
- Produces: `python replay_segmentation.py <episodes_dir> [--config config.yaml] [--limit N] [--tau 0.6] [--mock]` printing a baseline-vs-new metrics table.

- [ ] **Step 1: Write the script**

Create `replay_segmentation.py`:

```python
"""Replay segmentation over recorded episodes and compare old vs new behavior.

Baseline = URL-boundary cuts only (the old algorithm, tau disabled).
New      = candidate cuts (URL + axtree similarity) -> LLM cut points -> nav merge.

    python replay_segmentation.py outputs/wa_run_02/episodes --limit 50 --mock
    python replay_segmentation.py outputs/wa_run_02/episodes --limit 50   # real LLM

--mock uses MockLLM (echoes candidates; no key needed): it evaluates the
candidate/merge machinery but not LLM cut quality. Note: episodes recorded
before Step.url was persisted (e.g. run 02) have url="" for every step, so the
baseline there under-cuts (documented limitation); the axtree signal is exact.
"""
from __future__ import annotations

import argparse
import glob
import json
import os

from hsge.llm import MockLLM
from hsge.schema import Step
from hsge.segmentation import (
    _action_verb, _candidate_boundaries, _spans_from_cuts, segment_trajectory,
)
from run_webarena import _effective_llm_config, _load_config, _load_dotenv

_NAV = {"click", "goto", "go_back"}


def load_steps(ep_dir: str) -> list[Step]:
    steps = []
    for line in open(os.path.join(ep_dir, "episode.jsonl")):
        rec = json.loads(line)
        if rec.get("record_type") != "step":
            continue
        ax_rel = ((rec.get("observation") or {}).get("axtree_txt") or {}).get("path", "")
        ax_path = os.path.join(ep_dir, ax_rel) if ax_rel else ""
        axtree = open(ax_path).read() if ax_path and os.path.exists(ax_path) else ""
        steps.append(Step(action=rec.get("parsed_action") or "",
                          url=rec.get("url") or "",
                          obs_summary=rec.get("thought") or "", axtree=axtree))
    return steps


def successful_episodes(episodes_dir: str, limit: int) -> list[str]:
    out = []
    for ep in sorted(glob.glob(os.path.join(episodes_dir, "ep_*"))):
        meta_path = os.path.join(ep, "episode_meta.json")
        if not os.path.exists(meta_path):
            continue
        meta = json.load(open(meta_path))
        if (meta.get("outcome") or {}).get("success"):
            out.append(ep)
        if len(out) >= limit:
            break
    return out


def spans_metrics(all_spans: list[list[tuple[int, int]]],
                  all_steps: list[list[Step]]) -> dict:
    n_seg = one_step = nav_only = 0
    for spans, steps in zip(all_spans, all_steps):
        for a, b in spans:
            n_seg += 1
            if b - a == 1:
                one_step += 1
            if all(_action_verb(s.action) in _NAV for s in steps[a:b]):
                nav_only += 1
    return {"segments": n_seg,
            "avg_per_traj": n_seg / max(1, len(all_spans)),
            "pct_one_step": 100.0 * one_step / max(1, n_seg),
            "pct_nav_only": 100.0 * nav_only / max(1, n_seg)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes_dir")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--tau", type=float, default=0.6)
    ap.add_argument("--mock", action="store_true",
                    help="use MockLLM (no key; candidates+merge only)")
    args = ap.parse_args()

    _load_dotenv()
    if args.mock:
        llm = MockLLM()
    else:
        ns = argparse.Namespace(provider=None, model=None, base_url=None)
        cfg = _effective_llm_config(ns, _load_config(args.config)["llm"],
                                    "trajectory_segmenter")
        from hsge.backends import OpenAILLM
        print(f"[llm] provider={cfg['provider']} model={cfg['model']}")
        llm = OpenAILLM(model=cfg["model"], base_url=cfg["base_url"],
                        api_key=cfg["api_key"], temperature=cfg["temperature"])

    eps = successful_episodes(args.episodes_dir, args.limit)
    print(f"replaying {len(eps)} successful episodes from {args.episodes_dir}")
    all_steps, base_spans, new_spans, labels = [], [], [], set()
    for ep in eps:
        steps = load_steps(ep)
        if not steps:
            continue
        all_steps.append(steps)
        # baseline: URL cuts only (tau=-1 -> the axtree branch never fires)
        base_spans.append(_spans_from_cuts(
            _candidate_boundaries(steps, -1.0), len(steps)))
        subs = segment_trajectory(llm, steps, site=args.episodes_dir,
                                  task="replay", axtree_sim=args.tau)
        new_spans.append(_subs_to_spans(subs))
        labels.update(s.subgoal for s in subs)

    for name, m in (("baseline (URL only)", spans_metrics(base_spans, all_steps)),
                    ("new (v2)", spans_metrics(new_spans, all_steps))):
        print(f"\n{name}:")
        print(f"  segments={m['segments']}  avg/traj={m['avg_per_traj']:.2f}  "
              f"1-step={m['pct_one_step']:.1f}%  nav-only={m['pct_nav_only']:.1f}%")
    print(f"\nnew: {len(labels)} distinct subgoal labels")


def _subs_to_spans(subs) -> list[tuple[int, int]]:
    spans, pos = [], 0
    for s in subs:
        spans.append((pos, pos + len(s.steps)))
        pos += len(s.steps)
    return spans


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-run with MockLLM (no key, no network)**

Run: `python replay_segmentation.py outputs/wa_run_02/episodes --limit 10 --mock`
Expected: prints `replaying 10 successful episodes...`, then two metric blocks. Sanity: baseline `avg/traj` ≈ 1.0 (run-02 steps have no url), new `pct_nav_only` ≤ baseline's.

- [ ] **Step 3: (Optional, needs OPENAI_API_KEY) real replay**

Run: `python replay_segmentation.py outputs/wa_run_02/episodes --limit 50`
Expected: new mode shows fewer 1-step/nav-only segments than baseline and plausible subgoal labels. Record the numbers in the commit message body.

- [ ] **Step 4: Update spec status + memory changelog**

- In `docs/superpowers/specs/2026-07-14-segmentation-v2-design.md`, change `**Status:** approved, awaiting implementation plan` to `**Status:** implemented (see docs/superpowers/plans/2026-07-14-segmentation-v2.md)`.
- Get the timestamp: `date "+%Y-%m-%d %H:%M"`, then append one entry under the current date heading in `.claude/memory/changelog.md` summarizing: segmentation v2 (files: `hsge/segmentation.py`, `hsge/discovery.py`, `hsge/webarena/runtime.py`, `run_webarena.py`, `replay_segmentation.py`, tests) + the replay numbers if Step 3 ran.

- [ ] **Step 5: Commit**

```bash
git add replay_segmentation.py .claude/memory/changelog.md \
        docs/superpowers/specs/2026-07-14-segmentation-v2-design.md
git commit -m "Add offline segmentation replay harness over recorded episodes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
