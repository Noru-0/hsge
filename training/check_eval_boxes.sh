#!/usr/bin/env bash
# Preflight every eval box at once: report GPU, driver, CUDA toolkit, disk, and
# exactly which wheels vast_setup.sh will choose there.
#
#   bash training/check_eval_boxes.sh 1.2.3.4:25639 5.6.7.8:12345 ...
#   bash training/check_eval_boxes.sh --site-url https://<tunnel> <host:port>   # also test reachability
#
# Why this exists: a CUDA mismatch on this pipeline does not announce itself, it
# just costs hours. On an EVAL box the binding constraint is **vLLM**, not torch:
# the eval driver is an HTTP client against vLLM's OpenAI endpoint, so vLLM's own
# precompiled kernels do the work and the wheel's CUDA major is what decides
# whether the server survives.
#
#   - CUDA 13 + any GPU: unpinned vLLM. Proven in this repo (A100-80GB, driver
#     595.71.05, CUDA 13.2) -- survived its first request and a full smoke run.
#   - CUDA 12 + SM 8.x (A100): needs `vllm==0.18.0`, the only release that is both
#     cu12 and aware of Qwen3.5 (0.14.0 knows only Qwen3Next; 0.20.0+ is cu13).
#     A narrow window, but it works.
#   - CUDA 12 + SM 9.0 (H100/Hopper): KNOWN BROKEN. vLLM reaches READY and then
#     exits on the first completion request, because flashinfer JIT-compiles
#     gdn_prefill_sm90 at run time and fails ("fatal error: cuda/ptx") on an image
#     with no CCCL headers. Do not try to symlink CCCL from pip -- that was
#     attempted and made it worse. Use a CUDA-13 box instead.
#
# NOTE the torch/nvcc story below matters for a TRAINING box, not this one:
# `vast_setup.sh eval` skips the train venv entirely, so causal-conv1d is never
# built here and the Qwen3.5 GDN fast path in transformers is not on the eval
# path at all. nvcc is reported because it is what selects the vLLM wheel.
#
# vast_setup.sh now picks by `nvcc` automatically; this script shows you what it
# will pick BEFORE you spend 40 minutes per box finding out.
set -uo pipefail

SITE_URL=""
BOXES=()
while [ $# -gt 0 ]; do
    case "$1" in
        --site-url) SITE_URL=$2; shift 2 ;;
        *) BOXES+=("$1"); shift ;;
    esac
done
[ ${#BOXES[@]} -gt 0 ] || { echo "usage: $0 [--site-url URL] host:port [host:port ...]" >&2; exit 2; }

printf '%-22s %-26s %-10s %-8s %-6s %-9s %-9s %s\n' \
    BOX GPU DRIVER NVCC SM DISK TORCH VLLM
printf '%.0s-' {1..118}; echo

for box in "${BOXES[@]}"; do
    host=${box%:*}; port=${box##*:}
    [ "$host" = "$port" ] && port=22
    out=$(ssh -p "$port" -o BatchMode=yes -o ConnectTimeout=12 \
              -o StrictHostKeyChecking=accept-new "root@$host" '
        gpu=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        drv=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
        nvcc_v=$(nvcc --version 2>/dev/null | grep -oE "release [0-9]+\.[0-9]+" | grep -oE "[0-9]+\.[0-9]+" | head -1)
        # Compute capability decides the causal-conv1d arch flag; without it the
        # build compiles 9 architectures instead of 1.
        sm=$(python3 -c "import torch;print(\"%d.%d\"%torch.cuda.get_device_capability(0))" 2>/dev/null \
             || nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1)
        disk=$(df -BG /workspace 2>/dev/null | tail -1 | awk "{print \$4}")
        [ -z "$disk" ] && disk=$(df -BG / | tail -1 | awk "{print \$4}")
        echo "$gpu|$drv|$nvcc_v|$sm|$disk"' 2>/dev/null)

    if [ -z "$out" ]; then
        printf '%-22s %s\n' "$box" "UNREACHABLE (check host/port/ssh key)"
        continue
    fi
    IFS='|' read -r gpu drv nvcc sm disk <<<"$out"
    major=${nvcc%%.*}
    if [ -z "$nvcc" ]; then
        torch="?? no nvcc"; vllm="?? no nvcc"
    elif [ "${major:-12}" -ge 13 ]; then
        torch="2.11.0+cu130"; vllm="unpinned"
    else
        torch="2.11.0+cu128"; vllm="==0.18.0"
    fi
    printf '%-22s %-26s %-10s %-8s %-6s %-9s %-9s %s\n' \
        "$box" "${gpu:0:26}" "${drv:-?}" "${nvcc:-none}" "${sm:-?}" "${disk:-?}" "$torch" "$vllm"
done

echo
echo "Notes (EVAL box: the constraint is vLLM, not torch -- eval mode builds no"
echo "train venv and never compiles causal-conv1d):"
echo "  DISK   needs ~45 GB free: base model 19 GB + merged model 19 GB + venvs."
echo "  NVCC   selects the vLLM wheel. 'none' means the selection falls back to the"
echo "         cu12 pin, which is wrong on a CUDA-13 box -- install a toolkit or"
echo "         pass the version by hand."
echo "  BEST   CUDA 13.x + any GPU -> unpinned vLLM. Proven here on A100-80GB /"
echo "         driver 595.71.05 / CUDA 13.2."
echo "  OK     CUDA 12.x + SM 8.x (A100) -> vllm==0.18.0, a narrow but working window."
echo "  AVOID  CUDA 12.x + SM 9.0 (H100/Hopper) -> vLLM reaches READY then dies on"
echo "         the first request (flashinfer JIT of gdn_prefill_sm90, no CCCL headers)."
echo "         On SM 8.0 that kernel is not the code path, which is why A100 is fine."

if [ -n "$SITE_URL" ]; then
    echo
    echo "=== reachability of $SITE_URL FROM each box ==="
    echo "(local reachability proves nothing -- the tunnel must work from the box)"
    for box in "${BOXES[@]}"; do
        host=${box%:*}; port=${box##*:}
        [ "$host" = "$port" ] && port=22
        code=$(ssh -p "$port" -o BatchMode=yes -o ConnectTimeout=12 "root@$host" \
               "curl -s -o /dev/null -w '%{http_code} %{time_starttransfer}s' --max-time 30 '$SITE_URL'" 2>&1)
        printf '  %-22s %s\n' "$box" "${code:-unreachable}"
    done
fi
