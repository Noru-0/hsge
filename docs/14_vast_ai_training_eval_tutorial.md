# 14 — Tutorial: fine-tuning + WebArena eval on rented vast.ai GPUs

A step-by-step walkthrough for LoRA fine-tuning an open model on the HSGE solver
dataset and evaluating it on WebArena, entirely on rented vast.ai GPU instances.
This tutorial narrates the *why* behind each step; `training/README.md` is the
terse command reference for the same pipeline. Concrete numbers throughout are
from a real run (`Qwen/Qwen3.5-9B` on `training/train_12.jsonl`, 2026-07-14/15).

## What you end up with

```
rent GPU instance -> setup venvs -> prepare dataset -> LoRA train -> merge
    -> serve (vLLM) -> evaluate (official WebArena task subset via BrowserGym)
```

Everything runs on the instance except the WebArena site itself, which you host
yourself (locally, or wherever) and expose to the instance over a tunnel
(Cloudflare Tunnel, ngrok, Tailscale funnel, ...).

## 0. Prerequisites

- A vast.ai account with billing set up.
- A WebArena site reachable **from the internet** (or at least from vast.ai's
  network) — a Cloudflare quick tunnel (`cloudflared tunnel --url
  http://localhost:PORT`) is the fastest way to expose a locally-hosted
  instance without opening firewall ports.
- Hugging Face access to your base model (`huggingface-cli login` isn't needed
  for public models like `Qwen/Qwen3.5-9B`).
- An SFT dataset in OpenAI `messages` chat format, one JSON object per line:
  `{"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}`.
  This tutorial's example (`training/train_12.jsonl`, 370 examples) is HSGE's
  own solver-format dataset (see `docs/06_training.md` for how it's produced).

## 1. Rent the instance

Pick a GPU with enough VRAM for your model size and method. For a 9B model with
LoRA: **1× A100-80GB** or **L40S/A6000-48GB** is comfortable (LoRA gradients +
optimizer state are small; the big memory cost is loading the base model once
in bf16, plus vLLM's KV cache when serving). Disk: **150–200 GB** — base
weights (~19 GB for a 9B model), the merged checkpoint (another ~18 GB), vLLM
build artifacts, and Playwright/Chromium for the eval driver all add up.

**Container caveat:** vast.ai's default image is an *unprivileged Docker
container*, not a VM — you're root, but you cannot run Docker-in-Docker, load
kernel modules, or mount block devices. This is irrelevant for training/eval
(everything here runs as plain Python processes), but rules out trying to
`docker run` WebArena's own site containers on the same box. If you need to
self-host WebArena *and* train on the same rented machine, request a vast.ai
**VM instance** instead of the default container type.

Once rented, you get an SSH command like:

```
ssh -p <PORT> root@<HOST>
```

Confirm the GPU and disk before doing anything else:

```bash
ssh -p <PORT> root@<HOST> 'nvidia-smi --query-gpu=name,memory.total --format=csv,noheader; df -h / | tail -1'
```

## 2. One-time environment setup

Copy [`training/vast_setup.sh`](../training/vast_setup.sh) to the box and run
it detached (it takes several minutes — package installs + a multi-GB model
download):

```bash
scp -P <PORT> training/vast_setup.sh root@<HOST>:/workspace/
ssh -p <PORT> root@<HOST> 'cd /workspace && nohup bash vast_setup.sh > setup.log 2>&1 &'
ssh -p <PORT> root@<HOST> 'tail -f /workspace/setup.log'   # Ctrl-C when it prints SETUP COMPLETE
```

### Why three separate venvs

The script creates `/workspace/venvs/{train,serve,eval}`, each isolated with
`uv venv`. This isn't cargo-culting — it avoids two real dependency conflicts:

1. **Training needs bleeding-edge `transformers`.** Newer model families (this
   tutorial's Qwen3.5 uses a hybrid Gated-DeltaNet + attention architecture)
   often land in `transformers` `main` weeks before a package release.
   `vast_setup.sh` installs `transformers @ git+...@main` into the `train`
   venv specifically for this reason. **vLLM, on the other hand, pins an exact
   `transformers` version** for its own compatibility guarantees — installing
   both in one environment means one of them loses.
2. **The eval driver needs neither.** It only talks to vLLM's OpenAI-compatible
   HTTP API and drives a browser (`browsergym-webarena` + Playwright) — pulling
   in either ML framework would just be dead weight and one more source of
   version conflicts.

If your model is an older, well-supported architecture, you can likely
collapse `train`+`serve` into one venv. Keep `eval` separate regardless — it
has its own heavy, unrelated dependency (`playwright install chromium` pulls
~300 MB of browser binaries).

### Gotcha: LLaMA-Factory's version gate

LLaMA-Factory checks its installed `transformers` version against a hardcoded
range (e.g. `>=4.55.0,<=5.8.0`) before every command. Installing
`transformers@main` for a brand-new model routinely puts you *above* that
ceiling (we hit `5.14.0.dev0` against a `<=5.8.0` gate). The fix is not to
downgrade — that would break the new model's support — but to skip the gate:

```bash
DISABLE_VERSION_CHECK=1 llamafactory-cli train ...
```

Every `llamafactory-cli` invocation in this tutorial carries that env var.

## 3. Sync your repo and prepare the dataset

```bash
rsync -az -e "ssh -p <PORT>" --exclude .git --exclude outputs --exclude __pycache__ \
    ./ root@<HOST>:/workspace/hsge/

ssh -p <PORT> root@<HOST> 'cd /workspace/hsge && \
    /workspace/venvs/train/bin/python training/prepare_dataset.py training/train_12.jsonl'
```

[`prepare_dataset.py`](../training/prepare_dataset.py) splits **by
trajectory**, not by example — a multi-step episode's steps never straddle the
train/val boundary, which would otherwise leak near-duplicate context across
the split. It also writes LLaMA-Factory's `dataset_info.json` and prints
character-length stats so you can sanity-check `cutoff_len` before training
(our 370-example set: max ~8.3K chars ≈ 2.8K tokens, comfortably under a 4096
cutoff).

## 4. Train the LoRA adapter

```bash
ssh -p <PORT> root@<HOST> 'cd /workspace/hsge && DISABLE_VERSION_CHECK=1 \
    /workspace/venvs/train/bin/llamafactory-cli train training/qwen35_9b_lora.yaml'
```

[`training/qwen35_9b_lora.yaml`](../training/qwen35_9b_lora.yaml) is a
LLaMA-Factory SFT config. The parts worth understanding rather than
copy-pasting:

- **`template`** must match your model family *and* your data's format. This
  is the step most likely to silently produce a bad model: get the template
  wrong and training "succeeds" (loss goes down) while learning the wrong
  chat-formatting conventions. Find the right name by grepping the installed
  LLaMA-Factory's own template registry rather than guessing:
  ```bash
  grep -n 'name="qwen' /workspace/LLaMA-Factory/src/llamafactory/data/template.py
  ```
  We found `qwen3_5_nothink` this way — LLaMA-Factory had already shipped
  family-specific support before the model's official docs caught up.
- **`nothink`:** Qwen3.5 (like Qwen3) thinks by default, wrapping a
  `<think>...</think>` block before its answer. Our dataset's assistant turns
  are bare `{"thought": "...", "action": "..."}` JSON with no think block —
  because they're extracted from a live agent's actual tool-call outputs, not
  authored chain-of-thought. Training with the *thinking* template on
  *non-thinking* data teaches the model an inconsistent format. Always check
  whether your target model's default template matches your data's actual
  shape, and pick the `_nothink` variant when it doesn't.
- **`lora_target: all`**, rank 16 / alpha 32 — reasonable defaults for a
  small (hundreds-of-examples) dataset. Don't reach for full SFT at this data
  scale; it overfits fast and costs far more compute for no benefit.
- **Batch size × accumulation × epochs** determine step count. 352 train
  examples, batch 2, accumulation 8 (effective batch 16), 3 epochs → 66
  optimizer steps. On an A100-80GB this took **~27 minutes** and converged to
  `train_loss=0.32` / `eval_loss=0.24` — a small, fast job precisely because
  LoRA + a few hundred examples doesn't need much wall-clock time. If your
  dataset is 10–100× larger, expect proportionally longer training and
  consider `gradient_checkpointing: false` if VRAM allows (faster, at the cost
  of more memory).

## 5. Merge the adapter into a standalone checkpoint

vLLM can technically serve a LoRA adapter as a separate flag, but merging
first is simpler and lets you serve the finetuned model exactly like any other
checkpoint:

```bash
ssh -p <PORT> root@<HOST> 'cd /workspace/hsge && DISABLE_VERSION_CHECK=1 \
    /workspace/venvs/train/bin/llamafactory-cli export training/merge_lora.yaml'
```

[`training/merge_lora.yaml`](../training/merge_lora.yaml) points at the base
model + the adapter directory and writes a full merged checkpoint to
`export_dir`. This step is fast (tens of seconds — it's just a weighted-sum
merge and a re-save, not a forward/backward pass) but the *output* is
full-model size again (~18 GB for a 9B model in bf16), which matters if you
ever need to move it (see §7).

## 6. Serve with vLLM

```bash
ssh -p <PORT> root@<HOST> 'nohup bash /workspace/hsge/training/serve_vllm.sh \
    /workspace/models/<merged-checkpoint> > /workspace/vllm.log 2>&1 &'
ssh -p <PORT> root@<HOST> 'until curl -sf localhost:8000/v1/models; do sleep 5; done'
```

[`training/serve_vllm.sh`](../training/serve_vllm.sh) always serves under the
name `qwen35-9b` regardless of which checkpoint is loaded, so downstream
tooling (the eval script, ad-hoc `curl` tests) never needs to change.

**Disabling thinking at serve time**, to match the nothink training template,
is a per-*request* flag, not a server flag — set it on every chat completion:

```json
{"chat_template_kwargs": {"enable_thinking": false}, ...}
```

The repo's `hsge.backends.OpenAILLM` doesn't know about this vLLM-specific
extension by default; `training/eval_webarena.py` subclasses it to
inject `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` into
every request (see `NoThinkOpenAILLM` in that file). If you roll your own
client, do the same — forgetting this flag produces responses wrapped in
`<think>` blocks that your action-parsing regex won't expect.

**Sanity-check the served model before running a full eval.** A cheap way to
catch template/prompt mismatches early: send one chat completion with your
exact production system prompt and a minimal page, and check the action comes
back in your expected format (e.g. `click('52')`, not a natural-language
description of the click). We caught exactly this class of bug during
development — an ad-hoc test prompt that *approximated* the real prompt
produced natural-language actions, while the real `SOLVER_SYS` + properly
formatted page produced the correct `click('bid')` syntax. Always test with
the *exact* prompt your pipeline sends, not an approximation.

## 7. Evaluate on the official WebArena GitLab subset

> The script has since been generalized to any single site: `--site reddit
> --site-url <url>` and so on (`--gitlab-url` is kept as an alias, so the
> commands in this section still work verbatim). This walkthrough narrates the
> original GitLab run; `training/README.md` is the current command reference.

```bash
ssh -p <PORT> root@<HOST> 'cd /workspace/hsge && /workspace/venvs/eval/bin/python \
    training/eval_webarena.py --gitlab-url https://<your-tunnel> \
    --out /workspace/eval/finetuned'
```

[`training/eval_webarena.py`](../training/eval_webarena.py)
does three things worth understanding:

1. **Pulls the official task set** (`test.raw.json` from the WebArena repo)
   and filters to `sites == ["gitlab"]` — the same ~180 tasks any published
   WebArena GitLab number is measured against, so your result is comparable.
2. **Drives BrowserGym's scored `browsergym/webarena.<id>` env** (not the
   open-ended exploration env this repo otherwise uses) — the scored env runs
   each task's official evaluator (string-match, URL-match, or program-based
   HTML check) and returns a reward, which is what makes the result
   comparable to published numbers rather than a self-graded approximation.
3. **Reuses the live Solver's exact prompt** (`SOLVER_SYS`, the axtree
   truncation, the outcome-annotated history) instead of writing a fresh
   eval-only prompt. This matters specifically *because* you just fine-tuned
   on that exact prompt shape — evaluating with a different prompt would be
   measuring a distribution-shifted variant of your model, not the one you
   trained.

One integration detail if you build something similar: the Solver's terminal
action (`send_msg_to_user(...)` / `report_infeasible(...)`) is *never*
executed against the browser during normal exploration (it's just how the
Solver signals "I'm done" to its caller) — but WebArena's string-match
evaluators read their answer from the env's chat history, so the eval driver
has to explicitly replay that final action into the scored env after the
Solver returns. Skipping this silently zeroes out every task whose evaluator
checks the chat answer instead of a URL/DOM check.

Run a 2–3 task smoke test before committing to the full sweep — it catches
config typos (wrong `--gitlab-url`, wrong port) for the cost of a minute
instead of hours:

```bash
... training/eval_webarena.py --gitlab-url https://<tunnel> --out /tmp/smoke --limit 2
```

The run is **resumable**: re-running the same command skips task ids already
present in `results.jsonl`. Add `--no-resume` to force a clean re-run.

## 8. Baseline vs. fine-tuned comparison

Run step 7 once against the base checkpoint and once against the merged
checkpoint (swap which model `serve_vllm.sh` loads between runs — one vLLM
server per GPU at a time), then diff `summary.json`:

```bash
ssh -p <PORT> root@<HOST> 'cat /workspace/eval/base/summary.json /workspace/eval/finetuned/summary.json'
```

**Reset your WebArena instance between the two full runs.** Many GitLab tasks
mutate state (open an issue, post a comment, fork a repo); running the
baseline and fine-tuned sweeps back-to-back without a reset means the second
run starts from a dirtier state than the first, which is score-sensitive for
mutation-dependent tasks and content-existence checks.

## 9. Advanced: two-machine parallel evaluation

A full 180-task sweep took ~4–8 hours in our run. If you've rented a second
GPU instance (e.g. specifically to evaluate the fine-tuned model while a first
machine finishes the baseline), two problems need solving: getting the
checkpoint to the second machine efficiently, and running both sweeps without
one run's writes corrupting the other's reads on your *single* shared WebArena
instance.

### Moving the model between machines without re-transferring 18 GB

Don't scp the merged checkpoint between machines. The base weights are already
on both boxes (each ran its own `vast_setup.sh`, which downloads the base
model from Hugging Face directly — fast, cloud-to-cloud). The only artifact
unique to your training run is the **LoRA adapter**, which is far smaller
(1.7 GB for a rank-16 adapter over a 9B model, vs. 18 GB merged):

```bash
# machine A (trained) -> local -> machine B (serves + evals)
scp -P <PORT_A> -r root@<HOST_A>:/workspace/saves/<adapter-dir> ./adapter/
scp -P <PORT_B> -r ./adapter/<adapter-dir> root@<HOST_B>:/workspace/saves/
ssh -p <PORT_B> root@<HOST_B> 'cd /workspace/hsge && DISABLE_VERSION_CHECK=1 \
    /workspace/venvs/train/bin/llamafactory-cli export training/merge_lora.yaml'
```

Re-running the merge step (§5) on machine B is a ~15-second local operation;
it's strictly cheaper than moving the merged checkpoint over the network,
regardless of your bandwidth. This does mean machine B needs the `train` venv
too (the export step depends on the same LLaMA-Factory/transformers stack as
training, even though machine B never trains anything).

### Safely running two sweeps against one shared, live site

WebArena's GitLab tasks aren't all read-only. If machine A (baseline) and
machine B (fine-tuned) both run the full 180-task set concurrently against
the same GitLab instance, a write task from one run (e.g. "fork this repo")
can land in the middle of the other run's read task (e.g. "how many repos have
I contributed to"), producing a spurious pass or fail that has nothing to do
with either model's actual competence.

The fix we used: **classify every task by its `intent` text into read-only vs.
state-mutating**, and only run the read-only subset concurrently. Anything
that creates/edits/deletes/follows/forks/stars/comments is deferred until the
first run finishes and you've reset the instance.

```python
import json, re

WRITE_PHRASES = [
    r'\bcreate\b', r'\bsubmit\b', r'\bpost\b', r'\bcomment\b', r'\breply\b',
    r'\bleave an?\b', r'\bclose\b', r'\bmerge the\b', r'\bmerge this\b',
    r'\bdelete\b', r'\bremove\b', r'\bfork\b', r'\bstar the\b', r'\bstar this\b',
    r'\bfollow\b', r'\bassign\b', r'\blabel the\b', r'\brename\b', r'\bedit\b',
    r'\bupdate\b', r'\bchange\b', r'\bset\b', r'\binvite\b', r'\badd\b',
    r'\bupload\b', r'\bpush\b', r'\bmake the license\b',
    r'\bopen an? (new )?(issue|merge)\b',
    # ... see training/eval_webarena.py's design doc for the full list
]
write_re = re.compile('|'.join(WRITE_PHRASES), re.I)

configs = json.load(open('test.raw.json'))
gitlab = [c for c in configs if c.get('sites') == ['gitlab']]
read_safe = [c['task_id'] for c in gitlab if not write_re.search(c['intent'])]
```

Two traps that make a naive first pass under-conservative — worth checking for
by hand, not just trusting the regex:

- **GitLab noun phrases collide with write verbs.** "Checkout **merge
  requests** assigned to me" is a read (navigate to a filtered list); a bare
  `\bmerge\b` pattern flags it as a write because "merge request" is GitLab's
  feature name, not the verb. Same for "list issues that **report** bugs"
  (`report` as a noun) and "**react** apps" (a framework name colliding with
  the verb "react to"). Fix by matching multi-word phrases (`merge the`,
  `react to`) instead of bare verbs where the collision is common.
- **Word insertions defeat naive phrase patterns.** `\bopen an? issue\b` misses
  "Open **a new** issue" — the inserted adjective breaks the two-word match.
  We only caught this by printing the *entire* candidate "safe" list and
  reading every line before trusting it, not by reasoning about the regex in
  the abstract. **Always eyeball the full classified-safe list by hand before
  running anything concurrently against a live shared instance** — a false
  "read-only" classification means a write silently lands mid-run on the
  other machine, and unlike a crash, a bad classification here doesn't announce
  itself; the numbers just come out quietly wrong. When in doubt, default a
  task to *write* (deferred) rather than *read* (run now) — the cost of being
  wrong is asymmetric.

Then run the same eval script against the curated subset:

```bash
ssh -p <PORT_B> root@<HOST_B> 'cd /workspace/hsge && /workspace/venvs/eval/bin/python \
    training/eval_webarena.py --gitlab-url https://<tunnel> \
    --out /workspace/eval/finetuned_readsafe --tasks 44,45,46,...'
```

Once the baseline machine finishes its full 180-task run and you've reset the
instance, run the deferred write-classified subset for the fine-tuned model
the same way, then merge both partial `results.jsonl` files for the complete
180-task comparison.

## Cost and time reference (this run)

| Step | Time | Notes |
|---|---|---|
| Instance setup (venvs + model download) | ~10 min | mostly package installs |
| LoRA training (352 ex × 3 epochs, A100-80GB) | ~27 min | 66 optimizer steps |
| Adapter merge | ~15 s | |
| vLLM cold start | ~1–2 min | model load into GPU memory |
| Full 180-task GitLab eval | ~4–8 h | dominated by browser/LLM round-trips, not compute |
| Adapter transfer between machines | a few min | 1.7 GB, vs. ~18 GB for the merged checkpoint |

For a single A100-80GB instance, expect **most of the wall-clock to be eval,
not training** — a small LoRA job on a few hundred examples is cheap; running
a browser-driving agent through ~180 multi-step tasks is not.

## Troubleshooting

- **`ImportError: transformers>=X,<=Y is required ... but found Z`** during
  `llamafactory-cli` — see §2; prefix the command with `DISABLE_VERSION_CHECK=1`.
- **Wrong action format from the served model** (natural language instead of
  `click('bid')`) — almost always a template mismatch (§4) or a test prompt
  that doesn't match production (§6), not a training failure. Verify with the
  exact system prompt before assuming the fine-tune didn't work.
- **`Page.goto: Timeout ... exceeded`** against a Cloudflare-tunneled site —
  usually transient tunnel latency, not a real failure. The eval script's
  `results.jsonl` records it as an error for that task; re-run just that task
  id (`--tasks <id> --no-resume`) to confirm before treating it as a genuine
  model/environment problem.
- **vLLM OOM on server start** — lower `--gpu-memory-utilization` or
  `--max-model-len` in `serve_vllm.sh`.
- **Two eval runs' results look worse than expected on tasks near each
  other's write activity** — see §9; you likely ran overlapping write-capable
  tasks concurrently against a shared instance without realizing it.
