# Qwen3.5-9B SFT + WebArena GitLab eval — design

Status: **approved** (2026-07-15). Implementation lives in `training/`.

## Goal

Fine-tune `Qwen/Qwen3.5-9B` on the HSGE-collected solver dataset
(`training/train_12.jsonl`, 370 chat examples in the live Solver's exact prompt
format) and evaluate the result on the **official WebArena GitLab task subset**,
comparing against the un-finetuned base model.

## Topology

- **vast.ai GPU instance** (1× A100-SXM4-80GB, 200 GB disk, unprivileged Docker
  container — no Docker-in-Docker): training, LoRA merge, vLLM serving, and the
  eval driver (headless Playwright/Chromium) all run here.
- **WebArena GitLab** is self-hosted by the user and exposed through a Cloudflare
  tunnel (URL supplied at run time via `WA_GITLAB` / `--gitlab-url`). Reachability
  from the instance was verified (HTTP 302 to the sign-in page). GitLab resets
  between eval runs are the user's responsibility.
- No other WebArena site is needed; the six unused `WA_*` env vars are set to
  dummy values to satisfy `WebArenaInstance.__init__`.

## Training

- **Method:** LoRA (bf16) via **LLaMA-Factory** (fallback: Unsloth, which has an
  official Qwen3.5 guide, if LLaMA-Factory's support for the hybrid
  Gated-DeltaNet architecture proves broken). 370 examples ⇒ LoRA is enough;
  full SFT would overfit and cost far more.
- **Thinking mode:** Qwen3.5 thinks by default (`<think>…</think>`), but the
  dataset's assistant turns are bare `{"thought": …, "action": …}` JSON. Train
  with the **nothink** chat template and serve with thinking disabled, so
  train/inference templates match.
- **Data prep:** `prepare_dataset.py` splits ~350 train / 20 val (seeded, by
  trajectory so a trajectory's steps never straddle the split), writes
  LLaMA-Factory `dataset_info.json` (sharegpt/openai messages mapping), and
  prints token-length stats to sanity-check `cutoff_len`.
- Merge the adapter into a standalone checkpoint (`llamafactory-cli export`) for
  vLLM serving.

## Serving

vLLM OpenAI-compatible server on the instance (localhost), one model at a time:
first the base model (baseline eval), then the merged checkpoint. Thinking
disabled via chat-template kwargs/template default. The eval driver talks to it
with the repo's `OpenAILLM` (`base_url=http://localhost:<port>/v1`).

## Eval

- **Task set:** official WebArena `test.raw.json` filtered to
  `sites == ["gitlab"]` (~180 tasks), run through **BrowserGym**
  (`browsergym/webarena.<id>`) so the official evaluators/reward compute success
  — comparable to published numbers.
- **Agent:** a lean driver loop in `training/eval_webarena_gitlab.py` that
  reuses the repo Solver's prompt pieces (`SOLVER_SYS`, `_cap_axtree`,
  `step_outcome`, action parsing) for **prompt parity** with the training data,
  but executes actions in the BrowserGym env directly. `send_msg_to_user` is
  executed in the env (not intercepted) so string-match evaluators see the
  answer; `report_infeasible` likewise maps to the env's chat action.
- **Outputs:** per-task `results.jsonl` (task id, reward, steps, answer) +
  aggregate success rate. Run once with the base model, once with the finetuned
  one.
- Smoke test (2–3 tasks) gates the full run; full runs (~4–8 h for 180 tasks)
  are triggered explicitly by the user since they cost instance time.

## Deliverables (`training/`)

`README.md` (runbook), `vast_setup.sh` (two venvs: train = LLaMA-Factory +
transformers@main; serve/eval = vLLM + browsergym-webarena + Playwright;
model download), `prepare_dataset.py`, `qwen35_9b_lora.yaml`,
`merge_lora.yaml`, `serve_vllm.sh`, `eval_webarena_gitlab.py`.

## Risks

- LLaMA-Factory template name / architecture support for Qwen3.5 is new —
  verified on the machine during setup; Unsloth is the fallback.
- vLLM's pinned `transformers` may conflict with the `transformers@main` the
  model card requires — hence two isolated venvs.
- Cloudflare tunnel latency/stability affects eval wall-clock, not correctness;
  the driver uses generous Playwright timeouts.
