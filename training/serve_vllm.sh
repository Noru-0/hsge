#!/usr/bin/env bash
# Serve a model with vLLM's OpenAI-compatible API on localhost.
#
#   bash training/serve_vllm.sh                                   # merged (finetuned) model
#   bash training/serve_vllm.sh /workspace/models/Qwen3.5-9B      # base model (baseline eval)
#
# Detached:  nohup bash training/serve_vllm.sh > /workspace/vllm.log 2>&1 &
# The served model name is always "qwen35-9b" so eval commands don't change
# between baseline and finetuned runs.
#
# The default model path must exist: it used to point at
# /workspace/models/Qwen3.5-9B-hsge, a path the current merge step never
# creates, so calling this with no argument silently served the BASE model and
# the eval that followed measured the wrong thing under the finetuned label.
# Guard against that by failing loudly instead.
set -euo pipefail

MODEL=${1:-/workspace/models/Qwen3.5-9B-all}
PORT=${2:-8000}

if [ ! -d "$MODEL" ]; then
    echo "ERROR: model dir does not exist: $MODEL" >&2
    echo "Merge the adapter first (training/merge_lora_peft.py), or pass the base" >&2
    echo "model path explicitly for a baseline run." >&2
    exit 1
fi
if [ ! -f "$MODEL/config.json" ]; then
    echo "ERROR: $MODEL has no config.json -- not a model directory" >&2
    exit 1
fi
echo "serving: $MODEL  (as 'qwen35-9b' on 127.0.0.1:$PORT)"

# --max-model-len 8192: the dataset's longest example is 4040 tokens by the real
# tokenizer, so this leaves ample room for the prompt plus generation without
# reserving KV cache the run cannot use.
exec /workspace/venvs/serve/bin/vllm serve "$MODEL" \
    --served-model-name qwen35-9b \
    --host 127.0.0.1 --port "$PORT" \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.85
