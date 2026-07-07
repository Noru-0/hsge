# Semantic multi-hop tasks (Part B) — design

**Date:** 2026-07-07
**Status:** deferred — approved in brainstorm, implementation postponed until
Part A (`2026-07-07-phase2-run04-fixes-design.md`) has landed and been
measured (run_05). Re-review this spec before planning: Part A's gates and
the run_05 numbers may shift details here.

**Goal:** make phase-2 tasks genuinely multi-hop and semantically richer, so
verified GEN episodes carry longer, navigation-bearing trajectories for SFT.

## Why (run_04 evidence)

- **57/60 INFO tasks start on the page holding the answer** — all 43
  verified INFO episodes solved in ≤2 steps (median 1). The composer sets
  `start_url` to the evidence node itself.
- 96/100 accepted tasks cite exactly one source node; all 60 INFO tasks draw
  every `answer_fact_refs` entry from a single node. No task combines
  information across pages.
- The LLM's self-reported `hops` is untrustworthy: 87/100 ≤1 (19 claim 0),
  none 3-4, despite `PREFERRED HOPS: 2-4` in the prompt — prompt-only
  pressure demonstrably does not work. `hops` currently feeds `difficulty`
  in the SFT dataset, so curriculum ordering is built on a fiction.
- Verified step-count medians: INFO 1, NAV 5, MOD 14.5 — post-Part-5-gates
  MOD is already the best source of long trajectories; INFO is the worst.

## Chosen approach

**Code shapes the semantics, the LLM only phrases.** (Rejected: prompt-only
pressure — proven ineffective above; fully templated code generation — loses
the phrasing diversity SFT needs.)

## Changes

### 1. `real_hops`: computed, not claimed

Build a directed adjacency from SiteKB (`node.url` → `node.outlinks`, edges
only between known nodes). For every accepted task, compute BFS distance
from the `start_url` node to the task's target node:
- INFO: the evidence node(s) of `answer_fact_refs` (max distance if several)
- NAV: the `reference_url` node
- MOD: the `program_html` target node (skip `"last"`)

Overwrite `task["hops"]` with this number; it becomes the SFT `difficulty`.
A target **unreachable** through known links from `start_url` → reject
(`"target unreachable from start_url"`): the solver cannot legitimately
navigate there.

### 2. Far `start_url` policy for INFO

Code overrides INFO `start_url` to the site root (`kb.site`), regardless of
what the LLM proposed. Require `real_hops ≥ 1`; quota keeps the majority at
`real_hops ≥ 2` (exact split decided at plan time, e.g. reject single-hop
INFO beyond ~20% of the INFO quota, reason `"single-hop quota exhausted"`).

**Accepted trade-off (explicit user decision):** INFO verified rate will
drop (est. 83% → 60-70% even with the site-map hint below) in exchange for
INFO trajectories going from 1-2 steps to real navigation sequences. Fewer,
richer episodes.

### 3. Comparison/aggregation tasks (new INFO shape)

Code scans the KB for pairs of same-type entities on **different** nodes
with comparable grounded attrs (comment counts, scores, timestamps):
- Code computes the answer itself (which post has more comments / is newer)
  — ground truth stays 100% code-side, both values must pass Part A's
  evidence-containment gate.
- The LLM is asked only to phrase the intent naturally (template fallback if
  the phrasing fails gates).
- `answer_fact_refs` cites both nodes; eval is `string_match` on the winning
  entity's name/value; `start_url` = site root; `real_hops` = max of the two
  distances. `_is_stale` already re-checks each ref on its own node page
  (Part A/task-4 work), so both sources are protected.

This is the pipeline's first true two-source task shape.

### 4. Site-map hint for the Solver

`GenerationRunner` builds once per run a compact site map from
`kb.known_urls()` (URL templates plus one example each, capped) and passes
it into `solver.solve(..., hints=...)` alongside the existing skill hints
for every GEN task. General site knowledge — does not leak any specific
answer. This is the compensation that keeps the far-start policy from
cratering the verified rate.

### 5. Acceptance metrics (run after implementation)

Beyond verified rate, two new headline numbers vs run_04:
- median step count of verified INFO episodes: 1 today, target ≥ 3;
- share of verified tasks with `real_hops ≥ 2`: ~0 today (13 claimed, none
  code-verified), target ≥ 50%.

## Dependencies / sequencing

Independent of Part A in code, but must land **after** it so run_05 measures
Part A cleanly and this package is measured on its own (run_06). Reuses
Part A's `url_key` helper and evidence-containment gate.

## Open questions to resolve at plan time

- Exact near/far quota split for INFO (proposed ~20% single-hop cap).
- Whether NAV/MOD also get the far-start override or keep LLM-proposed
  start_url (proposal: NAV yes — a NAV task starting at its target is
  already rejected by Part A gate #1; MOD keep as-is, its trajectories are
  already long).
- Site-map hint format and size cap (proposal: ≤15 template lines).
