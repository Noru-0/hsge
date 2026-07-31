# Phase C Plan — Solver Competence on Multi-Step GOALs

Design roadmap for Phase C, **reprioritized by the second real run**
(`outputs/wa_seed_shopping_v2`, 2026-07-31, with the B1 verifier + `goal_max_steps=25`
on). Detailed TDD implementation plans (Phase A / B1-C1 style) follow per slice.
Companion to `docs/16_phaseBC_verification_refinement_plan.md`.

## What run v2 proved

The B1 verifier + tightened seed made the numbers honest, and that honesty
localizes the remaining problem precisely:

- **Seed goals are now concrete & verifiable** (SEEDER_SYS fix worked): "Select
  the 'Electronics' category and add the first in-stock item to the cart",
  "Use the search bar to find 'wireless headphones' and open the top result".
- **GOAL = 2 verified success / 0 fail / 4 infeasible** (v1 was 4 self-graded /
  1 / 1). The 2 verified successes are both **navigation/read** goals (search →
  open page, open page → reviews), finished fast (3-4 steps) with real judge
  reasons.
- **All 4 infeasible are multi-step / state-changing** goals: add-to-cart
  (26 steps → "budget exhausted"), add-to-wishlist (26 → exhausted), advanced
  search + filter (13 → "page blank", a site issue), open-cart-remove-checkout
  (26 → "cart empty", a *dependency* on the failed add-to-cart).

**Diagnosis:** the solver can reach and read pages, but **cannot carry out a
multi-step, state-changing flow** (select options → add to cart → …) within
budget — it churns for 25 steps and gives up. This, not verification, is now the
binding constraint. Phase C targets it.

## Reprioritized Phase C

| # | Item | Fixes which v2 finding | Priority |
|---|------|------------------------|----------|
| C2 | **Subgoal-guided GOAL solving** — decompose a multi-step GOAL into ordered subgoals and pursue them one at a time, so the solver follows the flow instead of churning | 4/4 infeasible multi-step GOALs | **P0** |
| C3 | **Progress-based anti-wandering** — the stuck guard only catches same-target-no-change; widen it to "K steps, no new page/state reached" so a churning episode stops early instead of burning 25 steps | the 3 "budget exhausted" infeasibles | P1 |
| C5 | **Stronger solver for GOAL (config)** — allow GOAL episodes to use a separate, stronger solver model than LOCAL (gpt-4o-mini struggles on the add-to-cart flow) | multi-step reasoning | P1 (cheap) |
| C4 | **Grounding-gated operator admission** — reject operators whose induced effect scores `effect_confirmed≈0` (the hallucinated `p1` in v1/doc 13) so the operator graph stays honest | operator quality | P2 |
| — | Seed-goal independence/ordering (ep_0020 failed because ep_0009 did) | dependency artifact | note only |

## Design

### C2 — Subgoal-guided GOAL solving (the core)

The seed goal is already a concrete multi-step intent ("open Electronics, add
first in-stock item to cart"). Before solving, an LLM **planner** turns it into
an ordered subgoal list; the Solver pursues subgoal *i*, and advances to *i+1*
when that subgoal's short checkable condition is met (or after a per-subgoal
step cap). The final subgoal's completion is what the B1 verifier already
checks. This keeps the solver on the flow instead of re-deciding the whole goal
every step (the churn seen in v2).

- New role `goal_planner` (or reuse `trajectory_segmenter`'s model): goal → 
  `["subgoal 1", "subgoal 2", ...]`.
- `Solver.solve` gains an optional ordered-subgoal mode: shows the current
  subgoal in the prompt, advances on the solver's own "subgoal done" signal or a
  per-subgoal cap, keeps the overall `max_steps`/`goal_max_steps` as the outer
  bound.
- **Open question:** upfront planner-decompose (structured, one extra call) vs
  Explorer-style per-action refinement (the solver re-states its current subgoal
  each step, no planner). Recommend upfront decompose — cheaper, and the subgoal
  boundaries also give cleaner skill segmentation downstream.

### C3 — Progress-based anti-wandering

Today `_stuck_streak` needs the *same target* with no change; v2's churners hit
*different* targets with no real progress and ran to the cap. Add a
"global progress" signal: if the last K executed actions produced no *new*
url/axtree the episode hasn't seen before, warn then hard-stop (like the existing
`_WARN_AFTER_REPEATS`/`_MAX_REPEATS`, but keyed on observation-novelty, not
target-repeat). Saves the 25-step burns.

### C5 — Stronger solver for GOAL (cheap)

`config.yaml` already routes models per role. Add an optional `solver_goal` role
(or a `goal_solver_model` knob) so GOAL episodes can use a stronger model than
the LOCAL `gpt-4o-mini`, since the multi-step failures are reasoning-bound. One
config line + a second Solver instance in the runtime; default = same as
`solver` (no change).

### C4 — Grounding-gated operator admission

`_promote_skill_to_operator` already computes `operator_grounding`
(`effect_accuracy`). Add a gate: if every induced effect scores below a
threshold (e.g. `effect_confirmed < 0.5`), reject the operator (log
`operator_rejected reason=ungrounded`) instead of admitting a hallucinated-effect
operator like v1's `add_to_cart`→`p1(0.0)`. Keeps future chains meaningful.

## Open questions to confirm before the detailed TDD plan

1. **C2 approach:** upfront planner-decompose (recommended) vs per-action refine.
2. **C2 subgoal advance:** trust the solver's own "subgoal done" signal, a
   per-subgoal step cap, or both (recommended: both — signal, capped).
3. **C5:** add a `solver_goal` role now, or defer until C2 lands? (Recommend
   defer — see if subgoal-guiding alone lifts completion before spending on a
   bigger model.)
4. **C4 threshold:** `effect_confirmed < 0.5` reject, or only flag? (Recommend
   reject when ALL effects are below threshold; flag otherwise.)

## Recommendation

Implement **C2 (subgoal-guided GOAL solving) first** as the next detailed TDD
plan — it targets 4/4 of v2's infeasible GOALs, and its subgoal boundaries also
improve skill segmentation. Bundle **C3 (anti-wandering)** with it since both
touch `Solver.solve` and both fight the same churn. C4 and C5 follow as small
separate slices. Confirm the four open questions and pick the slice to detail.

## Status note for bug O2 / thesis

Run v2 gives the first **verified** (not self-graded) non-zero GOAL success on a
live site — strong enough to update bug O2 from "0 GOAL" to "GOAL verified
non-zero". But both verified successes are navigation/read goals; no *multi-step
compositional* GOAL has been completed yet, so do NOT claim "goal composition
executed on a real website" until a state-changing GOAL passes the verifier
(the point of C2). Keep Appendix C.3 honest until then.
