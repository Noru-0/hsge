# 12 — Session Report: Real-Run Bug Fixes (Task Diversity, Tag Reliability, Solver Loops)

Covers commits `e99ee86`..`077eaa2` on branch `original`. Starting point: the
user read a real `outputs/wa_run/` (57 episodes, 11 nodes, gpt-4o `page_explorer`
+ gpt-4o-mini `solver`, deepseek for the other roles) and flagged two visible
symptoms — task counts uneven/low per node, and almost no `[INFO]/[NAV]/[MOD]`
tags showing up in the output. Investigating those two led to a third, more
consequential bug that the visible symptoms didn't hint at directly. All three
fixes, plus a follow-up escalation driven by a second real run, are covered here.
This directly acts on three items `docs/11_vision_auth_hardening_session.md`'s
"Suggested next steps" had flagged but left unimplemented: task-level dedup,
already-proposed-task context in the prompt, and solver loop-detection.

## 1. Root-cause analysis of `outputs/wa_run/`

Quantified from the run's `nodes.json`/`run_log.jsonl`/`episode.jsonl` files
(not guessed):
- **46% of all proposed tasks (26/57) were near-duplicate sitewide nav-menu
  boilerplate** ("Go to the Forums/Wiki/Home/Notifications/Messages page"),
  re-proposed almost verbatim at nearly every node because the header nav
  appears on every page and `PageExplorer` has no memory across nodes.
- **89% of tasks (51/57) had no `[INFO]/[NAV]/[MOD]` bracket at all**, despite
  `EXPLORER_SYS` asking for one on every call; only one node's batch (6/57)
  complied. Since `read_only`'s MOD filter and the NAV/MOD-over-INFO
  truncation priority both matched on a literal bracket substring, both were
  silently defeated for the other 51 tasks — a real MOD task in that run
  ("Click the 'Save' button to create the new page.", `ep_0050`) shipped with
  no tag, meaning `--read-only` would not have caught it.
- **A third bug the visible symptoms didn't point at:** 12/57 task failures
  (100% of them, verified across 5+ sampled episodes) shared the identical
  pattern — the Solver clicks a nav link, it genuinely navigates, but the
  link re-appears under a new bid on the destination page and the agent keeps
  clicking it 13-14 more times without recognizing it already arrived,
  burning the entire `max_steps=15` budget every time (`ep_0004`, `ep_0013`,
  `ep_0015`, `ep_0021`, `ep_0026`, `ep_0037` all showed the exact same
  `click(sameBid) x14` shape). Confirmed via `page_state/step_*_axtree.txt`
  diffs: the root cause is real navigation success followed by the model not
  recognizing arrival, not a browser/action-mapping failure.

Before implementing, three parallel sub-agents searched the open agent-skills
ecosystem (`skills.sh`/`npx skills find`) for existing packaged skills covering
loop-detection, diverse-output generation, and structured-output enforcement.
None cleared the quality bar (1K+ installs, reputable source) for this specific
need — see the conversation transcript for the full search trail. All three
fixes below are therefore direct code changes, not skill installs.

## 2. Solver: warn on a repeated no-progress action (later escalated, see §5)

**Fix.** `Solver.solve()` tracks executed-action `history`; if the same action
succeeds twice in a row with no exception, the next prompt gets an explicit
`WARNING` telling the model to call `send_msg_to_user` if the goal is already
met instead of repeating. This was the first-pass fix, proven insufficient by
a second real run (§5).

Files: `hsge/webarena/agents.py`, `hsge/tests/test_solver.py`.

## 3. `PageExplorer`: cross-node task dedup + negative-context prompting

**Fix.** One `PageExplorer` instance lives for the whole run (`runtime.py`
constructs it once), so it now keeps `self._seen: dict[str, str]` (normalized
task text → original text) across every `propose()` call. Each prompt echoes
recent entries back as `ALREADY PROPOSED (do not repeat these or
near-duplicates)` negative context, and the code drops any newly parsed task
whose normalized text already matches an entry in `_seen`, independent of
whether the model actually avoided it. `EXPLORER_SYS` also gained an explicit
rule against re-proposing sitewide nav-menu links from a different page.

Files: `hsge/webarena/agents.py`, `hsge/tests/test_page_explorer.py`.

## 4. Structured `type` field instead of a free-text `[TAG]` bracket

**Root cause, not just a symptom fix.** `PageExplorer._coerce_task`'s own
docstring already noted that gpt-4o "wraps a task in an object instead" (e.g.
`{"task": "...", "type": "NAV"}`) — but the old code only salvaged the `task`
text and **discarded the `type` field**, which is very likely why 89% of tasks
came back looking untagged: the model had already classified them, and the
code threw the classification away.

**Fix.** `EXPLORER_SYS` now asks directly for `{"tasks": [{"text": ...,
"type": "INFO"|"NAV"|"MOD"}, ...]}`. `_parse_task()` reads the `type` field
first, falls back to a legacy leading `[TAG]` bracket for models that still
emit one, and tags anything with neither as `UNKNOWN`. `read_only` now drops
`UNKNOWN` along with `MOD` (fail-closed — an unclassifiable task might be a MOD
the model forgot to tag) instead of the old literal-substring-on-`[MOD]`
check, which a genuinely untagged MOD task would have slipped straight past.

Files: `hsge/webarena/agents.py`, `hsge/tests/test_page_explorer.py`.

## 5. Bug found via a second real run: the §2 warning wasn't enough

**Symptom.** A fresh real run (`outputs/wa_run_01`, `max_tasks` bumped 6→9 in
`config.yaml`) still showed two task failures burning the full `max_steps=15`:
- `ep_0003`: `click('117')` issued **identically for all 15 steps**.
  `page_state/step_*_axtree.txt` diffs confirmed the page never changed at
  all — the click was a genuine no-op, and the §2 `WARNING` (present in the
  prompt from the 3rd call onward, per that fix's own logic) did not change
  the model's behavior even once.
- `ep_0005`: `select_option('378', ...)` repeated **9 times with a different
  argument each time** ("Choose one…" / "Forum Name" / "Another Forum Name").
  The exact-action-string check from §2 never even triggered, since no two
  consecutive calls were textually identical — but axtree diffs confirmed the
  combobox's actual value never changed regardless of argument, i.e. the
  *target* (bid 378) was genuinely stuck even though the *action string*
  wasn't repeating.

**Fix.** Generalized `Solver`'s stuck-detection to key off two things instead
of exact-string equality: (a) the action's *target* (bid/url, extracted via
regex) rather than the full action string, and (b) whether the *observation
actually changed* (url/axtree captured before vs. after each action). A
trailing run of same-target actions with **zero observation change** now
counts toward the streak, regardless of what argument each call used.
Escalates from a `WARNING` at 2 in a row to a hard stop (`break`, no further
LLM calls) at 4 in a row — the first real run already proved a text nudge
alone isn't reliably obeyed, so continuing to ask nicely for 11 more calls
wastes the rest of the budget for nothing.

**Caught before it shipped:** requiring only "same target" (dropping the
observation-change condition) would have been simpler but is wrong — verified
by running `--dry-run` after the first draft of this fix, which false-triggered
a hard stop on the scripted mock solver (its "advance" action is always
`click('1')` by design, reused across genuinely different pages). Re-adding
the "no observation change" requirement fixed the false positive while still
catching both real transcripts; confirmed via `--dry-run` returning to its
pre-fix baseline (`steps=6, success=True`) afterward.

Files: `hsge/webarena/agents.py`, `hsge/tests/test_solver.py`.

## What's verified vs. not

**Verified in this session:**
- All fixes are covered by unit tests reproducing the *exact* real transcripts
  that exposed each bug (not synthetic/hypothetical scenarios) — 38 tests
  passing by the end, up from 36 at the start of the session (2 pre-existing
  + regression tests added per fix).
- `--dry-run` re-verified after every change, including the escalation in §5,
  which required a second iteration specifically because the first attempt
  broke it.
- §1's quantified claims (46% duplicate tasks, 89% missing tags, 12/57
  identical-shape failures) came from directly parsing the user's real run
  output files, not estimation.

**Not verified (needs the user's environment):**
- Whether a fresh real run now shows `ep_0003`/`ep_0005`-style episodes
  stopping at `_MAX_REPEATS` (4) steps instead of exhausting `max_steps` (15).
- Whether the §4 structured-`type`-field change actually raises tag coverage
  above the 11% observed in the first run — needs a fresh run to confirm gpt-4o
  reliably populates `type` the way its own past behavior (wrapping tasks in
  objects) suggested it would.
- Whether §3's dedup meaningfully reduces the 46% duplicate-task rate in
  practice, versus the model finding new near-duplicate phrasings that evade
  the normalized-text match.

## Suggested next steps (not started)

- **`ep_0005`'s underlying bug is bounded, not fixed.** The hard stop in §5
  stops the episode from wasting the rest of its budget, but doesn't explain
  *why* `select_option('378', ...)` never actually changed the combobox's
  value no matter what argument was tried. One plausible cause: BrowserGym's
  axtree may not enumerate a `<select>`'s real `<option>` list while it's
  collapsed (`expanded=False`), so the model is guessing plausible-sounding
  option text ("Forum Name") that doesn't match any real option instead of
  reading actual forum names off the page — worth checking `browser.py`'s
  axtree extraction (`extra_element_properties`) for collapsed comboboxes
  specifically.
- **Frontier growth still depends entirely on solved-task navigation**, not
  on links scraped directly from the axtree/DOM (carried over from
  `docs/11`'s suggested next steps — still not implemented).
