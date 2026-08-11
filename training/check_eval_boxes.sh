#!/usr/bin/env bash
# Preflight every eval box at once: report GPU, driver, CUDA toolkit, disk, and
# exactly which wheels vast_setup.sh will choose there.
#
#   bash training/check_eval_boxes.sh 1.2.3.4:25639 5.6.7.8:12345 ...
#   bash training/check_eval_boxes.sh --site-url https://<tunnel> <host:port>   # also test reachability
#
# Why this exists: a CUDA mismatch on this pipeline does not announce itself, it
# just costs hours.
#   - torch installed from the wrong index reports `no CUDA` (a cu13 wheel on a
#     12.x driver) or refuses to compile causal-conv1d (a cu128 wheel against a
#     13.2 nvcc), and without causal-conv1d every Qwen3.5 GDN layer silently
#     falls back to plain torch -- measured 2.3x slower, with the GPU oscillating
#     0-100%% at 130-200 W instead of a steady 100%% / 630 W.
#   - vLLM ships precompiled kernels, so the wheel's CUDA major is what matters,
#     not torch's. 0.18.0 is the only release that is both cu12 and aware of
#     Qwen3.5; on a CUDA-13 box the unpinned release is the correct one, and the
#     cu12 build on Hopper + CUDA 12 reaches READY and then dies on its first
#     request when flashinfer JIT-compiles gdn_prefill_sm90 against a mismatched
#     toolkit.
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
echo "Notes:"
echo "  DISK   needs ~45 GB free: base model 19 GB + merged model 19 GB + venvs ~6 GB."
echo "  NVCC   'none' means causal-conv1d cannot be compiled at all -> Qwen3.5's GDN"
echo "         fast path stays off (~2.3x slower). Pick a box with a CUDA toolkit."
echo "  SM     the compute capability vast_setup.sh passes as TORCH_CUDA_ARCH_LIST,"
echo "         so causal-conv1d builds one architecture (~7 min) not nine (~1 h)."
echo "  A CUDA-12 box with a Hopper GPU (SM 9.0) is the one known-bad combination:"
echo "         vLLM reaches READY and dies on the first request. Prefer CUDA 13 there."

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
