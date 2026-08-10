# Fine-tune Qwen3.5-9B on the HSGE solver datasets + eval on WebArena

Design: `docs/superpowers/specs/2026-07-15-qwen35-9b-sft-gitlab-eval-design.md`.
For a narrated walkthrough (why each step is shaped this way, gotchas hit
along the way, and a two-machine parallel-eval technique) see
`docs/14_vast_ai_training_eval_tutorial.md`. This file is the terse command
reference for the same pipeline.

Everything below runs on a vast.ai GPU instance (tested: 1× A100-SXM4-80GB,
200 GB disk). The only external dependency is the WebArena site under test
being reachable *from the vast.ai box* (e.g. via a Cloudflare tunnel); resets
between eval runs are manual and happen on the WebArena host.

**Current configuration: one cross-domain model.** A single LoRA trained on
reddit + shopping + shopping_admin + gitlab combined
(`train_all.jsonl` via `training/merge_datasets.py`), then evaluated
separately against each of the four sites' own task subset. Per-site LoRAs
(`qwen35_9b_lora_{reddit,shopping}.yaml`) are kept for comparison/ablation —
see "Alternative: per-site models" below. The original GitLab-only config
(`qwen35_9b_lora.yaml`, `merge_lora.yaml`, `training/train_12.jsonl`) is kept
unchanged for reference; it predates `--require-judge` and `train_gitlab.jsonl`
and should not be used for new runs.

| domain | dataset | examples / trajectories | share of train_all.jsonl |
|---|---|---|---|
| reddit | `train_reddit.jsonl` | 1,672 / 465 | 44.6% |
| shopping | `train_shopping.jsonl` | 773 / 290 | 20.6% |
| shopping_admin | `train_shopping_admin.jsonl` | 241 / 89 | 6.4% |
| gitlab | `train_gitlab.jsonl` | 1,065 / 339 | 28.4% |
| **all (merged)** | `train_all.jsonl` | **3,751 / 1,183** | — |

All four were built with `--require-judge`, so every declared-success episode
was re-checked by an LLM judge; `report_infeasible` episodes are kept.
shopping_admin is under-represented (fewer collected episodes) — if that
matters for training, resample/upweight before running `merge_datasets.py`
rather than changing `qwen35_9b_lora_all.yaml`'s effective batch math.

`training/merge_datasets.py` prefixes each source file's `trajectory_id` with
its domain name before concatenating: HSGE numbers episodes `ep_0000`,
`ep_0001`, ... independently per run, so e.g. reddit's `ep_0005` and
shopping's `ep_0005` are unrelated trajectories that happen to share an id —
concatenating the raw files would make `prepare_dataset.py`'s trajectory
grouping silently merge them across domains.

## Layout on the box

```
/workspace/
  hsge/                      # this repo (rsync'd)
  LLaMA-Factory/             # cloned by vast_setup.sh
  venvs/{train,serve,eval}   # isolated: vLLM pins transformers, training needs
                             # transformers@main, eval needs neither
  models/Qwen3.5-9B          # base weights
  models/Qwen3.5-9B-all      # merged LoRA (step 4)
  saves/qwen35-9b-lora-all   # adapter checkpoint
  eval/<site>/{base,finetuned}/  # results.jsonl + summary.json, one <site> per domain
```

## 1. One-time setup

```bash
scp -P <port> training/vast_setup.sh root@<host>:/workspace/
ssh -p <port> root@<host> 'cd /workspace && nohup bash vast_setup.sh > setup.log 2>&1 &'
# progress: tail -f /workspace/setup.log ; done when all 4 markers exist:
#   ls /workspace/.setup_markers  -> train_venv serve_venv eval_venv model_download
```

Sync the repo (from the local repo root). `train_all.jsonl` (and the four
per-domain `train_<domain>.jsonl` it was built from) live at the repo root and
come along with this rsync:

```bash
rsync -az -e "ssh -p <port>" --exclude .git --exclude outputs --exclude __pycache__ \
    ./ root@<host>:/workspace/hsge/
```

If `train_all.jsonl` doesn't exist yet, build it locally first (pure Python,
no GPU needed) from the four per-domain datasets:

```bash
python training/merge_datasets.py \
    train_reddit.jsonl train_shopping.jsonl train_shopping_admin.jsonl train_gitlab.jsonl \
    -o train_all.jsonl
```

## 2. Prepare the dataset

Split by **task** — `(site, goal)`, read back out of each prompt's `# Goal`
block — not by trajectory. `run.unprefixed_sampling` records every solved task
twice (LOCAL from its node, UNPREFIXED from the site root), so one goal owns
two trajectories; splitting per trajectory puts one in train and its twin in
val. That leaked 29 of 56 val trajectories (50% of val examples) in the first
cross-domain dataset, which is what `eval_loss` — and the epoch-2-vs-3
checkpoint choice — was read off. The script asserts no val goal appears in
train, so a regression fails loudly instead of quietly inflating the number.

Same-goal **same-difficulty** repeats (the seed-capability GOAL generator
re-proposing a goal at another node) are dropped, keeping the longest; the
LOCAL/UNPREFIXED pair is never touched. `--keep-repeats` disables it. On the
four `wa_run_20_*` domains this drops 13 of 1133 trajectories (56 examples).

`--name` must match the `dataset:` key in the training yaml. `--keep-all-fields`
writes every column instead of just `messages`, for an auditable intermediate
copy (this is the shape `training_data/{train,val}.jsonl` is kept in).

```bash
cd /workspace/hsge
/workspace/venvs/train/bin/python training/prepare_dataset.py \
    train_all.jsonl --name all --out-dir training/data/all
```

Writes `{train,val}.jsonl` + `dataset_info.json` registering
`hsge_all_{train,val}`.

## 3. Train the LoRA

The assistant turns are bare `{"thought","action"}` JSON, so training uses the
`qwen3_5_nothink` template (no `<think>` blocks); serving disables thinking to
match (step 5). `cutoff_len` is 6144 — the longest example across all four
domains is ~2.9k tokens, but truncation would silently drop the assistant
target, so this keeps the same safety margin as the per-site configs rather
than cutting it to the measured max.

```bash
cd /workspace/hsge
/workspace/venvs/train/bin/llamafactory-cli train training/qwen35_9b_lora_all.yaml
```

~223 steps/epoch on 3,561 training examples at effective batch 16 × 3 epochs.
Measured on an H100-80GB at the config's 4×4 split: **~11–13 s/step, so ~2.2 h**
for the 669 steps.

The micro-batch split matters far more than it looks. At 2×8 — same effective
batch — the same run takes **~5 h** at 0–46% GPU util and ~150 W: the GPU is
starved, not saturated. 8×2 OOMs, and *where* it OOMs is the useful part:
`cross_entropy` requests 22 GiB in a single allocation, because Qwen3.5's ~151k
vocab makes the logits tensor (batch × seq × vocab × 4 B) the biggest object in
the step — bigger than the activations. To go past batch 4, turn on
`enable_liger_kernel: true`: its fused linear cross-entropy never materializes
those logits (liger does implement `qwen3_5`; not tested in this repo yet).

Three other levers were measured and rejected: the flash-linear-attention
backend is irrelevant (tilelang and triton 3.7.1 give the same step time and the
same loss), padding waste is only 1.18× so `group_by_length` would buy ~15% at
most, and `packing` is unsafe here — GDN layers carry recurrent state along the
sequence and ignore `neat_packing`'s block-diagonal mask, so packed examples
would leak state into each other.

Multi-GPU is the remaining lever if wall-clock matters: LoRA DDP scales close to
linearly, but total GPU-hours barely move, so a 4× box is ~4× faster at ~4× the
hourly rate — buy it for latency, not cost.

## 4. Merge the adapter

```bash
/workspace/venvs/train/bin/llamafactory-cli export training/merge_lora_all.yaml
# -> /workspace/models/Qwen3.5-9B-all
```

On a box that only serves and evaluates, use `training/merge_lora_peft.py`
instead — same result with peft alone, so the box needs no train venv (by far
the slowest and most fragile part of `vast_setup.sh`). Upload the adapter
checkpoint you want (~195 MB) rather than the merged model (~18 GB):

```bash
rsync -az -e "ssh -p <port>" training/artifacts/qwen35-9b-lora-all/checkpoint-446/ \
    root@<host>:/workspace/saves/qwen35-9b-lora-all/
/workspace/venvs/serve/bin/python training/merge_lora_peft.py \
    /workspace/models/Qwen3.5-9B /workspace/saves/qwen35-9b-lora-all \
    /workspace/models/Qwen3.5-9B-all
```

It must load the base with `AutoModelForImageTextToText`: Qwen3.5-9B is
`Qwen3_5ForConditionalGeneration`, and `AutoModelForCausalLM` would keep only
the text tower, writing a `Qwen3_5TextConfig` with the 348 vision tensors
dropped — which vLLM refuses at startup. The script asserts the output config
and tensor count, and that every attached LoRA site is backed by a saved weight
(`target_modules` are bare suffixes that could also match vision-tower modules).
The 15 `mtp.*` speculative-decoding tensors are always dropped and are the one
allowed difference.

### On a CUDA-13 box

`vast_setup.sh`'s `torch`/`vllm` pins exist only for a CUDA-12 driver. On a
CUDA-13 box (e.g. driver 595.71.05 / CUDA 13.2), install `vllm` unpinned — the
newest wheel is the right one, and it avoids the JIT-compile failure documented
in `bugs.md` outright. An eval-only box needs just the `serve` and `eval` venvs
(plus `peft` for the merge above); skip `train` entirely.

## 5. Serve with vLLM

The served name is always `qwen35-9b` so eval commands don't change between
base and finetuned runs:

```bash
nohup bash training/serve_vllm.sh /workspace/models/Qwen3.5-9B > /workspace/vllm.log 2>&1 &      # baseline
nohup bash training/serve_vllm.sh /workspace/models/Qwen3.5-9B-all > /workspace/vllm.log 2>&1 &  # finetuned
```

Ready when `curl -s localhost:8000/v1/models` answers. The eval client sends
`chat_template_kwargs: {"enable_thinking": false}` on every request (Qwen3.5
thinks by default; the training data has no think blocks).

## 6. Evaluate the one model on each of the four domains

`eval_webarena.py --site <site>` runs the WebArena tasks whose `sites` is
exactly `[<site>]`, scored by the official BrowserGym/WebArena evaluators.
Multi-site tasks are skipped. The agent is the repo's `Solver` unchanged — same
prompt the model was trained on. Every site other than `--site` is pointed at
an unreachable dummy URL (WebArenaInstance demands all seven `WA_*` vars). The
same served model (base, then finetuned) is evaluated against all four sites
in turn — this is one model generalizing across domains, not four separate
per-site models.

```bash
cd /workspace/hsge
# smoke test first:
/workspace/venvs/eval/bin/python training/eval_webarena.py --site reddit \
    --site-url https://<reddit-tunnel> --out /workspace/eval/reddit/base --limit 3
# full runs (hours; resumable — re-running skips finished tasks):
/workspace/venvs/eval/bin/python training/eval_webarena.py --site reddit \
    --site-url https://<reddit-tunnel> --out /workspace/eval/reddit/base
```

Eight full runs make the comparison (serve the matching model first, step 5;
`--site-url` points at that domain's own WebArena tunnel):

| server model | command |
|---|---|
| base | `--site reddit --out /workspace/eval/reddit/base` |
| base | `--site shopping --out /workspace/eval/shopping/base` |
| base | `--site shopping_admin --out /workspace/eval/shopping_admin/base` |
| base | `--site gitlab --out /workspace/eval/gitlab/base` |
| `-all` | `--site reddit --out /workspace/eval/reddit/finetuned` |
| `-all` | `--site shopping --out /workspace/eval/shopping/finetuned` |
| `-all` | `--site shopping_admin --out /workspace/eval/shopping_admin/finetuned` |
| `-all` | `--site gitlab --out /workspace/eval/gitlab/finetuned` |

Serve each model once and run all four `--site` evals against it before
swapping, so each model is loaded twice total (not eight times).

Outputs per run: `results.jsonl` (task id, goal, reward, steps, last action)
and `summary.json` (site, model, success rate). Compare `base` vs `finetuned`
within each site, then compare the finetuned success rate across sites to see
how the single cross-domain model generalizes.

Notes:
- **Reset each site between its base and finetuned runs** — many tasks mutate
  state, shopping and shopping_admin especially (and they share one Magento
  DB — never run their evals concurrently). Use scratch instances, not ones
  you care about.
- `--tasks 156,258` runs explicit ids; `--keep-thinking` leaves Qwen3.5's
  thinking mode on (mismatch with training — for ablation only).
- The other six `WA_*` vars are set to dummies automatically; site login uses
  WebArena's standard benchmark accounts inside BrowserGym.
- `--gitlab-url` is still accepted as an alias for `--site-url` (historical).

### Alternative: per-site models

`qwen35_9b_lora_{reddit,shopping}.yaml` / `merge_lora_{reddit,shopping}.yaml`
train one LoRA per domain instead of the combined model above (steps 2–4
become one `prepare_dataset.py` + train + export per site, each into its own
`training/data/<site>` / `saves/qwen35-9b-lora-<site>` /
`models/Qwen3.5-9B-<site>`). Useful for an ablation against the cross-domain
model, or if in-domain performance matters more than a single deployable
model. shopping_admin and gitlab don't have per-site configs yet — copy the
reddit/shopping ones and swap the dataset/paths if needed.

## Troubleshooting

- **LLaMA-Factory fails on the hybrid architecture** (Gated DeltaNet):
  make sure `flash-linear-attention` installed (setup.log warns if not);
  fallback plan is Unsloth's official Qwen3.5 guide.
- **vLLM OOM**: lower `--gpu-memory-utilization` in `serve_vllm.sh` or
  `--max-model-len 6144`.
- **Training OOM at `cutoff_len: 6144`**: drop
  `per_device_train_batch_size` to 1 and raise `gradient_accumulation_steps`
  to 16 (same effective batch).
- **Eval env fails at task setup**: check the tunnel URL is reachable from the
  box (`curl -I $WA_REDDIT`) and that the site is fully up (not 502).
