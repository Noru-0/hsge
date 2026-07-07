# Run 02 Exploration Log (reddit, 2026-07-06)

Session log for a real WebArena run against the `reddit` site (Postmill-style
forum clone), analyzed post-hoc from `outputs/wa_run_02/{run_log.jsonl,
nodes.json,summary.json,skills.json,operators.json}`. Written in response to
three questions: why the run ended where it did, how good the exploration
was, and a record for future comparison.

## Run parameters

- `site: reddit`, `out_dir: outputs/wa_run_02`, config as committed in
  `config.yaml` at the time (`max_nodes: 500`, `max_depth: 300`, `max_tasks:
  9`, `maturity: 2`, `terminal_goal: null` — reddit has no configured
  terminal goal, so this run is exploration-only; no GOAL-tagged episodes
  are expected).
- Duration: `started_at_iso 2026-07-06T20:30:41` → `ended_at_iso
  2026-07-06T22:18:00`, `duration_sec: 6438.8` (~1h 47m).
- `status: "done"`, `error: null` — the run ended normally, not via the
  `run_error` path added in the timing/logging feature earlier this
  session.

## Why the run stopped at 57 nodes (well short of `max_nodes: 500`)

Not a crash and not a limit hit:

- `run_log.jsonl` has no `run_error` event, and `summary.json` reports
  `status: "done"` — the process reached the natural end of `run()`'s
  `while frontier and len(visited) < self.max_nodes:` loop, not an
  exception.
- It didn't hit `max_nodes` (63 total node slots consumed — 57 visited + 6
  duplicate-content skips — against a ceiling of 500) or `max_depth` (deepest
  node reached was depth 6, against a ceiling of 300).
- The actual stop condition was **`frontier` emptying out**. Depth
  distribution over the run: `{0: 1, 1: 5, 2: 16, 3: 19, 4: 14, 5: 6, 6:
  2}` — growth tapers off sharply after depth 3-4 and produces almost
  nothing new by depth 6.

This matches a limitation already called out in
[`.claude/rules/architecture.md`](../.claude/rules/architecture.md)'s
"Known gap": frontier growth is driven entirely by URLs the agent actually
*navigates to while solving a proposed task* (`Step.url` for every step,
plus open tabs) — **not** by mining every `<a href>` out of the page's
axtree/DOM directly. Two compounding effects starved the frontier in this
run:

1. A large share of proposed tasks are `[INFO]` (read-only lookups — "find
   the number of upvotes for...", "find the publication date for...") which
   by design never navigate anywhere, so they contribute zero new frontier
   URLs regardless of how many links are visible on the page.
2. Of the tasks that *could* have grown the frontier (`[NAV]`/`[MOD]`), a
   meaningful fraction failed outright — e.g. node 58's two "Go to the
   'Delete' option for..." NAV tasks both failed (7 and 5 steps), node 62's
   "Go to the 'Subscribe via RSS' link" NAV task failed after burning the
   full 15-step budget. A failed episode still contributes whatever URLs the
   solver happened to visit mid-attempt (`seen_urls.update(st.url for st in
   steps)` runs unconditionally), but a NAV task that never reaches its
   target obviously can't add that target URL.

Combined with the denylist (`logout|\?p=|product_list_|[?&]sort=`, which
blocks pagination and sort-order variants of the same page) narrowing what's
even admissible, the reachable "novel" URL surface under this run's
allow/deny rules was exhausted by depth 6 on this fixed-content forum
instance. **This is an expected consequence of a documented architectural
gap, not a bug** — but it does mean runs against link-dense sites will
under-explore relative to `max_nodes` until frontier expansion also mines
unclicked `<a href>`s directly, as the architecture doc already suggests as
a next step.

## Exploration quality assessment

**Coverage:** 57 unique nodes visited (62 unique URLs total across
visits+duplicate-skips), 196 solver episodes attempted, depth capped at 6
for the reasons above.

**Task success:** 140/196 LOCAL episodes succeeded (71.4%). Failed episodes
used more than double the steps on average (11.1 vs. an overall average of
4.95) — consistent with the Solver repeatedly retrying before either
succeeding late, exhausting `max_steps: 15`, or hitting the same-target
stuck-loop guard (`_MAX_REPEATS`) documented in
`.claude/rules/architecture.md`. No GOAL episodes ran, correctly matching
`terminal_goal: null` for this site.

**Skill/operator quality — the interesting finding.** 7 skills were admitted
(recurred `maturity: 2`+ times), but only 6 were promoted to operators —
`locate_and_click_navigation_link` induced no usable effect predicate and
was silently dropped by `_promote_skill_to_operator`'s `if not eff: return`
guard. Of the 6 operators that *were* created, the grounding-check feature
added earlier this session (`operator_grounding_check` events) shows real
quality variance that would have been invisible before:

| Operator | Precondition | Effect | Grounding | Verdict |
|---|---|---|---|---|
| `find_latest_revision_id` | p4 (100%) | p5 (100%) — distinct from precondition | strong | **Genuinely useful** — a real state change, well-confirmed both ways. |
| `navigatetomainpage` | p1 (100%) | p1 (100%) — same predicate as precondition | tautological | Confirmed-true, but effect restates the precondition — contributes nothing new to chain toward. |
| `locateprimarynavigationm` | p8 (100%) | p8 (100%) — same predicate | tautological | Same issue. |
| `findlasteditedtimebypost` | p2, p3 (100%/100%) | p3 (100%) — reuses one precondition | partially tautological | Only weakly informative for planning. |
| `selectforum` | p6, p7 (50%/50%) | p6 (50%) | weakly grounded | Only true in 1 of 2 members — low-confidence induction either way. |
| `navigate_to_notification` | p0 (100%) | p0 (**0%**) | **ungrounded** | The stated effect never actually held after the skill ran in either member — a hallucinated/wrong effect that the LLM asserted with no support. |

Only 1 of 6 induced operators (`find_latest_revision_id`) is a clean,
compositionally useful precondition→effect pair. Three are tautological
(precondition == effect, so `OperatorGraph.successors()` can never treat
them as newly-enabling anything — see `hsge/operators.py`'s `successors()`,
which explicitly filters out predicates already true in the current state).
One is weakly grounded (50%), and one has a completely unconfirmed effect.
This is exactly the failure mode the grounding-check feature (this
session's earlier work) was built to surface, and this run is the first
real evidence it catches real problems, not just theoretical ones.

## Takeaways for future runs

1. **Frontier starvation on link-dense/read-heavy sites is expected** until
   frontier expansion also mines `<a href>`s from the axtree/DOM directly
   (already flagged as a next step in the architecture doc) rather than
   relying solely on solved-task navigation.
2. **Operator induction quality is uneven** — half of this run's operators
   were tautological or ungrounded. The grounding-check accuracy fields in
   `operators.json` (`precondition_confirmed`/`effect_confirmed`) are now
   the right place to look before trusting an operator for planning; a
   follow-up could consider filtering/flagging operators where
   `precondition == effect` or grounding accuracy is 0, though that's a
   deliberate scope decision to make separately (the grounding-check feature
   was built observation-only, per its design spec).
3. **Failed NAV/MOD tasks cost the most** — both in wasted step budget (11.1
   avg steps on failures vs. 4.95 overall) and in frontier growth forgone,
   since a failed NAV task is exactly the case that would have added a new
   URL had it succeeded.
