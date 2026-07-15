# Fine-tune Qwen3.5-9B on the HSGE solver dataset + eval on WebArena GitLab

Design: `docs/superpowers/specs/2026-07-15-qwen35-9b-sft-gitlab-eval-design.md`.
For a narrated walkthrough (why each step is shaped this way, gotchas hit
along the way, and a two-machine parallel-eval technique) see
`docs/14_vast_ai_training_eval_tutorial.md`. This file is the terse command
reference for the same pipeline.

Everything below runs on a vast.ai GPU instance (tested: 1× A100-SXM4-80GB,
200 GB disk). The only external dependency is a WebArena **GitLab** instance
reachable *from the vast.ai box* (e.g. via a Cloudflare tunnel); resets between
eval runs are manual and happen on the GitLab host.

## Layout on the box

```
/workspace/
  hsge/                 # this repo (rsync'd)
  LLaMA-Factory/        # cloned by vast_setup.sh
  venvs/{train,serve,eval}   # isolated: vLLM pins transformers, training needs
                             # transformers@main, eval needs neither
  models/Qwen3.5-9B          # base weights
  models/Qwen3.5-9B-hsge     # merged LoRA (created in step 4)
  saves/qwen35-9b-lora-hsge  # adapter checkpoints
  eval/{base,finetuned}/     # results.jsonl + summary.json per run
```

## 1. One-time setup

```bash
scp -P <port> training/vast_setup.sh root@<host>:/workspace/
ssh -p <port> root@<host> 'cd /workspace && nohup bash vast_setup.sh > setup.log 2>&1 &'
# progress: tail -f /workspace/setup.log ; done when all 4 markers exist:
#   ls /workspace/.setup_markers  -> train_venv serve_venv eval_venv model_download
```

Sync the repo (from the local repo root):

```bash
rsync -az -e "ssh -p <port>" --exclude .git --exclude outputs --exclude __pycache__ \
    ./ root@<host>:/workspace/hsge/
```

## 2. Prepare the dataset

```bash
cd /workspace/hsge
/workspace/venvs/train/bin/python training/prepare_dataset.py training/train_12.jsonl
# -> training/data/{train.jsonl,val.jsonl,dataset_info.json}  (352 train / 18 val,
#    split by trajectory so episodes never straddle the split)
```

## 3. Train LoRA

The dataset's assistant turns are bare `{"thought","action"}` JSON, so training
uses the `qwen3_5_nothink` template (no `<think>` blocks); serving disables
thinking to match (step 5).

```bash
cd /workspace/hsge
/workspace/venvs/train/bin/llamafactory-cli train training/qwen35_9b_lora.yaml
```

~66 optimizer steps (352 examples × 3 epochs / batch 16); minutes on an A100.

## 4. Merge the adapter

```bash
/workspace/venvs/train/bin/llamafactory-cli export training/merge_lora.yaml
# -> /workspace/models/Qwen3.5-9B-hsge
```

## 5. Serve with vLLM

One model at a time (the A100 hosts one server); the served name is always
`qwen35-9b` so eval commands don't change between runs:

```bash
nohup bash training/serve_vllm.sh /workspace/models/Qwen3.5-9B > /workspace/vllm.log 2>&1 &   # baseline
# ... run baseline eval, then kill and restart with the merged model:
nohup bash training/serve_vllm.sh > /workspace/vllm.log 2>&1 &                                 # finetuned
```

Ready when `curl -s localhost:8000/v1/models` answers. The eval client sends
`chat_template_kwargs: {"enable_thinking": false}` on every request (Qwen3.5
thinks by default; the training data has no think blocks).

## 6. Evaluate on the official GitLab subset

~180 tasks (`sites == ["gitlab"]` in WebArena's `test.raw.json`), scored by the
official BrowserGym/WebArena evaluators. The agent is the repo's `Solver`
unchanged — same prompt the model was trained on.

```bash
cd /workspace/hsge
# smoke test first:
/workspace/venvs/eval/bin/python training/eval_webarena_gitlab.py \
    --gitlab-url https://<your-tunnel> --out /workspace/eval/base --limit 3
# full runs (hours; resumable — re-running skips finished tasks):
/workspace/venvs/eval/bin/python training/eval_webarena_gitlab.py \
    --gitlab-url https://<your-tunnel> --out /workspace/eval/base
# swap the served model (step 5), then:
/workspace/venvs/eval/bin/python training/eval_webarena_gitlab.py \
    --gitlab-url https://<your-tunnel> --out /workspace/eval/finetuned
```

Outputs per run: `results.jsonl` (task id, goal, reward, steps, last action)
and `summary.json` (success rate). Compare `eval/base` vs `eval/finetuned`.

Notes:
- Reset GitLab between the two full runs — some tasks mutate state.
- MOD-type tasks write to the GitLab instance; use a scratch instance, not one
  you care about.
- `--tasks 156,258` runs explicit ids; `--keep-thinking` leaves Qwen3.5's
  thinking mode on (mismatch with training — for ablation only).
- The six non-GitLab `WA_*` vars are set to dummies automatically; GitLab login
  uses WebArena's standard `byteblaze` benchmark account inside BrowserGym.

## Troubleshooting

- **LLaMA-Factory fails on the hybrid architecture** (Gated DeltaNet):
  make sure `flash-linear-attention` installed (setup.log warns if not);
  fallback plan is Unsloth's official Qwen3.5 guide.
- **vLLM OOM**: lower `--gpu-memory-utilization` in `serve_vllm.sh` or
  `--max-model-len 6144`.
- **Eval env fails at task setup**: check the tunnel URL is reachable from the
  box (`curl -I $WA_GITLAB`) and that GitLab is fully up (not 502).
