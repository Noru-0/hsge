# 01 — Overview

## The problem

Flat exploration agents collect web trajectories by enumerating, at each page, the
tasks doable *there* (search, sort, filter). These are locally completable and
locally verifiable, so the agent succeeds and stops — and the collected data never
contains long-horizon, goal-directed tasks like completing a purchase. A purchase
is not an affordance of any single page; it is a *composition* across many pages,
and bottom-up enumeration cannot generate it.

## The method

HSGE adds a high-level layer on top of flat exploration:

1. **Online skill discovery.** Recurring sub-trajectories are segmented and
   clustered into reusable skills *during* exploration. Clustering is nonparametric
   (a cosine-threshold / DP-means stream), so the library grows from data with no
   fixed cluster count.

2. **Verification-gated admission.** A discovered skill is a hypothesis. It enters
   the library only after it *executes successfully* in held-out contexts (≥ k
   successes). Low performers are pruned. This is the quality gate.

3. **Hierarchical skill graph.** Skills are options ⟨I, π, β⟩: an initiation set
   (preconditions), a parameterized policy (action template + slots), and a
   termination/success predicate. `skill→skill` edges are derived from
   precondition/effect matching — "checkout follows cart follows product" — not from
   page similarity or co-occurrence.

4. **Curriculum generation.** Planning over the skill graph from a start state to a
   sampled goal predicate emits composed tasks. Difficulty = chain length; targeting
   a terminal predicate (`order_confirmed`) yields the full purchase chain.

5. **Cross-domain transfer.** Verified skills are retrieved and re-grounded on
   unseen sites, covering sub-goals with no fresh exploration.

## What makes it different

| | Flat exploration | Workflow memory (AWM) | HSGE |
| --- | --- | --- | --- |
| reusable skills | no | yes | yes |
| verification gate | no | no | **yes** |
| precondition/effect operators | no | no | **yes** |
| planned hierarchical graph | no | no | **yes** |
| difficulty-graded curriculum | no | no | **yes** |
| transfer | none | unverified reuse | **verified** |

The abstraction row is the honest one: workflow-memory methods already abstract and
reuse, so abstraction alone is not the contribution. HSGE's deltas are the
verification gate, the planned precondition/effect graph, the composition curriculum,
and *verified* transfer.

## Key design choices a reviewer will probe

- **No fixed k.** The one clustering knob is an interpretable cosine threshold.
- **Verification is the quality story** — skills must execute before admission.
- **Cost accounting.** Discovery and verification call an LLM; efficiency claims
  must net out that overhead, not just count downstream steps.
- **Terminal verification, not self-report.** Success is judged by reaching a goal
  state programmatically, so "search done" is no longer a win.
