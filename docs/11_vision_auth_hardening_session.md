# 11 — Session Report: Vision/SoM, Login/Auth, and Real-Run Hardening

Covers commits `2ecb855`..`ba2ad65` on branch `original` (14 commits). Starting
point: the WebArena runtime could run for real but a trial run against a live
reddit instance showed real inefficiencies (duplicate node re-exploration, no
persisted skill/operator output beyond stdout). Ending point: real vision
support for `PageExplorer`/`Solver`, real login/session handling, and four
distinct real-run crashes/stalls found and fixed from the user's own terminal
output — most of this session's fixes were driven by actual real-run evidence,
not speculation.

## 1. Node content-dedup + persisted run artifacts + structured logging

**Problem.** A trial run's `outputs/wa_run/` showed 8 of 12 episodes sharing
byte-identical initial-page content (confirmed via hashing each episode's
`step_000_axtree.txt`) — two different frontier URLs rendered the same page,
so the crawler burned a full `PageExplorer`+`Solver` batch re-discovering
content it already had. Separately, the only research payload of a run (which
skills/operators got discovered) existed only in RAM and one stdout summary
line — lost once the process exited.

**Fix.**
- `runtime.py::run()`: hash each node's initial axtree; skip re-exploring a
  node whose content hash was already seen (no wasted explorer/solver calls).
- `_dump_artifacts()` (new): writes `skills.json`, `operators.json`,
  `graph.json`, `predicates.json` (canonical `p0`/`p1`/... id → original NL
  text, so operator preconditions/effects are legible instead of opaque),
  `nodes.json` (per-node: url, depth, duplicate flag, every task tried at
  that node with pass/fail + step count), and `summary.json` — rewritten
  after **every** node, not just at the end, so a run interrupted partway
  through still leaves a consistent, inspectable snapshot.
- `_log()` (new): mirrors every meaningful event (`node_visit`,
  `node_duplicate_skip`, `task_result`, `skill_admitted`, `operator_induced`,
  `frontier_expand`, `run_summary`) to `out_dir/run_log.jsonl`, not just
  stdout.

Files: `hsge/webarena/runtime.py`.

## 2. GPT-4o vision (+ Set-of-Marks) for `PageExplorer`/`Solver`, `OpenAILLM` retry/backoff

Brainstormed and spec'd first (`docs/superpowers/specs/2026-07-03-webarena-
vision-support-design.md`), then two follow-up ideas (Set-of-Marks bbox
overlay, retry/backoff) were folded into the same spec and implemented
together.

**Vision.** `LLM.complete_json`/`OpenAILLM.complete_json` gained optional
`image_b64`/`image_detail` params (default `None`, backward compatible).
`WebArenaBrowser.screenshot_b64(som=...)` JPEG-encodes the screenshot
BrowserGym already computes on every observation; `som=True` overlays
bid-tagged bounding boxes via BrowserGym's own
`browsergym.utils.obs.overlay_som` (reusing `extra_element_properties`
already extracted for the axtree — no custom drawing code). `PageExplorer`/
`Solver` gained `vision`/`som`/`image_detail`, resolved per-role in
`config.yaml` (`page_explorer` → `gpt-4o`, `solver` → `gpt-4o-mini`, both
`vision`+`som` on) via `run_webarena.py::_resolve_agent_vision`, the same
role>shared>default precedence as the existing per-role LLM routing.
Screenshots that get sent to the model are also persisted:
`page_state/step_XXX_screenshot.jpg` per solver step, `node_state/
node_XXXX_screenshot.jpg` per node (referenced from `nodes.json`) — only
when actually captured, so non-vision runs are byte-for-byte unaffected.

**Retry/backoff.** `OpenAILLM._create_with_retry` wraps
`chat.completions.create` with up to 3 retries (exponential backoff + jitter)
for `RateLimitError`/`APIConnectionError`/`APITimeoutError`/
`InternalServerError`; `AuthenticationError`/`BadRequestError` are not
retried (non-transient).

Files: `hsge/llm.py`, `hsge/backends.py`, `hsge/webarena/browser.py`,
`hsge/webarena/agents.py`, `hsge/webarena/runtime.py`, `run_webarena.py`,
`config.yaml`, `requirements.txt` (added `pillow`).

## 3. Bug found via first real run with gpt-4o: `PageExplorer` crash on non-string tasks

**Symptom:** `KeyError: slice(None, 50, None)` in `runtime.py`'s
`task[:50]` print. Confirmed by reproduction: slices are hashable since
Python 3.12, so `dict[:50]` raises exactly this `KeyError` — meaning a
proposed "task" was a `dict`, not a `str`.

**Root cause.** `PageExplorer.propose()` trusted `out["tasks"]` to always be
`list[str]` per the prompt's schema. DeepSeek always complied; `gpt-4o` (just
switched to for `page_explorer`) sometimes wraps a task in an object (e.g.
`{"task": "...", "type": "NAV"}`) instead.

**Fix.** `_coerce_task()`: accepts a plain string as-is, or salvages the text
from a wrapping dict's `task`/`description`/`text` key; drops anything else.
Fixed at the API boundary, not the crash site.

Files: `hsge/webarena/agents.py`.

## 4. Bug found via first real vision call: `OpenAILLM` crash on `content=None`

**Symptom:** `AttributeError: 'NoneType' object has no attribute 'strip'` in
`complete_json`.

**Root cause.** The OpenAI API can return `message.content=None` (e.g.
`finish_reason="content_filter"`, or a populated `message.refusal`) —
distinct from the malformed-JSON case already tolerated.

**Fix.** Check for `content is None` before `.strip()`; log `finish_reason` +
`refusal` for diagnosis, and degrade to `{}` the same way a malformed JSON
response already does, instead of crashing.

Files: `hsge/backends.py`.

## 5. WebArena login/auth: login once, cache the session

Brainstormed and spec'd first (`docs/superpowers/specs/2026-07-03-webarena-
login-auth-design.md`). `hsge/webarena/auth.py` (new): per-site login flows
(reddit/gitlab/shopping/shopping_admin) ported from
`browsergym.webarena.instance.WebArenaInstance.ui_login` /
`references/webarena-main`'s `auto_login.py` (same selectors). HSGE doesn't
construct `WebArenaInstance` directly — its `__init__` hard-requires all
seven `WA_*` site URL env vars to be set, even though a given HSGE run only
explores one site. `ensure_login(site, root_url)` returns a cached,
still-valid `storage_state` path if one exists (checked via a per-site
"am I still logged in" URL/keyword probe), else does a one-time live login
and caches it under `.auth/<site>_state.json`. Credentials:
`WA_<SITE>_USERNAME`/`WA_<SITE>_PASSWORD` in `.env`, falling back to the
standard published WebArena benchmark test accounts when unset.
`WebArenaBrowser` gained `storage_state=`, merged into the existing
`pw_context_kwargs` — every node's browser context starts already
authenticated instead of logging in per node. A full instance reset
(`--full-reset-url`) deletes the cached session first, since a reset can
invalidate it. `.auth/` added to `.gitignore` (cached cookies are live
session credentials).

Files: `hsge/webarena/auth.py`, `hsge/webarena/browser.py`,
`run_webarena.py`, `.gitignore`.

## 6. Bug found via first real vision run: exploration stalled after a refusal

**Symptom:** a real run against gpt-4o + a Set-of-Marks screenshot got
refused outright (`"I'm unable to assist with that."`) on the very first
`PageExplorer` call. Because `propose()` got zero tasks, no local task was
solved at the root node, and because `runtime.py`'s frontier growth relies on
URLs visited while solving a task (plus open-tab links), the run had almost
no way to discover new URLs and stalled after 2 node-visits instead of
reaching `max_nodes=15`.

**Root cause** is an external model policy decision (not reproducible or
controllable directly) — the existing `{}` fallback from §4 already
prevented a crash, but a single refusal could still stall an entire run.

**Mitigation.** `PageExplorer.propose()`/`Solver.solve()` now retry once
without the image whenever a vision-attached call returns empty, since some
providers are stricter about a screenshot of a real, named,
bounding-box-annotated site than the same request as text-only. This also
self-diagnoses on the next run: if the text-only retry succeeds, that
confirms the image was the trigger; if it's refused too, the prompt/content
itself is the issue.

**Separately noted, not fixed:** frontier growth depending entirely on
solved-task navigation (not on links scraped directly from the axtree/DOM)
is a pre-existing architectural gap this exposed — see "Suggested next
steps".

Files: `hsge/webarena/agents.py`.

## 7. Bug found via the same real run: `[INFO]` tasks leaking their own answer

**Symptom:** `outputs/wa_run/` showed episodes like `"Read the number of
submissions for 'relationship_advice' (5,718 submissions)."` — the goal
already states the answer, so the Solver just parrots it back in one step
with zero real page-reading, making the trajectory useless as SFT training
data (input already contains the output). 6 of 8 episodes in that run had
this pattern.

**Root cause.** `EXPLORER_SYS`'s "be SPECIFIC using names/values visible on
the page" rule is correct for `[NAV]`/`[MOD]` tasks (name which item/post to
act on) but backfired for `[INFO]` tasks, where being "specific" about an
extraction target naturally led the model to also state the answer.

**Fix.** Added an explicit rule forbidding the value/answer from appearing in
`[INFO]` task text, with the exact leaking pattern as a NOT-example. Can't
unit-test LLM compliance directly, so added a regression guard asserting the
instruction text itself doesn't get accidentally removed.
**Pre-existing leaking episodes in that run's `outputs/wa_run/` should be
excluded from any SFT dataset built from it** — the fix only affects future
runs.

Files: `hsge/webarena/agents.py`.

## 8. `PageExplorer.max_tasks` made configurable (4 → 6 default)

Was hardcoded with no override, so a page with more plausible tasks than the
cap would silently drop the rest. Wired through the same `config.yaml` + CLI
precedence chain as `max_nodes`/`max_depth`/`max_steps`: `run.max_tasks`,
`--max-tasks` CLI flag, `WebArenaExplorer(max_tasks=...)` →
`PageExplorer(max_tasks=...)`.

Files: `hsge/webarena/runtime.py`, `run_webarena.py`, `config.yaml`.

## 9. Bug found via a later real run: frontier stalled again, different cause

**Symptom:** `run_log.jsonl` showed a `/forums` listing-page node proposing 4
tasks, all `[INFO]`, with `frontier_added=0`; a `/wiki` node had 2 `[INFO]` +
a `[NAV]` to an already-visited page + a `[NAV]` "Go to the Wiki page" that
**failed after all 15 steps** — the Solver clicked the same bid 15 times
because it was already on that page and the click never went anywhere.
Result: only 3 real nodes visited instead of 15.

**Root cause A.** `EXPLORER_SYS` asks the model to list `[INFO]` tasks first,
then `[NAV]`, then `[MOD]` — but `propose()` truncated the result with a
naive `tasks[:max_tasks]` slice. On any page offering more `[INFO]`
candidates than `max_tasks` (e.g. a listing page with many sub-items), every
`[NAV]`/`[MOD]` task silently got cut, even though those are exactly what
grows the frontier (`[INFO]` tasks read the page but never navigate).

**Root cause B.** No rule against proposing navigation to the page the user
is already on.

**Fix.** When there are more tasks than `max_tasks`, drop `[INFO]` first and
keep `[NAV]`/`[MOD]`, instead of slicing in list order. Added an
`EXPLORER_SYS` rule against proposing navigation to the current page.

Files: `hsge/webarena/agents.py`.

## What's verified vs. not

**Verified in this session:**
- Mock pipeline stays green throughout (`pytest hsge/tests/ -q`); every new
  test added this session is additive (vision/som precedence, retry/backoff,
  auth credential precedence, task-coercion, truncation-priority — 29 tests
  total by the end, up from 7 at the start).
- `--dry-run` re-verified after every single change in this session (dedup,
  artifact persistence, vision+SoM wiring against a stub screenshot, auth
  no-op paths, prompt edits, `max_tasks`).
- §1, §3, §4, §6, §7, §9 were each found from the user's own real-run output
  (episode files, `run_log.jsonl`, or a pasted traceback) — not
  hypothesized bugs. §3/§4 were reproduced standalone before fixing
  (systematic-debugging discipline); §6/§7/§9 involve external model
  behavior or prompt-compliance that can't be reproduced in this sandbox
  (no live WebArena instance, no OpenAI network access here), so those were
  diagnosed by tracing the code/log evidence and fixed defensively, with the
  expectation that the next real run's logs confirm or refute the exact
  mechanism.

**Not verified (needs the user's environment):**
- End-to-end confirmation that vision/SoM actually improves task proposal or
  click accuracy — only the wiring (capture → attach → persist) was
  verified, not a quality comparison against text-only.
- Whether the retry-without-image mitigation (§6) actually resolves the
  refusal in practice, or whether the model refuses the text-only retry too
  (which would point at the prompt/content instead of the image).
- Whether the `[INFO]`/`[NAV]` truncation-priority fix (§9) actually reaches
  `max_nodes=15` on a full run now — needs a fresh real run.
- Login/auth (`ensure_login`, `is_logged_in`) end-to-end against a real
  instance — only the pure-logic parts (credential precedence, no-op for
  sites without a login flow) were unit-tested; the LAN-only reddit instance
  is unreachable from this sandbox.

## Suggested next steps (not started)

- **Frontier growth still depends entirely on solved-task navigation**, not
  on `<a href>` links scraped directly from the axtree/DOM. A node where
  every task is `[INFO]` (now less likely after §9, but not impossible)
  still can't discover new URLs on its own. Mining links directly from the
  page would be a more robust primary source; flagged twice this session
  (§6, §9) but deliberately not implemented — it's a larger architecture
  change, not a contained fix.
- **Task-level dedup against already-admitted skills**: pitched during
  brainstorming but not implemented. `PageExplorer` has no memory across
  nodes, so it can keep re-proposing (and re-solving) tasks semantically
  close to a skill already admitted (e.g. a common nav-bar click), instead
  of steering toward genuinely new affordances.
- **Passing already-visited URLs into `PageExplorer`'s prompt**: offered as
  an optional extra scope alongside §9's fix; declined for this session
  (user chose the two contained fixes). Would let the model avoid proposing
  `[NAV]` to destinations already in `visited`, rather than relying on
  `_admit_url`'s post-hoc filter to just silently drop the resulting
  frontier candidate.
- **Solver loop-detection**: the failed "Go to Wiki while on Wiki" episode
  (§9) burned all 15 steps clicking the identical bid because `SOLVER_SYS`'s
  "reflect on your past actions" instruction didn't stop the repetition in
  practice. An explicit check (same action repeated N times with no
  observation change → force a different action or fail fast) would save
  the rest of that step budget instead of exhausting it.
- **Set-of-Marks/vision refusals**: watch `[explorer]`/`[solver] ... retrying
  text-only` log lines across future runs. If they recur often, that's
  evidence the image (not the text) is the trigger, and disabling `vision`
  for `page_explorer` (or dropping `som`) may be worth trying.
