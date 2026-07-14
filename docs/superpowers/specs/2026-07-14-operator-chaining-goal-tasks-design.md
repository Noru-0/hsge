# Operator Chaining + Depth-Gated Goal Tasks — Design

**Status:** approved, awaiting implementation plan
**Date:** 2026-07-14

## Problem

Real-run evidence from `outputs/wa_run_09` (reddit, 62 nodes, 228 episodes, 4 skills →
4 operators) shows the operator layer produces no composable structure, so no GOAL
task was ever attempted:

1. **Zero cross-operator edges.** The chaining rule is `A -> B iff effects(A) ∩
   preconditions(B) ≠ ∅` on canonical predicate ids — and no two operators in the
   run share a single id (10 predicates, all distinct, each operator an island).
2. **Predicate fragmentation is measured, not hypothesized.** With the run's own
   embedder (`all-MiniLM-L6-v2`) and threshold (0.6), the one pair that *should*
   merge scores below threshold while a pair that should *not* merge scores above:
   - `p1` "a notification indicator with a count is present" vs `p8` "notification
     icon is visible" → cosine **0.570** (true synonym pair, not merged — the edge
     `report_notification → open_notification` never formed);
   - `p3` "a reply button is visible" vs `p4` "a submit button is visible" →
     cosine **0.606** (false pair, above threshold).
   The false pair scores *higher* than the true pair, so **no threshold value can
   fix this** — embedding-only canonicalization at this granularity lacks the
   semantic resolution. Root cause upstream: `induce_operator`'s prompt never shows
   the LLM the existing predicate vocabulary, so every induction freely invents new
   phrasings and the embedding registry is the only (insufficient) unifying force.
3. **3 of 4 operators are tautological** (effects ⊆ preconditions: `p1→p1`,
   `p7→p7`, `p9→p9`) — the LLM restated a precondition as the "effect", so the
   operator encodes no state change. The 4th (`replytocomment`) has real effects
   but its grounding check confirmed them at 0.0 across members.
4. **`terminal_goal` is nil on non-shopping sites**, so even a well-formed graph
   would never produce a goal task there; and the goal instruction text is
   hardcoded to "Purchase an item…" (shopping-only wording).

## Decisions (made with the user)

| # | Question | Decision |
|---|---|---|
| 1 | Relationship between depth-based goals and `terminal_goal` | **Depth-based is the primary mechanism on all sites; `terminal_goal` is a two-level backup** (details in §3) |
| 2 | Initial state for chain computation / episode start | **Structural chains** (DFS over effect→precondition edges, no initial-state BFS) + episode starts from the first chain operator's recorded init URL, embedded in the instruction (`goto` is in the Solver's action space) |
| 3 | Verification of depth-based goal episodes | **Self-graded + judge**: Solver's `send_msg_to_user` = declared success, `judge_episodes.py` re-checks offline — no new verify machinery |
| 4 | Fixing predicate fragmentation | **Vocabulary-aware induction** (LLM sees existing predicates, reuses verbatim); embedding registry stays as a second-line safety net. LLM-judge canonicalization deferred until re-measured on a real run |
| 5 | Multiple chains to a goal | **Enumerate all simple chains ≥ 2 and attempt each once per run** (task variations = more data), capped per node visit |

## Design

### §1 Vocabulary-aware induction

`hsge/operator_induction.py::induce_operator` gains an optional parameter:

```python
def induce_operator(llm, card, boundary_obs,
                    known_predicates: list[str] | None = None) -> dict:
```

- Payload gains `"known_predicates": [...]` — a **mixed selection of up to 50**
  of the registry's existing labels: the **25 most frequently used** (by how many
  times `canonical()` resolved to that id — keeps the core vocabulary that
  foundational operators share) **+ the 25 most recent** (keeps new concepts
  visible), deduplicated. Recent-only selection would "forget" foundational
  predicates once the vocabulary outgrows the cap, prompting the LLM to re-coin
  phrases for old concepts.
- `PredicateRegistry` gains a usage counter (`self.counts: dict[int, int]`,
  incremented on every `canonical()` call) and a selector:

  ```python
  def vocabulary(self, max_frequent: int = 25, max_recent: int = 25) -> list[str]:
      """Labels for prompt context: most-used ids first, then most recent,
      deduplicated, capped at max_frequent + max_recent."""
  ```
- `_SYS` gains one rule: *"A list of KNOWN predicates from previously induced
  operators may be provided. If a precondition or effect you want to state is
  semantically equivalent to a known predicate, you MUST reuse that predicate's
  exact text verbatim instead of rephrasing it. Only coin a new phrase when no
  known predicate matches."*
- `runtime._promote_skill_to_operator` passes
  `known_predicates=self.registry.vocabulary()`.
- `PredicateRegistry` is unchanged — cosine 0.6 remains as fallback dedup for
  the cases where the LLM doesn't comply.

### §2 Anti-tautology gate

In `runtime._promote_skill_to_operator`, after canonicalization:

```python
eff = eff - pre          # drop effects that merely restate a precondition
if not eff:
    self._log("operator_rejected", skill_id=skill_id, name=_slug(card.name),
              reason="tautological", preconditions=sorted(pre))
    print(f"    [operator] rejected {_slug(card.name)}: no novel effects (tautological)")
    return
```

- A skill whose only "effects" restate its preconditions (typical for INFO skills
  that read state rather than change it) does not become an operator.
- Mixed case: novel effects survive the subtraction; only the tautological subset
  is dropped. The `operator_induced` log event gains an `effects_dropped` field
  (the tautological subset, canonical ids) so mixed-case promotions are auditable.
  **Known residual risk (monitor, don't fix yet):** a surviving novel effect can
  still be semantically trivial (e.g. a hover/focus state change), producing
  low-value chains. Audit `operator_rejected` + `effects_dropped` on the next
  real run before deciding whether a semantic-triviality filter is needed.
- The grounding check (`verify_operator_grounding`) **stays observation-only** —
  the 2026-07-06 design decision is not reversed here. Using `effect_confirmed`
  as a gate is explicitly deferred.

### §3 Goal tasks: depth-based primary, terminal backup

New method on `hsge/operators.py::OperatorGraph`:

```python
def all_chains(self, min_len: int = 2, max_len: int = 6,
               max_paths: int = 200) -> list[list[str]]:
    """Simple paths of min_len..max_len operators over effect->precondition
    edges (A -> B iff effects(A) & preconditions(B)). DFS with per-path
    visited set (cycle-safe). max_len and max_paths are circuit breakers:
    today's graphs are tiny (tens of operators), but once §1 fixes predicate
    fragmentation the graph becomes densely connected and unbounded
    simple-path enumeration is O(V!) in the worst case — DFS stops descending
    at max_len and returns as soon as max_paths chains are collected."""
```

`runtime._goal_task()` is rewritten:

1. **Primary (all sites):** `chains = self.opgraph.all_chains(min_len=2)`, minus
   chains already attempted this run (`self._attempted_chains: set[tuple[str, ...]]`),
   capped at `goal_chains_per_node` (config `run.goal_chains_per_node`, default
   **3**) new chains per node visit. For each selected chain, emit a task dict:
   - `goal`: generated from the chain's SkillCards — `"Start by navigating to
     <init_url>. Complete these steps in order: 1) <card A description>. 2) <card
     B description>. …"`. `init_url` is `steps[0].url` of the first member of the
     first chain operator's source skill, recorded at promotion time
     (`self._op_meta: dict[str, dict]` mapping op name → `{card_name,
     description, init_url}`). This replaces the hardcoded "Purchase an item…"
     wording entirely.
   - `difficulty`: `len(chain)`.
   - `kind`: `"depth"`.
   - `goal_predicate`: **`self.terminal_goal` iff the chain's last operator is
     `terminal=True` and `terminal_goal` is configured** (backup verify — the
     deterministic `reached()` check kicks in exactly when a chain reaches a
     terminal state); otherwise `None` (self-graded + judge, decision #3).
2. **Backup (goal source):** if no depth chain is available (graph too shallow —
   the user's `depth < 2` gate) **and** `terminal_goal` is configured **and** the
   old `plan(self.opgraph, frozenset(), goal)` finds a chain toward a terminal
   predicate → emit the legacy terminal task (`kind: "terminal"`,
   `goal_predicate=self.terminal_goal`) with the existing behavior.
3. Neither → `None` (no goal task this node; exploration continues).

`_goal_task()` return type changes from `dict | None` to `list[dict]` (0..N tasks
per node); the GOAL block in `run()` iterates it. Every attempted chain is added
to `_attempted_chains` regardless of outcome (attempt-once-per-run rule; unlike
the deterministic terminal path, self-graded repeats mostly duplicate data).

### §4 Runtime integration & artifacts

- GOAL block in `run()`: loops over `_goal_task()`'s list; per task passes its own
  `goal_predicate`; logs a new `goal_task_selected` event (`kind`, `chain`,
  `goal_predicate`) before solving; existing `task_result` logging unchanged
  (tag stays `GOAL`).
- Config/CLI: `run.goal_chains_per_node` (default 3), CLI `--goal-chains-per-node`.
  Standard precedence (CLI > config.yaml > default).
- `operators.json` gains nothing; `run_log.jsonl` gains `operator_rejected` and
  `goal_task_selected` events; `nodes.json` task entries unchanged in shape.
- `_promote_skill_to_operator` records `self._op_meta[op.name]` at promotion.

### §5 Testing (mock, deterministic)

- **Induction:** payload carries `known_predicates` (and omits it when not given);
  `_SYS` contains the verbatim-reuse rule.
- **Registry vocabulary:** `counts` increments per `canonical()` call;
  `vocabulary()` returns most-frequent first + most-recent, deduplicated, capped.
- **Tautology gate:** eff ⊆ pre → not promoted + `operator_rejected` logged;
  mixed eff → novel subset survives and `effects_dropped` is logged; existing
  empty-eff early return preserved.
- **`all_chains`:** correct enumeration on a synthetic 4-op graph (linear chain,
  branch, cycle) with `min_len` respected; cycle-safe; `max_len` stops descent;
  `max_paths` bounds the result count.
- **`_goal_task`:** (a) shallow graph + no terminal_goal → `[]`; (b) shallow graph
  + terminal_goal + plannable → legacy terminal task; (c) deep graph → depth tasks
  with generated instruction containing init URL + both card descriptions,
  `difficulty == len(chain)`; (d) chain ending in a terminal op + terminal_goal
  set → that task carries `goal_predicate=terminal_goal`; (e) attempted chains
  are not re-emitted; (f) per-node cap respected.
- Full suite stays green; `--dry-run` still completes (its scripted flow reaches
  the terminal path via the DryLLM's terminal operator).

## Out of scope

- LLM-judge canonicalization for the registry (deferred; re-measure predicate
  sharing on a real run after §1 lands).
- Grounding-confirmed effect filtering as a promotion gate (grounding stays
  observation-only per the 2026-07-06 design).
- Resume-interrupted-runs mechanism (separate discussion, not started).
- Changing `reached()`/`predicates.py` or the mock pipeline's
  `curriculum.py::generate_curriculum` (demo-only code path).
