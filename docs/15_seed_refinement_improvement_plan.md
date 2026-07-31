# Improvement Plan — Seed-Conditioned Bottom-Up Refinement

Concise, implementation-ready plan consolidating ideas from two papers to
attack HSGE's headline limitation: **0 GOAL episodes across all runs** (the
operator graph stays edgeless, so `all_chains(min_len=2)` never fires — see
`.claude/memory/bugs.md`, open bug O2).

## Source ideas

- **Explorer** (Pahuja et al., Findings ACL 2025) — bottom-up trajectory
  synthesis: propose an *abstract* task, then a **Task Refiner** rewrites it
  after every action into a longer, more specific multi-step task; a **Task
  Summarizer** states the goal as WHAT-not-HOW; a dedicated **Task Verifier**
  discards trajectories misaligned with intent.
- **InfiniteWeb** (Zhang et al.) — a **website seed** (a brief site
  description) conditions task generation so tasks match the site's intended
  capabilities; per-task **verifiable evaluators** give deterministic reward.
  We borrow only the *descriptive* half (seed → task conditioning); HSGE
  explores a **real** WebArena site, it does not synthesize one, so the seed
  is **derived by self-summarizing the real site**, not used to build one.

## Unified concept

Attack the atomic-task → atomic-skill → tautological-operator → 0-GOAL cascade
from **both ends**:

- **Top-down (InfiniteWeb seed):** derive one site-level seed per run
  (short description + a list of high-level capabilities/goals). Use it to
  (a) condition task proposals, (b) emit GOAL tasks **directly from
  uncovered capabilities** — a GOAL source that does **not** depend on the
  operator graph having edges, and (c) steer the frontier toward uncovered
  capabilities.
- **Bottom-up (Explorer refinement):** shape each task into a genuine
  multi-step trajectory so segmentation yields non-trivial skills (entry-state
  ≠ exit-state), which also feeds better precondition/effect vocabulary.
- **Verification (Explorer verifier + InfiniteWeb evaluators):** an inline
  verifier gate that rejects intent-misaligned episodes, and an auto-generated
  URL/DOM predicate per GOAL so verification is deterministic even on sites
  with no configured `terminal_goal`.

## Plan (priority order)

| # | Improvement | Source | Limitation it targets | Main edit points | Priority / effort |
|---|-------------|--------|-----------------------|------------------|-------------------|
| P1 | **Site-seed derivation** — one LLM call at run start over homepage + first pages → `{description, capabilities[]}`; persist as `seed.json`, checkpoint it. | InfiniteWeb | Missing site-level prior | `runtime.py` (new `_derive_seed`), new `agents.py` role | P0 / low |
| P2 | **Seed→GOAL curriculum** — each uncovered capability becomes a GOAL task, independent of `all_chains`. Track coverage; attempt each once. | InfiniteWeb | **0 GOAL episodes (bug O2)** — the top prize | `runtime.py::_goal_tasks`, coverage tracker | P0 / medium |
| P3 | **Seed-conditioned proposals** — feed seed into `PageExplorer.propose()`: propose tasks that advance a listed capability, still grounded in the live axtree. | InfiniteWeb | Myopic page-local tasks | `agents.py::EXPLORER_SYS`, `propose()` | P0 / low |
| P4 | **Bottom-up refinement** — abstract proposal → per-action Refiner rewrite so tasks become genuinely multi-step. | Explorer | Single-hop tasks → atomic skills (cascade stage 1) | `agents.py` (new Refiner), `Solver.solve` loop | P1 / high |
| P5 | **Inline Verifier gate** — LLM critic (final-page markdown + screenshot) rejects intent-misaligned episodes *before* Discovery ingests them. | Explorer | Self-graded verification | `runtime.py` (gate before `discovery.on_trajectory`), reuse `judge_episodes` prompt | P1 / medium |
| P6 | **Auto verify-predicate per GOAL** — generate a URL-re/DOM-text checker with each GOAL task → deterministic verify on non-shopping sites. | InfiniteWeb | `terminal_goal` cung/None | `predicates.py`, `runtime.py::_goal_tasks` | P2 / medium |
| P7 | **Coverage-driven frontier steering** — prioritize frontier items that reach uncovered capabilities, not just href novelty. | InfiniteWeb | Frontier starvation (#4) | `runtime.py` priority key | P2 / low |

## Rollout phases

1. **Phase A (P1+P2+P3)** — the minimal path to a **non-zero GOAL bucket** on a
   live run. Seed gives a top-down GOAL source that bypasses the edgeless graph.
   This is the single most valuable slice; ship and verify it first.
2. **Phase B (P4+P5)** — raise skill/trajectory quality so the *operator graph
   itself* starts chaining (complements P2, doesn't replace it).
3. **Phase C (P6+P7)** — deterministic verification everywhere + goal-directed
   coverage.

## Config additions (all default off/backward-compatible)

- `run.use_site_seed` (bool, default `false`), `run.seed_max_pages` (int).
- `llm.agents.site_seeder`, `llm.agents.task_refiner`, `llm.agents.task_verifier`
  (inherit shared `llm.*` like every other role).
- `run.seed_goal_per_run` cap; `run.refine_max_iters`.

## Risks / honest caveats

- **Hallucinated capabilities** — a derived seed may list affordances the site
  lacks. Every seed-conditioned proposal MUST stay gated on the live axtree +
  the Verifier; without that gate this is worse than today.
- **Descriptive, not generative** — no free "dense reward" like InfiniteWeb's
  TDD evaluators; deterministic verify still needs the P6 predicate.
- **Seed complements, not replaces, refinement** — with seed but no P4, the
  Solver may still finish a GOAL in one action → skill stays atomic. Phase A
  proves GOAL *plumbing*; Phase B proves GOAL *quality*.
- **Mock pipeline must stay deterministic** — all new roles are LLM-backed and
  `None`-guarded; the numpy mock tests (`test_clustering.py` et al.) unchanged.

## Verification criteria

- Phase A done when a live WebArena run produces `summary.json` with
  `GOAL.success + GOAL.fail > 0` (first time ever) — closes/updates bug O2.
- Each phase follows the repo TDD convention; full suite must stay green
  (currently 165 passed).
