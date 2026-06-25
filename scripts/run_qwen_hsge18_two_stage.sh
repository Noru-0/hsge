#!/usr/bin/env bash
set -euo pipefail

cd /workspace/hsge
source /venv/main/bin/activate

export HF_HOME=/workspace/.hf_home
export PYTHONPATH=.
export BASE_MODEL=${BASE_MODEL:-Qwen/Qwen2.5-7B-Instruct}
export MAX_SEQ_LENGTH=${MAX_SEQ_LENGTH:-8192}
export NUM_TRAIN_EPOCHS=${NUM_TRAIN_EPOCHS:-3}
export TRAIN_BATCH_SIZE=${TRAIN_BATCH_SIZE:-1}
export EVAL_BATCH_SIZE=${EVAL_BATCH_SIZE:-1}
export GRAD_ACCUM_STEPS=${GRAD_ACCUM_STEPS:-8}
export LEARNING_RATE=${LEARNING_RATE:-2e-4}
export LOGGING_STEPS=${LOGGING_STEPS:-5}
export SAVE_TOTAL_LIMIT=${SAVE_TOTAL_LIMIT:-2}

SINGLE_OUT=${SINGLE_OUT:-outputs/lora/qwen25_7b_hsge18_singleturn}
MULTI_OUT=${MULTI_OUT:-outputs/lora/qwen25_7b_hsge18_singleturn_multiturn}

echo "=== Stage 1: hsge18 single-turn ==="
export TRAIN_FILE=data/sft_hsge18/single18_train.jsonl
export DEV_FILE=data/sft_hsge18/single18_dev.jsonl
export OUTPUT_DIR="$SINGLE_OUT"
export EVAL_STEPS=${SINGLE_EVAL_STEPS:-50}
export SAVE_STEPS=${SINGLE_SAVE_STEPS:-100}
unset PEFT_MODEL_PATH
accelerate launch scripts/train_qwen_webarena_json_lora.py

echo "=== Stage 2: hsge18 multi-turn ==="
export PEFT_MODEL_PATH="$SINGLE_OUT"
export TRAIN_FILE=data/sft_hsge18/multi18_train.jsonl
export DEV_FILE=data/sft_hsge18/multi18_dev.jsonl
export OUTPUT_DIR="$MULTI_OUT"
export EVAL_STEPS=${MULTI_EVAL_STEPS:-25}
export SAVE_STEPS=${MULTI_SAVE_STEPS:-50}
accelerate launch scripts/train_qwen_webarena_json_lora.py

echo "=== Done ==="
echo "Single-turn adapter: $SINGLE_OUT"
echo "Final multi-turn adapter: $MULTI_OUT"
