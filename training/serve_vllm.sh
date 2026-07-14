#!/usr/bin/env bash
# Serve a model with vLLM's OpenAI-compatible API on localhost.
#
#   bash training/serve_vllm.sh                                   # merged (finetuned) model
#   bash training/serve_vllm.sh /workspace/models/Qwen3.5-9B      # base model (baseline eval)
#
# Detached:  nohup bash training/serve_vllm.sh > /workspace/vllm.log 2>&1 &
# The served model name is always "qwen35-9b" so eval commands don't change
# between baseline and finetuned runs.
set -euo pipefail

MODEL=${1:-/workspace/models/Qwen3.5-9B-hsge}
PORT=${2:-8000}

exec /workspace/venvs/serve/bin/vllm serve "$MODEL" \
    --served-model-name qwen35-9b \
    --host 127.0.0.1 --port "$PORT" \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.85
