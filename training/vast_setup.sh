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
    # Pin the torch CUDA build to match the box's nvcc, and pin all three of
    # torch/torchvision/torchaudio to the SAME release family.
    #
    # Why match nvcc and not just the driver: `causal-conv1d` has no prebuilt
    # wheel and must compile, and torch's cpp_extension refuses to build when
    # torch.version.cuda differs from the nvcc it finds. Without causal-conv1d,
    # transformers' `is_fast_path_available` for Qwen3.5 is False -- it requires
    # ALL of causal_conv1d_fn/_update + chunk_gated_delta_rule +
    # fused_recurrent_gated_delta_rule -- so *every* Gated DeltaNet layer falls
    # back to plain torch. Measured on an H100: 30-33 s/step with the GPU
    # oscillating 0-100% at 130-200 W, versus 13 s/step at a steady 100% / 630 W
    # once the fast path is on. 2.3x, for one missing package.
    #
    # Why the family pin: torchaudio's newest release is 2.11.0, so asking for
    # plain `torch` on the cu130 index resolves torch to 2.13.0 and leaves
    # torchaudio at 2.11.0 -- an ABI mismatch that breaks `import torchaudio`,
    # which breaks llamafactory-cli itself. torch 2.11.0 exists on BOTH the
    # cu128 and cu130 indexes, so the same known-good version works either way.
    local CUDA_MAJOR TORCH_IDX TV_VER
    CUDA_MAJOR=$(nvcc --version 2>/dev/null | grep -oE 'release [0-9]+' | grep -oE '[0-9]+' | head -1)
    if [ "${CUDA_MAJOR:-12}" -ge 13 ]; then
        TORCH_IDX=cu130; TV_VER=0.26.0+cu130
        log "nvcc reports CUDA $CUDA_MAJOR -> installing torch 2.11.0+cu130"
        uv pip install --python "$VENVS/train/bin/python" \
            --reinstall-package torch --reinstall-package torchvision \
            --reinstall-package torchaudio \
            "torch==2.11.0+cu130" "torchvision==$TV_VER" "torchaudio==2.11.0+cu130" \
            --index-url https://download.pytorch.org/whl/cu130 || return 1
    else
        log "nvcc reports CUDA ${CUDA_MAJOR:-unknown} -> installing torch 2.11.0+cu128"
        uv pip install --python "$VENVS/train/bin/python" \
            --reinstall-package torch --reinstall-package torchvision \
            --reinstall-package torchaudio \
            torch==2.11.0 torchvision torchaudio==2.11.0+cu128 \
            --index-url https://download.pytorch.org/whl/cu128 || return 1
    fi
    # NEVER uninstall the nvidia-*-cu12 packages to "clean up" after switching
    # index: several of them install to the same paths as their cu13 twins at the
    # same version (nvidia-nvshmem 3.4.5 is one), so uninstalling the cu12 one
    # deletes the shared .so files and leaves the cu13 package's metadata
    # pointing at nothing -- torch then dies with
    # `ImportError: libnvshmem_host.so.3: cannot open shared object file`.
    # A --reinstall-package of the torch trio, as above, replaces the nvidia deps
    # correctly on its own; leftover cu12 wheels are inert.
    "$VENVS/train/bin/python" -c "
import torch, torchaudio, torchvision
assert torch.cuda.is_available(), 'no CUDA'
print('torch', torch.__version__, 'cuda', torch.version.cuda,
      '| torchaudio', torchaudio.__version__, '| torchvision', torchvision.__version__)" || return 1
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
    # causal-conv1d is the last piece of Qwen3.5's fast path (see the torch pin
    # above for why it is worth 2.3x). It ships no wheel, so it compiles here --
    # ~7 min for the one arch below. Do NOT leave TORCH_CUDA_ARCH_LIST unset:
    # the default builds 9 architectures (sm_75 through sm_121), 9x the work for
    # a box that has exactly one GPU model. Detect it instead.
    local SM
    SM=$("$VENVS/train/bin/python" -c "import torch;print('%d.%d'%torch.cuda.get_device_capability(0))" 2>/dev/null)
    if [ -n "$SM" ]; then
        log "building causal-conv1d for sm_${SM/./} only"
        TORCH_CUDA_ARCH_LIST="$SM" MAX_JOBS="$(nproc)" \
            uv pip install --python "$VENVS/train/bin/python" causal-conv1d --no-build-isolation \
            || log "WARN causal-conv1d install failed; Qwen3.5 GDN layers fall back to plain torch (~2.3x slower)"
    else
        log "WARN could not detect GPU arch; skipping causal-conv1d"
    fi
    # Report the fast path explicitly -- it is the difference between a 3 h and a
    # 7 h run, and the only in-band signal is a single warning line buried in the
    # training log ("The fast path is not available because one of the required
    # library is not installed").
    "$VENVS/train/bin/python" -c "
from transformers.models.qwen3_5.modeling_qwen3_5 import is_fast_path_available
print('Qwen3.5 GDN fast path:', 'ON' if is_fast_path_available else 'OFF (expect ~2.3x slower training)')" \
        || log "WARN could not query is_fast_path_available"
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
    # Pick by the box's CUDA major, the same way the torch pin above does: a
    # CUDA-12 box needs the pin (0.18.0 is the only release that is both cu12 and
    # aware of Qwen3.5), while pinning it on a CUDA-13 box installs the WRONG
    # wheel -- measured: unpinned vllm on CUDA 13.2 serves this model fine,
    # whereas the cu12 build on Hopper + CUDA 12 dies on its first request when
    # flashinfer JIT-compiles gdn_prefill_sm90 against a mismatched toolkit.
    local CUDA_MAJOR
    CUDA_MAJOR=$(nvcc --version 2>/dev/null | grep -oE 'release [0-9]+' | grep -oE '[0-9]+' | head -1)
    if [ "${CUDA_MAJOR:-12}" -ge 13 ]; then
        log "nvcc reports CUDA $CUDA_MAJOR -> installing unpinned vllm (cu13)"
        uv pip install --python "$VENVS/serve/bin/python" vllm "huggingface_hub[cli]" || return 1
    else
        log "nvcc reports CUDA ${CUDA_MAJOR:-unknown} -> pinning vllm==0.18.0 (cu12)"
        uv pip install --python "$VENVS/serve/bin/python" "vllm==0.18.0" "huggingface_hub[cli]" || return 1
    fi
    # peft is what lets an eval-only box merge the adapter (merge_lora_peft.py)
    # without building the train venv at all -- by far the slowest and most
    # fragile stage, and useless on a box that never trains.
    uv pip install --python "$VENVS/serve/bin/python" peft || return 1
    "$VENVS/serve/bin/python" -c "
import torch, vllm, peft
from vllm.model_executor.models.registry import ModelRegistry
assert torch.cuda.is_available(), 'no CUDA'
assert 'Qwen3_5ForConditionalGeneration' in ModelRegistry.get_supported_archs(), 'vllm lacks Qwen3.5'
print('vllm', vllm.__version__, 'torch', torch.__version__, 'peft', peft.__version__)"
}

# --- eval venv: BrowserGym WebArena + Playwright ----------------------------
setup_eval() {
    make_venv eval
    uv pip install --python "$VENVS/eval/bin/python" \
        browsergym-webarena playwright openai requests python-dotenv numpy pyyaml || return 1
    # `playwright install --with-deps` fails on Ubuntu 24.04 (noble): it asks apt
    # for `libasound2`, which noble renamed to `libasound2t64` as part of the
    # 64-bit time_t transition, and apt reports "Package 'libasound2' has no
    # installation candidate" -> exit 100 -> the whole eval venv stage fails.
    # Install the deps explicitly with the noble names, then fetch the browser
    # itself without --with-deps. `|| true` on apt because a box may already have
    # them (or be a distro where a name differs again) and Chromium's own launch
    # check below is the real gate.
    apt-get install -y --no-install-recommends \
        libnspr4 libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 \
        libatspi2.0-0t64 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
        libgbm1 libxkbcommon0 libpango-1.0-0 libcairo2 libasound2t64 \
        >/dev/null 2>&1 || log "WARN apt deps for chromium incomplete; launch check will tell"
    "$VENVS/eval/bin/python" -m playwright install chromium || return 1
    "$VENVS/eval/bin/python" -c "import browsergym.webarena; print('browsergym-webarena ok')" || return 1
    # Actually launch it: a missing shared library only surfaces on launch, and
    # discovering that six hours into a sweep is the expensive way to find out.
    "$VENVS/eval/bin/python" - <<'PY' || return 1
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(); page.set_content("<h1>ok</h1>")
    assert page.title() is not None
    b.close()
print("chromium launches ok")
PY
}

# --- model download ----------------------------------------------------------
download_model() {
    "$VENVS/serve/bin/hf" download Qwen/Qwen3.5-9B --local-dir "$BASE/models/Qwen3.5-9B" || return 1
    ls -lh "$BASE/models/Qwen3.5-9B" | head
}

# Mode selects which stages run. An eval-only box (serve + score a model trained
# elsewhere) does not need the train venv: it merges the adapter with
# training/merge_lora_peft.py, which needs only peft from the serve venv. Skipping
# it saves ~13 min per box and, more importantly, skips the entire class of
# environment breakage that stage carries (the torch/CUDA pin, flash-linear-
# attention, tilelang, and the causal-conv1d compile).
MODE=${1:-all}
case "$MODE" in
    all)
        stage train_venv setup_train
        stage serve_venv setup_serve
        stage eval_venv  setup_eval
        stage model_download download_model
        ;;
    eval)
        log "MODE=eval -> skipping the train venv (merge via merge_lora_peft.py)"
        stage serve_venv setup_serve
        stage eval_venv  setup_eval
        stage model_download download_model
        ;;
    *)
        echo "usage: bash vast_setup.sh [all|eval]" >&2
        exit 2
        ;;
esac

log "SETUP COMPLETE"
