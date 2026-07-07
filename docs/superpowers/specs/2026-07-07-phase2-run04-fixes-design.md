# Phase-2 run_04 fixes (Part A) — design

**Date:** 2026-07-07
**Status:** approved (brainstorm session, run_04 failure review)
**Scope note:** Part A of a two-part effort. Part B (semantic multi-hop task
redesign) is specced separately in
`2026-07-07-semantic-multihop-tasks-design.md` and deliberately deferred —
this spec must land and be measured first.

**Goal:** close the five concrete failure classes found in the run_04
measurement (71/92 = 77.2% verified; INFO 43/52, NAV 12/20, MOD 16/20) with
small code-side gates and one probe extension. All five are compose-time or
solve-time guards; none change the Solver.

## Context: the five limitations (from run_04 episode review)

| # | Class | Evidence |
|---|---|---|
| 1 | Composer sets a NAV task's `reference_url` to its own `start_url` | `gen_0004`: intent "Go to the Messages page from the notifications page", `reference_url` = `.../notifications` (the start page). `validate_task` only checks membership in `kb.known_urls()`, which the start page trivially passes. Unwinnable-as-specified task. |
| 2 | NAV dead-target probe never fired (0/8 NAV failures marked stale) | Failed NAV refs like `/f/movies/13/-/comment/56/edit` (another user's comment-edit page) exist but redirect (login) or render permission errors — no `_NOT_FOUND_MARKERS` phrase, so the probe says "live" and the solve burns its budget. The real Postmill 404 copy has also never been captured from the live instance. |
| 3 | Site-mechanics INFO questions the solver systematically misreads | 3× "short URL" tasks (`gen_0014`/`0048`/`0082`): reference is Postmill's short-link (`http://host/15`), solver always answers the full permalink. Postmill-specific UI trivia, worthless as SFT signal. |
| 4 | Relative timestamps in intents | `gen_0074`: "the comment ... written 17 minutes ago" — true at digest time, meaningless at solve time. The intent itself goes stale; no page-content stale-check can catch it. |
| 5 | Volatile reference values the stale-check cannot protect | `gen_0064`: reference score "-1", live answer "0 points". The reference value was not inside the cited ref's quoted `evidence`, so `_is_stale`'s evidence re-grounding could not detect the drift. |

## Changes

All gates live in `hsge/webarena/composer.py::validate_task` unless noted.
Every rejection returns a distinct reason string (tests assert on substrings).

### 1. NAV `reference_url == start_url` gate

Factor the URL-normalization key out of `evaluator.url_match` into a public
helper `url_key(u)` (netloc, slug-blind path, sorted query — exactly the
existing inner `key`) and reuse it here: in the NAV branch, reject when
`url_key(reference_url) == url_key(task.get("start_url") or kb.site)`.
(`generate()` applies `setdefault("start_url", kb.site)` only after
validation, so the gate must fall back to `kb.site` itself.)
Reason: `"NAV reference_url equals start_url"`.

### 2. NAV probe: landed-URL check + real 404 copy

`hsge/webarena/collect.py::_is_stale`, NAV branch — two additions:

- After `goto(reference_url)`, also compare the **landed URL** (the `url`
  field of the observation the goto returned) against the requested one via
  `url_key`. A mismatch means the site redirected (login page, permission
  bounce, moved content) → treat as stale/unreachable, same skip path as the
  text markers. This catches the run_04 class (permission-gated edit pages)
  that no not-found phrasing will ever catch.
  Known accepted risk: a legitimate redirect that changes path shape (e.g.
  Postmill short URL `/15` → full permalink) would false-positive; composer
  refs are full URLs from the KB, so this is rare — documented, not handled.
- **User action item (one-time, live instance):** `curl` a known-dead URL on
  the real Postmill instance (e.g. `http://192.168.1.31:8880/f/movies/99999`)
  and paste the actual not-found copy; its distinctive phrase joins
  `_NOT_FOUND_MARKERS`. Until then the widened heuristic tuple from commit
  `4a8fb79` stands.

### 3. Site-mechanics INFO ban

- Prompt: add one INFO rule line to `COMPOSER_SYS`: questions must be about
  page *content* (posts, comments, authors, counts, dates), never about the
  site's own UI mechanics (short URL, RSS links, formatting help, keyboard
  shortcuts).
- Code net: `INFO_META_RE = re.compile(r"\b(short\s*url|rss|formatting\s+help|keyboard\s+shortcut)\b", re.I)`
  — reject INFO intents that match. Reason: `"site-mechanics INFO intent"`.

### 4. Relative-time gate (all task types)

`RELATIVE_TIME_RE = re.compile(r"\b\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago\b|\b(?:yesterday|today|last\s+(?:week|month|year))\b", re.I)`
— reject any intent that matches, before the type-specific branches.
Reason: `"relative-time reference in intent"`.

### 5. Evidence-containment gate for INFO references

Today the INFO branch checks each reference target against the *resolved
value* of a cited ref (`fact.a` / entity name / attr). Add: each target must
also be a normalized substring of at least one cited ref's quoted
`evidence` (`kb.resolve_ref_evidence`). A value the digester paraphrased out
of its evidence quote cannot be protected by `_is_stale`'s re-grounding, so
it must not become a reference. Reason:
`"reference answer not inside cited evidence"`.

## Testing

Mock unit tests, each gate fed the real run_04 failure shape it kills:
`gen_0004`'s self-referential NAV; a fake browser whose goto lands on
`/login` (redirect probe); a "short URL" INFO intent; the "17 minutes ago"
intent; an INFO task whose reference value is absent from its evidence quote.
Plus a passing-shape test per gate so the gates don't over-reject.

## Measurement (run_05)

Same procedure as run_04 (fresh out dir, copy `sitekb.json`/`skills.json`/
`operators.json`/`graph.json` from run_03, `--phase generate`). Baseline:
run_04's 71/92 (INFO 43/52, NAV 12/20, MOD 16/20, 8 stale-skipped). Expected
movement: the `gen_0004`/short-URL/relative-time classes disappear from
`accepted` (visible in `gen_tasks.json.rejected` reasons); NAV
`stale_skipped` > 0 if permission-gated refs recur.

## Out of scope

Part B (real-hops computation, far start_url policy, comparison tasks,
solver site-map hint) — separate spec. Solver capability failures (step
exhaustion on live pages) — untouched by design.
