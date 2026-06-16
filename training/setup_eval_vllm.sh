#!/usr/bin/env bash
# ==========================================================================
# Setup & eval LoRA model on new vast.ai instance with vLLM 0.8.x
#
# Prerequisites: copy these from old machine to /root/:
#   - webarena-main/  (code)
#   - training/outputs/qwen_7b_hsge_agent/final_checkpoint/  (LoRA weights)
# ==========================================================================
set -euo pipefail

echo "============================================"
echo "  LoRA Eval Setup (vLLM) - vast.ai"
echo "============================================"

# ---- 1. System check ----
echo ""
echo "=== Step 1: System check ==="
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
python3 --version

# ---- 2. Install vLLM 0.8.x (compatible with torch 2.5.x / CUDA 12.x) ----
echo ""
echo "=== Step 2: Install vLLM 0.8.x ==="
# vLLM 0.8.5 works with torch 2.5.x and CUDA 12.x (any driver >= 525)
pip3 install vllm==0.8.5 2>&1 | tail -5
python3 -c "import vllm; print(f'vLLM {vllm.__version__} OK')"

# ---- 3. Install other deps ----
echo ""
echo "=== Step 3: Other dependencies ==="
pip3 install openai 'browsergym-core>=0.5' 'browsergym-webarena>=0.5' -q 2>&1 | tail -3
playwright install chromium 2>&1 | tail -3
playwright install-deps chromium 2>&1 | tail -3

# ---- 4. Generate prompts & filter config ----
echo ""
echo "=== Step 4: Config ==="
cd /root/webarena-main
export SHOPPING="https://farmers-matched-dishes-vbulletin.trycloudflare.com"
export SHOPPING_ADMIN="https://farmers-matched-dishes-vbulletin.trycloudflare.com/admin"
export REDDIT="http://localhost:9999"
export GITLAB="http://localhost:8023"
export WIKIPEDIA="http://localhost:8888"
export MAP="http://localhost:3000"
export HOMEPAGE="http://localhost:4399"

PYTHONPATH=/root/webarena-main python3 agent/prompts/to_json.py
python3 -c "
import json, os
with open('config_files/test.raw.json') as f:
    all_tasks = json.load(f)
shopping = [t for t in all_tasks if t['sites'] == ['shopping']]
print(f'Shopping tasks: {len(shopping)}')
with open('config_files/test_shopping.json', 'w') as f:
    json.dump(shopping, f, indent=2)
for t in shopping:
    with open(f'config_files/{t[\"task_id\"]}.json', 'w') as out:
        json.dump(t, out, indent=2)
ids = [t['task_id'] for t in shopping]
print(f'Task IDs: {min(ids)} - {max(ids)}')
"

# Replace URL placeholders
for f in config_files/*.json; do
    sed -i "s|__SHOPPING__|$SHOPPING|g; s|__SHOPPING_ADMIN__|$SHOPPING_ADMIN|g" "$f" 2>/dev/null
done
echo "Config ready: 187 shopping tasks"

# ---- 5. Start vLLM server ----
echo ""
echo "=== Step 5: Start vLLM ==="
nohup vllm serve "Qwen/Qwen2.5-7B-Instruct" \
    --enable-lora \
    --lora-modules "hsge-agent=/root/training/outputs/qwen_7b_hsge_agent/final_checkpoint" \
    --max-model-len 16384 \
    --gpu-memory-utilization 0.85 \
    --port 8000 \
    --host 0.0.0.0 \
    > /root/vllm.log 2>&1 &

echo "Waiting for vLLM to load model (1-2 min)..."
for i in $(seq 1 30); do
    sleep 10
    if curl -s http://localhost:8000/v1/models > /dev/null 2>&1; then
        echo "vLLM ready after $((i*10))s"
        curl -s http://localhost:8000/v1/models | python3 -c "import sys,json; print([m['id'] for m in json.load(sys.stdin)['data']])"
        break
    fi
    echo "  waiting... ${i}0s"
done

# ---- 6. Run LoRA eval ----
echo ""
echo "=== Step 6: Run LoRA eval (hsge-agent) ==="
export OPENAI_API_KEY="not-needed"
export OPENAI_BASE_URL="http://localhost:8000/v1"
export PYTHONPATH="/root/webarena-main"

cd /root/webarena-main
rm -rf results/lora_model

python3 run.py \
    --provider openai \
    --model hsge-agent \
    --mode chat \
    --temperature 0.0 \
    --top_p 1.0 \
    --max_steps 30 \
    --max_tokens 512 \
    --max_obs_length 1920 \
    --context_length 0 \
    --action_set_tag id_accessibility_tree \
    --observation_type accessibility_tree \
    --instruction_path agent/prompts/jsons/p_hsge_actree_2s.json \
    --test_start_idx 0 \
    --test_end_idx 1000 \
    --result_dir results/lora_model \
    --parsing_failure_th 5 \
    --repeating_action_failure_th 5 \
    --max_retry 3

echo ""
echo "=== LoRA Eval Complete ==="
echo "Results: results/lora_model/"
echo "Average score shown in log above"
