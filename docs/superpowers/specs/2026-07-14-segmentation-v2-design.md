# Segmentation v2: axtree-similarity candidates + LLM-arbitrated cut points (design)

**Date:** 2026-07-14
**Status:** implemented (see docs/superpowers/plans/2026-07-14-segmentation-v2.md)
**Context:** [`docs/13_run02_reddit_exploration_log.md`](../../13_run02_reddit_exploration_log.md),
[`hsge/segmentation.py`](../../../hsge/segmentation.py)

## Problem

`segment_trajectory` cuts a trajectory purely at URL changes; the LLM only names
the resulting spans and is never allowed to move a boundary. Two failure modes:

1. **One URL, many sub-goals** — long same-page interactions (forms, SPA-style
   pages) collapse into a single segment.
2. **One sub-goal, many URLs** — e.g. search → click result is split mechanically.

Downstream consequence, visible in run 02: 1-step "click through to page X"
segments become sub-trajectories, cluster trivially (same single `click` verb
signature), hit `maturity` fast, and produce boilerplate skills
(`navigatetomainpage`, `locateprimarynavigationm`) whose induced operators are
tautological or ungrounded (only 1 of 6 operators was compositionally useful).

## Goal

Segments that correspond to *meaningful sub-goals*: correct boundaries in both
directions (merge across URLs, split within a URL), and no trivial 1-step
navigation segments reaching the skill library. LLM proposes, code validates,
deterministic fallback always exists. Mock pipeline stays deterministic.

## Design

Pipeline inside `segment_trajectory` (one LLM call per successful trajectory,
same as today):

```
candidate boundaries (code, cheap)          LLM (1 call)                  code
  URL change ─────────────┐        propose final cut points        validate each cut
  axtree sim < τ ─────────┴──────► (may drop/add candidates) ────► (drop invalid ones,
                                   + subgoal name per segment       fallback if none)
                                                                        │
                                                              safety net: merge 1-step
                                                              nav segments into the next
```

### Component 1 — candidate boundaries (code-side)

- Keep the URL-change boundary (cheap, nearly always right when it fires).
- New: `_axtree_similarity(a, b)` — Jaccard over the sets of stripped, non-empty
  axtree lines of consecutive steps. A boundary candidate is added between steps
  `i-1, i` when similarity `< τ` ("the page changed substantially").
- `τ` = `run.seg_axtree_sim`, default **0.6**, CLI `--seg-axtree-sim`
  (precedence CLI > config.yaml > default, as everywhere).
- If either axtree is empty (mock pipeline, missing observation), the similarity
  signal is off for that pair — URL boundaries alone remain, i.e. exactly
  today's behavior.

### Component 2 — LLM protocol: propose cuts, code validates

Prompt payload (no full axtrees — too expensive; actions + `obs_summary` only):

```json
{"steps": [{"i": 0, "action": "click('42')", "obs": "..."}, ...],
 "segments": [{"span": [0, 3], "subgoal": "segment 0"}, ...]}   // candidates
```

Response format (same `segments` key, so `MockLLM._segment`'s echo is already a
valid identity response):

```json
{"segments": [{"span": [0, 5], "subgoal": "open forum X and read the thread"}, ...]}
```

Only the **start index** of each returned span is trusted, as a cut point.
Validation, per cut independently: integer, `0 < start < n_steps`, sorted,
deduplicated — an invalid cut is dropped alone, not the whole response (the
lesson from the old "never trust the LLM to echo spans" comment, kept but
relaxed from "trust nothing" to "trust each number after checking it").
Segment ends are recomputed from consecutive starts + `n_steps`. If no valid
cuts survive, fall back to the candidate spans; labels fall back to hints
exactly as today. The LLM may merge candidates (omit their starts) and split
(introduce new starts).

### Component 3 — trivial-nav safety net (code-side, unconditional)

After segments are final: any 1-step segment whose action verb is in
`{click, goto, go_back}` is merged into the **following** segment (into the
preceding one if it is last). This guarantees run-02-style junk segments die
even when the LLM ignores instructions. Runs after LLM output so it applies to
both the LLM path and every fallback path.

Note: this can change the exact skill counts asserted by the deterministic mock
tests/demos. Determinism is preserved (the merge is pure code); if counts
shift, the assertions are updated once, deliberately, in the same commit.

### Component 4 — persist `Step.url` in episodes

`runtime.py::_record` currently drops `Step.url`, which is why run-02 episodes
cannot replay URL-boundary segmentation faithfully. Add `"url": st.url` to each
step record. One line; makes every future run replayable.

### Component 5 — offline replay harness (`replay_segmentation.py`, repo root)

Argparse script: `python replay_segmentation.py <episodes_dir> [--config config.yaml]
[--limit N] [--tau 0.6]`. For each successful episode: reconstruct steps
(`parsed_action`, `thought` as obs_summary, axtree from `page_state/*.txt`,
`url` when present), run old vs new segmentation, print per-mode metrics:
segments/trajectory, % 1-step segments, % nav-only segments, distinct subgoal
labels. Uses the `trajectory_segmenter` role from config.yaml (cheap — the only
LLM call). Known limitation, stated in the report header: run-02 episodes have
no per-step URL, so the old-behavior baseline there is approximate; the axtree
signal (the new part) is fully evaluable.

## Non-goals

- No changes to clustering, abstraction, verification, or operator induction —
  better inputs only.
- No vision/screenshot input to the segmenter.
- No re-scoring or migration of skills from past runs.
- No new similarity backends (embedding-based boundary detection rejected as
  heavier and non-deterministic; line-Jaccard is cheap and reproducible).

## Verification

1. Unit tests (`hsge/tests/test_segmentation.py`, scripted LLM, no network):
   similarity function edge cases (empty, identical, disjoint); candidate
   generation (URL-only, axtree-only, both); cut validation (out-of-range /
   non-int / unsorted cuts dropped individually; none valid → candidate
   fallback); trivial-nav merge (first/middle/last positions); MockLLM echo =
   identity with today's output.
2. `python -m pytest hsge/tests/ -q` — full suite; mock-count assertions
   updated deliberately if the safety net shifts them.
3. `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2` still passes.
4. `python replay_segmentation.py outputs/wa_run_02/episodes --limit 50` —
   report shows fewer 1-step/nav-only segments vs baseline; spot-check labels.
