# Phase-2 verified-rate package — design

**Date:** 2026-07-07
**Status:** approved (brainstorm session, run_03 phase-2 re-run review)
**Goal:** raise the phase-2 verified rate (run_03 baseline: 58/89 = 65%; INFO 41/49, NAV 11/20, MOD 6/20, 11 stale-skipped) by eliminating the four dominant false-negative / unsatisfiable-spec classes found in the run_03 failure review.

## Context: what run_03's re-run actually measured

The 16:47 re-run reused `gen_tasks.json` composed at 12:06 — *before* commit
`697be79` (15:28) added the composer MOD/ref gates. So the re-run exercised only
the evaluator-side fixes; the composer gates have never run against a real
site. Failure taxonomy of the 31 failed GEN tasks:

| Class | Count | Root cause |
|---|---|---|
| Pseudo-MOD ("Check if / Verify ...") | 8 of 14 MOD | pre-gate composer output; `MOD_READONLY_RE` now rejects these |
| Real MOD, unsatisfiable `program_html` | ~6 MOD | `must_include` is NL prose ("comment posted successfully"), jQuery `:contains()` locators, invented attrs (`input[name="Formatting help"]`), `checked='false'` never in outerHTML |
| NAV: exact url_match vs slug drift / dead refs / step exhaustion | 9 NAV | post retitled → slug changed (`/f/movies/15/your-title-here` vs live slug); `-` placeholder; some ref URLs mutated away; 3 tasks hit the 25-step cap |
| INFO: stale ground truth not caught | ~5 INFO | timestamps/comment counts/scores mutated by earlier MOD batches; `_is_stale` covers only single-hop INFO on the start page |
| Judge blind to the question | 1–2 INFO | judge sees only answer+reference; `"Yes"` vs "the moderation log is currently empty" cannot match without the question |

## Changes

### 1. Extend solve-time stale-check (`hsge/webarena/collect.py::_is_stale`)

Current: single-hop INFO only, evidence checked against the start-page axtree.

- **Multi-hop INFO:** resolve each `answer_fact_refs` entry (`n12.f3`) to its
  SiteKB node URL; `goto` that page and require the ref's quoted `evidence` to
  still be a literal substring of the live axtree (`evidence_grounded`). Any
  dead evidence → `stale_skipped` (not failed), same as today. Cost: one goto
  per checked node, no LLM calls. After the check, the browser returns to
  `start_url` before solving.
- **NAV:** `goto(reference_url)` before solving; if the page is dead — axtree
  contains a not-found marker (e.g. "Page not found", "404") — skip as stale
  instead of burning a 25-step solve on a target that no longer exists.

`SiteKB` grows a helper to map a ref string to its node URL (alongside the
existing `resolve_ref_evidence`).

### 2. Self-verifying MOD tasks (`hsge/webarena/composer.py`)

Prompt (COMPOSER_SYS, MOD rule): the intent must embed, in quotes, the literal
content the agent is to write (e.g. *post a comment saying "Great analysis of
the cinematography"*), and `program_html` must be
`{url: <page where the change is visible>, locator: "", required_contents:
{must_include: [<that exact quoted phrase>]}}`. For state-toggle MODs with no
written content (subscribe/vote), the intent must name the expected post-state
text (e.g. *... so the button shows "Unsubscribe"*).

New code gates in `validate_task` (MOD branch), on top of the existing
denylist / read-only / collision gates:

- every `must_include` string must be a substring of the intent (both sides
  `normalize_answer`-normalized) — kills NL-prose assertions the DOM will
  never contain;
- `locator` must be `""` (whole-page axtree check) — kills jQuery
  `:contains()` and invented-attribute selectors wholesale;
- each `program_html` entry's `url` must be `"last"` or a `kb.known_urls()`
  member.

Trade-off (accepted): MODs whose success state cannot be named as literal page
text get rejected at compose time; the intent now also tells the solver what
success looks like, which is acceptable for SFT-data generation.

### 3. Slug-tolerant `url_match` (`hsge/webarena/evaluator.py`)

Replace the exact-path key with a normalized key: split the path into
segments and **wildcard any segment that immediately follows a purely numeric
segment** (Postmill's slug position: `/f/movies/15/<slug>`, including the `-`
placeholder). Everything else — segment count, other segments, sorted query —
still compares strictly, so `/f/movies/13/<slug>` does not match
`/f/movies/13/<slug>/comment/56`. Deliberately **not** reusing
`runtime._url_template`, which wildcards everything after the first id-like
segment (right for frontier dedup, far too loose for eval).

### 4. Judge receives the task intent (`hsge/webarena/evaluator.py`)

`evaluate()` already holds the task: pass `task["intent"]` through
`string_match` into `_judge_match`, add a `question` field to the judge
payload, and reword `JUDGE_SYS` to judge whether the answer conveys the same
information as the reference *as an answer to that question*. Fixes the
`"Yes"`-reference class (legacy tasks) and any future short-form reference the
composer's never-Yes/No rule doesn't catch.

## Re-run procedure (no new CLI flag)

Recomposing inside `wa_run_03` would reissue `gen_0000...` ids that
`_done_task_ids()` already considers done (old GEN episodes) and skip every
new task. Instead:

```bash
mkdir -p outputs/wa_run_04
cp outputs/wa_run_03/{sitekb.json,skills.json,operators.json,graph.json} outputs/wa_run_04/
python run_webarena.py --phase generate --out outputs/wa_run_04
```

`wa_run_03` stays untouched as the comparison baseline.

## Testing

Mock unit tests in `hsge/tests/` (no browser, no API):

- `validate_task` MOD gates: accept a token-style task; reject each real
  failure shape from run_03 (prose `must_include`, non-empty locator,
  unknown target URL).
- `url_match`: slug-drift pairs match; structurally different paths
  (submission vs comment permalink) do not; query/trailing-slash behavior
  unchanged.
- `_is_stale`: multi-hop INFO with dead evidence on a linked node → stale;
  NAV with a not-found target → stale; live refs → not stale (fake browser).
- judge payload includes `question`; code-substring match still short-circuits
  before any judge call.

**Success metric:** verified rate of `wa_run_04` vs run_03's 58/89, with
per-type breakdown (MOD is the headline: 30% today).

## Out of scope (tracked in the phase-2 backlog memory)

Ungrounded-bundle filter, composer call cap, operator effect pruning, solver
answer nudge, site-map hints for NAV solving, WebArena instance reset +
re-explore.
