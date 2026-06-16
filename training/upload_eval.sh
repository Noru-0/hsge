#!/usr/bin/env bash
# ==========================================================================
# Upload eval files to vast.ai instance
#
# Prerequisites:
#   1. SSH key added to vast.ai
#   2. Training complete → LoRA checkpoint at training/outputs/qwen_7b_hsge_agent/final_checkpoint/
#
# Usage:
#   chmod +x upload_eval.sh
#   ./upload_eval.sh
# ==========================================================================
set -euo pipefail

VAST_SSH="ssh -p 48574 root@146.115.17.155"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$LOCAL_DIR")"
WEBARENA_DIR="$PROJECT_DIR/webarena-main"
TRAINING_OUTPUT="$PROJECT_DIR/training/outputs/qwen_7b_hsge_agent/final_checkpoint"

echo "=== Uploading eval files to vast.ai ==="
echo "SSH: $VAST_SSH"
echo ""

# ---- 1. Test connection ----
echo "Step 1: Testing SSH connection..."
$VAST_SSH "echo 'SSH OK' && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader" || {
    echo "ERROR: Cannot connect to vast.ai."
    exit 1
}
echo ""

# ---- 2. Create remote directories ----
echo "Step 2: Creating remote directories..."
$VAST_SSH "mkdir -p /root/webarena-main /root/final_checkpoint"
echo ""

# ---- 3. Upload LoRA checkpoint ----
echo "Step 3: Uploading LoRA checkpoint..."
if [ -d "$TRAINING_OUTPUT" ]; then
    scp -r -P 48574 "$TRAINING_OUTPUT"/* root@146.115.17.155:/root/final_checkpoint/
else
    echo "WARNING: LoRA checkpoint not found at $TRAINING_OUTPUT"
    echo "Upload your checkpoint manually to /root/final_checkpoint/"
fi
echo ""

# ---- 4. Upload patched webarena-main ----
echo "Step 4: Uploading patched webarena-main..."
# Upload key files only (not media/, tests/, etc.)
FILES_TO_UPLOAD=(
    "run.py"
    "agent/agent.py"
    "agent/prompts/prompt_constructor.py"
    "agent/prompts/to_json.py"
    "agent/prompts/raw/p_hsge_actree_2s.py"
    "agent/prompts/raw/p_cot_id_actree_2s.py"
    "browser_env/env_config.py"
    "browser_env/auto_login.py"
    "llms/lm_config.py"
    "llms/utils.py"
    "llms/providers/openai_utils.py"
    "llms/tokenizers.py"
    "scripts/filter_shopping.py"
)

for f in "${FILES_TO_UPLOAD[@]}"; do
    # Create parent dir on remote
    $VAST_SSH "mkdir -p /root/webarena-main/\$(dirname '$f')"
    scp -P 48574 "$WEBARENA_DIR/$f" "root@146.115.17.155:/root/webarena-main/$f"
done
echo ""

# ---- 5. Upload eval script ----
echo "Step 5: Uploading setup_eval.sh..."
scp -P 48574 "$LOCAL_DIR/setup_eval.sh" root@146.115.17.155:/root/
echo ""

echo "=== UPLOAD COMPLETE ==="
echo ""
echo "Next steps on vast.ai:"
echo "  1. SSH in:   ssh -p 48574 root@146.115.17.155"
echo "  2. Run eval: cd /root && bash setup_eval.sh"
