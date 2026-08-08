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

**Current configuration: two per-site models.** One LoRA on reddit, one on
shopping, each evaluated in-domain against its own site. The original GitLab
config (`qwen35_9b_lora.yaml`, `merge_lora.yaml`, `training/train_12.jsonl`) is
kept unchanged for reference.

| | reddit | shopping |
|---|---|---|
| dataset | `train_reddit.jsonl` | `train_shopping.jsonl` |
| examples / trajectories | 2,829 / 540 | 4,034 / 614 |
| train / val split | 2,673 / 156 | 3,827 / 207 |
| adapter | `/workspace/saves/qwen35-9b-lora-reddit` | `.../-shopping` |
| merged model | `/workspace/models/Qwen3.5-9B-reddit` | `.../-shopping` |
| eval subset | ~106 `sites == ["reddit"]` tasks | ~187 `sites == ["shopping"]` tasks |

Both datasets were built with `--require-judge`, so every declared-success
episode was re-checked by an LLM judge; `report_infeasible` episodes are kept.

## Layout on the box

```
/workspace/
  hsge/                      # this repo (rsync'd)
  LLaMA-Factory/             # cloned by vast_setup.sh
  venvs/{train,serve,eval}   # isolated: vLLM pins transformers, training needs
                             # transformers@main, eval needs neither
  models/Qwen3.5-9B                    # base weights
  models/Qwen3.5-9B-{reddit,shopping}  # merged LoRAs (step 4)
  saves/qwen35-9b-lora-{reddit,shopping}   # adapter checkpoints
  eval/<site>/{base,finetuned}/            # results.jsonl + summary.json
```

## 1. One-time setup

```bash
scp -P <port> training/vast_setup.sh root@<host>:/workspace/
ssh -p <port> root@<host> 'cd /workspace && nohup bash vast_setup.sh > setup.log 2>&1 &'
# progress: tail -f /workspace/setup.log ; done when all 4 markers exist:
#   ls /workspace/.setup_markers  -> train_venv serve_venv eval_venv model_download
```

Sync the repo (from the local repo root). `train_reddit.jsonl` /
`train_shopping.jsonl` live at the repo root and come along with this rsync:

```bash
rsync -az -e "ssh -p <port>" --exclude .git --exclude outputs --exclude __pycache__ \
    ./ root@<host>:/workspace/hsge/
```

## 2. Prepare the datasets

Split by trajectory (a trajectory's steps never straddle the split) into a
per-site directory. `--name` must match the `dataset:` key in the training yaml.

```bash
cd /workspace/hsge
/workspace/venvs/train/bin/python training/prepare_dataset.py \
    train_reddit.jsonl --name reddit --out-dir training/data/reddit
/workspace/venvs/train/bin/python training/prepare_dataset.py \
    train_shopping.jsonl --name shopping --out-dir training/data/shopping
```

Each writes `{train,val}.jsonl` + `dataset_info.json` registering
`hsge_<site>_{train,val}`.

## 3. Train the LoRAs

The assistant turns are bare `{"thought","action"}` JSON, so training uses the
`qwen3_5_nothink` template (no `<think>` blocks); serving disables thinking to
match (step 5). `cutoff_len` is 6144 here rather than the GitLab config's 4096 —
the longest reddit example is ~4.0k tokens and truncation would silently drop
the assistant target.

```bash
cd /workspace/hsge
/workspace/venvs/train/bin/llamafactory-cli train training/qwen35_9b_lora_reddit.yaml
/workspace/venvs/train/bin/llamafactory-cli train training/qwen35_9b_lora_shopping.yaml
```

~500 steps (reddit) and ~720 steps (shopping) at effective batch 16 × 3 epochs;
roughly 1–2 h each on an A100 at `cutoff_len: 6144`.

## 4. Merge the adapters

```bash
/workspace/venvs/train/bin/llamafactory-cli export training/merge_lora_reddit.yaml
/workspace/venvs/train/bin/llamafactory-cli export training/merge_lora_shopping.yaml
# -> /workspace/models/Qwen3.5-9B-{reddit,shopping}
```

## 5. Serve with vLLM

One model at a time (the A100 hosts one server); the served name is always
`qwen35-9b` so eval commands don't change between runs:

```bash
nohup bash training/serve_vllm.sh /workspace/models/Qwen3.5-9B > /workspace/vllm.log 2>&1 &          # baseline
nohup bash training/serve_vllm.sh /workspace/models/Qwen3.5-9B-reddit > /workspace/vllm.log 2>&1 &   # reddit
nohup bash training/serve_vllm.sh /workspace/models/Qwen3.5-9B-shopping > /workspace/vllm.log 2>&1 & # shopping
```

Ready when `curl -s localhost:8000/v1/models` answers. The eval client sends
`chat_template_kwargs: {"enable_thinking": false}` on every request (Qwen3.5
thinks by default; the training data has no think blocks).

## 6. Evaluate on the official per-site subsets

`eval_webarena.py --site <site>` runs the WebArena tasks whose `sites` is
exactly `[<site>]`, scored by the official BrowserGym/WebArena evaluators.
Multi-site tasks are skipped. The agent is the repo's `Solver` unchanged — same
prompt the model was trained on. Every site other than `--site` is pointed at
an unreachable dummy URL (WebArenaInstance demands all seven `WA_*` vars).

```bash
cd /workspace/hsge
# smoke test first:
/workspace/venvs/eval/bin/python training/eval_webarena.py --site reddit \
    --site-url https://<reddit-tunnel> --out /workspace/eval/reddit/base --limit 3
# full runs (hours; resumable — re-running skips finished tasks):
/workspace/venvs/eval/bin/python training/eval_webarena.py --site reddit \
    --site-url https://<reddit-tunnel> --out /workspace/eval/reddit/base
```

Four full runs make the comparison (serve the matching model first, step 5):

| server model | command |
|---|---|
| base | `--site reddit --out /workspace/eval/reddit/base` |
| base | `--site shopping --out /workspace/eval/shopping/base` |
| `-reddit` | `--site reddit --out /workspace/eval/reddit/finetuned` |
| `-shopping` | `--site shopping --out /workspace/eval/shopping/finetuned` |

Serve the base model once and do *both* base runs before swapping, so the model
is loaded twice, not four times.

Outputs per run: `results.jsonl` (task id, goal, reward, steps, last action)
and `summary.json` (site, model, success rate). Compare `base` vs `finetuned`
within each site.

Notes:
- **Reset the site between the base and finetuned runs** — many tasks mutate
  state, and shopping especially. Use a scratch instance, not one you care
  about.
- `--tasks 156,258` runs explicit ids; `--keep-thinking` leaves Qwen3.5's
  thinking mode on (mismatch with training — for ablation only).
- The other six `WA_*` vars are set to dummies automatically; site login uses
  WebArena's standard benchmark accounts inside BrowserGym.
- `--site gitlab` reproduces the original GitLab eval; `--gitlab-url` is still
  accepted as an alias for `--site-url`.

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
