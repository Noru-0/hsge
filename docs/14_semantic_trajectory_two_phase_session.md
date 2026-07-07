# 14 — Session Report: Semantic-Trajectory Two-Phase Pipeline (Explore → Compose)

Covers commits `18891a8`..`7925777` on branch `original` (design spec
`3461888`, implementation plan `776c776` precede this range). Starting point:
the user's stated goal for HSGE is to produce *semantic trajectories* — long,
meaningful, multi-step task trajectories usable as SFT training data for an
SLM benchmarked on WebArena — but the architecture wasn't producing them.
`docs/13_run02_reddit_exploration_log.md` was the evidence: `wa_run_02`'s 196
episodes were almost all short (avg ~5 steps, `difficulty: 1` for all of
them), success was self-reported (`send_msg_to_user('done...')` counted as
success with no independent check), zero GOAL/composed episodes ran, and the
discovered skill/operator layer was both weak (half the run's induced
operators were tautological or ungrounded, per `docs/13`'s grounding-check
findings) and unused by `build_sft_dataset.py` — the SFT dataset was a
clickstream of short nav/lookup fragments, not WebArena-like trajectories.

## 1. Design: two phases instead of fixing operator induction

Brainstormed and approved before implementation (full rationale and rejected
alternatives in `docs/superpowers/specs/2026-07-07-semantic-trajectory-two-phase-design.md`):

- **Definition settled first:** "semantic trajectory" = long, realistic,
  multi-step task trajectory (WebArena-like), regardless of annotation
  format. Eval target is the official WebArena benchmark, so generated tasks
  should mimic its distribution (multi-hop, cross-page, INFO/NAV/MOD) and
  carry the same kind of automatically-checkable eval spec WebArena uses.
- **Mechanism chosen: a top-down task-generation layer on top of the existing
  pipeline**, not a fix to skill/operator induction quality. The skill layer
  is retained as *site knowledge* (solver hints, curriculum signal) rather
  than the sole source of long tasks — explicitly out of scope to fix
  operator-induction quality on this critical path.
- **Verification is strict, WebArena-style:** every generated task carries an
  eval spec; only trajectories that pass it enter the SFT dataset. No
  self-reported success in training data — this is the direct fix for
  `wa_run_02`'s self-reported-success problem.
- **Reset-frugal:** the user's WebArena instance can be reset but resets are
  slow, so MOD tasks are batched to the end of a collection run and the
  instance reset fires at most once, after the whole batch.

Two phases (see `.claude/rules/architecture.md`'s "Semantic-trajectory
generation is two-phase" section for the wired-in module map):

```
PHASE 1 — EXPLORE (existing frontier loop + online digest)
  frontier loop (runtime.py, unchanged)
    → NodeDigester (digest.py, role node_digester): one LLM call per node,
      distills page → entities/facts/outlinks into a Site Knowledge Base
      (SiteKB), gated by a CODE-SIDE evidence-substring check, not the LLM's
      say-so

PHASE 2 — GENERATE & COLLECT (new; run_webarena.py --phase generate|all)
  TaskComposer (composer.py, role task_composer): samples SiteKB context
    bundles, generates WebArena-style tasks with eval specs
    (string_match/url_match/program_html), code-gated at generation time
  GenerationRunner (collect.py): solves each task (Solver + skill hints),
    scores with evaluator.py, records tag-GEN episodes with verified: true/false
    — INFO/NAV before the MOD batch, one instance reset after it
  build_sft_dataset.py: keeps only verified GEN episodes by default
```

## 2. Implementation: 9 plan tasks, subagent-driven, one reviewer per task

Executed via `superpowers:subagent-driven-development` — a fresh implementer
subagent per task (TDD: failing test → implementation → passing test →
commit), a fresh reviewer subagent per task (spec compliance + code quality
verdicts), and a final whole-branch review on the most capable model after
all 9 tasks. Full task list and exact interfaces in
`docs/superpowers/plans/2026-07-07-semantic-trajectory-two-phase.md`.

| # | Commit | What |
|---|--------|------|
| 1 | `18891a8` | Extracted episode persistence out of `runtime.py`'s `_record` into `hsge/webarena/recording.py`'s `record_episode(...)`, adding an `extra_meta` merge parameter so phase 2 can attach `verified`/`task_id`/eval metadata without touching the phase-1 write path. |
| 2 | `dd05bc6` | New `hsge/webarena/digest.py`: `NodeDigester` (one LLM call distilling a page into entities/facts) + `SiteKB` (ref resolution: `n<idx>.f<i>` / `n<idx>.e<i>` / `n<idx>.e<i>.attrs.<key>`). The anti-hallucination gate is `evidence_grounded()` — a whitespace-normalized literal-substring check of quoted `evidence` against the axtree, computed by code, never taken from the LLM. |
| 3 | `7f6a1b8` | Wired the digester into `runtime.py`'s node loop: every visited node's axtree is persisted to `node_state/node_XXXX_axtree.txt` and a digest is added to `sitekb.json` after every node (dumped alongside the other per-run artifacts). A digester exception logs `digest_error` and the run continues — one node's knowledge is lost, not the run. Added 3 new `AGENT_ROLES`: `node_digester`, `task_composer`, `judge`. |
| 4 | `7d866ac` | New `hsge/webarena/evaluator.py`: `string_match`/`url_match`/`program_html`, all fail-closed (no eval type declared → never verifies). Added `WebArenaBrowser.eval_js` (fail-soft to `""`) for `program_html`'s DOM checks, and an optional `hints` parameter on `Solver.solve` so phase 2 can inject top-k discovered skills as "known procedures" context. |
| 5 | `2cab4d3` | New `hsge/webarena/composer.py`: `TaskComposer` samples "context bundles" from the SiteKB (link-neighborhoods + same-entity-type clusters) rather than dumping the whole KB into one prompt, so multi-hop tasks are grounded in pages that really link together. `validate_task()` is the hard gate: INFO reference answers must trace to a `grounded: true` SiteKB ref, NAV targets must be known URLs, MOD intents pass a destructive-action denylist and can't collide on `program_html` targets. |
| 6 | `a972ecb`, `ed48521` | New `hsge/webarena/collect.py`: `GenerationRunner` solves composer-generated tasks (INFO/NAV before the MOD batch), scores each with `evaluator.evaluate`, records `tag: GEN` episodes via `record_episode` with `verified` in `extra_meta`. Resume is idempotent (already-recorded `task_id`s skipped). Instance reset fires at most once, only if a MOD task ran, after the whole batch. `ed48521` is a same-day follow-up fix: a task reviewer flagged that no test verified `_dump_stats` merges into `summary.json["gen"]` without clobbering phase-1's own keys in that file — added. |
| 7 | `1cbabfd` | `run_webarena.py --phase explore\|generate\|all` (default `explore`, byte-for-byte today's behavior for the frontier loop). `--phase generate` needs an existing `sitekb.json` and reuses `gen_tasks.json` on re-run instead of re-invoking the composer. Extended `_DryLLM`/`_FakeBrowser` so `--dry-run --phase all` exercises the whole pipeline offline. Added `config.yaml`'s `gen:` block and the `node_digester`/`task_composer`/`judge` LLM roles. |
| 8 | `922e8b2` | `build_sft_dataset.py` now gates on verification instead of self-reported success: by default only `GEN`-tagged episodes with `verified: true` are kept (a failed/unverified GEN episode is *never* admitted, even with the opt-in flag); `--include-local` additionally admits self-reported LOCAL/GOAL successes. `difficulty` in the emitted examples is now the task's real `hops`, not a constant `1`. |
| 9 | `7925777` | Documented the two-phase pipeline in `.claude/rules/architecture.md` and `.claude/rules/commands.md`; dropped one unused import left over from task 8's argparse refactor. |

## 3. What's verified vs. not

**Verified in this session:**
- 74/74 tests passing at the end (up from 50 at the start), each task's tests
  written before its implementation and reviewed by a fresh subagent for
  spec compliance and code quality.
- The anti-hallucination guarantee holds **end to end**, confirmed by the
  final whole-branch review tracing the full path: `digest.py`'s
  `evidence_grounded` (code-side substring check) → `composer.validate_task`
  (rejects any INFO ref that isn't `grounded: true`, and rejects any
  reference answer not actually backed by that ref's value) →
  `evaluator.string_match` (compares the solver's real answer against that
  same reference). There is no path for an ungrounded fact to become a
  graded reference answer.
- `--dry-run --phase all` runs the whole pipeline offline (explore →
  `sitekb.json` → compose → verify → GEN episode) and a second run of the
  same command reuses `gen_tasks.json` and reports zero newly-attempted
  tasks (resume path). `--dry-run` with `--phase` omitted reproduces prior
  behavior exactly (no `[gen]` output, no `gen_tasks.json`, no `summary.json`
  `"gen"` key).
- `build_sft_dataset.py` run against real dry-run output kept only the one
  verified GEN episode, with `difficulty` equal to that task's `hops` — the
  curriculum-sort signal that was a constant `1` before this session.

**Not verified (needs a real WebArena instance — the sandbox this session ran
in can't reach the user's LAN-hosted instance):**
- Real grounding rates: what fraction of a real site's digested
  entities/facts actually pass `evidence_grounded` (mock/dry-run LLMs always
  quote real page text; a real LLM's evidence-quoting discipline is
  untested).
- Real composer rejection rates: `gen_tasks.json`'s `rejected` list, with
  reasons, has only ever been exercised against a scripted `_DryLLM`.
- Whether `TaskComposer`'s bundle-sampling produces genuinely useful
  multi-hop tasks against a real, large `sitekb.json` (hundreds of nodes),
  versus degenerate or repetitive ones.
- End-to-end MOD-task collection and the reset-frugal batching against a
  real, resettable instance.

## 4. Suggested next steps (not started)

Flagged by the final whole-branch review as Minor / worth doing before a
large real run, none of them blocking:

- **`TaskComposer.generate()` has no cap on total composer LLM calls.** It
  loops once per sampled bundle until quota is met; if every generated task
  from a stretch of bundles gets rejected (e.g. persistently ungrounded
  refs), `remaining` never decrements and it keeps burning one
  strong-model (`task_composer`, e.g. `gpt-4o`) call per bundle across the
  whole KB. Bounded by bundle count, not unbounded, but worth a
  consecutive-rejection cap or total-call cap before a run against a
  500-node `sitekb.json`.
- **`run_webarena.py --phase generate` (real, non-dry-run) still fires the
  up-front `WA_FULL_RESET` reset** in the branch that resolves
  `full_reset_url`, even though generate-only mode does no exploration that
  would need a fresh instance state. Harmless but wastes one slow reset;
  could gate that call on `args.phase != "generate"`.
- **No automated test exercises the full `digest → compose → collect →
  build_sft_dataset` chain together** — each module's tests mock its
  neighbors, and only the manual `--dry-run` path (and the final review's
  ad-hoc `build_sft_dataset` run against dry-run output) covers the real
  seam. Worth promoting that dry-run path into a pytest test.
- **First real-run recommendation** (from the plan's Execution notes):
  `python run_webarena.py --phase all --max-nodes 10 --read-only` against
  reddit, then inspect `sitekb.json` grounding rates and `gen_tasks.json`
  rejection reasons before committing to a full collection run — this is
  the natural next session once the user has LAN access to the instance.
