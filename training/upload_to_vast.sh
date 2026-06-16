#!/usr/bin/env bash
# ==========================================================================
# Upload training files to vast.ai instance
#
# Prerequisites:
#   1. Add your SSH public key to vast.ai: https://vast.ai/console/account/
#      cat ~/.ssh/id_ed25519.pub  (or ~/.ssh/id_rsa.pub)
#   2. Test connection:
#      ssh -p 48574 root@146.115.17.155 "nvidia-smi"
#
# Usage:
#   chmod +x upload_to_vast.sh
#   ./upload_to_vast.sh
# ==========================================================================
set -euo pipefail

VAST_SSH="ssh -p 48574 root@146.115.17.155"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$LOCAL_DIR")"

echo "=== Uploading training files to vast.ai ==="
echo "SSH: $VAST_SSH"
echo ""

# ---- 1. Test connection ----
echo "Step 1: Testing SSH connection..."
$VAST_SSH "echo 'SSH OK' && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader" || {
    echo "ERROR: Cannot connect to vast.ai."
    echo "Make sure your SSH public key is added at https://vast.ai/console/account/"
    echo "Your public key:"
    cat ~/.ssh/id_ed25519.pub 2>/dev/null || cat ~/.ssh/id_rsa.pub 2>/dev/null
    exit 1
}
echo ""

# ---- 2. Create remote directory ----
echo "Step 2: Creating remote directories..."
$VAST_SSH "mkdir -p /root/training /root/data"
echo ""

# ---- 3. Upload training scripts ----
echo "Step 3: Uploading training scripts..."
scp -P 48574 \
    "$LOCAL_DIR/train_qwen_sft.py" \
    "$LOCAL_DIR/setup_vast.sh" \
    "$LOCAL_DIR/run_train.sh" \
    "$LOCAL_DIR/requirements_train.txt" \
    root@146.115.17.155:/root/training/
echo ""

# ---- 4. Upload training data ----
echo "Step 4: Uploading train.jsonl (5 MB)..."
scp -P 48574 \
    "$PROJECT_DIR/temp/train.jsonl" \
    root@146.115.17.155:/root/data/train.jsonl
echo ""

# ---- 5. Upload validation script ----
echo "Step 5: Uploading validation script..."
scp -P 48574 \
    "$LOCAL_DIR/validate_data.py" \
    root@146.115.17.155:/root/training/
echo ""

echo "=== UPLOAD COMPLETE ==="
echo ""
echo "Next steps on vast.ai:"
echo "  1. SSH in:  ssh -p 48574 root@146.115.17.155"
echo "  2. Setup:   cd /root/training && bash setup_vast.sh"
echo "  3. Validate: python3 validate_data.py /root/data/train.jsonl"
echo "  4. Train:   bash run_train.sh /root/data/train.jsonl"
echo ""
echo "Or do it all in one go:"
echo "  ssh -p 48574 root@146.115.17.155 'cd /root/training && bash setup_vast.sh && python3 validate_data.py /root/data/train.jsonl && bash run_train.sh /root/data/train.jsonl'"
