#!/usr/bin/env bash
# ==========================================================================
# Eval HSGE LoRA agent on WebArena Shopping benchmark (vast.ai)
#
# Prerequisites on vast.ai: upload these to /root/
#   - webarena-main/           (this patched codebase)
#   - final_checkpoint/        (LoRA adapter from training)
#
# Usage:
#   chmod +x setup_eval.sh && ./setup_eval.sh
# ==========================================================================
set -euo pipefail

echo "============================================"
echo "  HSGE Agent WebArena Eval Setup (vast.ai)"
echo "============================================"

# ---- Config ----
MODEL_ID="Qwen/Qwen2.5-7B-Instruct"
LORA_PATH="${LORA_PATH:-/root/final_checkpoint}"
LORA_NAME="hsge-agent"
VLLM_PORT=8000
SHOPPING_PORT=7770
SHOPPING_ADMIN_PORT=7780

# ---- 1. System deps ----
echo ""
echo "=== Step 1: System dependencies ==="
apt-get update -qq && apt-get install -y -qq docker.io docker-compose 2>/dev/null || true
nvidia-smi
echo ""

# ---- 2. Python packages ----
echo "=== Step 2: Python packages ==="
pip install --upgrade pip -q
pip install vllm openai==0.28.1 2>/dev/null || pip install vllm openai  # old openai for webarena compat
pip install playwright browsergym-core browsergym-webarena -q
playwright install chromium
playwright install-deps chromium
echo ""

# ---- 3. Host WebArena Shopping ----
echo "=== Step 3: Host WebArena Shopping (Docker) ==="
if [ -f /root/webarena/docker-compose.shopping.yml ]; then
    cd /root/webarena
    docker-compose -f docker-compose.shopping.yml up -d
else
    # Standalone Magento via docker run
    echo "Docker compose not found. Starting Magento via docker..."
    docker run -d --name magento \
        -p ${SHOPPING_PORT}:80 \
        -p ${SHOPPING_ADMIN_PORT}:7780 \
        --restart unless-stopped \
        webarena/shopping:latest 2>/dev/null || echo "Docker image may need manual setup"
fi
sleep 10
echo ""

# ---- 4. Generate HSGE prompt JSON ----
echo "=== Step 4: Generate HSGE prompt JSON ==="
cd /root/webarena-main
python agent/prompts/to_json.py
echo ""

# ---- 5. Filter Shopping-only tasks ----
echo "=== Step 5: Filter Shopping tasks ==="
python scripts/filter_shopping.py config_files/test.raw.json config_files/test_shopping.json
echo ""

# ---- 6. Serve LoRA model via vLLM (background) ----
echo "=== Step 6: Serve LoRA model via vLLM ==="
echo "Model: $MODEL_ID"
echo "LoRA: $LORA_PATH → $LORA_NAME"
echo "Port: $VLLM_PORT"

vllm serve "$MODEL_ID" \
    --enable-lora \
    --lora-modules "${LORA_NAME}=${LORA_PATH}" \
    --max-model-len 16384 \
    --gpu-memory-utilization 0.85 \
    --port $VLLM_PORT \
    --host 0.0.0.0 &
VLLM_PID=$!
echo "vLLM PID: $VLLM_PID"

# Wait for vLLM to be ready
echo "Waiting for vLLM to be ready..."
for i in $(seq 1 60); do
    if curl -s "http://localhost:${VLLM_PORT}/v1/models" > /dev/null 2>&1; then
        echo "vLLM ready after ${i}s"
        break
    fi
    sleep 2
done
echo ""

# ---- 7. Set env vars ----
echo "=== Step 7: Environment ==="
export SHOPPING="http://localhost:${SHOPPING_PORT}"
export SHOPPING_ADMIN="http://localhost:${SHOPPING_ADMIN_PORT}/admin"
export REDDIT="http://localhost:9999"
export GITLAB="http://localhost:8023"
export WIKIPEDIA="http://localhost:8888"
export MAP="http://localhost:3000"
export HOMEPAGE="http://localhost:4399"
export OPENAI_API_KEY="not-needed"
export OPENAI_BASE_URL="http://localhost:${VLLM_PORT}/v1"

echo "SHOPPING=$SHOPPING"
echo "SHOPPING_ADMIN=$SHOPPING_ADMIN"
echo "OPENAI_BASE_URL=$OPENAI_BASE_URL"
echo ""

# ---- 8. Smoke tests ----
echo "=== Step 8: Smoke tests ==="
echo -n "Shopping site: "
curl -s -o /dev/null -w "%{http_code}" "$SHOPPING" || echo "UNREACHABLE"
echo ""
echo -n "vLLM models: "
curl -s "http://localhost:${VLLM_PORT}/v1/models" | python3 -c "import sys,json; print([m['id'] for m in json.load(sys.stdin)['data']])" 2>/dev/null || echo "NOT READY"
echo ""

# ---- 9. Run eval ----
echo "=== Step 9: Run WebArena Eval ==="
echo "Instruction: agent/prompts/jsons/p_hsge_actree_2s.json"
echo "Config: config_files/test_shopping.json"
echo "Model: $LORA_NAME"
echo ""

python run.py \
    --provider openai \
    --model "$LORA_NAME" \
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
    --result_dir results/hsge_agent_shopping \
    --parsing_failure_th 5 \
    --repeating_action_failure_th 5 \
    --max_retry 3

echo ""
echo "=== Eval Complete ==="
echo "Results: results/hsge_agent_shopping/"
