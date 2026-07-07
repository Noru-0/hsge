# Semantic Trajectories via Two-Phase Explore → Compose (Design)

**Date:** 2026-07-07
**Status:** Approved (brainstorm), pending implementation plan

## Problem

HSGE's stated purpose is to generate *semantic trajectories* — long, meaningful,
multi-step task trajectories — as SFT training data for a small language model
(SLM) that will be evaluated on the **official WebArena benchmark**. The current
architecture does not produce them. Evidence from `outputs/wa_run_02` (reddit,
57 nodes, 196 episodes):

- Every episode is a short LOCAL task (avg ~5 steps; e.g. "Go to the 'Tags'
  page" = 2 steps). `difficulty` is 1 for all of them. Zero GOAL/composed
  episodes ran (`terminal_goal: null` for reddit).
- Episode success is largely **self-reported** — the Solver saying
  `send_msg_to_user('done...')` counts as success for most LOCAL tasks. There
  is no independent check that an INFO answer is correct.
- The semantic layer HSGE discovers (skills/operators/predicates) is both weak
  (7 trivial nav skills; 1 of 6 operators has a genuinely useful
  precondition→effect pair — see `docs/13_run02_reddit_exploration_log.md`)
  and **unused by the training pipeline**: `build_sft_dataset.py` emits raw
  per-step `(axtree, action)` examples and never touches skills or operators.

Net: the SFT dataset is a clickstream of short nav/lookup fragments, not
WebArena-like trajectories.

## Decisions taken during brainstorming

1. **"Semantic trajectory" = long, meaningful, realistic multi-step task
   trajectory** (WebArena-like), regardless of annotation format.
2. **Eval target is the official WebArena benchmark**, so generated tasks
   should mimic its distribution: multi-hop, cross-page, INFO aggregation +
   NAV + MOD transactions, each with an automatically checkable success spec.
3. **Mechanism: add a top-down task-generation layer** on top of the existing
   exploration/skill pipeline. The skill layer is retained as *site knowledge*
   (solver hints, curriculum signal), not as the sole source of long tasks.
   Fixing operator-induction quality is explicitly *not* on this critical path.
4. **Verification is strict, WebArena-style**: every generated task carries an
   eval spec; only trajectories that pass enter the SFT dataset. No
   self-reported success in training data.
5. **The WebArena instance can be reset but resets are slow** → MOD tasks are
   collected in one batch at the end so a single reset covers them, and INFO
   answers are collected before any MOD runs.

## Architecture overview

Two phases. Phase 1 is the existing frontier loop plus one distillation step;
phase 2 is new.

```
PHASE 1 — EXPLORE (current loop + online digest)
  frontier loop (runtime.py, unchanged)
    → PageExplorer proposes local tasks → Solver solves them   (as today)
    → NodeDigester (NEW): 1 LLM call per node distills
         (url, axtree, solved-task results)
         → node digest: page_type, entities, grounded facts, outlinks
    → SiteKB (NEW): accumulates every node digest + skills.json,
         dumped after every node like the other artifacts

PHASE 2 — GENERATE & COLLECT (new; runs after phase 1)
  TaskComposer (NEW): reads the whole SiteKB
    → generates WebArena-style tasks: multi-hop, cross-page,
      EACH TASK CARRIES AN EVAL SPEC (string_match / url_match / program_html)
  Collection loop (NEW):
    per task: fresh browser at start_url → Solver (with skill hints from SiteKB)
    → Evaluator (NEW) scores automatically against the eval spec
    → only PASSING episodes are marked verified for SFT
  MOD batch: runs last; one instance reset per batch
```

Key properties:

- **SiteKB is the new central product of exploration** (not skills/operators).
  Skills are still discovered exactly as today and become part of the SiteKB
  (solver hints + difficulty signal), but are no longer the only path to long
  tasks.
- **Answers are known before solving**: INFO tasks are composed *from grounded
  facts in the SiteKB*, so the reference answer exists up front and
  verification is a string comparison — this is the root fix for
  self-reported success.
- **Eval specs mirror WebArena's evaluator format** (`string_match`,
  `url_match`, `program_html`), so the SLM trains on the same task/verdict
  distribution it will be benchmarked on.
- **Phase 1 never re-crawls**: digests are extracted online while the node's
  browser is still open.

New modules: `hsge/webarena/digest.py` (NodeDigester + SiteKB),
`hsge/webarena/composer.py` (TaskComposer), `hsge/webarena/evaluator.py`
(the three eval types). New LLM roles in `config.yaml`: `node_digester`
(cheap model), `task_composer` (strong model), optional `judge` for
`fuzzy_match`. `run_webarena.py` gains `--phase explore|generate|all`.

## SiteKB schema and anti-hallucination

`sitekb.json` is dumped alongside the other artifacts and updated after every
node:

```json
{
  "site": "http://<host>:8880",
  "nodes": [{
    "node_index": 1,
    "url": "http://<host>:8880/f/AskReddit",
    "url_template": "<host>:8880/f/*",
    "page_type": "forum_listing",
    "title": "AskReddit",
    "entities": [{
      "type": "post",
      "name": "What is the best...",
      "attrs": {"author": "hlz0", "upvotes": "183", "posted": "2 years ago"},
      "evidence": "link 'What is the best...' ... text '183'"
    }],
    "facts": [{
      "q": "How many comments does post X have?",
      "a": "45",
      "source": "axtree",
      "evidence": "text '45 comments'",
      "grounded": true
    }],
    "outlinks": ["..."],
    "axtree_path": "node_state/node_0001_axtree.txt"
  }],
  "skills": [ /* copied from skills.json, plus member episode ids */ ]
}
```

Anti-hallucination is layered, and the load-bearing layer is **code, not an
LLM**:

1. **Mandatory evidence + code-side substring check.** The digester must quote
   an `evidence` string for every entity and fact. Code verifies (after
   whitespace normalization) that the evidence **is literally a substring of
   the node's axtree**; otherwise the item gets `grounded: false`. The LLM
   cannot self-declare groundedness.
2. **Persist each node's axtree to disk** (`node_state/node_XXXX_axtree.txt`;
   today only screenshots are saved). Phase 2 can re-check any fact, and the
   evidence check is reproducible after the run.
3. **Facts from solved INFO episodes** (the answer the Solver sent via
   `send_msg_to_user`) are only `grounded: true` if the answer text also
   appears in that episode's final axtree (same substring check). Otherwise
   they are kept as hints (`source: "episode", grounded: false`) and are never
   used as reference answers.
4. **TaskComposer may only use `grounded: true` facts/attrs as reference
   answers.** Ungrounded facts may still inspire task *topics*, never
   graded answers.

Secondary decisions:

- **Open vocabulary** for `page_type` / `entity.type` (the digester names them
  freely) rather than a per-site hardcoded schema — no new schema per site
  (reddit/shopping/gitlab). Trade-off: type strings may drift ("post" vs
  "submission"); acceptable because the composer reads names/attrs too.
- **Volatility** (vote/comment counts change if MOD tasks run first) is
  handled by ordering: phase 2 collects all INFO before the MOD batch (the
  same order the reset-frugality requirement already forces).
- **Size caps**: ~20 entities + ~10 facts per node so a 500-node run's SiteKB
  still fits the TaskComposer's context (sample/compress later if needed).

## TaskComposer

Module `hsge/webarena/composer.py`, LLM role `task_composer`.

**Generation is per context bundle, not whole-KB-in-one-prompt.** Each call,
code samples a related bundle from the SiteKB — e.g. a forum + its posts + the
author's user page (joined via `source_nodes`/outlinks), or a cluster of
same-type entities spanning several nodes — and asks the composer for 3–5
tasks from that bundle. Repeat until quota is met. This forces *genuinely*
multi-hop tasks (the answer is spread across pages) instead of letting the
LLM invent connections.

Generated task schema (mirrors WebArena's task-config format):

```json
{
  "task_id": "gen_0042",
  "intent": "In the 'movies' forum, find the post with the most upvotes and tell me who submitted it",
  "type": "INFO",
  "start_url": "http://<host>:8880/",
  "hops": 3,
  "source_nodes": [4, 12, 13],
  "answer_fact_refs": ["n12.f3", "n13.e1.attrs.author"],
  "eval": {
    "eval_types": ["string_match"],
    "reference_answers": {"exact_match": "hlz0"},
    "reference_url": null,
    "program_html": []
  }
}
```

Hard gates at generation time (code, not LLM):

- **INFO**: `answer_fact_refs` must point to facts/attrs that **exist and are
  `grounded: true`** in the SiteKB, and `reference_answers` must match the
  referenced content — otherwise the task is rejected before costing a single
  episode.
- **NAV**: `reference_url` must be a URL known to the SiteKB (visited or in
  outlinks).
- **MOD**: regex denylist on the intent
  (`delete|remove|logout|password|ban|deactivate`) rejects destructive tasks;
  the composer prompt also forbids them, but code is the final gate.
- **Dedup**: the composer sees the list of already-generated tasks (like
  PageExplorer's proposal memory) plus a code-level near-duplicate filter.
- **Quota** from config: `gen.quota: {INFO: 60, NAV: 20, MOD: 20}` plus a
  target hop distribution (2–4 hops preferred).

## Evaluator

Module `hsge/webarena/evaluator.py` — a minimal reimplementation of
WebArena's evaluator subset:

- **`string_match`**: the answer is the text the Solver sent via
  `send_msg_to_user`. Compare `exact_match` / `must_include` after
  normalization (lowercase, trim, strip surrounding punctuation).
  `fuzzy_match` calls the LLM `judge` role — only when the composer declared
  it, never the default.
- **`url_match`**: compare the episode's final URL against `reference_url`
  (normalize scheme / trailing slash / query, WebArena-style).
- **`program_html`**: after the episode, using the still-open browser — goto
  `url` (or sentinel `"last"` = current page), run the locator, check
  `must_include` on the text. This is the only real verification for MOD
  (did the comment appear, is the subscription on).

## Collection loop (phase 2)

```
sort tasks: INFO/NAV first, MOD batch last
per task:
  fresh browser at start_url → Solver.solve(intent, skill_hints=top-k from SiteKB)
  → Evaluator scores → verified true/false
  → record episode: tag "GEN", difficulty=hops, meta carries eval spec +
     verdict + the solver's answer (failures are recorded too — future DPO
     pairs — but verified=false)
  → verified GEN episodes also feed Discovery like LOCAL ones (free skill data)
```

- **Skill hints**: top-k skills from the SiteKB by embedding similarity to the
  intent, injected into the Solver prompt as "known procedures" — the skill
  layer's direct contribution.
- **Step budget**: separate `gen.max_steps` (default ~25; GEN tasks are longer
  than LOCAL's 15).
- **MOD batch & reset**: MOD runs last → **one reset after the whole batch**
  (INFO answers were collected beforehand, so MODs cannot dirty them). Within
  the batch, composer/code avoid two MOD tasks targeting the same entity so
  one task's `program_html` check is not broken by another.

## build_sft_dataset.py upgrades

- **Gate on verification, not self-report**: by default only episodes with
  `tag: GEN` and `verified: true` in `episode_meta.json` are included (the new
  meta carries `verified`, the eval spec, verdict, and the solver's answer).
  LOCAL episodes (self-reported success) are included only behind
  `--include-local` — optional difficulty-1 warmup data.
- **`difficulty` = real `hops`** of the GEN task instead of the constant 1 —
  the easy→hard curriculum sort finally has a real signal.
- The final step of an INFO episode (`send_msg_to_user(answer)`) is now a
  **verified answer** — the SLM learns to answer correctly, not just click
  correctly.
- DPO pairs (fail/success for the same `task_id`) are a noted extension;
  this design only requires that failed episodes are stored with full meta
  (they are, per the collection loop).

## Config / CLI

- `config.yaml`: new `gen:` block (quota by type, hop distribution,
  `max_steps`, `skill_hints: true`) and two new roles under `llm.agents`:
  `node_digester` (cheap model), `task_composer` (strong model); optional
  `judge` role for `fuzzy_match`.
- `run_webarena.py --phase explore|generate|all`, **default `explore`** — the
  current behavior is unchanged and old runs/scripts keep working. `generate`
  requires an `out_dir` that already contains `sitekb.json`; `all` chains
  both phases.
- Phase-2 artifacts: `gen_tasks.json` (every generated task, **including
  rejected ones with the rejection reason** — composer-quality
  observability), GEN episodes in the same `episodes/` dir, `summary.json`
  extended with GEN stats.

## Error handling

- **Digester failure / bad JSON** → log the event, that node simply has no
  digest, the run continues (SiteKB misses one node; the run does not die).
- **Composer emits a bad task** (bad refs, missing eval) → rejected with a
  reason into `gen_tasks.json`; costs no episode.
- **Episode crash mid-collection** → record the episode as errored, continue
  the loop; artifacts are dumped after *every task* (same
  dump-after-every-node pattern as today, so an interrupted run leaves a
  consistent snapshot).
- **Resume**: the collection loop skips `task_id`s that already have an
  episode on disk — re-running after Ctrl+C is idempotent and re-burns no
  LLM calls.
- Browsers are created fresh per task (already the `browser_factory`
  pattern), so a dead browser does not cascade.

## Testing

Follows the repo's existing pattern (mock + dry-run; tests standalone-runnable
without pytest):

- **Unit (deterministic, no LLM)**: evidence-substring check;
  `string_match`/`url_match` normalization and comparison; `program_html`
  against a fake browser; composer gates (reject ungrounded refs, MOD
  denylist); resume-skip logic.
- **Extended dry-run**: `--dry-run` with the scripted LLM + fake browser runs
  end-to-end through `explore → sitekb.json → generate → gen_tasks.json →
  collect → verified episodes → build_sft_dataset` — the same full-wiring
  smoke test the current `--dry-run` provides.
- The original mock pipeline (`hsge/tests/test_clustering.py`, ...) is
  untouched — all changes live in `hsge/webarena/` + top-level scripts.

## Out of scope

- Improving operator-induction quality (tautological/ungrounded operators from
  run 02) — observation-only grounding checks stay as they are.
- DPO/preference-pair dataset construction (extension; failed GEN episodes
  are stored with enough meta to build it later).
- Hindsight stitching of existing short episodes into synthetic long tasks
  (possible cheap augmentation later, rejected as the primary mechanism).
- Multi-site transfer of the SiteKB/composer (design is site-agnostic via the
  open vocabulary, but only one site per run is exercised here).
