# Operator Grounding-Check Design

Date: 2026-07-06

## Problem

`operator_induction.py::induce_operator` asks an LLM to state a skill's
preconditions/effects in free NL, using only the first 2 members'
before/after axtrees as context. `runtime.py::_promote_skill_to_operator`
takes that output at face value and turns it into an `Operator` with no
signal on whether the stated preconditions/effects actually hold across the
skill's real occurrences. There is currently no way to tell, from the run
artifacts, whether an induced predicate is well-grounded or an LLM
hallucination — quality of the operator layer is unobserved.

## Goal

Add a second, independent verification pass — a "grounding check" — that
tests each induced precondition/effect against the real boundary axtrees of
every member of the skill, and surface the resulting accuracy in the run's
output artifacts. This is purely observational: it must not change which
operators get created, how planning composes them, or the mock pipeline
(`operator_induction.py` and this new code are only exercised from the real
WebArena runtime; see `hsge/webarena/runtime.py`).

## Design

### 1. `verify_operator_grounding()` — new function in `operator_induction.py`

```python
def verify_operator_grounding(
    llm: LLM,
    preconditions: list[str],
    effects: list[str],
    boundary_obs: list[tuple[str, str]],
) -> dict:
    """Check induced predicates against every member's real boundary axtree.

    Returns {"precondition_accuracy": {text: float}, "effect_accuracy":
    {text: float}, "member_count": int}. Accuracy is the fraction of members
    where the LLM confirmed the predicate holds (preconditions checked
    against each member's `before` axtree, effects against `after`).
    """
```

- One batched LLM call per skill: the payload lists all precondition/effect
  predicate strings plus the `(before, after)` axtree pair (capped by the
  existing `_AXTREE_CAP`) for **every** member of the skill (`card.member_ids`
  in full — not the `[:2]` sample `induce_operator` uses for context).
- Prompt asks the LLM to return, per predicate, a list of booleans aligned to
  member order (`true` = the predicate holds in that member's relevant
  axtree).
- If the LLM returns a malformed/short list for a predicate, missing entries
  count as unconfirmed (`false`) rather than erroring — this is a quality
  signal, not a gate, so it must degrade gracefully.
- Accuracy = confirmed_count / member_count per predicate. `member_count`
  reflects how many members actually had usable axtrees (mirrors the
  existing `members = [m for m in members if m and m.steps]` filtering in
  `runtime.py`).

### 2. Wiring in `runtime.py::_promote_skill_to_operator`

- After `induce_operator()` runs (unchanged: still samples 2 members for the
  induction call itself) and canonical predicate ids are assigned, fetch
  boundary axtrees for **all** of `card.member_ids` (a new, separate fetch
  from the induction sample).
- Call `verify_operator_grounding(self.operator_llm, induced["preconditions"], induced["effects"], all_boundary)`.
- Map the by-text accuracy dicts to canonical ids via `self.registry.canonical(text)` — reuses the same ids already computed for `pre`/`eff`, so results index consistently with what's in `operators.json`.
- Store the mapped result in a new instance dict `self.operator_grounding: dict[str, dict]` keyed by `op.name`, holding `{"precondition_accuracy": {pid: float}, "effect_accuracy": {pid: float}, "member_count": int}`.
- `Operator` (the frozen dataclass in `operators.py`) is **not** changed —
  grounding data lives alongside it in the explorer, not inside the planning
  data structure.
- Log a new event: `self._log("operator_grounding_check", name=op.name, skill_id=skill_id, member_count=..., precondition_accuracy={pid: acc, ...}, effect_accuracy={pid: acc, ...})`.

### 3. Output surface: `operators.json` only

In `_dump_artifacts()`, each operator entry gains two fields alongside the
existing `precondition_labels`/`effect_labels`:

```json
{
  "name": "...",
  "preconditions": ["p3"],
  "effects": ["p7"],
  "terminal": false,
  "precondition_labels": {"p3": "search results are shown"},
  "effect_labels": {"p7": "an item is in the cart"},
  "precondition_confirmed": {"p3": 0.5},
  "effect_confirmed": {"p7": 1.0}
}
```

Sourced from `self.operator_grounding.get(op.name, {})`; missing entries
(e.g. an operator whose grounding check hasn't run, shouldn't happen in
practice but defend anyway) default to an empty dict.

`summary.json` and console `print()` output are explicitly **out of scope**
for this change — only `operators.json` and `run_log.jsonl` gain new fields.

## Non-goals

- No change to operator admission, planning (`operators.py::plan`), or which
  predicates end up in `Operator.preconditions`/`effects`.
- No change to `induce_operator()`'s own sampling (still 2 members) — only
  the new grounding check uses the full member set.
- No change to `summary.json` or console output.
- No change to the mock pipeline or any existing test (grounding check code
  is only reachable from `WebArenaExplorer._promote_skill_to_operator`).

## Testing

- Unit test for `verify_operator_grounding()` with a stub LLM returning a
  fixed accuracy pattern (mirrors existing test style for
  `operator_induction.py`, if any exists — otherwise a new
  `hsge/tests/test_operator_grounding.py`), covering: all-true, mixed,
  malformed/short response handling.
- Manual check: `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2` and inspect `operators.json` for the new fields.
