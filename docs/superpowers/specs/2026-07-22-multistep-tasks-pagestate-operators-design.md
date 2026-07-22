# Design: multi-step tasks + page-state operators (unlock GOAL tasks)

**Date**: 2026-07-22
**Status**: approved, pending implementation
**Bug**: see `.claude/memory/bugs.md` — "Predicate canonicalization never unifies
synonyms..." (Open; re-diagnosed 2026-07-22 as a three-stage loss cascade).

## Problem

Two fresh live runs (`wa_run_13_shopping`, `wa_run_14_reddit`, 77/79 nodes,
~290 episodes each) still produce **GOAL 0/0/0** despite the 2026-07-22
synonym-canonicalization fix. Direct analysis of the run artifacts shows the
zero is the end of a **three-stage loss cascade**, of which synonym-merging is
only stage 3 and not the binding constraint:

1. **Single-hop tasks.** `EXPLORER_SYS` asks for tasks doable on *this page*, so
   104/221 (reddit) and 118/230 (shopping) successful episodes are literally one
   action (median 2 steps). Atomic tasks → atomic skills.
2. **Anti-tautology gate kills ~half the skills.** 4/7 (reddit) and 3/5
   (shopping) admitted skills are rejected `operator_rejected reason=tautological`
   because an atomic skill's effect is phrased ≈ its precondition
   (`uncheck_checkbox`: pre "a checkbox exists" / eff "the checkbox is checked" →
   `eff-pre=∅`). Only 3 / 2 operators survive.
3. **Effect/precondition vocabulary disjunction.** Survivors' effects are all
   page-state ("the wiki page is displayed") while preconditions are all
   element-presence ("a menu toggle is present"); `effects ∩ preconditions = ∅`
   in both runs → 0 edges (`operators.py:44` `A→B iff effects(A) & preconds(B)`)
   → `all_chains(min_len=2)` empty → 0 GOAL. Synonym canonicalization cannot help
   because eff/pre are different predicate *types*, not synonyms.
   (Canonicalization itself works — reddit `p0` is reused across two operators.)

## Goal

Produce non-zero GOAL tasks on a live run by (A) generating multi-step tasks so
adjacent skills form, and (B) inducing operators whose exit page-state reads
identically to the next skill's entry page-state so an effect→precondition edge
materializes. Both are surgical, prompt-level changes; no new modules, no schema
changes, no `operators.py` edge-rule change.

## Non-goals

- No compositional task generator that reads the skill library (explicitly
  rejected — keep A a prompt nudge, revisit only if A is insufficient).
- No change to `max_steps`, the clustering/maturity gate, or `operators.py`.
- No re-wording of the three thesis overstatements until a live run confirms
  GOAL > 0 (they stay as-is; the bug stays Open until then).

## A — COMPOSITE task type (`hsge/webarena/agents.py`)

A new task type `COMPOSITE`: a 2–3 step sequence of actions a real user chains on
one flow, each step specific to values visible on the page (e.g. "Add the Sony
PS5 to the cart, then open the cart", "Open the post 'Best budget GPU', upvote
it, then post a reply"). When the Solver runs one COMPOSITE task, its trajectory
spans multiple states; `segment_trajectory()` cuts it into **adjacent**
sub-trajectories, so skill *k+1*'s entry state is skill *k*'s exit state — the
raw material B needs to chain.

Changes:

1. **`EXPLORER_SYS`** (agents.py:25): add `COMPOSITE` to the `"type"` enum in the
   JSON contract and to the type-definition sentence; add one rule line: prefer a
   COMPOSITE when the page affords a natural next step, keeping each step concrete
   (names/values on the page), 2–3 steps max. Keep every existing rule
   (specificity, no-answer-in-INFO, no-repeat, no account deletion).
2. **`PageExplorer._TAG_RE`** (agents.py:102): add `COMPOSITE` to the alternation
   so a legacy `[COMPOSITE]` bracket is stripped by `_normalize`/`_parse_task`.
3. **`PageExplorer._parse_task`** (agents.py:150): add `"COMPOSITE"` to the valid
   `explicit_type` set (the `raw_type.strip().upper() in (...)` tuple).

Deliberately unchanged:

- **Truncation** (agents.py:201): `nav_mod = [p for p in parsed if p[1] != "INFO"]`
  already keeps every non-INFO tag over INFO, so COMPOSITE is retained — no edit.
- **`read_only`** (agents.py:185): keeps only `INFO`/`NAV`; COMPOSITE is dropped
  (fail-closed — a composite may contain a MOD step). Correct default. The
  reddit/shopping runs allow MOD, so COMPOSITE flows there.

Downstream: the `[COMPOSITE]` prefix is an opaque string to `runtime.py`, which
strips the leading tag before solving and buckets any non-GOAL task under `LOCAL`.
Implementation must confirm `runtime.py` has no hard `tag ∈ {INFO,NAV,MOD}`
assertion (grep before editing); if one exists, extend it to include COMPOSITE.

## B — page-state vocabulary (`hsge/operator_induction.py::_SYS`)

Reshape the induction prompt so preconditions and effects are expressed as
**page states** (what page/screen the user is on, what is visible) in a
**consistent** phrasing, so one skill's exit-state reads identically to another's
entry-state.

Changes to `_SYS`:

- Instruct: state preconditions/effects as page states ("on the product listing
  page", "the cart page is shown", "the checkout page is shown"), NOT
  element-presence ("a cart link is present"). Require at least one precondition
  describing the **entry** page-state and at least one effect describing the
  **exit** page-state, worded so a downstream skill starting from that exit state
  would phrase its entry precondition the same way.
- Keep the existing "reuse a KNOWN predicate's exact text verbatim" instruction
  (it demonstrably works and now has more chances to fire, since page states
  recur across skills).
- No schema change; `operators.py::edges()` and `all_chains` unchanged.

Side effect (fixes stage 2): any skill that navigates or changes state has
entry ≠ exit, so `eff − pre ≠ ∅` and the anti-tautology gate no longer rejects
it. A pure read-only INFO skill has entry == exit and is still rejected as
tautological — which is correct, it has no planning effect.

## Testing

Deterministic mock tests (must not perturb existing exact-count assertions; the
prompt strings A/B edit are ignored by `MockLLM`, and the parser change is
additive for INFO/NAV/MOD):

1. `_parse_task` returns tag `COMPOSITE` for `{"text": ..., "type": "COMPOSITE"}`
   and for a leading `[COMPOSITE]` bracket.
2. `read_only=True` drops a COMPOSITE task (kept: INFO/NAV).
3. Truncation keeps a COMPOSITE task over an INFO task when over `max_tasks`.
4. `operators.py` level: two skills whose induced effect/precondition share a
   page-state predicate form an edge, `all_chains(min_len=2)` returns the chain,
   and `_goal_tasks()` emits one GOAL task. (Verifies the mechanism A+B feed;
   the prompt wording itself is only verifiable against a real LLM.)

Acceptance criterion (the bug stays Open until this passes): a live
shopping + reddit re-run produces **GOAL > 0** (`summary.json` GOAL bucket
non-zero and `goal_task` events in `run_log.jsonl`). Only then: move the bug to
Fixed and reword the three thesis overstatements (O2 in Chapter1/Chapter6,
§5.1 sentence in Chapter5).

## Files touched

- `hsge/webarena/agents.py` — `EXPLORER_SYS`, `_TAG_RE`, `_parse_task`.
- `hsge/operator_induction.py` — `_SYS`.
- `hsge/webarena/runtime.py` — only if a tag-enum assertion is found (verify).
- `hsge/tests/` — new/extended tests per the four cases above.
- `.claude/memory/{changelog.md,bugs.md}` — updated in the same commit.
