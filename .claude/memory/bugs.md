# Bugs

Known bugs found in this project — open ones at the top, fixed ones below.
Entry format:

```
### <short title>
- **Status**: open | fixed (YYYY-MM-DD HH:MM)
- **Found**: YYYY-MM-DD, where/how it was noticed
- **Where**: file(s):line(s)
- **Symptom**: what goes wrong
- **Cause**: root cause (once known)
- **Fix**: what was changed (commit hash if committed)
```

## Open

### `run_webarena.py` hangs indefinitely mid-run, immune to SIGINT
- **Status**: open (mitigated with an external watchdog, root cause unconfirmed)
- **Found**: 2026-08-16, `outputs/wa_run_21_reddit` (real WebArena run, new
  tunnel instances). Hit **3 times** in one run: 21:33–22:42 (shopping_admin,
  same run family), 14:36–15:05 and 17:42–18:24+ (reddit).
- **Where**: somewhere inside the Playwright sync-API call chain reached from
  `hsge/webarena/browser.py` / `hsge/webarena/agents.py::Solver.solve` /
  `WebArenaExplorer._solve_with_retries` — exact frame unconfirmed (see Cause).
- **Symptom**: the process is still alive (`ps` shows it running, not zombie)
  but CPU time stops advancing entirely (e.g. +0.03s of CPU over 15+ real
  minutes) and `run_log.jsonl`/episode files stop being written. No exception,
  no timeout error, nothing in stdout. **`SIGINT` does not interrupt it** —
  sent directly to the hung PID, the process was completely unaffected (no
  traceback, no exit), meaning it's blocked in a native/C call, not stopped at
  a Python bytecode boundary where `KeyboardInterrupt` could fire.
- **Cause**: unconfirmed. Could not get a stack trace in this environment:
  `py-spy dump --pid` requires root on macOS (unavailable here), and
  `lldb -p <pid>` attach itself stalled indefinitely (likely blocked on a
  macOS permission prompt this sandbox can't answer). Leading hypothesis based
  on the SIGINT-immunity + frozen-CPU signature: a Playwright sync-API call is
  blocked in the IPC layer between the Python process and its Node.js driver
  subprocess (or the driver and the underlying Chromium subprocess), which has
  no timeout of its own — `page.goto(timeout=10000)` etc. bound the
  *navigation*, not the underlying pipe read if the driver/browser process
  itself stops responding. All 3 hangs occurred around heavy
  Playwright activity (a broken admin route retried on 10s goto timeouts, a
  154-comment thread, and immediately after a 24-step episode finished) but no
  single common trigger was isolated.
- **Fix**: root cause not fixed (would need a stack trace this sandbox can't
  capture, or reproducing under `py-spy`-capable conditions). Mitigated with
  `scripts/watchdog_webarena.sh`: polls `run_log.jsonl` mtime every 2 min, and
  if it goes stale >= 30 min while the process is still alive, `SIGKILL`s it
  (SIGKILL always works, unlike SIGINT/SIGTERM which can't interrupt a blocked
  native call) and relaunches with `--resume`. This automates the manual
  kill+resume cycle already performed 3x by hand for this run. Run it instead
  of calling `run_webarena.py` directly for any long unattended collection run:
  `bash scripts/watchdog_webarena.sh <site> <out_dir> [max_nodes] [stall_secs] [target_success]`.

### The stall watchdog killed a slow-but-legitimate task 8 times in a row
- **Status**: fixed (2026-08-12 07:05). Thresholds corrected; the underlying
  design flaw (two guards with inverted thresholds) is what to remember.
- **Found**: 2026-08-12, during the clean base sweep. reddit sat at 91/106 for
  82 minutes, restarting every ~691s.
- **Where**: `training/stall_watchdog.sh` `STALL_S`, vs `eval_webarena.py`
  `--task-timeout-s`.
- **Symptom**: looked exactly like the deterministic Playwright hang below --
  same task retried forever, no row ever appended -- and was misdiagnosed as
  one. It was not a hang at all.
- **Cause**: **`webarena.721` legitimately takes 718s** (15 steps, no error).
  The watchdog's 600s threshold had been sized off shopping_admin's worst case
  (304s, p95 170s), but reddit's distribution has a much fatter tail: median
  90s, p95 227s, max 718s. So the watchdog killed the task at 600s, resume put
  it back at the head of the queue, and the cycle repeated 8 times.
  Compounding it: the in-process `--task-timeout-s` (900s) that was supposed to
  break exactly this loop could **never fire**, because the watchdog killed the
  process first every time. Two guards, and the weaker one won.
- **Fix**: watchdog default 1200s -> **2400s**, `--task-timeout-s` 900s ->
  **1500s**, with the invariant written into both files: the watchdog threshold
  must stay ABOVE the in-process timeout, so the timeout is what fires and the
  task gets recorded. Applied live at 1800s to the running boxes, which
  unblocked reddit immediately -- 721 then completed normally in 718s.
- **Lesson**: do not size a kill-threshold off a median or p95 when the metric
  has a fat tail, and never let a coarse external guard preempt a precise
  in-process one. Also: a task being retried forever is NOT sufficient evidence
  of a hang -- check the task's own elapsed time first.

### An unreset WebArena instance scores the second sweep on the first sweep's work
- **Status**: open (methodology, not code) — found 2026-08-12 02:xx, confirmed by
  the user the same session.
- **Found**: comparing the restarted base sweep against the abandoned one. reddit
  was 1/21 where the earlier run had been 7/21, while shopping (13 vs 14) and
  gitlab (12 vs 11) agreed within one.
- **Where**: run procedure, not a file. `training/bootstrap_eval_box.sh` gates
  nine things and instance freshness is not one of them.
- **Symptom**: a sweep run against an instance a previous sweep already mutated
  is scored **too high**, silently. No error, no log line, and the run looks
  complete and healthy.
- **Cause**: WebArena evaluators check only the site's **final state**, never
  that this agent caused it. The finetuned sweep ran first and completed the
  stateful `[MOD]` tasks (`Upvote the newest post in <forum>`, `Change my reddit
  bio to ...`); the base sweep that followed inherited that work and was scored
  success for wandering through. Concentrated in reddit because its early task
  block is dense with such tasks — which is exactly why only reddit moved.
- **Consequence**: `outputs/eval/*/base_instance1/` is void, and the anomaly it
  produced (base 21.7% "beating" finetuned 20.8% on reddit) was an artefact. The
  `136/655 = 20.8%` finetuned figure ran *first* on that instance and so is less
  exposed, but its own starting state is **unverified** — do not pair it with
  the clean 2026-08-12 base run until that is confirmed.
- **Resolved for the 2026-08-12 run**: the user confirmed the instance was
  cleaned before it, so that base sweep's numbers stand. The finding remains
  open as a *procedural* one — nothing in the tooling enforces or checks it.
- **Fix**: reset the WebArena Docker stack between sweeps. Worth adding as gate
  0 in `bootstrap_eval_box.sh` (assert a known seed value, e.g. that the reddit
  user's bio is at its default) so a contaminated instance fails fast instead of
  producing a plausible number. Detection method meanwhile: compare two runs
  **task-id by task-id** — a uniform shift is the model, a single-domain shift
  concentrated in MOD tasks is contamination.

### A sweep can hang forever inside Playwright, and nothing detects it
- **Status**: mitigated (2026-08-11 11:24) by `training/stall_watchdog.sh`; the
  underlying Playwright hang is **not** fixed and its trigger is unknown.
- **Found**: 2026-08-11, during the 4-box parallel eval. reddit sat at 1/106 for
  ~20 minutes while the other three boxes advanced normally.
- **Where**: `training/eval_webarena.py` `run_task()`, inside BrowserGym env
  setup/step; no bounding timeout on that path.
- **Symptom**: the sweep process stays alive and `supervisorctl status` reports
  `RUNNING`, but no row is ever appended. Evidence from the live box: Chrome had
  been up 19 minutes with **zero network sockets** and ~2s total CPU; the main
  Python thread was in `ep_poll` on the Playwright driver pipe with 15 threads in
  `futex_wait`; vLLM had logged no request for 16 minutes.
- **Frequency (revised at end of run — it is NOT a one-off)**: reddit hung once.
  **shopping_admin hung repeatedly** — the watchdog logged a 1201s stall and
  restarted the sweep, which ran 9 more tasks and hung again 18 min later, and
  I restarted it by hand a third time. Exact totals are unrecoverable: the boxes
  were destroyed and `stallwatch.log` went with them. So on some boxes this
  costs one restart, and on others it recurs every ~20 tasks. Budget for it.
- **Threshold tuning**: 1200s was cut to **600s** mid-run for the two surviving
  boxes, sized off real data — shopping_admin's longest legitimate task was
  304s (p95 170s, median 75s), so 600s keeps ~2x headroom. It did not misfire:
  shopping_admin's best interval of the whole run (13 tasks / 20 min) came
  immediately after the change.
- **Cause**: not root-caused. Not task-specific — the same task (webarena.28)
  had completed during the smoke run minutes earlier, and
  completed again immediately after a restart. Note the misleading signal: the
  process holds a `CLOSE-WAIT` socket to vLLM, which looks like a stuck HTTP
  read but is just an idle keep-alive connection the server reaped. `OpenAILLM`
  already sets a 180s timeout with `max_retries=0`, so the LLM path is bounded;
  the browser path is not.
- **Why nothing caught it**: BrowserGym's `10000 => 30000` override bounds
  *actions*, not env setup. `eval_webarena.py`'s exit-3 guard counts consecutive
  **errors**, and a hang produces no error. `eval_status.py` does report `STALE`,
  but only if a human is looking.
- **Fix (mitigation)**: `training/stall_watchdog.sh`, run as a supervisor program
  beside `evalsweep`, restarts the sweep when `results.jsonl` has not been
  appended to for 20 min. Safe because a hung task has no row yet, so resume
  re-runs it whole — nothing partial is ever recorded. Threshold is 20 min
  against a worst legitimate task of ~9 min (16 steps x 30s action timeout +
  LLM + per-step `validate()`), and the watchdog sleeps a full interval after
  restarting so a slow first task cannot livelock it.
- **Watchdog limitation found later (2026-08-12)**: it rescues a *transient*
  hang, but a *deterministic* one becomes an infinite loop -- a hung task writes
  no row, so resume puts it straight back at the head of the queue and the
  restart re-runs the same task. reddit was stuck at 94/106 for ~35 minutes on
  `webarena.724`, which hung on all three attempts and had to be excluded by
  hand; that domain's first baseline is still 105/106.
- **Real fix (2026-08-12 02:22, commit `7aec94f`)**: `--task-timeout-s`
  (default 900s, ~3x the longest legitimate task at 304s) raises `TaskTimeout`
  from a SIGALRM handler inside `run_task()`. SIGALRM rather than a watchdog
  thread because the hang is a *blocking* one (main thread parked in `ep_poll`
  on the driver pipe), which a thread can observe but not interrupt; under
  PEP 475 the interrupted syscall runs Python-level handlers before retrying.
  The row is kept and **never requeued** -- `prune_errored()` skips `timed_out`
  rows -- because requeueing assumes the retry might score, which is exactly
  what a deterministic hang violates. It stays an `error` row, so the task is
  **unscored, not 0**: scoring it would convert an infrastructure hang into a
  model failure. Note this makes the sweep self-healing but does **not**
  root-cause the Playwright hang, which is still unknown.

### `serve_vllm.sh`'s default model path pointed at a directory nothing creates
- **Status**: fixed (2026-08-11 10:08)
- **Found**: 2026-08-11, preparing the 4-box parallel eval.
- **Where**: `training/serve_vllm.sh`, `MODEL=${1:-...}` default.
- **Symptom**: the default was `/workspace/models/Qwen3.5-9B-hsge`, a path the
  current merge step never produces (it writes `Qwen3.5-9B-all`). Invoking the
  script with no argument therefore served nothing useful -- and on a box where
  someone had pulled the base model to a similarly named path it would serve the
  BASE model while every downstream artifact was labelled finetuned. Across four
  boxes, one omitted argument is enough.
- **Fix**: default corrected to the merged path, and the script now refuses to
  start unless the directory exists and contains `config.json`.

### `vast_setup.sh` pinned vLLM to a CUDA-12 build regardless of the box
- **Status**: fixed (2026-08-11 10:08)
- **Found**: 2026-08-11, same preparation.
- **Where**: `training/vast_setup.sh`, `setup_serve()`.
- **Symptom**: `vllm==0.18.0` is the newest cu12 release that knows Qwen3.5, and
  was pinned unconditionally after the CUDA-12 Hopper episode. On a CUDA-13 box
  that pin installs the wrong wheel; the measured working configuration there is
  plain unpinned `vllm`.
- **Fix**: reads the CUDA major from `nvcc` and selects the pin or the unpinned
  release accordingly, mirroring what the torch pin already does. `peft` is also
  installed into the serve venv so an eval box can merge the adapter without
  building the train venv at all.


### A retried eval task appends a second row, corrupting the success denominator
- **Status**: fixed (2026-08-11 09:37)
- **Found**: 2026-08-11, while fixing the resume-skips-errored bug below — the
  obvious fix (skip rows carrying `error` when building the resume set) would
  have introduced this one.
- **Where**: `training/eval_webarena.py`, `results.jsonl` handling.
- **Symptom**: `results.jsonl` is append-only and both `total` and the success
  count are computed over its rows, so re-running a task leaves the old row AND
  the new one and every retry quietly shifts the denominator.
- **Fix**: `prune_errored()` rewrites the file on resume, keeping exactly one row
  per `task_id` (last clean row wins; a later `error` clears an earlier success,
  since the last attempt is the one that did not score) and preserving a `.bak`.
  This also absorbs what the previous session's throwaway `requeue_errored.py`
  did by hand, and removes its "only run while the sweep is stopped" caveat.

### `summary.json`'s success_rate used the attempted count as its denominator
- **Status**: fixed (2026-08-11 09:37)
- **Found**: 2026-08-11, same review.
- **Where**: `training/eval_webarena.py`, summary block.
- **Symptom**: `total = len(done) + len(todo)`, i.e. what this invocation
  attempted — so an interrupted sweep reports a rate over a smaller denominator
  and looks better than it is. With four 6-hour sweeps behind ephemeral quick
  tunnels, interruption is the expected case, not the exception.
- **Fix**: `summary.json` now carries `n_site_tasks` (the site's full official
  set), `n_scored`, `n_errored`, `n_success`, both `success_rate` (over
  `n_site_tasks`, the figure comparable to published numbers) and
  `success_rate_attempted`, plus `complete` and `judge_model_override`. The
  script prints an explicit INCOMPLETE line when the sweep is not finished.


### Qwen3.5's `is_fast_path_available` needs FOUR packages, so one missing wheel costs 2.3x training speed
- **Status**: fixed (2026-08-11 09:02) in `training/vast_setup.sh`; the trap itself
  is upstream behaviour and will recur on any box set up by hand.
- **Found**: 2026-08-11, first training run on the new 4-domain dataset was
  running at 30-33 s/step against a `training/README.md` baseline of 11-13 s/step
  for the same effective batch.
- **Where**: `transformers/models/qwen3_5/modeling_qwen3_5.py:205`.
- **Symptom**: 2.3x slower training, and the GPU is *starved* rather than busy —
  utilization oscillating 0-100% at 130-200 W instead of a steady 100% / 630 W.
  The only in-band signal is one line, logged once, buried in the model-loading
  spew: "The fast path is not available because one of the required library is
  not installed."
- **Cause**: `is_fast_path_available = all((causal_conv1d_fn,
  causal_conv1d_update, chunk_gated_delta_rule,
  fused_recurrent_gated_delta_rule))`. `vast_setup.sh` installed
  flash-linear-attention and tilelang (which supply the last two) but never
  `causal-conv1d`, so the `all()` was False and **every** Gated DeltaNet layer —
  not just the conv — fell back to plain torch. Misleading in two ways: the
  warning names two projects, so it reads as "fla is missing" when fla was fine;
  and nothing scales with the missing kernel, so the slowdown looks like a data
  or batch problem.
- **Ruled out**: not the new dataset being longer (measured with the real
  tokenizer: median 2706 vs the old dataset's 2314, max 4040 vs 3794 — ~17%, not
  150%); not a memory leak (VRAM flat at 78.3 GB across steps); not tilelang
  recompiling (0 "TileLang begins to compile" lines in that run's log).
- **Fix**: `vast_setup.sh` now builds `causal-conv1d` and prints the fast-path
  state explicitly at the end of setup. Confirmed on the H100: 13 s/step, 100%
  util, 630-658 W, and the warning gone from the log.

### Building `causal-conv1d` needs torch's CUDA to match nvcc, and the fix has two sharp edges
- **Status**: fixed (2026-08-11 09:02) in `training/vast_setup.sh`
- **Found**: 2026-08-11, installing causal-conv1d for the entry above.
- **Where**: `training/vast_setup.sh` (torch pin), box environment.
- **Symptom 1 — cannot build at all**: `RuntimeError: The detected CUDA version
  (13.2) mismatches the version that was used to compile PyTorch (12.8)`.
  causal-conv1d has no prebuilt wheel, so it must compile, and torch's
  `cpp_extension._check_cuda_version` refuses to. The box had only CUDA 13.2
  under `/usr/local/cuda`, so the toolkit could not be downgraded to match.
- **Symptom 2 — `undefined symbol: ncclCommResume`** after switching torch to
  the cu130 index. Two causes stacked: (a) `uv pip install --reinstall-package
  torch ...` replaces only the packages named, leaving every `nvidia-*-cu12`
  dependency in place for a cu130 torch to link against; (b) asking for plain
  `torch` on that index resolves **2.13.0**, while torchaudio's newest release is
  only **2.11.0**, so the trio silently desynchronizes — and a broken
  `import torchaudio` takes `llamafactory-cli` down with it.
- **Symptom 3 — `ImportError: libnvshmem_host.so.3: cannot open shared object
  file`** after "cleaning up" by uninstalling the `nvidia-*-cu12` packages.
  `nvidia-nvshmem-cu12` and `nvidia-nvshmem-cu13` were both version 3.4.5 and
  install to the same paths, so removing the cu12 one deleted the shared `.so`
  files and left the cu13 package's metadata pointing at nothing. Diagnosed by
  walking each `nvidia-*`/`cuda-*` dist-info `RECORD` and checking whether its
  `.so` entries still exist on disk — exactly one package was affected (12/12
  `.so` missing), so a targeted reinstall fixed it without touching the rest.
- **Fix**: `vast_setup.sh` reads the CUDA major from `nvcc`, picks the cu128 or
  cu130 index accordingly, and pins **all three** of
  torch/torchvision/torchaudio to the 2.11.0 family (2.11.0 exists on both
  indexes, so the same known-good version works either way). It also documents,
  in-line, never to uninstall the cu12 packages — leftover wheels are inert, and
  removing them is what breaks nvshmem.
- **Also**: the default `causal-conv1d` build compiles **9** architectures
  (sm_75 through sm_121). `vast_setup.sh` now detects the GPU's own capability
  and sets `TORCH_CUDA_ARCH_LIST` to just that one (~7 min instead of ~1 h).

### `cutoff_len` carried over from an older dataset OOMs the H100
- **Status**: fixed (2026-08-11) in `training/qwen35_9b_lora_all.yaml`
- **Found**: 2026-08-11, first run on the new dataset died at step 9/804.
- **Where**: `training/qwen35_9b_lora_all.yaml`, `cutoff_len`.
- **Symptom**: `torch.OutOfMemoryError: Tried to allocate 15.01 GiB` with
  66.6 of 79.2 GiB already in use, at `per_device_train_batch_size: 4` — a
  configuration the README records as working.
- **Cause**: `cutoff_len: 6144` was inherited from `train_all.jsonl`'s rough
  chars/3 length estimate. Measured with the real Qwen3.5 tokenizer, the new
  dataset's max is **4040** tokens (p99 3672, zero examples over 4096), so 6144
  bought ~2100 tokens of padding headroom that only enlarged the worst-case
  activation footprint, and the varying padded lengths across micro-batches
  fragmented the allocator (the OOM message's own "12.93 GiB reserved but
  unallocated" note).
- **Fix**: `cutoff_len: 4096` (zero truncation risk against the measured max)
  plus `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. Peak settled at
  78.3/81.5 GiB and the run completed all 804 steps. **Re-measure rather than
  copying this number** to the next dataset.

### Zero-effective-action successes: 40% of kept trajectories never click/fill/goto anything
- **Status**: partially fixed (2026-08-11 03:43) — non-INFO episodes are now kept
  out of the dataset, but the runtime still produces them
- **Found**: 2026-08-11, same audit.
- **Where**: dataset-level symptom; originates in the MOD/COMPOSITE
  page-change gate in `hsge/webarena/agents.py` and in `[NAV]` success scoring.
- **Symptom**: 432 of 1077 train trajectories (40%) contain no action from
  {click, fill, select_option, press, goto, go_back, tab_*} at all — only
  scroll/noop/hover then `send_msg_to_user`. By tag: INFO 323/455 (71%, largely
  legitimate), **NAV 47/156 (30%)** and **MOD 33/193 (17%)**, which should be
  impossible: a NAV task that navigated nowhere and a MOD task that modified
  nothing are false successes the judge still passed. The MOD gate demands a
  url/axtree change, and a late-loading page after `noop()` apparently satisfies
  it without any real action.
- **Fixed at dataset level (2026-08-11 03:43)**: `build_sft_dataset.py` now
  drops a non-INFO episode whose *exported* steps contain no click/fill/
  select_option/press/goto/go_back/tab_* action (`_n_effective_actions` +
  `_needs_effective_action`, `--keep-ineffective` opts out). Counting the raw
  episode would not have worked: the usual shape is one click that ERRORED --
  and `episode_to_examples` drops error steps -- so the trajectory that reaches
  training is noop/scroll then send_msg_to_user while the episode file looks
  like it acted. Dropped 104 trajectories / 279 examples across the four
  `wa_run_20_*` domains (NAV 49, MOD 31, COMPOSITE 20, untagged GOAL 4). The
  11 non-INFO zero-effective episodes that remain are all `report_infeasible`,
  exempt on the same grounds as `--min-actions` exempts them.
- **Still open at the collection layer**: the MOD/COMPOSITE gate in
  `hsge/webarena/agents.py` accepts a url/axtree delta, which a late-loading
  page after `noop()` supplies, and the episode judge passes these because the
  final page it inspects is a plausible unchanged one. So the runtime keeps
  producing them (and spending an episode each); only training is protected.

### Seed-capability GOAL tasks are re-proposed at every node, so ~35% of kept episodes are duplicate goals
- **Status**: open
- **Found**: 2026-08-10, comparing episode quality of `wa_run_20_*` (4 domains)
  against `wa_eval_*_1`.
- **Where**: the seed-capability GOAL generator in `hsge/webarena/runtime.py`
  (`goal_seed_capabilities_attempted` path).
- **Symptom**: among kept (success/infeasible) episodes, distinct goal texts are
  only 62-68% of episodes in run 20 (reddit 67/108, shopping_admin 47/75) versus
  ~99% in the `wa_eval_*_1` runs. Top offenders repeat x3, e.g. reddit's
  "[GOAL] Submit a new post to the 'allentown' forum ...". Duplicated SFT
  examples inflate the dataset without adding behaviour.
- **Cause**: not task retries (`run.task_retries: 0`, every duplicate has
  `attempts: 1`) — the same seed capability is instantiated again at each new
  node, and even twice at the same URL when node dedup admits it. `PageExplorer`
  keeps a run-wide memory of already-proposed task texts; the seed-capability
  path has no equivalent.
- **Fix**: not yet applied. Give the seed-capability generator the same run-wide
  proposed-text dedup `PageExplorer` already has, or dedup at dataset build time
  keeping the best attempt.
- **Largely mis-measured — corrected 2026-08-11.** The 62-68%-distinct figure
  above counts the **intentional `unprefixed_sampling` pairing** as duplication.
  Re-measured on the same runs by episode `metadata.tags`: of reddit's 130
  repeated kept goals, **125 are exactly one `LOCAL` + one `UNPREFIXED`
  episode** (shopping_admin: 82 of 85), i.e. the same task solved from its node
  and again from the site root — by design, and the unprefixed twin is
  substantially longer (mean 6.0 vs 3.4 steps), so it is not redundant. The
  genuine duplicates are **`GOAL`-tagged only and few**: 4 goals on reddit, 3 on
  shopping_admin. Same picture in `training_data/train.jsonl`: 365 of 367
  repeated-goal groups are a difficulty-1/difficulty-2 pair; only 8 groups are
  two same-difficulty episodes and 2 groups have three. **Downgrade this entry
  to minor**; the fix, if applied, should target the `GOAL`/seed-capability path
  only and must not dedup LOCAL/UNPREFIXED pairs.
- **Mitigated at dataset level (2026-08-11 03:32)**: `prepare_dataset.py` drops
  same-goal same-difficulty repeats (keeping the longest trajectory) and leaves
  LOCAL/UNPREFIXED pairs alone — 13 trajectories / 56 examples on the four
  `wa_run_20_*` domains, all difficulty-2 GOAL-branch repeats. The generator
  itself is unchanged, so the wasted collection cost (one extra live episode per
  repeat) is still there; this only keeps it out of training.

### `goto` accepts hallucinated placeholder targets
- **Status**: open
- **Found**: 2026-08-10, same run analysis.
- **Where**: `hsge/webarena/browser.py::act` / `hsge/webarena/urls.py`.
- **Symptom**: 26 of 72 `goto` actions in the run targeted a placeholder rather
  than a URL (`goto('url_of_compare_products_page')` x14,
  `goto('order_history_url')` x11). They navigate somewhere meaningless and
  cost the episode.
- **Cause**: `absolutize_goto` prepends the origin to anything, so a
  non-path string becomes a plausible-looking URL instead of an error the
  Solver could recover from. (The related absolute-host problem — 46 `goto`s
  with a hardcoded `http://192.168.1.31:8081/` — was fixed on 2026-08-10 by
  `5652977`, which post-dates this run.)
- **Fix**: not yet applied. Validate the target and raise `ActionError`.

### vLLM dies on the first request: the Qwen3.5 GDN prefill kernel is JIT-compiled at runtime and the compile fails
- **Status**: open
- **Found**: 2026-08-09, serving the merged cross-domain model on the vast.ai
  H100 box (driver 560.35.03 / CUDA 12.6, `vllm==0.18.0`).
- **Where**: not repo code — the box's serving environment. Surfaces in
  `/workspace/vllm.log`, `vllm/model_executor/models/qwen3_next.py:767`.
- **Symptom**: the server reaches `READY` and answers `/v1/models`, then exits
  cleanly (`INFO: Shutting down`) the moment the first completion request
  arrives. Reproduced 3×. This blocks step 6 (eval) entirely; training and merge
  are unaffected.
- **Cause**: `flashinfer` JIT-compiles `gdn_prefill_sm90` (the Gated DeltaNet
  prefill kernel for Hopper) on demand, and every variant fails to compile with
  `fatal error: cuda/ptx: No such file or directory` — the image has no CCCL
  headers under `/usr/local/cuda/include/cccl`. vLLM logs the warmup failure as
  a WARNING ("First inference may OOM due to autotuner") and starts anyway, so
  the failure only becomes fatal at request time.
- **Ruled out**: not an ssh-lifetime problem. The first two deaths coincided
  with the launching ssh session closing, which looked like SIGHUP; running vLLM
  under the image's own supervisor (`/etc/supervisor/conf.d/vllm.conf`, which
  the instance guide says is the right way to run long-lived services here)
  produced exactly the same death, which is what isolated it to the request.
  Also not a real OOM — the 72 "OOM" matches in the log are all the warning's
  own text.
- **Made it worse**: symlinking the pip `nvidia-cuda-cccl-cu12` headers into
  `/usr/local/cuda/include/cccl` mixes two CCCL versions against the toolkit's
  own libcu++ and turns one missing-header error into a wall of macro errors
  (`_LIBCUDACXX_BEGIN_NAMESPACE_CUDA_PTX is undefined`, ...). Reverted. Do not
  retry this shortcut.
- **Fix**: not yet applied. Untried options, cheapest first: (1) find the vLLM
  0.18 switch that forces the plain-torch GDN path instead of flashinfer;
  (2) install the CCCL version that actually matches `/usr/local/cuda`, not the
  newest pip one; (3) move to a CUDA-13 box and use current vLLM as
  `training/README.md` assumes; (4) drop vLLM and serve through transformers
  behind an OpenAI-compatible shim.
- **Resolved by avoidance (2026-08-10)**: option (3) was taken and works —
  A100-80GB, driver 595.71.05 / CUDA 13.2, plain unpinned `uv pip install vllm`.
  The server survived its first request and a full smoke run. Two independent
  reasons it cannot recur there: the wheel is CUDA-13 so nothing JIT-compiles
  against a mismatched toolkit, and the GPU is SM80, so the `gdn_prefill_sm90`
  Hopper kernel is not the code path at all. **The CUDA-12 + Hopper combination
  is still unfixed** — this entry stays as the record of what to expect if a
  future box lands there, but it no longer blocks anything.

### WebArena eval needs `OPENAI_API_KEY`, and its hardcoded judge model no longer exists
- **Status**: fixed in repo (2026-08-11 09:37) — `eval_webarena.py` fails fast on a
  missing key, and `training/patch_webarena_judge.py` configures the judge on
  every box identically
- **Found**: 2026-08-10, user asked whether WebArena eval needs an OpenAI key —
  it does, and nothing in `training/README.md` or `eval_webarena.py` says so.
- **Where**: `webarena/evaluation_harness/helper_functions.py:162` (`llm_fuzzy_match`)
  and `:197` (`llm_ureader_eval`), reached from BrowserGym's `task.validate()`.
- **Symptom**: without `OPENAI_API_KEY`, `generate_from_openai_chat_completion`
  raises `ValueError`. BrowserGym's `validate()` catches only `AssertionError`,
  so it propagates to `run_task`'s broad `except` and the task is recorded as
  errored — a silent, guaranteed 0. **70 of the 655 single-site tasks** use
  `fuzzy_match`: reddit 2, gitlab 8, **shopping 34 (18%)**, **shopping_admin 26
  (14%)**. So a keyless run understates shopping/shopping_admin badly while
  barely touching reddit/gitlab.
- **Second failure, only visible once a key is set**: the judge model is
  hardcoded to `gpt-4-1106-preview`, which is deprecated —
  `404 model_not_found` on a current project key. Having a key is not enough.
- **Worked around**: `gpt-4-turbo` (the direct successor of that preview model,
  and available on the user's key) substituted at both call sites on the box.
  Verified directly: correct answer → 1.0, wrong answer → 0.0. **This is a
  deliberate deviation from the official evaluator and must be disclosed
  whenever these numbers are reported.**
- **Cost note**: `validate()` runs on *every step*, not once per episode, so a
  fuzzy task costs one judge call per step (~400-500 GPT-4-turbo calls for the
  70 tasks).
- **Repo fix not applied**: `eval_webarena.py` should fail fast when
  `OPENAI_API_KEY` is unset and the selected site has fuzzy_match tasks, rather
  than letting 10.7% of the benchmark silently error out.

### `eval_webarena.py`'s resume treats an errored task as done, so infrastructure blips become permanent zeros
- **Status**: fixed (2026-08-11 09:37) in `prune_errored()`
- **Found**: 2026-08-10, after restarting vLLM mid-sweep — 4 reddit tasks
  recorded `APIConnectionError` and would have been skipped forever.
- **Where**: `training/eval_webarena.py`, the `done` set built from
  `results.jsonl` (only `--no-resume` bypasses it, which redoes everything).
- **Symptom**: any task whose row carries an `error` field is treated as
  complete on the next run, permanently scoring 0 for a reason unrelated to the
  model.
- **Worked around**: a helper that drops errored rows (keeping a `.bak`) before
  restarting, run with the sweep stopped.
- **Fix**: not applied. Resume should skip only rows without an `error`.
- **Operational trap found alongside it**: `supervisorctl restart` kills the
  shell but not its already-running python child, so two eval processes end up
  appending to one `results.jsonl`. Fixed with `stopasgroup=true` /
  `killasgroup=true`. Also note `pkill -f "vllm serve"` / `pgrep -f
  "eval_webarena.py"` issued over ssh **matches the ssh command's own string and
  kills the session**; use a bracketed regex (`eval_webarena[.]py`).

### The model emits invalid JSON escapes, so the step is silently dropped
- **Status**: open
- **Found**: 2026-08-10, WebArena eval smoke run on shopping task 23.
- **Where**: model output; surfaces in `hsge/backends.py:142`
  (`OpenAILLM.complete_json`).
- **Symptom**: `[OpenAILLM] non-dict JSON response, returning {}` on output that
  *looks* well-formed:
  `{"thought": "...", "action": "click('12\xa0 Reviews')"}`. `complete_json`
  returns `{}`, the Solver gets no action, and the episode ends at that step
  (task 23 ended at 1 step). Observed in 1 of 12 smoke episodes (~8%), so it is
  not rare enough to ignore when reading success rates.
- **Cause**: the model copies a non-breaking space out of the axtree and escapes
  it Python-style as `\xa0`. JSON has no `\x` escape — only `\uXXXX` — so
  `json.loads` rejects the string, and the `\{.*\}` salvage regex re-parses the
  same invalid text. The log line is also misleading: it says "non-dict" for
  what is really "unparseable" (`parsed` is `None` on this path, not a list).
- **Fix**: not applied, deliberately. Making the parser lenient (e.g. escaping
  stray `\x` before `json.loads`) mid-eval would change the quantity being
  measured and break comparability with the existing gitlab base numbers. Do it
  before the *next* collection run, not between two runs being compared.

### `goal_task_selected` logs an empty `goal`
- **Status**: open
- **Found**: 2026-08-08, same audit — all 16 `goal_task_selected` events in
  `run_log.jsonl` carry `"goal": ""`.
- **Where**: `hsge/webarena/runtime.py`, `goal_task_selected` event emission.
- **Symptom**: GOAL selection cannot be traced from the log alone; the goal has to
  be recovered by joining against `episodes/*/episode_meta.json`.
- **Fix**: not yet applied.

### Predicate canonicalization never unifies synonyms, so the operator graph stays edgeless and no semantic task is ever generated
- **Status**: open, but **downgraded 2026-08-08 — the symptom is no longer zero.**
  `outputs/wa_eval_reddit` (158 nodes, 887 episodes) induced 4 operators whose
  predicate sets finally intersect: `p5 "a post listing page is shown"` is an
  effect of `attempt_to_find_comment_` AND a precondition of
  `apply_featured_filter` -> **1 edge**, 1 depth-chain, and GOAL
  **2 success / 4 fail / 1 infeasible** (first non-zero GOAL on a live site).
  The three thesis overstatements can now be reworded against real evidence,
  though "1 edge out of 4 operators" is still weak and 3/7 skills were rejected
  as tautological. Grounding stays shaky: `effect_confirmed` was 0.0 for
  `navigate_to_wiki`, 0.5 for two others, 1.0 for only one.
  Earlier status: the synonym-canonicalization fix **implemented +
  unit-tested (2026-07-22)** did NOT resolve the symptom. Two fresh live runs
  (wa_run_13_shopping, wa_run_14_reddit, 77/79 nodes, ~290 episodes each) still
  show **GOAL 0/0/0**. Re-analysis (2026-07-22) shows the root cause is a
  **three-stage loss cascade**, of which synonym-merging is only stage 3 and
  not the binding constraint. Stays open until a run produces non-zero GOAL.
- **Re-diagnosis (2026-07-22, runs 13/14)**: the cascade, measured directly:
  (1) **single-hop tasks** — `EXPLORER_SYS` asks for tasks doable on THIS page,
  so 104/221 (reddit) and 118/230 (shopping) success episodes are literally
  1 action (median 2 steps); atomic tasks → atomic skills.
  (2) **anti-tautology gate kills ~half the skills** — 4/7 (reddit), 3/5
  (shopping) admitted skills are rejected `operator_rejected reason=tautological`
  because an atomic skill's effect is phrased ≈ its precondition
  (`uncheck_checkbox`: pre "a checkbox exists" / eff "the checkbox is checked"
  → `eff-pre=∅`). So only 3/2 operators survive.
  (3) **effect/precondition vocabulary disjunction** — the survivors' effects
  are all page-state ("the wiki page is displayed") while preconditions are all
  element-presence ("a menu toggle is present"); `effects ∩ preconditions = ∅`
  in BOTH runs → 0 edges (operators.py:44 `A→B iff effects(A)&preconds(B)`)
  → `all_chains(min_len=2)` empty → 0 GOAL. Synonym canonicalization can't help
  here because eff/pre are different predicate *types*, not synonyms.
  Note canonicalization DOES work at the precondition level (reddit `p0` reused
  across two operators). Grounding `effect_accuracy` is often 0.5 (shaky
  predicate quality). Chosen fixes: **A** (multi-step task proposals, attacks
  stage 1 & 2) + **B** (align induced preconditions to page-state vocabulary,
  attacks stage 3).
- **Found**: 2026-07-20, while gathering Appendix C statistics for the thesis.
  Verified directly against `outputs/`: **0 of 1745 episodes** across all 12
  runs carry a `GOAL` tag, every `summary.json` shows
  `GOAL: {success: 0, fail: 0}`, and all 370 examples in
  `training/train_12.jsonl` come from low-level tasks.
- **Where**: `hsge/predicate_registry.py` + `run.predicate_sim` (0.6) in
  `config.yaml`; downstream effect in `hsge/operators.py::OperatorGraph.all_chains`
  and `hsge/webarena/runtime.py::_goal_tasks()`.
- **Symptom**: the operator graph is effectively edgeless, so
  `all_chains(min_len=2)` returns nothing and no composed GOAL task is ever
  attempted on a live site. The largest run (`wa_run_07`, 128 nodes, 13
  operators) has **exactly one** effect→precondition edge, and it only formed
  when the 13th and last operator was induced, after the run had been stopped.
- **Cause**: not a coding defect — embedding-only canonicalization cannot
  separate synonyms from near-neighbours at any single threshold. Measured on
  `wa_run_09`: a true synonym pair scored 0.570 while a false pair scored
  0.606, straddling the 0.6 threshold from both sides. Each operator therefore
  gets a private predicate vocabulary and nothing chains. The mechanism itself
  is implemented and passes the deterministic mock tests
  (`test_operators.py`, `test_goal_task.py`).
- **Fix (2026-08-08 17:17, three more attacks after the shopping_admin audit)**:
  the run showed the cascade's stage 2 and 3 both still live -- 3 of 6 skills
  rejected `tautological`, `skill_to_skill: {}`, and the 3 surviving operators
  all ungrounded (effect accuracy 0.5 / 0.0 / 0.5).
  (a) The anti-tautology gate and the page-state vocabulary pull against each
  other for a *page-local* skill (entry state == exit state), so
  `operator_induction._SYS` now requires the exit state to differ by naming the
  same page QUALIFIED by what the skill established ("on the product edit page"
  -> "...with a save confirmation"), forbidding both a bare repetition and an
  element-level fallback. NOTE: the initially proposed fix -- "forbid
  location-shaped predicates as effects" -- was wrong and would have removed the
  chaining mechanism itself.
  (b) `verify_operator_grounding` is now a GATE on effects
  (`_EFFECT_GROUNDING_MIN` 0.5), not a log line; an operator with no grounded
  effect is rejected `ungrounded`. Preconditions are scored but never dropped.
  (c) A self-declared infeasible retires a seed capability immediately
  (`_score_capability`), so a genuinely absent feature stops consuming GOAL
  budget. Tests: `hsge/tests/test_grounding_gate_and_capability_retire.py`.
  **Still open**: none of this is confirmed on a live run yet -- the same
  standard as the 2026-07-22 fix below, which was unit-tested and did not move
  the symptom.
- **Fix**: LLM adjudication in the borderline band (2026-07-22, unit-tested;
  see changelog). `PredicateRegistry` now takes an optional `llm` +
  `adjudication_band` (default 0.15): cosine decides the confident tails
  (`>= sim_threshold+band` merge, `< sim_threshold-band` new id) and
  `predicates_equivalent()` settles only the ambiguous middle where a single
  cutoff provably fails. `OnlineClusterer` gained `nearest`/`add_to`/`spawn`
  to let the registry interpose that decision; `partial_fit` composes them
  (unchanged). `runtime.py` wires `operator_llm` in; `llm=None` keeps the old
  deterministic single-threshold path for the mock pipeline. This also repairs
  the upstream vocabulary-aware induction that already existed: once two
  synonyms collapse, the id's count grows, it enters `vocabulary()`'s frequent
  set, and the inducer starts reusing it verbatim (virtuous cycle). **Still
  needs a real-run to confirm goal tasks actually appear** — do not reword the
  three thesis overstatements below until that run succeeds.
- **Thesis impact**: three places currently overstate this — the O2 rows in
  `Chapter1`/`Chapter6` and a sentence in `Chapter5` §5.1 claiming operator
  chaining "executed against a real website". Appendix C.3 already reports the
  0 honestly, so the book is internally inconsistent until either the re-run
  succeeds or those three are reworded. See `Thesis_report/memory/07-dan-y-chi-tiet.md`.

## Fixed

### `datasets/README.md` claimed the wrong file trained checkpoint-536
- **Status**: fixed (2026-08-13 21:55)
- **Found**: 2026-08-13, updating the root `README.md` to match the current
  source tree.
- **Where**: `datasets/README.md`.
- **Symptom**: the file asserted `datasets/train_all.jsonl` (3,751 examples,
  merged from an earlier per-domain collection round) "is what checkpoint-536
  was trained on". That contradicts the thesis's `tab:dataset` table, which
  reports checkpoint-536 as trained on 4,554 examples (4,288 train / 266 val)
  from the four official `wa_run_20_*` runs — the dataset actually shipped as
  `training_data/train.jsonl`/`val.jsonl`.
- **Cause**: `datasets/README.md` describes an earlier training round and was
  never updated after the final `wa_run_20_*` collection + `training_data/`
  export superseded it; the checkpoint step number (536) coincidentally
  recurred across the two rounds, making the stale claim look plausible.
- **Fix**: `datasets/README.md` now states the correction explicitly (with
  date) and points to `training_data/` as the dataset behind the current
  result; the old per-file numbers are kept, relabeled as "an earlier
  collection round, superseded". `training/README.md` was not audited for
  the same stale claim — out of scope of this fix, flagged for a follow-up.

### The train/val split is trajectory-level, so 52% of val trajectories share a goal with train
- **Status**: fixed (2026-08-11 03:32)
- **Found**: 2026-08-11, auditing `training_data/{train,val}.jsonl` (built from
  `outputs/wa_run_20_*`).
- **Where**: `training/prepare_dataset.py` (group-by-`trajectory_id` split).
- **Symptom**: 29 of 56 val trajectories (124 of 249 val examples, 50%) carry a
  goal string that also appears verbatim in `train.jsonl`. `eval_loss` is
  therefore optimistic, and it is the number the last run used to pick
  `checkout-446` (epoch 2) over epoch 3 — that choice rests on a leaky signal.
- **Cause**: the split groups by `trajectory_id` so the *same trajectory* never
  straddles the split, which is correct but insufficient: `unprefixed_sampling`
  gives most solved tasks **two** trajectories with the same goal (one `LOCAL`,
  one `UNPREFIXED`), and the random trajectory-level split puts one in train and
  the other in val. 357 of the 367 repeated-goal groups in the pool are exactly
  such a pair, so this is the dominant mechanism, not incidental duplication.
- **Fix**: `training/prepare_dataset.py` now groups trajectories by
  `(site, goal)` — the goal read back out of the prompt's `# Goal` block, so no
  `episodes/` dir is needed — and holds out whole task groups. It asserts no val
  goal appears in train before writing, so a regression fails loudly. Legacy
  exports whose prompt uses the old `GOAL: ...` format fall back to
  `trajectory_id` (verified on `train_all.jsonl` and `training/train_12.jsonl`)
  instead of collapsing into one group. `training_data/{train,val}.jsonl` and
  `training/data/all/` regenerated: 4585 train / 243 val, 52 val trajectories /
  31 tasks, **0 goals shared** (was 29 of 56), all 4 sites still present in val.
  Re-running reproduces the split byte-identically.
  New test: `hsge/tests/test_prepare_dataset_split.py`.


### The Solver's three anti-loop guards are blind to FAILED actions, so a dead element eats the whole step budget
- **Status**: fixed (2026-08-10 04:03)
- **Found**: 2026-08-10, analysing `outputs/wa_eval_shopping_1` (shopping,
  179 nodes, 1069 episodes, 9065 steps).
- **Where**: `hsge/webarena/agents.py` — `Solver.solve()`, the
  `except Exception` branch around `browser.act(action)`.
- **Symptom**: 4115 of 9065 steps (45.4%) ended in an action error, 3305 of
  them a Playwright `Timeout 500ms exceeded` on click/select_option. 118
  episodes spent ALL 15 steps issuing the *same* failing action against the
  *same* bid (e.g. `click('229')` on `link 'My Wish List'`, 15x). Those
  episodes then hit the budget guard and the wrap-up call rationalised a
  `report_infeasible('action budget exhausted, ...')` — 199 of the run's 222
  infeasible episodes have a non-empty `stop_reason`. Failure/infeasible
  episodes hold 85% of all steps in the run.
- **Cause**: on `ActionError` the code appends the error to the step's thought
  and `continue`s *before* `history.append(action)`, so the failed action never
  enters `history` / `outcomes` / `progressed` / `seen_obs`. `_stuck_streak`
  (same-target, no-progress) and the C3 novelty guard both read exactly those
  lists, so neither can ever see a repeated *failing* action. Only the budget
  guard can stop such an episode, and it does so after burning the full budget.
- **Fix**: the `except` branch now appends the action to `history`, a
  `failed_outcome(err)` line to `outcomes`, `False` to `progressed` and bumps
  `novelty_streak`, so `stuck` fires after 4 repeats and `novelty` after 8.
  `build_sft_dataset.py` reproduces the same history line (shared helper) so
  the offline prompt still matches the live one. Regression tests:
  `hsge/tests/test_failed_action_guards.py`.

### `scroll` / `hover` are executable but undocumented, so the model never uses them
- **Status**: fixed (2026-08-10 04:03)
- **Found**: 2026-08-10, same run analysis.
- **Where**: `hsge/webarena/agents.py::ACTIONS_DOC`; subsets are enabled in
  `hsge/webarena/browser.py` (`HighLevelActionSet(subsets=[..., "bid", ...])`).
- **Symptom**: 2828 `Locator.click: Timeout 500ms exceeded` errors — the
  element is in the (visible-filtered) axtree but not actionable within
  BrowserGym's hardcoded 500 ms element timeout.
- **Cause**: browsergym's `bid` subset already contains `scroll`, `hover`,
  `noop`, so the executor accepts them, but `ACTIONS_DOC` lists only 10 actions
  and omits all three, so the LLM never emits them and has no way to make an
  element actionable. Go-Browse's action space (Table 6) includes all three.
- **Fix**: `ACTIONS_DOC` documents `scroll(0, 400)`, `hover('bid')` and
  `noop(500)`, plus explicit guidance that a Timeout means the element is not
  clickable *yet* and re-clicking it will time out again.

### The SFT pipeline distills the collection solver's *failures*: `--require-judge` selects for what gpt-4o-mini could finish, and admits its unverified give-ups
- **Status**: fixed at the curation layer (2026-08-10 03:40); the collection
  layer (F3) is **not** fixed — see "Still open" below.
- **Found**: 2026-08-10, root-causing the cross-domain LoRA's **0/57 reddit**
  score on the live WebArena benchmark.
- **Where**: `build_sft_dataset.py::_include_episode` (the infeasible
  short-circuit) and `episode_to_examples`; upstream cause in the
  `page_explorer`/`solver` model split in `config.yaml`.
- **Symptom**: the fine-tuned model reports infeasible on **22/57 (39%)** of
  reddit eval tasks, 15 self-decided, on tasks verified to be feasible (three
  "change my bio" tasks; the edit link is present at bid 155). 10/57 end in an
  off-site `goto('https://www.reddit.com/...')`, which BrowserGym terminates at
  reward 0. 9/57 hit the stuck guard repeating a dead action.
- **Cause — a four-stage funnel, measured on the four collection runs**:
  1. `EXPLORER_SYS` is **not** at fault: it demands COMPOSITE tasks first and
     they are 1218/3241 (38%) of episodes, median **15 steps**.
  2. The collection solver (gpt-4o-mini) cannot execute them: COMPOSITE is 79%
     fail+infeasible and only **9.5%** judge-passes, versus **58%** for INFO
     (median 1 step).
  3. `--require-judge` is individually correct but, as a filter, keeps exactly
     the subset the teacher could finish — so the dataset became 42% one-step
     trajectories, median length 2, and COMPOSITE's median fell 15 → 5.
  4. The infeasible branch short-circuited **above** the judge check, and
     `judge_episodes.py` never judges infeasible episodes, so 136 unverified
     give-ups (868 examples, **23%** of the dataset) entered — concentrated on
     the hard class: **75 of 191 COMPOSITE trajectories (39%)**, matching the
     model's 39% eval give-up rate. Their reasons are collection-time
     artifacts, not impossibility ("Too many failed login attempts",
     "askscience forum not found" on a site that has one).
  Also found: `episode_to_examples` never emitted the live Solver's
  `LAST ACTION ERROR:` block (agents.py:562), so the step *after* a failed
  action was trained without the evidence that motivated it — an unexplained
  action change instead of error recovery.
- **Fix (curation layer)**: (a) `--require-judge` now holds infeasible episodes
  to the same bar it documents for successes ("never judged is dropped, not
  silently trusted"); without the flag the old permissive behavior stands.
  (b) a `goto` to a host other than the current page's is excluded as a target
  (kept in history — it did execute). (c) the `LAST ACTION ERROR:` block is
  reconstructed from the errored step's `[action error: ...]` thought and
  placed where the live Solver puts it. Tests in
  `hsge/tests/test_build_sft_dataset.py` (7 new; suite 249 → 266).
- **Measured effect of the rebuild** (`--require-judge --min-actions 1`,
  3751 → 2399 examples): 1-step trajectories **42% → 1%**, `report_infeasible`
  terminals **11% → 0%**, median trajectory length 2 → 3, p90 8 → 10, `click`
  share 51% → 66%, off-origin `goto` targets 5 → 0, recovery examples carrying
  the error block 0 → 154.
- **Still open (F3, the actual root cause)**: curation cannot manufacture
  successful long trajectories — COMPOSITE's share still *fell* (29% → 26%) in
  the rebuild, because removing the give-ups removed long episodes. Until the
  collection solver can finish multi-step tasks (a stronger model on
  COMPOSITE/MOD, or subgoal-guided solving), the training distribution stays
  systematically easier than the benchmark. Retraining on V2 measures how much
  of the 0% is curation vs. teacher competence; it is not expected to close it.

### `eval_webarena.py` unpacks 6 values from `Solver.solve()`, which returns 7 — every eval episode errors out
- **Status**: fixed (2026-08-10 01:35)
- **Found**: 2026-08-10, first-ever run of the WebArena eval on a live site
  (reddit smoke, 3 tasks): all 3 came back
  `ERR ... ValueError: too many values to unpack (expected 6)`.
- **Where**: `training/eval_webarena.py:144`.
- **Symptom**: every episode reported `reward=0.0`, `steps=-`, `success=false`.
  Silently catastrophic rather than loud: the exception is raised *after* the
  Solver has done all its work, and `run_task`'s broad `except` turns it into an
  ordinary failed-task record, so an unattended full sweep would have produced a
  plausible-looking `summary.json` reading **0.0% on every site**.
- **Cause**: the 2026-08-08 03:08 change added `stop_reason` as `solve()`'s 7th
  return value and updated `runtime.py` plus all 30-odd test call sites, but
  `training/eval_webarena.py` is the only non-test caller outside `hsge/` and was
  missed. The eval had not been run since, so nothing caught it.
- **Fix**: unpack 7 values, and persist `stop_reason` into `results.jsonl`
  (it is exactly the diagnostic you want when reading a failed eval episode:
  `""` = the model chose to stop, else `budget`/`stuck`/`novelty`). Verified by
  re-running the same 3 reddit tasks: episodes now complete and score, with
  `stop_reason` populated (`stuck`, `budget`, `stuck`).

### LoRA merge with `AutoModelForCausalLM` silently strips Qwen3.5's vision tower, and vLLM then refuses the checkpoint
- **Status**: fixed (2026-08-10 01:05)
- **Found**: 2026-08-10, merging the cross-domain adapter with peft on the new
  eval box instead of `llamafactory-cli export` (this box has no LLaMA-Factory
  install — it only evaluates).
- **Where**: the merge script, not repo code at the time. Surfaces at vLLM
  startup in `vllm/multimodal/processing/context.py`.
- **Symptom**: `TypeError: Invalid type of HuggingFace config. Expected type:
  Qwen3_5Config, but found type: Qwen3_5TextConfig`. The merge itself reported
  success.
- **Cause**: Qwen3.5-9B is `Qwen3_5ForConditionalGeneration` (text tower +
  vision tower). `AutoModelForCausalLM.from_pretrained` loads only the text
  tower, and saving that back out writes a `Qwen3_5TextConfig` with the 348
  vision tensors dropped — 775 → 427 tensors, with no warning.
- **Fix**: load with `AutoModelForImageTextToText` instead. Two assertions were
  added so this fails at merge time rather than 10 minutes into a vLLM startup:
  the output config must be `Qwen3_5ForConditionalGeneration` with both
  `text_config` and `vision_config`, and the tensor count must match the base.
  **The tensor-count assert has one legitimate exception**: the 15 `mtp.*`
  tensors (the multi-token-prediction speculative-decoding head) are always
  dropped, because `transformers` does not model them — harmless unless MTP
  speculative decoding is enabled, which `serve_vllm.sh` does not do.
- **Related trap worth keeping**: `adapter_config.json`'s `target_modules` are
  bare suffixes (`q_proj`, `o_proj`, ...), which could also match same-named
  modules in the vision tower — those have no saved weights and peft would
  randomly initialize them without complaint. The merge script now asserts every
  attached LoRA site is backed by a tensor in `adapter_model.safetensors`
  (248 sites, all backed, for this adapter).

### `vast_setup.sh` builds venvs that cannot see the GPU (and a training path that aborts on Hopper)
- **Status**: fixed (2026-08-09 19:15)
- **Found**: 2026-08-09, first real use of `training/vast_setup.sh` on a rented
  vast.ai H100-80GB box (driver 560.35.03 = CUDA 12.6). Stage `train_venv`
  failed outright; the other three stages "succeeded" but were also broken.
- **Where**: `training/vast_setup.sh` — `setup_train()` and `setup_serve()`.
- **Symptom**: four separate failures, each masking the next:
  1. `assert torch.cuda.is_available()` fails — `no CUDA`.
  2. After pinning torch, `llamafactory-cli` dies at import:
     `OSError: Could not load this library: .../torchaudio/lib/_torchaudio.abi3.so`.
  3. After that, `llamafactory-cli` dies on
     `ImportError: transformers>=4.55.0,<=5.8.0 ... but found transformers==5.15.0.dev0`.
  4. Training then aborts at step 0 with `RuntimeError: Triton >= 3.4.0 and
     < 3.7.1 on Hopper GPUs produces incorrect results for gated chunk_bwd_dqkwg`.
  5. vLLM (step 5 of the README) would have failed too: the serve venv held
     `nvidia-cuda-runtime==13.0.96`.
- **Cause**: the script never pins a CUDA build. `uv` resolves the newest PyPI
  wheels, which are now CUDA 13: torch 2.13.0+cu130 needs a CUDA 13 driver, so a
  12.x box reports no GPU at all. The follow-on failures are the same root cause
  in different disguises — pinning only `torch` leaves `torchaudio` on its cu130
  wheel (ABI mismatch at load time), and downgrading torch to 2.11 drags triton
  down to 3.6.0, which flash-linear-attention refuses to use on Hopper rather
  than emit silently-wrong Gated DeltaNet gradients (fla issue #640). Separately,
  the `transformers @ main` line was stale: it predates Qwen3.5 landing in a
  released transformers (5.8.0 has `models/qwen3_5`), and main (5.15.0.dev0) now
  violates LLaMA-Factory's own `transformers<=5.8.0` gate. For vLLM, swapping
  torch is not enough — vLLM ships its own compiled kernels, so the wheel's CUDA
  major is what matters.
- **Fix**: `setup_train()` pins `torch==2.11.0` + `torchvision` +
  `torchaudio==2.11.0+cu128` from the cu128 index (cu12.8 runs on both 12.x
  drivers via minor-version compatibility and 13.x drivers via backward
  compatibility), drops the `transformers @ main` install, and adds `tilelang`.
  `setup_serve()` pins `vllm==0.18.0` and asserts both `torch.cuda.is_available()`
  and `Qwen3_5ForConditionalGeneration in ModelRegistry.get_supported_archs()`.
  The usable vLLM window on a CUDA-12 box is narrow and was measured, not
  guessed: 0.14.0 is cu12 but knows only `Qwen3Next`; **0.18.0 is cu12 (torch
  2.10.0+cu128) and does register Qwen3.5**; 0.20.0+ moved to CUDA 13. On a
  CUDA-13 box plain `-U vllm` is fine.
- **Note**: triton 3.7.1 was installed on the box as an alternative to tilelang
  and measured at the same step time (~26-29 s/it either way), so the fla backend
  is not what makes this model slow — see the changelog entry for the throughput
  analysis.

### `infeasible` conflates "impossible" with "out of steps", and a state-changing task can succeed without changing anything
- **Status**: fixed (2026-08-08 17:09)
- **Found**: 2026-08-08, auditing `outputs/wa_eval_shopping_admin` (222 episodes).
  27 of 56 infeasible episodes have `step_count` exactly at the budget (16);
  `[MOD] Send an email confirmation for order #000000299` is a one-step success
  whose only action is `send_msg_to_user('done: The order confirmation email was
  already sent.')`.
- **Where**: `hsge/webarena/agents.py::Solver.solve` (wrap-up block + the
  non-predicate success rule), `hsge/webarena/runtime.py::_record`,
  `build_sft_dataset.py::_include_episode`.
- **Symptom**: (a) the wrap-up call fires *because* a guard or the budget stopped
  the episode and is told so; whatever it then declares is a rationalization, not
  a conclusion. Those `report_infeasible` episodes were kept as SFT targets,
  teaching the model to give up. (b) a MOD/COMPOSITE task the model declared done
  counted as a success even when no action ever touched the page.
- **Cause**: `stop_reason` was computed (2026-08-08 04:31) only to make the
  wrap-up *prompt* honest; it was never returned or persisted, so no consumer
  could tell a wrap-up verdict from a self-decided one. And the non-predicate
  success rule was purely "the last action is send_msg_to_user", with no evidence
  requirement for tasks whose whole point is to change the site.
- **Fix**: `Solver.solve` returns a 7th value `stop_reason` (`""` = self-decided,
  else `budget`/`stuck`/`novelty`); `_record` writes `outcome.stop_reason`;
  `_include_episode` accepts an infeasible episode only when it is empty
  (pre-existing episodes lack the key and default to self-decided, since nothing
  can distinguish them retroactively). A `[MOD]`/`[COMPOSITE]` goal additionally
  requires one executed action that changed url or axtree. Measured on the real
  run the second gate demotes 1 of 33 MOD/COMPOSITE successes -- the rest of the
  inflation came from failing actions that silently no-op'd, which the
  `ActionError` fix above addresses instead. Tests:
  `hsge/tests/test_honest_outcomes.py`. Suite 241 -> 249.

### `WebArenaBrowser.act` never sees a failed action — BrowserGym swallows it into `last_action_error`
- **Status**: fixed (2026-08-08 17:12)
- **Found**: 2026-08-08, auditing `outputs/wa_eval_shopping_admin` (222 episodes).
  **Zero** episodes out of 222 contain the `[action error:` marker, even though
  70/1683 steps (4.2%) call `fill()`/`click()` with a field *label* instead of a
  bid (`fill('[global] Price * $', '19.99')`, `fill('[store view] Product Name *',
  ...)`, `fill('123 New Street', '789 New Ave')`).
- **Where**: `hsge/webarena/browser.py::WebArenaBrowser.act` (line ~104);
  consumers `hsge/webarena/agents.py:569-572` (`except Exception` /
  `last_error`) and `build_sft_dataset.py` (its `[action error:` filter).
- **Symptom**: an action that fails in the browser is reported to the Solver as a
  normal successful step. The Solver's error-recovery feedback
  (`LAST ACTION ERROR: ...` in the prompt) is dead code — `last_error` is always
  `""`. `build_sft_dataset.py`'s `[action error:` exclusion never fires, so
  **failed actions are exported as correct SFT targets**. 18/222 episodes contain
  at least one invalid bid and 6 of those are marked `success`.
- **Cause**: `browsergym.core.env.BrowserEnv.step` catches the action exception
  itself (`self.last_action_error = f"{type(e).__name__}: {e}"`, env.py:405-407)
  and returns it as the `last_action_error` observation key. It never raises, so
  HSGE's `try/except Exception` around `browser.act()` can never trigger.
- **Fix**: `hsge/webarena/browser.py` — new `ActionError`; `act()` reads
  `obs["last_action_error"]` and raises it (after updating `_last_obs`/
  `terminated`, so a caller that catches stays consistent). `Solver`'s existing
  `except Exception` now fires, so `last_error` populates the `LAST ACTION ERROR`
  prompt block and `[action error:` lands in `obs_summary` as designed. Tests:
  `hsge/tests/test_action_error_and_thought_fidelity.py`.

### Persisted `thought` is truncated at 100 characters, mid-word
- **Status**: fixed (2026-08-08 17:12)
- **Found**: 2026-08-08, same audit — 694/1683 steps (41.2%) have a `thought`
  sitting exactly at the 100-char ceiling, cut mid-word ("...as indicated by the
  message on th").
- **Where**: `hsge/webarena/agents.py:557` (`Step(..., obs_summary=thought[:100])`),
  persisted by `hsge/webarena/runtime.py:301-302` as both `action.thought` and
  the top-level `thought` field.
- **Symptom**: `thought` is the SFT training target's reasoning; 41% of examples
  train the model to emit a sentence that stops mid-word. Also degrades
  `reannotate_thoughts.py`'s input and segmentation's `obs_summary` signal.
- **Cause**: `obs_summary` was originally a short display summary; it later became
  the persisted training target without the truncation being revisited.
- **Fix**: `hsge/webarena/agents.py` — `Step(..., obs_summary=thought)` (both the
  main loop and the wrap-up step). The 100-char cap moved to the only consumer
  that needs it, `hsge/segmentation.py:99` (`st.obs_summary[:100]`), so that
  prompt's size is unchanged.

### `outcome.response` is always empty — INFO answers are never captured
- **Status**: fixed (2026-08-08 17:12)
- **Found**: 2026-08-08, same audit — 0/222 episodes have a non-empty
  `outcome.response`, although 44 successes are single-step
  `send_msg_to_user('done: Lifetime Sales value is $194.40')`.
- **Where**: `hsge/webarena/runtime.py` episode-meta assembly.
- **Symptom**: the answer text an INFO task produced only exists inside the raw
  `parsed_action` string. `judge_episodes.py` cannot check the answer against the
  page without re-parsing, and no eval can score INFO correctness.
- **Fix**: new `hsge/webarena/agents.py::terminal_message(action)` (ast-parses the
  argument of a terminal `send_msg_to_user`/`report_infeasible`, `""` otherwise);
  `runtime.py::_record` fills `outcome.response` from the last step. Derived at
  the record site rather than threaded through `Solver.solve`'s return tuple, so
  every call site benefits.

### Wrap-up prompt claims "action budget is exhausted" after a guard stop, so report_infeasible records a false reason
- **Status**: fixed (2026-08-08 04:31)
- **Found**: 2026-08-08, evaluating `outputs/wa_eval_shopping_admin` — episodes that ran only 5-6 steps recorded `report_infeasible('action budget exhausted, cannot uncheck the checkbox')` while `max_steps=15` and `goal_max_steps=25`.
- **Where**: `hsge/webarena/agents.py::Solver.solve` wrap-up prompt.
- **Symptom**: the recorded infeasible reason is wrong whenever the same-target stuck guard (`_MAX_REPEATS`) or the novelty guard (`_NOVELTY_MAX`) ended the episode — which is most short infeasible episodes. Pollutes failure analysis (can't separate "ran out of steps" from "got stuck") AND the SFT data, since infeasible episodes are kept as training targets: the model is taught to plead budget exhaustion when that is not what happened.
- **Cause**: the prompt hardcoded one sentence for every exit path; the model faithfully repeats whatever the prompt asserts.
- **Fix**: `stop_reason` (`budget`/`stuck`/`novelty`) is tracked at each exit and rendered from `Solver._STOP_REASONS`; the prompt also now asks for "the REAL obstacle, not the fact that you stopped". Tests in `test_stop_reason_and_capability_retire.py`.

### Seed capabilities are retried up to the repeat cap even when every attempt fails
- **Status**: fixed (2026-08-08 04:31)
- **Found**: 2026-08-08, same run — "Review recent orders and update the status of an order to 'Shipped'" ran 3 times (ep_0009/0015/0026), all infeasible, consuming 3 of the run's GOAL slots.
- **Where**: `hsge/webarena/runtime.py::_goal_task` — introduced by the 2026-08-08 03:08 `seed_capability_repeats` fix.
- **Symptom**: a capability beyond the solver's ability spends its whole repeat budget on identical failures.
- **Cause**: `_capability_attempts` counted attempts but never looked at outcomes.
- **Fix**: `_capability_failures` retires a capability after `_CAPABILITY_MAX_FAILS = 2` *consecutive* failures (a success resets it). Seed tasks now carry their `capability` name so the GOAL result loop can score them; the counter is checkpointed for `--resume`.

### Five data-quality defects found by auditing the wa_eval_reddit run (frontier flooding, GOAL starvation, INFO flood, unrunnable SkillCards, vacuous `verified`)
- **Status**: fixed (2026-08-08 03:08) — all five; each has a regression test in `hsge/tests/test_run_quality_fixes.py`.
- **Found**: 2026-08-08, auditing `outputs/wa_eval_reddit` (158 nodes, 887 episodes) before building an SFT dataset from it.
- **Where**: `hsge/webarena/runtime.py` (frontier pop-time cap, `_goal_task`), `hsge/webarena/agents.py::PageExplorer` (tag caps), `hsge/abstraction.py::_SYS`, `hsge/verification.py::verify_skill`, `build_sft_dataset.py`.
- **Symptoms, measured**:
  1. **Frontier flooding** — 58/158 nodes were `/f/AskReddit/*/*/*/*`; two forums accounted for 47% of the whole run, despite `per_template_cap: 3`.
  2. **GOAL starvation** — 7 GOAL tasks total (6 seed + 1 depth chain) across 158 nodes, none after node ~3.
  3. **INFO flood** — INFO was 272/560 (49%) of successful episodes, and 237 of those had ZERO browser actions (only `send_msg_to_user`). 44% of all successes were answer-only; 60% had <= 1 real action.
  4. **Unrunnable SkillCards** — `click({sel})` (unquoted), `fill('{{text}}', '')` (arguments swapped), `press('{{btn}}')` (one arg where two are needed), CSS-selector slot examples (`#notification-bell`) for a bid-only action space.
  5. **Vacuous `verified`** — every skill in `skills.json` was `"verified": true` next to `"n_verify_attempts": 0`.
- **Causes**: (1) the cap was written `if tier == 1 and ...`, exempting tier-0 — which is also the highest-priority tier, so solving one task inside a thread pushed every comment URL it touched ahead of the entire frontier. (2) `_attempted_capabilities` was a set of bare capability names, blocking a capability for the rest of the run after one attempt. (3) `_INFO_RESERVE` only bounds INFO inside the `len(parsed) > max_tasks` overflow branch, so a page proposing <= max_tasks tasks was never truncated at all. (4) the abstraction prompt passed only bare action verbs and never described the action space. (5) `successes >= k` is vacuously true at `k=0`, which is what the WebArena runtime passes (it verifies by terminal episode outcome instead).
- **Fixes**: (1) `reached_template_cap` (default 8) applied to tier 0 by the same lazy pop-time check — still looser than the mined cap, since reaching a page while solving is evidence it matters. (2) capabilities keyed `(name, url_template)` plus a `seed_capability_repeats` global cap (default 3). (3) unconditional `_INFO_CAP = 2`, mirroring the existing `_NAV_CAP`. (4) `_SYS` documents each action's exact arity and that elements are addressed by BID, never CSS/XPath; payload gained `example_actions` (members' literal action strings). (5) admission decision unchanged, but `.verified` now additionally requires `n_verify_attempts > 0`. Also `build_sft_dataset.py --min-actions N` (default 0, old behavior) to drop answer-only episodes.
- **Note**: `--min-actions 1` on the real reddit data drops 249 episodes (34%) but only 6.6% of examples (3767 -> 3518) — the dropped episodes were one step each, so the trade is heavily favourable.
- **Related, still open**: an LLM exception during a task still kills the whole run (see the API-timeout entry below).

### Every GOAL task stalls ~12 minutes then can kill the run (60s API timeout x the SDK's hidden retries, vs a reasoning goal-solver)
- **Status**: fixed (2026-08-07 17:22)
- **Found**: 2026-08-07, first 4-domain eval collection run — `outputs/wa_eval_shopping` produced 3 LOCAL episodes then froze with no file activity for 13 min, printing only `[OpenAILLM] retry 1/3` and `2/3 after APITimeoutError`. The reddit run in parallel was fine (13 episodes, 0 retries) — it had not reached a GOAL task yet.
- **Where**: `hsge/backends.py::OpenAILLM.__init__` (`_REQUEST_TIMEOUT_S`, missing `max_retries`).
- **Symptom**: the first GOAL task of a run hangs ~12 min, then raises `APITimeoutError`. That exception is not caught per-task (only browser errors get `node_error` + skip), so it propagates to the whole-loop handler, writes `run_error`, and re-raises — killing a long unattended run.
- **Cause**: `_REQUEST_TIMEOUT_S = 60.0` is below what `solver_goal: gpt-5.6-terra` needs — a non-streaming reasoning call over a 6000-char axtree + screenshot routinely takes longer. Compounding it, `OpenAI()` was constructed without `max_retries`, so the SDK's default 2 internal retries tripled each of `_create_with_retry`'s 4 attempts: 4 x 3 x 60s ~ 12 min of silent blocking. `sample <pid>` confirmed the stack (`_ssl__SSLSocket_read -> PySSL_select -> poll`), and `/v1/models` confirmed `gpt-5.6-terra` is present on the account — slowness, not a bad model id.
- **Fix**: `_REQUEST_TIMEOUT_S` 60 -> 180s, and `max_retries=0` on the client so this class's own logged, transient-only backoff loop is the single retry policy (worst case 4 x 180s, and every wait is now logged instead of hidden inside the SDK).
- **Note (still open, separate)**: an LLM exception during a task still kills the whole run rather than failing just that task. `--resume` recovers, but a per-task guard like the existing `node_error` one would be more robust for long unattended runs.

### Real run crashes on GPT-5.x/o-series models that reject a custom temperature
- **Status**: fixed (2026-07-31 23:10)
- **Found**: 2026-07-31, first real run with `solver_goal: gpt-5.6-terra` — `openai.BadRequestError 400: "Unsupported value: 'temperature' does not support 0.0 with this model. Only the default (1) value is supported."` (`run_webarena.py` → `Solver.solve` → `OpenAILLM.complete_json`).
- **Where**: `hsge/backends.py::OpenAILLM.complete_json` / `_create_with_retry` (always sent `temperature`).
- **Symptom**: any GPT-5.x / o-series model 400s when given a non-default temperature (the whole run aborts), because `config.yaml` set `solver_goal.temperature: 0.0`.
- **Cause**: those models only accept the default temperature (1); the backend unconditionally passed the configured value.
- **Fix**: `OpenAILLM` now (a) catches the temperature-specific 400, drops the param, retries, and sets `self._omit_temperature` so later calls skip it (`_is_unsupported_temperature`); and (b) `complete_json` omits `temperature` once flagged. Also set `config.yaml` `solver_goal.temperature: 1` to avoid the first wasted 400. Tests in `hsge/tests/test_backends_temperature.py`.

### C2 subgoal-advance signal is hijacked into send_msg_to_user, ending the episode at subgoal 1
- **Status**: fixed (2026-07-31 19:58, commit 685a93b)
- **Found**: 2026-07-31, run v3 (`outputs/wa_seed_shopping_v3`) GOAL dropped to 0 success / 4 fail / 2 infeasible (v2 was 2/0/4); 3/6 GOAL episodes ended after 2-3 steps.
- **Where**: `hsge/webarena/agents.py::Solver.solve` subgoal-mode advance.
- **Symptom**: gpt-4o-mini emitted the advance as a **terminal** `send_msg_to_user('subgoal_done...')` instead of the JSON field, so `solve` ended the episode after subgoal 1; the B1 verifier correctly FAILed it ("navigated to Electronics but did not add to cart"). The 2 easy nav/read goals that PASSED in v2 were the ones killed.
- **Cause**: the `subgoal_done` JSON field is unreliable with gpt-4o-mini, which conflates "advance subgoal" with the send_msg terminal action.
- **Fix**: a `send_msg_to_user` (or a `subgoal_done` field) on a NON-last subgoal now ADVANCES instead of terminating; only the last subgoal may end the episode. Regression test `test_send_msg_on_nonlast_subgoal_advances_not_terminates`.

### C3 stuck/novelty guards miss same-target churn that only wiggles the axtree
- **Status**: fixed (2026-07-31 19:58, commit 685a93b)
- **Found**: 2026-07-31, run v3: `click('247')` ×9, `click('1790')` ×8 burned ~10-19 steps.
- **Where**: `hsge/webarena/agents.py::Solver.solve` (`progressed` fed to `_stuck_streak`).
- **Symptom**: hammering one control never tripped the same-target stuck guard, because each click wiggled the axtree (dropdown/toggle) and the guard's "progress" = url-OR-axtree change reset the streak.
- **Cause**: keying progress on axtree changes too; a slightly-mutating page defeats it.
- **Fix**: the same-target stuck guard now keys "progress" on **URL change only** — a legit multi-step flow uses different targets (so the same-target guard never groups it) or changes the URL, so this is safe. Regression test `test_stuck_guard_fires_on_same_target_when_url_does_not_change`. (The different-target-no-new-page case is still handled by the exact-obs novelty guard; a slightly-mutating different-target churn remains a minor known gap.)

### Frontier re-explores the same landed page under different URL strings (URL dedup keyed the pre-navigation frontier string, not the page actually loaded)
- **Status**: fixed (2026-07-22 13:59)
- **Found**: 2026-07-22, auditing whether already-explored URLs (esp. root) get re-explored.
- **Where**: `hsge/webarena/runtime.py::run()` — `visited`/`queued` dedup on the
  frontier `url` (pre-navigation mined/reached string) and `_admit_url`, while the
  node is logged and content-compared by `obs["url"]` (the POST-navigation landed
  URL). `_url_template` normalization was used only for the tier-1 per-template cap.
- **Symptom**: the same logical page fully re-explored (new explorer+solver LLM
  batch, not skipped) when reached via a different frontier string. Confirmed on
  run 13: `checkout/cart/#payment` explored **twice** (depths 3 and 4);
  `electronics.html` **18×** / `sports-outdoors.html` **11×** across `?cat=`/`?price=`
  variants. Root was at latent risk (its front page is the most dynamic, so the
  content-hash backstop is least reliable there).
- **Cause**: URL identity for dedup was the pre-navigation frontier key, but many
  distinct keys resolve to the same page after navigation (`#fragment`,
  trailing-slash/case, redirects, login redirects). The only backstop was
  `seen_content` (sha256 of the initial axtree), which fails whenever the page
  content differs even slightly between visits (dynamic content). Two compounding
  gaps: (a) no normalization of the dedup key; (b) no dedup on the actual landed
  `obs["url"]`, so a redirect/alias to an already-visited page slipped through
  whenever the content-hash also differed.
- **Fix**: added `WebArenaExplorer._norm_url` (strips `#fragment`, lowercases
  scheme+host, drops a non-root trailing `/`, KEEPS the query since `?cat=1`≠`?cat=2`)
  and keyed `visited`/`queued`/`_admit_url` by it (part 1). Added a `visited_landed`
  set of normalized POST-navigation urls, checked alongside the content-hash in the
  duplicate-skip block, so a redirect/alias to an already-loaded page is skipped even
  when its content changed (part 2). `visited_landed` is checkpointed/restored (kept
  out of `_LOOP_KEYS`; `load_checkpoint` defaults it via `.get` for back-compat with
  older checkpoints). Regression tests in `hsge/tests/test_frontier_mining.py`:
  `_norm_url` canonicalization, `_admit_url` rejecting a fragment/slash variant of a
  visited url, and an end-to-end redirect browser proving the second route to a
  canonical page is skipped (RED before the fix). Full suite 157 -> 160 passed.
  **Not fixed (separate design question):** query-string / tier-0 proliferation
  (`electronics.html`×18) — different `?cat=` pages are genuinely different content,
  so whether to cap them is a coverage-vs-cost decision left open.

### Windows run crashes writing an axtree with non-cp1252 characters (UnicodeEncodeError)
- **Status**: fixed (2026-07-22 09:10)
- **Found**: 2026-07-22, a real run on a Windows machine (`D:\...\hsge`,
  conda env, cp1252 locale) crashed at node 3 with
  `UnicodeEncodeError: 'charmap' codec can't encode character '↓'`
  (a `↓` down-arrow in the page's accessibility tree).
- **Where**: `hsge/webarena/runtime.py::_record` line ~213 (the axtree
  `page_state/step_*.txt` write) plus every other text-mode `open()` in the
  pipeline (episode/artifact writes in `runtime.py`, and the readers in
  `build_sft_dataset.py` / `judge_episodes.py` / `reannotate_thoughts.py` /
  `replay_segmentation.py`, plus `browser.py` headers and `run_webarena.py`
  config load).
- **Symptom**: on Windows the run dies mid-node when any visited page's axtree
  contains a character outside cp1252 (arrows, bullets, box-drawing, emoji —
  all common in real sites). Invisible on macOS/Linux, whose default text
  encoding is UTF-8.
- **Cause**: `open(path, "w")` / `open(path)` in text mode with no `encoding=`
  uses the platform default codec, which is cp1252 on a typical Windows
  install. The axtree files hold **raw** page text (not JSON-escaped), so a
  non-cp1252 glyph is unencodable. The `json.dump` artifact files did *not*
  crash (default `ensure_ascii=True` escapes non-ASCII to `\uXXXX`), but their
  reads would still mis-decode on Windows, so those were hardened too.
- **Fix**: added `encoding="utf-8"` to every text-mode `open()` across the
  runtime and the four SFT-pipeline scripts (writes and reads), so files are
  always UTF-8 regardless of platform locale. Regression test
  `hsge/tests/test_encoding.py::test_record_writes_axtree_with_non_cp1252_chars`
  patches `builtins.open` to simulate the Windows cp1252 default and asserts
  `_record` writes a `↓`-containing axtree without crashing (RED cross-platform
  before the fix). Full suite 152 passed.

### A single flaky/slow frontier URL crashes the whole exploration run
- **Status**: fixed (2026-07-14 18:41)
- **Found**: 2026-07-14, real gitlab exploration run — a mined `.../tree/main`
  page exceeded Playwright's navigation timeout (`Page.goto: Timeout 10000ms
  exceeded`), and the entire multi-hour run terminated with an uncaught
  traceback instead of skipping that one node.
- **Where**: `hsge/webarena/runtime.py::WebArenaExplorer.run()` — the
  per-node `browser = self.browser_factory(url); obs = browser.reset()`
  call had no exception handling of its own; only the whole-loop `try/except`
  around the entire `while` existed, which logs the failure as `run_error`
  and then **re-raises**.
- **Symptom**: any single URL whose browser construction or navigation
  raised (timeout, unreachable, browser-launch failure, ...) killed the
  entire run, discarding the rest of the frontier even though the run had
  already discovered nodes/skills worth continuing past.
- **Cause**: no node-level exception boundary around browser creation/reset,
  unlike every other node-processing step (duplicate-content skip, action
  errors inside `Solver.solve`) which already degrade gracefully instead of
  crashing.
- **Fix**: wrapped `browser_factory(url)` + `browser.reset()` in a
  try/except that logs a new `node_error` event, appends a `nodes_log`
  entry (`nodes.json`, `"error": <message>`), best-effort closes the
  partially-constructed browser, increments a `node_errors` counter
  (subtracted from `nodes_visited` everywhere it's reported, including the
  final print line and `summary.json`), and `continue`s to the next
  frontier item instead of propagating. The whole-loop `try/except` still
  exists and still re-raises for genuinely unexpected exceptions elsewhere
  in node processing (e.g. a bug in Discovery/skill promotion) — only
  browser-load failures are now treated as recoverable per-node events.
  Regression tests: `hsge/tests/test_node_error_resilience.py` (reset()
  failure and browser-construction failure, both mid-run and not crashing
  the loop, `summary.json` status stays `"done"`). Updated
  `hsge/tests/test_run_timing.py::test_run_logs_run_error_and_reraises`
  to inject its failure via the LLM call (`PageExplorer.propose()`) instead
  of `browser_factory`, since the latter is no longer an unhandled-exception
  path — the test's "still crashes on a genuinely unexpected exception"
  contract is unchanged, only its trigger point moved.

### Same crash, second call site: `_solve_with_retries` also calls unguarded `browser.reset()`
- **Status**: fixed (2026-07-14 18:50)
- **Found**: 2026-07-14, real gitlab exploration run, same session as the bug
  above -- the previous fix only guarded `run()`'s node-visit `reset()` (the
  *first* reset when a node is entered); `_solve_with_retries` calls
  `browser.reset()` again before *every task* at that node (to return to a
  clean page), and that second call site was still unguarded.
- **Where**: `hsge/webarena/runtime.py::WebArenaExplorer._solve_with_retries`
  (line ~156).
- **Symptom**: identical crash (`playwright._impl._errors.TimeoutError:
  Page.goto: Timeout 10000ms exceeded`), this time thrown from inside
  `_solve_with_retries` after the node's own initial page load had already
  succeeded -- a second/later navigation between tasks at the same node
  still took down the whole run.
- **Cause:** audited every `WebArenaBrowser` method call in `runtime.py`
  (`close`/`screenshot_b64`/`links`/`page_hrefs` are all already
  internally fail-soft in `browser.py` -- they catch and return a safe
  default) and found `reset()` is the *only* method with no internal
  exception handling of its own, since a real network/timeout failure
  there has no safe default observation to fall back to. It had two call
  sites in `runtime.py`; only one was guarded by the previous fix.
- **Fix**: wrapped `_solve_with_retries`'s `browser.reset()` in the same
  try/except pattern: on failure, logs `task_reset_error`, treats it like
  a solve failure (bounded by `task_retries`, no bogus 0-step episode
  recorded since `self.solver.solve()` never even ran), and returns a
  clean `(None, [], {}, False, False, attempts, urls_seen)` once retries
  are exhausted instead of propagating. Regression tests added to
  `hsge/tests/test_task_retries.py`: reset failing every attempt (bounded,
  no episode recorded, solver never called) and reset recovering after one
  failure (task completes normally once the browser comes back). Full
  suite: 113 passed.

_(Bugs fixed before this log existed are documented in `docs/11_vision_auth_hardening_session.md`, `docs/12_real_run_bug_fixes_session.md`, and `docs/13_run02_reddit_exploration_log.md`.)_
