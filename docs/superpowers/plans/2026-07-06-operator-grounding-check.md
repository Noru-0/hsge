# Operator Grounding-Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second LLM-verification pass that checks each induced operator precondition/effect against the real boundary axtrees of every member of its skill, and surface per-predicate accuracy in `operators.json` and `run_log.jsonl` — observation only, no change to admission or planning.

**Architecture:** A new `verify_operator_grounding()` function in `hsge/operator_induction.py` takes the already-induced precondition/effect text lists plus `(before, after)` axtree pairs for *all* members of a skill, makes one batched LLM call, and returns per-predicate confirmation accuracy. `WebArenaExplorer._promote_skill_to_operator` (in `hsge/webarena/runtime.py`) calls it right after `induce_operator()`, maps text→canonical predicate id via the existing `PredicateRegistry`, stores the result in a new `self.operator_grounding` dict, and logs it. `_dump_artifacts()` merges that dict into each operator's entry in `operators.json`.

**Tech Stack:** Python 3, existing `LLM.complete_json` abstraction (no new deps).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-06-operator-grounding-check-design.md`
- No change to `Operator` (frozen dataclass in `hsge/operators.py`), planning (`hsge/operators.py::plan`), or which predicates end up in an operator's `preconditions`/`effects`.
- `induce_operator()`'s own sampling stays at 2 members — only the new grounding check uses the full member set (`card.member_ids`, unsliced).
- Only `operators.json` and `run_log.jsonl` gain new fields. `summary.json` and console `print()` output are unchanged.
- This code path is only reachable from `WebArenaExplorer._promote_skill_to_operator` (real WebArena runtime) — must not affect the mock pipeline or any existing test.
- Malformed/short LLM responses degrade to "unconfirmed" (`false`), never raise.

---

### Task 1: `verify_operator_grounding()` in `operator_induction.py`

**Files:**
- Modify: `hsge/operator_induction.py`
- Test: `hsge/tests/test_operator_grounding.py` (new)

**Interfaces:**
- Consumes: `hsge.llm.LLM` (`complete_json(system, prompt, image_b64=None, image_detail="low") -> dict`), nothing else new.
- Produces: `verify_operator_grounding(llm: LLM, preconditions: list[str], effects: list[str], boundary_obs: list[tuple[str, str]]) -> dict` returning `{"precondition_accuracy": {text: float}, "effect_accuracy": {text: float}, "member_count": int}`. `runtime.py` (Task 2) calls this exact signature.

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_operator_grounding.py`:

```python
"""verify_operator_grounding checks induced predicates against every
member's real boundary axtree, independent of the 2-member sample
induce_operator() itself uses for context."""

from hsge.operator_induction import verify_operator_grounding


class _StubLLM:
    def __init__(self, response):
        self._response = response
        self.last_prompt = None

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.last_prompt = prompt
        return self._response


def test_all_confirmed_across_all_members():
    llm = _StubLLM({
        "results": [
            {"predicate": "search results are shown", "type": "precondition",
             "member_holds": [True, True]},
            {"predicate": "an item is in the cart", "type": "effect",
             "member_holds": [True, True]},
        ]
    })
    boundary = [("before1", "after1"), ("before2", "after2")]

    out = verify_operator_grounding(
        llm, ["search results are shown"], ["an item is in the cart"], boundary)

    assert out == {
        "precondition_accuracy": {"search results are shown": 1.0},
        "effect_accuracy": {"an item is in the cart": 1.0},
        "member_count": 2,
    }


def test_mixed_confirmation_computes_fraction():
    llm = _StubLLM({
        "results": [
            {"predicate": "search results are shown", "type": "precondition",
             "member_holds": [True, False]},
        ]
    })
    boundary = [("before1", "after1"), ("before2", "after2")]

    out = verify_operator_grounding(llm, ["search results are shown"], [], boundary)

    assert out["precondition_accuracy"] == {"search results are shown": 0.5}
    assert out["member_count"] == 2


def test_missing_or_short_member_holds_counts_as_unconfirmed():
    llm = _StubLLM({
        "results": [
            {"predicate": "an item is in the cart", "type": "effect",
             "member_holds": [True]},  # only 1 entry for 3 members
        ]
    })
    boundary = [("b1", "a1"), ("b2", "a2"), ("b3", "a3")]

    out = verify_operator_grounding(llm, [], ["an item is in the cart"], boundary)

    assert out["effect_accuracy"] == {"an item is in the cart": 1 / 3}
    assert out["member_count"] == 3


def test_predicate_missing_from_response_defaults_to_zero():
    llm = _StubLLM({"results": []})
    boundary = [("b1", "a1")]

    out = verify_operator_grounding(llm, ["never mentioned"], ["also missing"], boundary)

    assert out["precondition_accuracy"] == {"never mentioned": 0.0}
    assert out["effect_accuracy"] == {"also missing": 0.0}
    assert out["member_count"] == 1


def test_empty_predicates_and_boundary_returns_zero_member_count():
    llm = _StubLLM({"results": []})

    out = verify_operator_grounding(llm, [], [], [])

    assert out == {"precondition_accuracy": {}, "effect_accuracy": {}, "member_count": 0}


def test_malformed_response_does_not_raise():
    llm = _StubLLM({"results": "not a list"})
    boundary = [("b1", "a1")]

    out = verify_operator_grounding(llm, ["p"], ["e"], boundary)

    assert out == {"precondition_accuracy": {"p": 0.0}, "effect_accuracy": {"e": 0.0},
                   "member_count": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_operator_grounding.py -v`
Expected: FAIL — `ImportError: cannot import name 'verify_operator_grounding'`

- [ ] **Step 3: Implement `verify_operator_grounding()`**

Append to `hsge/operator_induction.py` (after the existing `induce_operator` function, keep `_AXTREE_CAP` shared):

```python
_GROUNDING_SYS = (
    "You verify PLANNING PREDICATES against real page states. You are given "
    "a list of predicates (each tagged precondition or effect) and, for "
    "each occurrence of the skill, the page's accessibility tree BEFORE and "
    "AFTER the skill ran. For a precondition, check it against the BEFORE "
    "tree of every occurrence; for an effect, check it against the AFTER "
    "tree of every occurrence. "
    'Return JSON {"results": [{"predicate": "<exact text>", "type": '
    '"precondition"|"effect", "member_holds": [true|false, ...]}, ...]}, '
    "one entry per predicate, with member_holds having exactly one boolean "
    "per occurrence in the order given."
)


def verify_operator_grounding(
    llm: LLM,
    preconditions: list[str],
    effects: list[str],
    boundary_obs: list[tuple[str, str]],
) -> dict:
    """Check induced preconditions/effects against every member's real
    boundary axtree (unlike induce_operator, which only samples 2 for
    context). Returns per-predicate confirmation accuracy; never raises on a
    malformed LLM response -- an unconfirmed predicate degrades to 0.0
    rather than breaking the run, since this is a quality signal, not a gate.
    """
    member_count = len(boundary_obs)
    occurrences = [
        {"before": (start or "")[:_AXTREE_CAP], "after": (end or "")[:_AXTREE_CAP]}
        for start, end in boundary_obs
    ]
    payload = {
        "preconditions": preconditions,
        "effects": effects,
        "occurrences": occurrences,
    }
    precondition_accuracy = {p: 0.0 for p in preconditions}
    effect_accuracy = {e: 0.0 for e in effects}
    if member_count == 0 and not preconditions and not effects:
        return {"precondition_accuracy": {}, "effect_accuracy": {}, "member_count": 0}

    out = llm.complete_json(_GROUNDING_SYS, f"<payload>{json.dumps(payload)}</payload>")
    results = out.get("results", [])
    if not isinstance(results, list):
        results = []

    for entry in results:
        if not isinstance(entry, dict):
            continue
        predicate = entry.get("predicate")
        holds = entry.get("member_holds", [])
        if not isinstance(holds, list):
            holds = []
        confirmed = sum(1 for h in holds[:member_count] if h is True)
        accuracy = (confirmed / member_count) if member_count else 0.0
        if entry.get("type") == "precondition" and predicate in precondition_accuracy:
            precondition_accuracy[predicate] = accuracy
        elif entry.get("type") == "effect" and predicate in effect_accuracy:
            effect_accuracy[predicate] = accuracy

    return {
        "precondition_accuracy": precondition_accuracy,
        "effect_accuracy": effect_accuracy,
        "member_count": member_count,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_operator_grounding.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add hsge/operator_induction.py hsge/tests/test_operator_grounding.py
git commit -m "$(cat <<'EOF'
Add verify_operator_grounding: check induced predicates against real axtrees

One batched LLM call per skill checks every induced precondition/effect
against ALL members' boundary axtrees (induce_operator itself still only
samples 2 for context) -- a quality signal for operator induction, not a
gate. Degrades to unconfirmed on malformed LLM output rather than raising.
EOF
)"
```

---

### Task 2: Wire grounding-check into `_promote_skill_to_operator`

**Files:**
- Modify: `hsge/webarena/runtime.py`

**Interfaces:**
- Consumes: `verify_operator_grounding` from Task 1 (`hsge/operator_induction.py`), `self.registry.canonical(text) -> str` (existing, `hsge/predicate_registry.py`), `self.library.subtrajs.get(mid)` (existing).
- Produces: `self.operator_grounding: dict[str, dict]` keyed by `Operator.name`, each value `{"precondition_accuracy": {pid: float}, "effect_accuracy": {pid: float}, "member_count": int}` — Task 3 (`_dump_artifacts`) reads this exact structure.

- [ ] **Step 1: Add the import and instance dict**

In `hsge/webarena/runtime.py`, change the import line:

```python
from ..operator_induction import induce_operator
```
to:
```python
from ..operator_induction import induce_operator, verify_operator_grounding
```

In `__init__`, right after `self.opgraph = OperatorGraph()` (around line 69), add:

```python
        self.opgraph = OperatorGraph()
        # name -> {"precondition_accuracy": {pid: float}, "effect_accuracy": {pid:
        # float}, "member_count": int}; observation-only signal, never gates
        # admission or planning (see docs/superpowers/specs/2026-07-06-...).
        self.operator_grounding: dict[str, dict] = {}
```

- [ ] **Step 2: Run the grounding check inside `_promote_skill_to_operator`**

In `hsge/webarena/runtime.py`, `_promote_skill_to_operator` currently reads (around lines 134-158):

```python
        card = self._card_by_id(skill_id)
        if card is None:
            return
        members = [self.library.subtrajs.get(mid) for mid in card.member_ids[:2]]
        members = [m for m in members if m and m.steps]
        if not members:
            print(f"[operator] skill {skill_id} has no usable member steps; "
                  "inducing without page context")
        boundary = [(m.steps[0].axtree, m.steps[-1].axtree) for m in members]
        induced = induce_operator(self.operator_llm, card, boundary)
        pre = frozenset(self.registry.canonical(p) for p in induced["preconditions"])
        eff = frozenset(self.registry.canonical(e) for e in induced["effects"])
        if not eff:
            return
        # terminal only when a real terminal goal is configured and a member reached it
        reached_terminal = bool(self.terminal_goal) and any(
            reached(self.terminal_goal, m.steps[-1].url, m.steps[-1].axtree) for m in members)
        op = Operator(_slug(card.name), pre, eff, terminal=induced["terminal"] or reached_terminal)
        self.opgraph.add(op)
        pre_txt = [f"{p}:{self.registry.label(p)}" for p in sorted(op.preconditions)]
        eff_txt = [f"{e}:{self.registry.label(e)}" for e in sorted(op.effects)]
        print(f"    [operator] {op.name}  pre={pre_txt}  eff={eff_txt}  terminal={op.terminal}")
        self._log("operator_induced", name=op.name, skill_id=skill_id,
                   preconditions=sorted(op.preconditions), effects=sorted(op.effects),
                   terminal=op.terminal)
```

Replace the whole block with (new code after the existing `self._log("operator_induced", ...)` call):

```python
        card = self._card_by_id(skill_id)
        if card is None:
            return
        members = [self.library.subtrajs.get(mid) for mid in card.member_ids[:2]]
        members = [m for m in members if m and m.steps]
        if not members:
            print(f"[operator] skill {skill_id} has no usable member steps; "
                  "inducing without page context")
        boundary = [(m.steps[0].axtree, m.steps[-1].axtree) for m in members]
        induced = induce_operator(self.operator_llm, card, boundary)
        pre = frozenset(self.registry.canonical(p) for p in induced["preconditions"])
        eff = frozenset(self.registry.canonical(e) for e in induced["effects"])
        if not eff:
            return
        # terminal only when a real terminal goal is configured and a member reached it
        reached_terminal = bool(self.terminal_goal) and any(
            reached(self.terminal_goal, m.steps[-1].url, m.steps[-1].axtree) for m in members)
        op = Operator(_slug(card.name), pre, eff, terminal=induced["terminal"] or reached_terminal)
        self.opgraph.add(op)
        pre_txt = [f"{p}:{self.registry.label(p)}" for p in sorted(op.preconditions)]
        eff_txt = [f"{e}:{self.registry.label(e)}" for e in sorted(op.effects)]
        print(f"    [operator] {op.name}  pre={pre_txt}  eff={eff_txt}  terminal={op.terminal}")
        self._log("operator_induced", name=op.name, skill_id=skill_id,
                   preconditions=sorted(op.preconditions), effects=sorted(op.effects),
                   terminal=op.terminal)

        # Grounding check: unlike induce_operator's 2-member sample, this uses
        # every member of the skill to score whether each induced predicate
        # actually holds -- observation-only, never gates admission/planning.
        all_members = [self.library.subtrajs.get(mid) for mid in card.member_ids]
        all_members = [m for m in all_members if m and m.steps]
        all_boundary = [(m.steps[0].axtree, m.steps[-1].axtree) for m in all_members]
        grounding = verify_operator_grounding(
            self.operator_llm, induced["preconditions"], induced["effects"], all_boundary)
        pre_acc = {self.registry.canonical(p): acc
                   for p, acc in grounding["precondition_accuracy"].items()}
        eff_acc = {self.registry.canonical(e): acc
                   for e, acc in grounding["effect_accuracy"].items()}
        self.operator_grounding[op.name] = {
            "precondition_accuracy": pre_acc,
            "effect_accuracy": eff_acc,
            "member_count": grounding["member_count"],
        }
        self._log("operator_grounding_check", name=op.name, skill_id=skill_id,
                   member_count=grounding["member_count"],
                   precondition_accuracy=pre_acc, effect_accuracy=eff_acc)
```

- [ ] **Step 3: Manual smoke check (no unit test framework touches `runtime.py` today)**

Run: `PYTHONPATH=. python run_webarena.py --dry-run --out /tmp/wa_grounding_check --max-nodes 2`
Expected: run completes without exceptions; then:

```bash
python -c "
import json
log = [json.loads(l) for l in open('/tmp/wa_grounding_check/run_log.jsonl')]
events = [r for r in log if r['event'] == 'operator_grounding_check']
print(f'{len(events)} operator_grounding_check events')
for e in events:
    print(e['name'], e['member_count'], e['precondition_accuracy'], e['effect_accuracy'])
"
```
Expected: prints one line per induced operator with `member_count >= 1` and accuracy dicts keyed by canonical predicate ids (e.g. `p0`, `p1`) mapping to floats.

- [ ] **Step 4: Commit**

```bash
git add hsge/webarena/runtime.py
git commit -m "$(cat <<'EOF'
Run grounding-check when promoting a skill to an operator

_promote_skill_to_operator now calls verify_operator_grounding after
inducing pre/effects, using ALL of the skill's members (induce_operator
itself still samples only 2 for context). Result is stored in
self.operator_grounding and logged as operator_grounding_check --
observation-only, doesn't affect which operators get created.
EOF
)"
```

---

### Task 3: Surface grounding accuracy in `operators.json`

**Files:**
- Modify: `hsge/webarena/runtime.py` (`_dump_artifacts`)

**Interfaces:**
- Consumes: `self.operator_grounding` dict produced in Task 2.
- Produces: two new keys per entry in the `operators.json` list: `precondition_confirmed`, `effect_confirmed`.

- [ ] **Step 1: Extend the `operators` list comprehension in `_dump_artifacts`**

In `hsge/webarena/runtime.py`, `_dump_artifacts` currently builds `operators` as (around lines 189-196):

```python
        operators = [{"name": op.name, "preconditions": sorted(op.preconditions),
                      "effects": sorted(op.effects), "terminal": op.terminal,
                      "precondition_labels": {p: self.registry.label(p)
                                              for p in sorted(op.preconditions)},
                      "effect_labels": {e: self.registry.label(e)
                                        for e in sorted(op.effects)}}
                     for op in self.opgraph.ops.values()]
```

Replace with:

```python
        operators = []
        for op in self.opgraph.ops.values():
            grounding = self.operator_grounding.get(op.name, {})
            operators.append({
                "name": op.name, "preconditions": sorted(op.preconditions),
                "effects": sorted(op.effects), "terminal": op.terminal,
                "precondition_labels": {p: self.registry.label(p)
                                        for p in sorted(op.preconditions)},
                "effect_labels": {e: self.registry.label(e)
                                  for e in sorted(op.effects)},
                "precondition_confirmed": grounding.get("precondition_accuracy", {}),
                "effect_confirmed": grounding.get("effect_accuracy", {}),
            })
```

- [ ] **Step 2: Manual smoke check**

Run: `PYTHONPATH=. python run_webarena.py --dry-run --out /tmp/wa_grounding_check --max-nodes 2`

```bash
python -c "
import json
ops = json.load(open('/tmp/wa_grounding_check/operators.json'))
for op in ops:
    print(op['name'], op.get('precondition_confirmed'), op.get('effect_confirmed'))
"
```
Expected: each operator prints `precondition_confirmed`/`effect_confirmed` dicts (non-empty if that operator has preconditions/effects and a successful grounding check ran).

- [ ] **Step 3: Commit**

```bash
git add hsge/webarena/runtime.py
git commit -m "$(cat <<'EOF'
Add precondition_confirmed/effect_confirmed to operators.json

Each operator entry now carries its grounding-check accuracy alongside the
existing NL labels, so run artifacts show not just what was induced but how
well it held up against the skill's real boundary axtrees.
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** `verify_operator_grounding()` (spec §1) → Task 1. Wiring + `self.operator_grounding` + `operator_grounding_check` log event (spec §2) → Task 2. `operators.json` fields (spec §3) → Task 3. Non-goals (no `Operator` schema change, no admission/planning change, no `summary.json`/console change, `induce_operator` still samples 2) are respected in all three tasks — verified no edits touch `hsge/operators.py`, `_goal_task`, `_dump_artifacts`'s `summary` block, or any `print()` call.
- **Placeholder scan:** none — every step has runnable code and exact expected output.
- **Type consistency:** `verify_operator_grounding` signature in Task 1 matches the call site in Task 2 exactly (`llm, preconditions, effects, boundary_obs`). `self.operator_grounding[op.name]` structure written in Task 2 matches what Task 3 reads via `.get("precondition_accuracy", {})` / `.get("effect_accuracy", {})`.
