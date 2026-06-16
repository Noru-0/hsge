#!/usr/bin/env bash
# ==========================================================================
# Launch training on vast.ai
#
# Usage (on vast.ai instance):
#   chmod +x run_train.sh
#   ./run_train.sh
#
# Or with wandb:
#   export WANDB_API_KEY="your_key"
#   ./run_train.sh
# ==========================================================================
set -euo pipefail

# ---- Config ----
DATA_FILE="${1:-train.jsonl}"
OUTPUT_DIR="${2:-outputs/qwen_7b_hsge_agent}"

echo "=== Training Qwen2.5-7B-Instruct (LoRA) ==="
echo "Data: $DATA_FILE"
echo "Output: $OUTPUT_DIR"
echo ""

# ---- If WANDB_API_KEY is set, use wandb; otherwise skip ----
WANDB_FLAG=""
if [ -n "${WANDB_API_KEY:-}" ]; then
    echo "W&B logging enabled (project: hsge-agent)"
else
    WANDB_FLAG="--no-wandb"
    echo "W&B disabled (set WANDB_API_KEY to enable)"
fi

# ---- Launch ----
python3 train_qwen_sft.py \
    --data "$DATA_FILE" \
    --output "$OUTPUT_DIR" \
    --lora \
    --epochs 2 \
    --batch-size 1 \
    --grad-accum 4 \
    --lr 2e-5 \
    $WANDB_FLAG

echo ""
echo "=== Training complete ==="
echo "Model saved to: $OUTPUT_DIR/final_checkpoint"
