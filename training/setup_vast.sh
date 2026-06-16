#!/usr/bin/env bash
# ==========================================================================
# Setup script for vast.ai instance
# Run once on fresh vast.ai instance BEFORE training:
#   chmod +x setup_vast.sh && ./setup_vast.sh
# ==========================================================================
set -euo pipefail

echo "=== 1. System info ==="
nvidia-smi || echo "NO GPU FOUND - abort"
python3 --version || (apt-get update && apt-get install -y python3 python3-pip)
echo ""

echo "=== 2. Upgrade pip ==="
pip install --upgrade pip setuptools wheel
echo ""

echo "=== 3. Install PyTorch with CUDA 12.1 ==="
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
echo ""

echo "=== 4. Install training dependencies ==="
pip install transformers>=4.45.0 datasets>=2.18.0 accelerate>=0.28.0
pip install trl>=0.8.0 peft>=0.10.0 bitsandbytes>=0.42.0
pip install wandb
echo ""

echo "=== 5. Install flash-attn (pre-built wheel) ==="
# flash-attn takes 10-20 min to compile from source. Use pre-built if available.
pip install flash-attn --no-build-isolation 2>/dev/null || {
    echo "flash-attn wheel not available, will skip (falls back to sdpa)"
}
echo ""

echo "=== 6. Verify critical imports ==="
python3 -c "
import torch; print(f'PyTorch {torch.__version__}, CUDA available: {torch.cuda.is_available()}')
print(f'GPU count: {torch.cuda.device_count()}')
for i in range(torch.cuda.device_count()):
    print(f'  GPU {i}: {torch.cuda.get_device_name(i)}, {torch.cuda.get_device_properties(i).total_mem/1024**3:.1f} GB')
import transformers; print(f'Transformers {transformers.__version__}')
import trl; print(f'TRL {trl.__version__}')
import peft; print(f'PEFT {peft.__version__}')
try:
    import flash_attn; print(f'Flash-Attn available')
except ImportError:
    print('Flash-Attn NOT available (will use sdpa)')
"
echo ""
echo "=== SETUP COMPLETE ==="
