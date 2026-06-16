#!/usr/bin/env bash
# ==========================================================================
# Package everything needed for the LoRA eval machine
# Run on local machine. Creates /tmp/hsge_eval_package.tar.gz
# Then upload to new vast.ai instance.
# ==========================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE="/tmp/hsge_eval_package.tar.gz"

echo "=== Packaging eval files ==="
echo "Project: $PROJECT_DIR"

cd "$PROJECT_DIR"

# Package: webarena-main (patched) + LoRA weights + setup script
tar czf "$PACKAGE" \
    --exclude='media' --exclude='tests' --exclude='resources' \
    --exclude='environment_docker' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.git' --exclude='.DS_Store' \
    webarena-main/ \
    training/outputs/qwen_7b_hsge_agent/final_checkpoint/ \
    training/setup_eval_vllm.sh

echo "Package: $PACKAGE ($(du -h "$PACKAGE" | cut -f1))"
echo ""
echo "=== Upload to new vast.ai instance ==="
echo ""
echo "Usage:"
echo "  1. Rent a GPU on vast.ai (>= 24 GB VRAM, any recent driver)"
echo "  2. Get SSH command: ssh -p <PORT> root@<IP>"
echo "  3. Upload package:"
echo "     scp -P <PORT> $PACKAGE root@<IP>:/root/"
echo "  4. SSH in and extract:"
echo "     ssh -p <PORT> root@<IP>"
echo "     cd /root && tar xzf hsge_eval_package.tar.gz"
echo "  5. Run setup + eval:"
echo "     bash /root/training/setup_eval_vllm.sh 2>&1 | tee /root/eval_lora.log"
