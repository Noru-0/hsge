#!/usr/bin/env bash
# One-time environment setup for the vast.ai GPU instance.
#
# Creates three isolated uv venvs under /workspace/venvs (deliberately separate:
# vLLM pins transformers, while Qwen3.5 training needs transformers@main, and
# the eval driver needs neither):
#   train — LLaMA-Factory (git main) + transformers@main + flash-linear-attention
#   serve — vLLM (OpenAI-compatible server)
#   eval  — browsergym-webarena + Playwright/Chromium + openai client
# and downloads Qwen/Qwen3.5-9B to /workspace/models/Qwen3.5-9B.
#
# Idempotent: each stage writes a marker file and is skipped when it exists.
# Run detached:  nohup bash vast_setup.sh > /workspace/setup.log 2>&1 &

set -uo pipefail

BASE=/workspace
VENVS=$BASE/venvs
MARKERS=$BASE/.setup_markers
export HF_HOME=$BASE/hf
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

# uv ships with the vast base image; fall back to installing it if missing.
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

make_venv() { [ -d "$VENVS/$1" ] || uv venv "$VENVS/$1" --python 3.12; }

# --- train venv: LLaMA-Factory + transformers@main -------------------------
setup_train() {
    make_venv train
    if [ ! -d "$BASE/LLaMA-Factory" ]; then
        git clone --depth 1 https://github.com/hiyouga/LLaMA-Factory.git "$BASE/LLaMA-Factory" \
            || git clone --depth 1 https://github.com/hiyouga/LlamaFactory.git "$BASE/LLaMA-Factory" \
            || return 1
    fi
    uv pip install --python "$VENVS/train/bin/python" -e "$BASE/LLaMA-Factory[torch,metrics]" || return 1
    # Pin the torch CUDA build. Left to resolve freely, uv installs the newest
    # PyPI wheel (torch 2.13.0+cu130), which needs a CUDA 13 driver; a box with a
    # 12.x driver (e.g. 560.35.03 / CUDA 12.6) then reports no CUDA at all.
    # cu128 is the newest CUDA-12 build and runs on both 12.x (minor-version
    # compatibility) and 13.x (drivers are backward compatible) drivers.
    # All three must be pinned together: leaving torchaudio on its cu130 wheel
    # makes `import torchaudio` fail to load _torchaudio.abi3.so, which breaks
    # llamafactory-cli itself.
    uv pip install --python "$VENVS/train/bin/python" \
        --reinstall-package torchaudio \
        torch==2.11.0 torchvision torchaudio==2.11.0+cu128 \
        --index-url https://download.pytorch.org/whl/cu128 || return 1
    # transformers is left at whatever LLaMA-Factory resolves (5.8.0 at the time
    # of writing). This used to install transformers@main because Qwen3.5 was
    # only on the main branch; it is in released transformers now
    # (models/qwen3_5), and main (5.15.0.dev0) violates LLaMA-Factory's own
    # `transformers<=5.8.0` check, which aborts llamafactory-cli at import time.
    # Triton kernels for the Gated DeltaNet layers (much faster than the eager
    # fallback); best-effort — training still works without it.
    uv pip install --python "$VENVS/train/bin/python" flash-linear-attention \
        || log "WARN flash-linear-attention install failed; GDN layers will use the slow eager path"
    # tilelang supplies the GDN backward kernels. Required on Hopper (H100):
    # the triton 3.6.0 that ships with torch 2.11 computes gated chunk_bwd_dqkwg
    # incorrectly there, and flash-linear-attention hard-aborts training rather
    # than emit wrong gradients (fla issue #640) unless tilelang is present.
    uv pip install --python "$VENVS/train/bin/python" tilelang \
        || log "WARN tilelang install failed; fla will abort on Hopper with triton < 3.7.1"
    "$VENVS/train/bin/python" -c "import torch; assert torch.cuda.is_available(), 'no CUDA'; print('torch', torch.__version__)"
}

# --- serve venv: vLLM -------------------------------------------------------
setup_serve() {
    make_venv serve
    # vllm is pinned rather than -U for the same driver reason as torch above,
    # but here swapping torch is not enough: vLLM ships its own compiled kernels,
    # so the wheel's CUDA major is what matters. 0.18.0 is the newest release
    # still built against CUDA 12 (torch 2.10.0+cu128); 0.20.0+ moved to CUDA 13
    # and cannot run on a 12.x driver at all. 0.18.0 is also the oldest release
    # that registers Qwen3_5ForConditionalGeneration -- 0.14.0 knows only
    # Qwen3Next -- so the usable window for this model on a CUDA-12 box is
    # narrow. On a CUDA-13 box, plain `-U vllm` is fine.
    uv pip install --python "$VENVS/serve/bin/python" "vllm==0.18.0" "huggingface_hub[cli]" || return 1
    "$VENVS/serve/bin/python" -c "
import torch, vllm
from vllm.model_executor.models.registry import ModelRegistry
assert torch.cuda.is_available(), 'no CUDA'
assert 'Qwen3_5ForConditionalGeneration' in ModelRegistry.get_supported_archs(), 'vllm lacks Qwen3.5'
print('vllm', vllm.__version__, 'torch', torch.__version__)"
}

# --- eval venv: BrowserGym WebArena + Playwright ----------------------------
setup_eval() {
    make_venv eval
    uv pip install --python "$VENVS/eval/bin/python" \
        browsergym-webarena playwright openai requests python-dotenv numpy pyyaml || return 1
    "$VENVS/eval/bin/python" -m playwright install --with-deps chromium || return 1
    "$VENVS/eval/bin/python" -c "import browsergym.webarena; print('browsergym-webarena ok')"
}

# --- model download ----------------------------------------------------------
download_model() {
    "$VENVS/serve/bin/hf" download Qwen/Qwen3.5-9B --local-dir "$BASE/models/Qwen3.5-9B" || return 1
    ls -lh "$BASE/models/Qwen3.5-9B" | head
}

stage train_venv setup_train
stage serve_venv setup_serve
stage eval_venv  setup_eval
stage model_download download_model

log "SETUP COMPLETE"
