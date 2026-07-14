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
    # Qwen3.5 model card requires transformers main; override LLaMA-Factory's pin.
    uv pip install --python "$VENVS/train/bin/python" \
        "transformers @ git+https://github.com/huggingface/transformers.git@main" || return 1
    # Triton kernels for the Gated DeltaNet layers (much faster than the eager
    # fallback); best-effort — training still works without it.
    uv pip install --python "$VENVS/train/bin/python" flash-linear-attention \
        || log "WARN flash-linear-attention install failed; GDN layers will use the slow eager path"
    "$VENVS/train/bin/python" -c "import torch; assert torch.cuda.is_available(), 'no CUDA'; print('torch', torch.__version__)"
}

# --- serve venv: vLLM -------------------------------------------------------
setup_serve() {
    make_venv serve
    uv pip install --python "$VENVS/serve/bin/python" -U vllm "huggingface_hub[cli]" || return 1
    "$VENVS/serve/bin/python" -c "import vllm; print('vllm', vllm.__version__)"
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
