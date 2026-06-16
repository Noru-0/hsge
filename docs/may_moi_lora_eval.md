# Máy Mới - Eval LoRA Model (hsge-agent via vLLM)

## Thông tin máy

| Item | Value |
|------|-------|
| **SSH** | `ssh -p 63558 root@146.115.17.156` |
| **GPU** | NVIDIA A100-SXM4-80GB (80GB VRAM) |
| **Driver** | 570.195.03 (CUDA 12.8) |
| **Python** | `/usr/bin/python3` (3.10.12) |
| **Python venv** | `/venv/main` (conda/uv, thiếu openai → dùng system python) |

## Kiến trúc

```
┌─────────────────────────────────────────────┐
│  run.py (WebArena eval)                     │
│  --provider openai --model hsge-agent       │
│  --instruction_path p_hsge_actree_2s.json   │
│  OPENAI_BASE_URL=http://localhost:8000/v1   │
│  OPENAI_API_KEY=not-needed                  │
└──────────────────┬──────────────────────────┘
                   │ HTTP (openai client)
┌──────────────────▼──────────────────────────┐
│  vLLM 0.8.5 (OpenAI-compatible API)         │
│  --enable-lora                              │
│  --lora-modules hsge-agent=/root/final_...  │
│  --api-key not-needed                       │
│  Port 8000                                  │
└─────────────────────────────────────────────┘
```

## Các bước setup

### 1. Cài vLLM
```bash
# vLLM 0.8.5 tương thích CUDA 12.x (không cần driver CUDA 13)
pip install vllm==0.8.5
```

### 2. Upload LoRA checkpoint
```bash
scp -P 63558 -r /path/to/final_checkpoint root@146.115.17.156:/root/
```
Kích thước: ~92MB (r=16, alpha=32, all linear layers)

### 3. Upload code WebArena
```bash
scp -P 63558 -r webarena-main root@146.115.17.156:/root/
```

### 4. Patch prometheus (fix 500 Internal Server Error)
```bash
python3 -c "
import ast
filepath = '/usr/local/lib/python3.10/dist-packages/prometheus_fastapi_instrumentator/routing.py'
with open(filepath) as f: content = f.read()
content = content.replace(
    'route_name = route.path',
    'route_name = getattr(route, \"path\", None)'
)
with open(filepath, 'w') as f: f.write(content)
ast.parse(open(filepath).read())  # verify syntax
print('OK')
"
```

### 5. Cài Playwright dependencies
```bash
apt-get install -y libatk-bridge2.0-0 libcups2 libatspi2.0-0 libxcomposite1 \
  libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
  libnss3 libnspr4 libatk1.0-0
playwright install chromium
```
Test: `python3 -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); print('OK'); b.close(); p.stop()"`

### 6. Filter + tạo config files shopping
```bash
cd /root/webarena-main
python3 -c "
import json
data = json.load(open('config_files/test.raw.json'))
shopping = [t for t in data if 'shopping' in str(t.get('sites',[])) and 'shopping_admin' not in str(t.get('sites',[]))]
for t in shopping:
    json.dump(t, open(f'config_files/{t[\"task_id\"]}.json','w'), indent=2)
print(f'Created {len(shopping)} shopping task files')
"
# Kết quả: 192 shopping task files (IDs từ 21 đến 798)
```

### 7. Serve model (vLLM với LoRA)
```bash
nohup vllm serve "Qwen/Qwen2.5-7B-Instruct" \
  --enable-lora \
  --lora-modules "hsge-agent=/root/final_checkpoint" \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.85 \
  --port 8000 \
  --host 0.0.0.0 \
  --api-key not-needed \
  > /root/vllm.log 2>&1 &

# Kiểm tra:
curl -s http://localhost:8000/v1/models -H "Authorization: Bearer not-needed"
# Phải thấy: Qwen/Qwen2.5-7B-Instruct + hsge-agent
```

### 8. Script chạy eval (`/root/run_eval.sh`)
```bash
#!/bin/bash
cd /root/webarena-main
export PYTHONPATH=/root/webarena-main
export OPENAI_BASE_URL=http://localhost:8000/v1
export OPENAI_API_KEY=not-needed
export REDDIT=http://localhost:9999
export SHOPPING=https://farmers-matched-dishes-vbulletin.trycloudflare.com
export SHOPPING_ADMIN=https://farmers-matched-dishes-vbulletin.trycloudflare.com/admin
export GITLAB=http://localhost:8023
export WIKIPEDIA=http://localhost:8888
export MAP=http://localhost:3000
export HOMEPAGE=http://localhost:4399
exec /usr/bin/python3 run.py \
  --provider openai --model hsge-agent --mode chat \
  --temperature 0.0 --top_p 1.0 --max_steps 30 \
  --max_tokens 512 --max_obs_length 1920 \
  --action_set_tag id_accessibility_tree \
  --observation_type accessibility_tree \
  --instruction_path agent/prompts/jsons/p_hsge_actree_2s.json \
  --test_start_idx 0 --test_end_idx 1000 \
  --result_dir results/lora_model \
  --parsing_failure_th 5 --repeating_action_failure_th 5 --max_retry 3
```

### 9. Chạy eval
```bash
# Dọn results cũ
rm -rf /root/webarena-main/results/lora_model
mkdir -p /root/webarena-main/results/lora_model

# Chạy
nohup /root/run_eval.sh > /root/eval_lora.log 2>&1 &
echo "PID: $!"
```

## Theo dõi tiến độ

```bash
# Ngắn gọn
grep -a -c "PASS\|FAIL" /root/eval_lora.log && grep -a -E "PASS|FAIL" /root/eval_lora.log | tail -5

# Đầy đủ
grep -a -E "task|Total|PASS|FAIL|Error|Intent|Average" /root/eval_lora.log | tail -10

# GPU
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
```

## Các lỗi đã gặp & fix

| # | Lỗi | Nguyên nhân | Fix |
|---|------|-------------|-----|
| 1 | `AttributeError: '_IncludedRouter' has no attribute 'path'` | prometheus_fastapi_instrumentator không tương thích FastAPI router mới | Patch `routing.py`: `route.path` → `getattr(route, "path", None)` |
| 2 | `ModuleNotFoundError: No module named 'browser_env'` | Thiếu `PYTHONPATH` | `export PYTHONPATH=/root/webarena-main` |
| 3 | `AssertionError: Please setup the URLs` | Thiếu env vars (SHOPPING, REDDIT...) | Export đủ 7 URL |
| 4 | `BrowserType.launch` missing deps | Thiếu system libraries cho Chromium | `apt-get install libnss3 libnspr4...` |
| 5 | `AuthenticationError 401: not-needed` | vLLM thiếu `--api-key` flag | Thêm `--api-key not-needed` khi serve |
| 6 | `ModuleNotFoundError: No module named 'openai'` | Venv Python thiếu openai | Dùng `/usr/bin/python3` thay vì `python3` |
| 7 | `No task left to run` | Results cũ khiến `get_unfinished()` skip hết | `rm -rf results/lora_model` trước khi chạy |
| 8 | `ZeroDivisionError` | Tất cả tasks fail → `len(scores)==0` | Fix các lỗi trên để tasks chạy được |

## Tổng kết

| Chỉ số | Giá trị |
|--------|---------|
| **Tổng tasks** | 192 (shopping only, IDs: 21-798) |
| **Model** | `hsge-agent` (Qwen2.5-7B + LoRA r=16) |
| **Serve** | vLLM 0.8.5 với `--api-key not-needed` |
| **GPU khi loaded** | ~70GB / 80GB (85% utilization) |
| **Thời gian load model** | ~90s (có cache torch.compile) |
