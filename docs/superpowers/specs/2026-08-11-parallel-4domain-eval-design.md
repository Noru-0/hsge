# Parallel four-domain WebArena evaluation — design

**Date**: 2026-08-11
**Status**: implemented (commits `39c5364`, `8d15e07`, and this doc's commit)
**Goal**: score one cross-domain LoRA (`checkpoint-536`) on all four WebArena
domains, on four boxes at once, and be able to explain the result afterwards.

## Problem

The model is trained (`training/artifacts/qwen35-9b-lora-all-v2`, epoch 2:
`eval_loss` 0.4343 versus 0.4711 and 0.4535 either side). Scoring it on the 655
single-site WebArena tasks in sequence takes ~22 h at the planning figure of
~120 s/task derived below. The user has four GPU boxes, so the work is
parallelisable by domain.

The previous sweep of this pipeline scored **0%** and **nothing in the artifacts
could say why** — the results file held an aggregate and a truncated last action,
which cannot distinguish "never found the page" from "found it and misread it"
from "the output was unparseable so the episode ended". Explaining the result is
therefore a first-class requirement, not a nice-to-have.

## Measured inputs

| domain | tasks | write | read | LLM-judged |
|---|---|---|---|---|
| reddit | 106 | 84 | 22 | 0 |
| shopping | 187 | 51 | 136 | 15 |
| shopping_admin | 182 | 70 | 112 | 20 |
| gitlab | 180 | 108 | 72 | 5 |
| **total** | **655** | 313 | 342 | **40** |

Counts from WebArena's own `config_files/test.raw.json`. "LLM-judged" counts
tasks whose `fuzzy_match` reference is not `"N/A"`; 70 tasks carry the key but
WebArena exact-matches the `"N/A"` ones without calling a model, so only 40
actually need `OPENAI_API_KEY`.

Per-task time, from the two archived gitlab sweeps in
`training/artifacts/eval_results/` (293 rows): **mean 101 s over non-errored
rows**, median 80 s, **p90 760 s**, and **mean 171 s over all rows** (errored
tasks are dominated by timeouts, which are slow, not fast). Planning below uses
**~120 s/task**, between those two means: 101 s is optimistic because it excludes
the timeouts a live sweep will hit, and 171 s is pessimistic because the resume
fix means a blip is retried rather than repeated. At 120 s/task shopping's 187
tasks are ~6.2 h; the 101 s bound would be 5.3 h and the 171 s bound 8.9 h.

Tunnels: four Cloudflare **quick** tunnels, warm TTFB 0.25–0.65 s (a first hit on
shopping cost 6.5 s — Magento cache warming, not a persistent cost). Quick
tunnels are ephemeral and rate-limited, which drives several decisions below.

## Approach

Chosen: **one domain per box, four in parallel**. Wall-clock becomes the slowest
domain (~6.2 h for shopping) instead of ~22 h. reddit's 106 tasks finish ~2.5 h
early, so that box can be destroyed early.

This is safe because the four domains are four separate services and, within a
box, tasks run one at a time. The one cross-domain hazard is shopping ↔
shopping_admin sharing state. Three earlier handoffs assert they "share one
Magento DB", but always as a bare claim with no evidence, while WebArena ships
them as **two separate docker images each containing its own MySQL**. The design
does not rely on either belief: the README records the one-command `docker ps`
check to run before those two go concurrent. Rejected alternatives: running the
second shopping\* domain read-only-first (safe unconditionally, ~8.5 h) and fully
serialising the pair (~12.2 h).

Only the finetuned model is evaluated — no base-model baseline — matching the
earlier decision to skip it.

## Design

### 1. Pre-flight: four silent-failure paths closed

Everything here produces *a plausible number* rather than an error, which is the
worst failure mode for a thesis measurement.

- **Errored tasks were treated as done on resume.** 55 of 180 rows in the
  archived gitlab baseline carry `error`; one tunnel blip became a permanent 0.
  `prune_errored()` requeues them. It also **rewrites** `results.jsonl` to one
  row per `task_id`, because the naive fix is worse than the bug: the file is
  append-only and both the total and the success count are computed over rows, so
  retrying would leave two rows for one task and shift the denominator on every
  retry. A later `error` clears an earlier success — the last attempt is the one
  that did not score.
- **`success_rate` divided by the attempted count**, so an interrupted sweep
  outscored a finished one. `summary.json` now carries `n_site_tasks`,
  `n_scored`, `n_errored`, both rates, and `complete`.
- **A missing `OPENAI_API_KEY` was not fatal.** Now it is, when the selected
  tasks include judged ones — counted per site, so a keyless reddit sweep stays
  valid. `--allow-missing-judge-key` opts out knowingly.
- **The judge model is retired.** `patch_webarena_judge.py` handles both builds:
  a current install reads `WEBARENA_EVAL_MODEL` and needs no source patch (its
  default `gpt-4.1-mini` is *not* the closest successor, so leaving it unset
  still changes the measurement quietly); an older hardcoded build is patched
  with a `.orig` kept. Both print `WA_JUDGE_MODEL_OVERRIDE`, which
  `summary.json` records so the deviation travels with the numbers.

### 2. Tracing: three records, deliberately not merged

Per episode the trace holds:

- `steps` — what the Solver accepted: thought, action, resulting URL, axtree size
  (full axtree under `--trace-axtree`).
- `llm_calls` — what the model actually emitted: `raw`, `parsed_ok`,
  `finish_reason`, latency, prompt size.
- `act_trace` — what the browser did: per-step reward (WebArena's `validate()`
  runs every step), `action_error`, URL either side, duration.

They are **not** zipped into one array because they are not 1:1 — a step can be
dropped by the Solver, the end-of-episode wrap-up call produces a call with no
step, and the replayed terminal action produces an act with no step. Aligning
them by index would invent a correspondence; `n_steps`/`n_llm_calls`/`n_acts` are
recorded so a mismatch is visible instead of hidden.

`raw` is the point: `complete_json` degrades a malformed response to `{}` and
reports it only on stderr, so a step that ended an episode on invalid JSON (the
`\xa0` escape, ~8% of episodes in a real smoke run) was indistinguishable from a
deliberate stop. Traces are written for errored tasks too — the case most in need
of one.

### 3. Per-box mechanics

`bootstrap_eval_box.sh`: one idempotent command per box, nine stages, each gating
the next — inputs, venvs, merge, serve, **endpoint generates**, judge configured,
**site reachable from that box**, smoke 3 tasks, full sweep. The sweep starts
only if the smoke test scored at least one task without error, so six hours is
never spent on a broken box. The two emphasised gates exist because the cheaper
version already failed: vLLM has reached `READY` and then died on its first real
request, and a tunnel reachable from the operator's laptop says nothing about
reachability from the box.

`vast_setup.sh eval` skips the train venv: an eval box merges with
`merge_lora_peft.py`, needing only `peft` in the serve venv. That saves ~13 min
per box and skips the entire class of environment breakage that stage carries
(the torch/CUDA pin, flash-linear-attention, tilelang, the `causal-conv1d`
compile). Both `vast_setup.sh` and the vLLM install now select by the box's CUDA
major rather than assuming CUDA 12.

Supervisor runs both programs with `stopasgroup`/`killasgroup` — a plain restart
kills the shell but not its python child, leaving two processes appending to one
`results.jsonl`. `autorestart=unexpected` with `exitcodes=0,3` keeps the new
consecutive-error abort (exit 3 after 5 errors in a row) from looping against a
dead tunnel; those tasks are requeued on the next run, so nothing is lost but
hours.

### 4. Monitoring, collection, explanation

`eval_status.py` prints one line per sweep **from `results.jsonl`, never the
log** — a buffered `grep` once put a log 31 minutes behind and raised a false
hang alarm. Progress is against the official per-site count; exit codes 3/2/0
mean aborted/stale/healthy so it can drive a cron check. It warns when two
domains used different judge models, which would silently make the four numbers
incomparable.

`collect_eval_results.sh` refuses to certify a copy while the sweep is still
writing, and compares digests afterwards: `rsync` exit 0 proves rsync ran, not
that the two sides match. It prints `MATCH -- <site> is safe to destroy`.

`analyze_eval_traces.py` gives every failed episode one primary cause (table
sums) plus every signal present (overlaps visible), each mapped to a concrete
field. Two categories justify the whole exercise:

- `declared_done_without_acting` — one step, `send_msg_to_user`, nothing touched.
  The pre-fix training set was 42% single-step trajectories and 104
  zero-effective-action ones were dropped from the current set, so this rate is
  the measurement that connects the dataset work to the eval result.
- `reached_goal_then_left` — a step scored but the episode ended at 0. Newly
  measurable via the per-step reward; if non-trivial, `--max-steps` is penalising
  the model rather than measuring it.

## Reporting obligations

1. Judge model substituted (`gpt-4-1106-preview` → `gpt-4-turbo`); recorded in
   every `summary.json`.
2. Quote `success_rate` (full official denominator), not
   `success_rate_attempted`; check `complete: true`.
3. `--max-steps 15` is our budget, not the benchmark's.

## Testing

`hsge/tests/test_eval_webarena_resume_and_trace.py` — 11 tests covering requeue,
the duplicate-row hazard, error-after-success ordering, the `"N/A"` judge
special case, trace contents, and both summary denominators. Suite 318 → 329.
`analyze_eval_traces.py` was exercised against synthetic traces covering all nine
categories; `eval_status.py` against the archived gitlab results, where it
reproduces that run's recorded 5.6%.

## Open, deliberately not addressed

- The `\xa0` JSON parse failure is **recorded but not fixed**. Making the parser
  lenient mid-measurement would change the quantity being measured; do it before
  the next collection run, not between two runs being compared.
- Whether shopping and shopping_admin truly share a database (one `docker ps`
  away; the plan works either way).
