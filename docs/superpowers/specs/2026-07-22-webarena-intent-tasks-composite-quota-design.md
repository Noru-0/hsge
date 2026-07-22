# Design — WebArena-style intent tasks + guaranteed COMPOSITE slots

Date: 2026-07-22

## Problem

Two complaints about `PageExplorer`'s proposals on real runs:

1. **Too few COMPOSITE tasks.** Last session added the `COMPOSITE` type as a soft
   prompt nudge, but it under-delivers. Two causes:
   - The prompt lists COMPOSITE **last** (`INFO → NAV → MOD → COMPOSITE`), so a
     model that front-loads its output emits few of them.
   - The truncation keep-order in `propose()` preserves that order inside the
     non-INFO bucket, so COMPOSITE is the **first non-INFO type dropped** when a
     page overflows `max_tasks`.
2. **Wording is too rigid.** Tasks read as UI action-chains
   (`"Open the post X, upvote it, then post a reply"`) rather than WebArena's
   natural **user-intent** phrasing (`"How much did I spend in March?"`,
   `"Add a Samsung Galaxy to my wish list"`).

## Scope

`hsge/webarena/agents.py` only (the `EXPLORER_SYS` prompt + the truncation
keep-order in `PageExplorer.propose()`), plus regression tests. No schema,
solver, or downstream operator/graph changes — `COMPOSITE` is already a
first-class tag through parsing, truncation, and `read_only`; it is only
under-produced and under-protected.

Explicitly **not** in scope: a compositional generator that reads the skill
library to synthesize tasks (still deferred per last session), any entry/exit
schema field, any solver change.

## Part 1 — Intent-style prompt (all task types)

Rewrite `EXPLORER_SYS` so tasks read as **user goals**, WebArena-style, for
every type — INFO/NAV/MOD/COMPOSITE — with a "phrase like a real user's
request, not a click-by-click script" instruction and WebArena-flavored
examples:

- INFO → `"What is the top-selling product this month?"` (unchanged rule: name
  what to find, **never** state the answer in the task text).
- NAV → `"Go to the wireless-headphones category"`.
- MOD → `"Add a Samsung Galaxy S21 to my wish list"`,
  `"Upvote the post titled 'Best budget GPU'"`.
- COMPOSITE → **redefined** as *an intent that inherently requires chaining
  several actions*, expressed as one natural goal, **not** a numbered step
  list: `"Buy the cheapest in-stock wireless mouse"`,
  `"Post a reply to the top comment on the newest post in r/technology"`,
  `"Add all books by Jane Smith to the cart and open the cart"`.

Ordering/quota: list **COMPOSITE first** and ask for **at least 2–3** COMPOSITE
among the proposals. All existing hard rules stay verbatim: no answer-leaking,
be specific with on-page names/values, no re-proposing, no NAV-to-current-page,
no account deletion.

## Part 2 — Reserve COMPOSITE slots in truncation

Replace the current two-bucket slice (`nav_mod + info`) with three buckets and a
reserve:

```
composite = [p for p in parsed if p[1] == "COMPOSITE"]
other     = [p for p in parsed if p[1] not in ("COMPOSITE", "INFO")]  # NAV/MOD/UNKNOWN
info      = [p for p in parsed if p[1] == "INFO"]                      # never grows frontier
keep = (composite[:RESERVE] + other + composite[RESERVE:] + info)[:max_tasks]
```

`_COMPOSITE_RESERVE = 3` guarantees up to 3 COMPOSITE survive overflow even when
a page floods NAV/MOD, while `other` fills the remaining slots so single-step
NAV/MOD discovery isn't starved. INFO stays dropped-first (it never grows the
frontier).

## Tests (TDD, `hsge/tests/test_page_explorer.py`)

1. Truncation reserves COMPOSITE against a flood of NAV/MOD.
2. Reserve does not wipe out NAV/MOD when COMPOSITE is scarce.
3. Prompt asserts: intent-style contract present, COMPOSITE listed first.
4. Existing COMPOSITE guards (parse, read-only drop, keep-over-INFO) still pass.

## Verification

`PYTHONPATH=. python -m pytest hsge/tests/ -q` — full suite green (was 160).
Semantic quality (does the model actually emit more, better-worded COMPOSITE
tasks) can only be confirmed on the user's next real WebArena acceptance run.
