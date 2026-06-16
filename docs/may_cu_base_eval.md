# Máy Cũ - Eval BASE Model (Qwen2.5-7B-Instruct)

## Thông tin máy

| Item | Value |
|------|-------|
| **SSH** | `ssh -p 48574 root@146.115.17.155` |
| **GPU** | NVIDIA A100-SXM4-80GB (80GB VRAM) |
| **Driver** | 570.195.03 (CUDA 12.8) |
| **Python** | `/usr/bin/python3` (3.10.12) |

## Kiến trúc

```
┌─────────────────────────────────────────────┐
│  run.py (WebArena eval)                     │
│  --provider openai --model Qwen2.5-7B-...   │
│  --instruction_path p_hsge_actree_2s.json   │
└──────────────────┬──────────────────────────┘
                   │ HTTP (openai client)
┌──────────────────▼──────────────────────────┐
│  model_server.py (FastAPI + transformers)   │
│  --base Qwen/Qwen2.5-7B-Instruct            │
│  Port 8000                                  │
└─────────────────────────────────────────────┘
```

## Các bước setup

### 1. Upload code
```bash
scp -P 48574 -r webarena-main root@146.115.17.155:/root/
```

### 2. Cài dependencies
```bash
ssh -p 48574 root@146.115.17.155
pip install fastapi uvicorn transformers torch accelerate peft openai
playwright install --with-deps chromium
```

### 3. Tạo HSGE prompt
File `agent/prompts/raw/p_hsge_actree_2s.py` - prompt template cho HSGE agent.
File `agent/prompts/jsons/p_hsge_actree_2s.json` - JSON version.

### 4. Patch code
- `llms/providers/openai_utils.py` - Rewrite cho openai>=1.0
- `llms/tokenizers.py` - Fallback cl100k_base cho non-OpenAI models
- `run.py` - Fix `openai.error` → `openai.OpenAIError`, `python` → `python3`

### 5. Serve model (FastAPI)
```bash
cd /root/webarena-main
nohup python3 /root/model_server.py \
  --base Qwen/Qwen2.5-7B-Instruct \
  --port 8000 \
  > /root/model_server.log 2>&1 &
```

### 6. Filter shopping tasks
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
```

### 7. Set environment variables
```bash
export PYTHONPATH=/root/webarena-main
export REDDIT=http://localhost:9999
export SHOPPING=https://farmers-matched-dishes-vbulletin.trycloudflare.com
export SHOPPING_ADMIN=https://farmers-matched-dishes-vbulletin.trycloudflare.com/admin
export GITLAB=http://localhost:8023
export WIKIPEDIA=http://localhost:8888
export MAP=http://localhost:3000
export HOMEPAGE=http://localhost:4399
```

### 8. Chạy eval
```bash
cd /root/webarena-main
nohup python3 run.py \
  --provider openai \
  --model Qwen2.5-7B-Instruct \
  --mode chat \
  --temperature 0.0 --top_p 1.0 \
  --max_steps 30 --max_tokens 512 --max_obs_length 1920 \
  --action_set_tag id_accessibility_tree \
  --observation_type accessibility_tree \
  --instruction_path agent/prompts/jsons/p_hsge_actree_2s.json \
  --test_start_idx 0 --test_end_idx 1000 \
  --result_dir results/base_model \
  --parsing_failure_th 5 --repeating_action_failure_th 5 --max_retry 3 \
  > /root/eval_base.log 2>&1 &
```

## Theo dõi tiến độ

```bash
ssh -p 48574 root@146.115.17.155 'grep -a -c "PASS\|FAIL" /root/eval_base.log && grep -a -E "PASS|FAIL" /root/eval_base.log | tail -5'
```

## Kết quả

| Chỉ số | Giá trị |
|--------|---------|
| **Tổng tasks** | 187 (shopping only) |
| **Tốc độ** | ~1.8 phút/task |
| **GPU usage** | ~17GB / 80GB (21%) |
| **Dự kiến** | ~5.5 giờ |

> **Note:** Đây là BASE model không LoRA, pass rate thấp (~8%) là dự kiến.
> Máy dùng FastAPI server thay vì vLLM vì driver CUDA 12.8 không tương thích vLLM mới.
