#!/usr/bin/env bash
# One-time environment setup for finetuning Qwen2.5-7B-Instruct on a vast.ai
# GPU instance. Trimmed version of vast_setup.sh: Qwen2.5-7B-Instruct is a
# plain dense GQA transformer, so it needs none of the Gated-DeltaNet-specific
# packages (flash-linear-attention, tilelang, causal-conv1d) that vast_setup.sh
# installs for Qwen3.5-9B.
#
# Creates two isolated uv venvs under /workspace/venvs:
#   train — LLaMA-Factory + torch
#   serve — vLLM (OpenAI-compatible server) + peft (for adapter merge)
# and downloads Qwen/Qwen2.5-7B-Instruct to /workspace/models/Qwen2.5-7B-Instruct.
#
# Idempotent: each stage writes a marker file and is skipped when it exists.
# Run detached:  nohup bash vast_setup_qwen25.sh > /workspace/setup_qwen25.log 2>&1 &

set -uo pipefail

BASE=/workspace
VENVS=$BASE/venvs
MARKERS=$BASE/.setup_markers_qwen25
export HF_HOME=$BASE/.hf_home
mkdir -p "$VENVS" "$MARKERS" "$BASE/models" "$HF_HOME"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

stage() {  # stage <name> <command...>
    local name=$1; shift
    if [ -f "$MARKERS/$name" ]; then
        log "SKIP $name (marker exists)"
        return 0
    fi
    log "BEGIN $name"
    if "$@"; then
        touch "$MARKERS/$name"
        log "OK $name"
    else
        log "FAIL $name (exit $?)"
        return 1
    fi
}

if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

make_venv() { [ -d "$VENVS/$1" ] || uv venv "$VENVS/$1" --python 3.12; }

# Same torch-pin logic as vast_setup.sh: match the box's nvcc CUDA major so
# torch's cpp_extension (used by any package that compiles) doesn't refuse to
# build, and keep torch/torchvision/torchaudio in the same release family.
_install_torch() {  # _install_torch <venv>
    local venv=$1 CUDA_MAJOR
    CUDA_MAJOR=$(nvcc --version 2>/dev/null | grep -oE 'release [0-9]+' | grep -oE '[0-9]+' | head -1)
    if [ "${CUDA_MAJOR:-12}" -ge 13 ]; then
        log "nvcc reports CUDA $CUDA_MAJOR -> installing torch 2.11.0+cu130"
        uv pip install --python "$VENVS/$venv/bin/python" \
            --reinstall-package torch --reinstall-package torchvision --reinstall-package torchaudio \
            "torch==2.11.0+cu130" "torchvision==0.26.0+cu130" "torchaudio==2.11.0+cu130" \
            --index-url https://download.pytorch.org/whl/cu130 || return 1
    else
        log "nvcc reports CUDA ${CUDA_MAJOR:-unknown} -> installing torch 2.11.0+cu128"
        uv pip install --python "$VENVS/$venv/bin/python" \
            --reinstall-package torch --reinstall-package torchvision --reinstall-package torchaudio \
            torch==2.11.0 torchvision torchaudio==2.11.0+cu128 \
            --index-url https://download.pytorch.org/whl/cu128 || return 1
    fi
}

# --- train venv: LLaMA-Factory -----------------------------------------------
setup_train() {
    make_venv train
    if [ ! -d "$BASE/LLaMA-Factory" ]; then
        git clone --depth 1 https://github.com/hiyouga/LLaMA-Factory.git "$BASE/LLaMA-Factory" || return 1
    fi
    uv pip install --python "$VENVS/train/bin/python" -e "$BASE/LLaMA-Factory[torch,metrics]" || return 1
    _install_torch train || return 1
    "$VENVS/train/bin/python" -c "
import torch, torchaudio, torchvision
assert torch.cuda.is_available(), 'no CUDA'
print('torch', torch.__version__, 'cuda', torch.version.cuda,
      '| torchaudio', torchaudio.__version__, '| torchvision', torchvision.__version__)" || return 1
}

# --- serve venv: vLLM --------------------------------------------------------
setup_serve() {
    make_venv serve
    local CUDA_MAJOR
    CUDA_MAJOR=$(nvcc --version 2>/dev/null | grep -oE 'release [0-9]+' | grep -oE '[0-9]+' | head -1)
    if [ "${CUDA_MAJOR:-12}" -ge 13 ]; then
        log "nvcc reports CUDA $CUDA_MAJOR -> installing unpinned vllm (cu13)"
        uv pip install --python "$VENVS/serve/bin/python" vllm "huggingface_hub[cli]" || return 1
    else
        log "nvcc reports CUDA ${CUDA_MAJOR:-unknown} -> pinning vllm==0.18.0 (cu12)"
        uv pip install --python "$VENVS/serve/bin/python" "vllm==0.18.0" "huggingface_hub[cli]" || return 1
    fi
    uv pip install --python "$VENVS/serve/bin/python" peft || return 1
    "$VENVS/serve/bin/python" -c "
import torch, vllm, peft
from vllm.model_executor.models.registry import ModelRegistry
assert torch.cuda.is_available(), 'no CUDA'
assert 'Qwen2ForCausalLM' in ModelRegistry.get_supported_archs(), 'vllm lacks Qwen2.5'
print('vllm', vllm.__version__, 'torch', torch.__version__, 'peft', peft.__version__)"
}

# --- model download -----------------------------------------------------------
download_model() {
    "$VENVS/serve/bin/hf" download Qwen/Qwen2.5-7B-Instruct --local-dir "$BASE/models/Qwen2.5-7B-Instruct" || return 1
    ls -lh "$BASE/models/Qwen2.5-7B-Instruct" | head
}

MODE=${1:-all}
case "$MODE" in
    all)
        stage train_venv setup_train
        stage serve_venv setup_serve
        stage model_download download_model
        ;;
    *)
        echo "usage: bash vast_setup_qwen25.sh [all]" >&2
        exit 2
        ;;
esac

log "SETUP COMPLETE"
