# Phase B/C Plan — Trustworthy Verification, then Solver Competence

Roadmap for the next two phases, **reprioritized by the first real run**
(`outputs/wa_seed_shopping`, 2026-07-31). Detailed TDD implementation plans
(Phase A style, under `docs/superpowers/plans/`) follow per slice once scope is
approved. Companion to `docs/15_seed_refinement_improvement_plan.md`.

## What the real run proved (and exposed)

Phase A worked end-to-end on a live WebArena shopping site: a good 6-capability
seed was derived and `GOAL success=4, fail=1, infeasible=1` — the first-ever
non-zero GOAL bucket. But the evaluation exposed three concrete weaknesses that
set the priority order below:

1. **Success is self-graded and inflated.** Every GOAL "success" used the full
   16 steps (15 `max_steps` + 1 wrap-up) and ended in a self-declared
   `send_msg_to_user('done: ...')`. Trajectories wandered (e.g. `click('1462')`
   ×3, `click('1591')` ×3) and two "successes" were trivially declarable
   (`'done: exploring Sports category'`, `'done: details are available'`). We
   **cannot trust `GOAL.success`** until verification is real. → **Phase B.**
2. **Solver can't finish multi-step goals in the budget.** All 6 GOAL episodes
   hit the step cap; the existing stuck-loop guard didn't fire (it needs the
   *same* target with no change; the solver wandered across *different* targets
   instead). → **Phase C.**
3. **The one operator chain that formed is ungrounded.** A real edge did form
   (`add_to_cart` eff `p1` → `notify_completion` pre `p1`), but `p1` scored
   `effect_confirmed=0.0` / `precondition_confirmed=0.0` — a hallucinated
   predicate. Composition is structurally there but semantically shaky. →
   **Phase C (optional grounding gate).**

Already fixed this session: vague seed goals (`SEEDER_SYS` now demands a
concrete, verifiable end-state).

## Reprioritized roadmap

| # | Item | Source | Fixes which run finding | Phase | Priority |
|---|------|--------|-------------------------|-------|----------|
| B1 | **Inline Verifier gate** — a dedicated verifier LLM judges the final observation (axtree + optional screenshot) against the goal and OVERRIDES the self-declared success before it counts / feeds Discovery | Explorer (P5) | #1 self-graded inflation | B | **P0** |
| B2 | **Auto verify-predicate per GOAL** — seed/goal carries a checkable URL-re/DOM-text predicate so verifiable-state goals get deterministic `reached()` verification instead of LLM judging | InfiniteWeb (P6) | #1 (deterministic where possible) | B | P1 |
| C1 | **Raise `max_steps` for GOAL/composite tasks** (config knob), since every GOAL hit the cap | run finding | #2 budget exhaustion | C | P0 (cheap) |
| C2 | **Bottom-up refinement** — Explorer's per-action Task Refiner gives the solver an explicit evolving subgoal so multi-step goals are followed, not wandered | Explorer (P4) | #2 wandering; also skill depth | C | P1 |
| C3 | **Stronger anti-wandering** — extend the stuck guard to also catch "many different targets, no progress toward goal" (not just same-target) | run finding | #2 wandering | C | P2 |
| C4 | **Grounding-gated operator admission** — reject/flag operators whose induced effect is `effect_confirmed≈0` so ungrounded chains don't form | run finding + doc 13 | #3 ungrounded chain | C | P2 |
| — | Coverage-driven frontier steering (P7) | InfiniteWeb | frontier breadth | later | defer |

## Phase B — Trustworthy verification (do first)

**Why first:** until success means something, we can't measure whether any
Phase C change (refinement, more steps) actually helps — every experiment would
be graded by the same unreliable self-report.

### B1 — Inline Verifier gate (the core)

- New role `episode_verifier` (or reuse the existing offline `episode_judge`
  prompt/model, brought inline). After a GOAL episode ends declared-success, a
  verifier LLM sees the goal + final axtree (+ screenshot if vision on) and
  returns `{verified: bool, reason}`. Only `verified` counts as GOAL success;
  otherwise it's a fail.
- Wire in `runtime.py` between the solver result and `task_stats`/`nodes.json`
  for GOAL tasks (LOCAL tasks optional — keep scope to GOAL first).
- This is exactly `judge_episodes.py`'s logic, run **live** instead of offline,
  so a wandering "done" is caught immediately and never inflates the bucket.
- Design decision to confirm: does a failed verification also **block the
  trajectory from Discovery** (so a bogus success can't seed a skill), or only
  correct the count? (Recommend: block — a self-declared-but-unverified episode
  is exactly the noise Discovery should not learn from.)

### B2 — Auto verify-predicate (deterministic where possible)

- When a seed capability names a checkable end-state (cart contains X, on a
  product page, order confirmed), emit a URL-re/DOM-text predicate alongside the
  GOAL so `reached()` verifies deterministically (like `terminal_goal` today).
- Falls back to B1's LLM verifier when no crisp predicate is derivable.
- Lower priority than B1 because B1 covers *every* goal; B2 only sharpens the
  subset with a crisp observable state.

## Phase C — Solver competence & skill depth

- **C1 (cheap, do alongside B):** add `run.goal_max_steps` (or raise
  `max_steps`) so multi-step GOALs aren't guaranteed to exhaust. Config-only +
  a wiring line.
- **C2 (the big one):** Explorer-style per-action refinement so the solver
  carries an explicit, evolving subgoal — the mechanism that both curbs
  wandering and makes discovered skills genuinely multi-step (attacks the
  original atomic-skill root cause from a different angle than seed).
- **C3:** widen the stuck guard to a goal-progress signal, not just
  same-target-no-change.
- **C4:** gate operator admission on grounding (`effect_confirmed`), so the
  hallucinated-predicate chains seen in this run and doc 13 don't form.

## Open questions to resolve before the detailed TDD plan

1. **B1 verifier model/source:** new `episode_verifier` role, or reuse
   `episode_judge` config + bring its prompt inline? (Recommend reuse — same
   job, avoids a second prompt to maintain.)
2. **B1 blocking vs counting:** does an unverified success also get withheld
   from Discovery? (Recommend block.)
3. **Scope of B1:** GOAL episodes only, or LOCAL too? (Recommend GOAL first;
   LOCAL is a bigger volume and cost.)
4. **C1 step budget:** a separate `goal_max_steps` knob, or just raise the
   shared `max_steps`? (Recommend a separate knob so LOCAL cost is unchanged.)

## Recommendation

Implement **Phase B first (B1 + C1 together)** as one detailed TDD plan: the
inline verifier makes success trustworthy, and the GOAL step-budget bump gives
multi-step goals a fair chance — the smallest slice that turns the next real run
into a *measurable* experiment. B2 and the rest of Phase C follow as separate
plans. Confirm the four open questions above and pick the slice to detail.
