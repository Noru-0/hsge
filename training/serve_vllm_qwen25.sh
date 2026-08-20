#!/usr/bin/env bash
# Serve the Qwen2.5-7B-Instruct (merged) model with vLLM's OpenAI-compatible
# API on localhost. Adapted from serve_vllm.sh for Qwen2.5 instead of Qwen3.5.
#
#   bash training/serve_vllm_qwen25.sh                                        # merged (finetuned) model
#   bash training/serve_vllm_qwen25.sh /workspace/models/Qwen2.5-7B-Instruct   # base model (baseline eval)
#
# Detached:  nohup bash training/serve_vllm_qwen25.sh > /workspace/vllm.log 2>&1 &
# The served model name is always "qwen25-7b" so eval commands don't change
# between baseline and finetuned runs.
set -euo pipefail

MODEL=${1:-/workspace/models/Qwen2.5-7B-Instruct-merged-v1}
PORT=${2:-8000}

if [ ! -d "$MODEL" ]; then
    echo "ERROR: model dir does not exist: $MODEL" >&2
    echo "Merge the adapter first (training/merge_lora_peft_qwen25.py), or pass the base" >&2
    echo "model path explicitly for a baseline run." >&2
    exit 1
fi
if [ ! -f "$MODEL/config.json" ]; then
    echo "ERROR: $MODEL has no config.json -- not a model directory" >&2
    exit 1
fi
echo "serving: $MODEL  (as 'qwen25-7b' on 127.0.0.1:$PORT)"

# --max-model-len 8192: same margin used for the Qwen3.5 pipeline (training's
# longest example is 3829 tokens by the real tokenizer, see
# qwen25_7b_lora_merged_v1.yaml); eval prompts can run longer with full
# history, so this leaves room without reserving KV cache the run cannot use.
exec /workspace/venvs/serve/bin/vllm serve "$MODEL" \
    --served-model-name qwen25-7b \
    --host 127.0.0.1 --port "$PORT" \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.85
