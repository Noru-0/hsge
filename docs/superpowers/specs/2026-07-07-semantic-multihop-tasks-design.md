# Semantic multi-hop tasks (Part B) — design

**Date:** 2026-07-07 (greenlit + scope-expanded 2026-07-08)
**Status:** greenlit — after a research-team + cross-verify diagnosis on
run_05/run_06, the user chose "enforcement-first" and expanded scope to add
changes 6–8 below (the diversity half of the complaint). Ready to plan.

**Goal:** make phase-2 tasks genuinely multi-hop and semantically richer, so
verified GEN episodes carry longer, navigation-bearing trajectories for SFT —
and diversify the task mix so it stops being 60% single-page INFO lookups.

## run_05/06 confirmation (2026-07-08 cross-verified)

The run_04 premise below still holds on newer runs, independently measured and
cross-checked: 89–92% of accepted tasks are `hops≤1`; 57–59/60 INFO tasks
start on the answer page; verified INFO median = 1 step; 60/60 INFO cite
exactly 1 ref; `hops` still self-reported and never enforced. **A verifier
agent REFUTED the "bundle collapse / sparse link graph" hypothesis**: the
SiteKB graph is dense (median 7 KB-outlinks/node, none ≤1), so multi-hop
material is available — shallowness is missing *enforcement*, not data
starvation. This validates the link-graph approach in change #1.

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

### 6. Rebalance the type quota — diversity (RC1)

The static `quota={INFO:60,NAV:20,MOD:20}` (`composer.py:186`,
`config.yaml:71`) is the *sole* determinant of the type mix (accepted mix ==
quota exactly in run_05/06), pinning the dataset at 60% single-page INFO
regardless of the site or WebArena's action-heavier true distribution.

- Rebalance the default toward more MOD/NAV (exact split decided at plan time,
  e.g. `INFO:40/NAV:20/MOD:40`); keep it in `config.yaml` so it stays tunable.
- Add a **depth sub-budget orthogonal to type**: enforce a minimum share of
  accepted tasks with `real_hops ≥ 2` (change #1 makes `real_hops`
  trustworthy). Reject surplus single-hop tasks once that budget is spent
  (reason `"single-hop budget exhausted"`), same mechanism as the per-type
  quota. This subsumes the "near/far quota split for INFO" open question into
  one global depth budget.

### 7. Composer near-duplicate suppression — diversity (RC5)

Dedup today is exact-normalized-string equality over the last 30 accepted
intents (`composer.py:68-69,109-110`); near-dups leak and `"duplicate intent"`
is the #1 rejection (15/38 in run_06 — the model keeps re-converging on one
template). Add embedding near-dup rejection reusing the project's
`Embedder`/cosine-threshold clusterer (the same one PageExplorer and the skill
library use): reject a candidate whose intent embedding is within `intent_sim`
cosine of any already-accepted intent (reason `"near-duplicate intent"`).
Threshold in `config.yaml`, default aligned with PageExplorer's. Keep the
exact-string check as a cheap pre-filter.

### 8. MOD variety — diversity (RC6)

MOD is capped at 20 (quota) and further at **one MOD per target URL** by the
collision rule (`composer.py:175-177`); MOD attempted 25–29 in run_05/06, so
the cap binds. Relax the collision key from `target_url` to
`(target_url, action-shape)` so distinct actions on the same page (post a
comment vs edit the title) can coexist; combined with the rebalanced MOD quota
(#6) this widens MOD variety.

**Caveat, now root-caused (2026-07-08 inspection of run_05 episodes):** the
65% MOD verified regression is not composer-rejection noise (only 9/29 MOD
attempts were rejected pre-solve) — it's 7/20 *accepted* MOD tasks failing at
solve time, all in one contiguous batch (`gen_0089..0096`), two distinct
failure modes neither existing gate catches:
- **Action/page-type mismatch (4/7):** intents like "post a comment on the
  'AskReddit' **forum page**" — Postmill has no comment affordance on a
  forum-listing page (comments belong to a submission/thread page); the
  Solver loops (`goto('/forums')` repeatedly) or improvises a wrong action
  (creates a whole new submission instead) and never satisfies the
  `program_html` check. The composer generates the "post a comment" verb
  without checking the target node's `page_type` (already in SiteKB digests)
  supports it (see `outputs/wa_run_05/episodes/ep_0078`, `gen_0089`'s trace).
- **Permission mismatch (1/7, `gen_0096` "Create a new forum"):** Solver fills
  the form correctly and clicks submit 4x with no effect — plausibly an
  admin-only action the seed test account can't perform. No gate checks
  action-vs-account-capability.

**New change for this package: add two feasibility gates to MOD generation**
(`composer.py` MOD branch, alongside the existing denylist/phrasing/
must_include gates): (a) reject a comment/reply-shaped intent whose target
node's `page_type` isn't a submission/thread-type page (reuse the digest's
existing `page_type` field — no new data needed); (b) a small
per-site denylist of admin/permission-gated action verbs (create forum,
ban, delete other's content, site settings) in `config.yaml`, mirroring the
existing destructive-action denylist. This subsumes the old "inspect before
widening" caveat — the fix is now specified, not just flagged.

### 9. Acceptance metrics (run after implementation → run_07)

Beyond verified rate, headline numbers vs run_06:
- median step count of verified INFO episodes: 1 today, target ≥ 3;
- share of verified tasks with `real_hops ≥ 2`: ~0 today (self-claimed only,
  none code-verified), target ≥ 50%;
- accepted type mix reflects the new quota (diversity: INFO no longer 60%);
- near-duplicate rejection replaces most of the old exact `"duplicate intent"`
  rejections, and accepted intents are more spread (fewer per-template repeats);
- distinct MOD actions per URL > 1 where the site supports it;
- MOD verified rate recovers toward run_04's 80% (from run_05's 65%) with the
  two feasibility gates in place, without the accepted MOD count dropping.

## Dependencies / sequencing

Independent of Part A in code, but must land **after** it so run_05 measures
Part A cleanly and this package is measured on its own (run_06). Reuses
Part A's `url_key` helper and evidence-containment gate.

## Open questions to resolve at plan time

- Rebalanced type quota target (proposal: `INFO:40/NAV:20/MOD:40`) and the
  global `real_hops ≥ 2` depth-budget share (proposal: ≥50%, matching the
  acceptance metric). Subsumes the old "near/far split for INFO".
- Whether NAV/MOD also get the far-start override or keep LLM-proposed
  start_url (proposal: NAV yes — a NAV task starting at its target is
  already rejected by Part A gate #1; MOD keep as-is, its trajectories are
  already long).
- Site-map hint format and size cap (proposal: ≤15 template lines).
- `intent_sim` cosine threshold for change #7 (proposal: align with
  PageExplorer's).
- Whether to inspect run_05 rejected MODs (change #8 caveat) as a plan task
  or a quick pre-plan check.
