# Hướng dẫn chạy HSGE Project

## Môi trường

```bash
# Tạo virtual environment (Python 3.10+)
python -m venv .venv
.venv\Scripts\activate

# Cài dependencies
pip install -r requirements.txt
pip install browsergym-core browsergym-webarena sentence-transformers openai
playwright install chromium
```

## 1. Chạy test

### Core tests

```bash
# Test clustering + pipeline
python -m pytest hsge/tests/test_clustering.py -v
```

**Kỳ vọng**: 4 tests passed.

### Dry-run (không cần WebArena thật)

```bash
# Dry-run cơ bản
python run_webarena.py --dry-run --out /tmp/test_dry

# Dry-run với screenshot
python run_webarena.py --dry-run --screenshot --out /tmp/test_dry_ss

# Dry-run với hybrid exploration mode
python run_webarena.py --dry-run --exploration-mode hybrid --out /tmp/test_hybrid
```

**Kỳ vọng**: Script chạy không lỗi, tạo output files.

---

## 2. Chạy demo (mock, không cần API key)

```bash
# Demo end-to-end pipeline
python demo.py

# Demo operator planning (purchase chain)
python demo_purchase.py

# Demo shopping domain
python demo_shopping.py
```

---

## 3. Chạy exploration trên WebArena thật

### 3.1 Chuẩn bị

Tạo file `.env` trong thư mục gốc:

```env
# DeepSeek
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# Hoặc OpenAI
# OPENAI_API_KEY=sk-your-key-here
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o-mini

# Provider (deepseek | openai | custom)
LLM_PROVIDER=deepseek
```

### 3.2 Chạy cơ bản

```bash
# DeepSeek
python run_webarena.py --provider deepseek --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 20

# OpenAI
python run_webarena.py --provider openai --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 20

python run_webarena.py --provider openai --explorer-model gpt-4o-mini --solver-model gpt-4o --screenshot --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 20 --storage-state ".auth/shopping_state.json"
```

### 3.3 Dual model (explorer rẻ + solver mạnh)

```bash
# DeepSeek: explorer dùng chat, solver dùng reasoner
python run_webarena.py --provider deepseek --explorer-model deepseek-chat --solver-model deepseek-reasoner --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 20

# OpenAI: explorer dùng mini, solver dùng full
python run_webarena.py --provider openai --explorer-model gpt-4o-mini --solver-model gpt-4o --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 20
```

### 3.4 Với screenshot (vision models)

```bash
# Chỉ OpenAI mới support vision
python run_webarena.py --provider openai --screenshot --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 20
```

### 3.5 Resume từ checkpoint

```bash
python run_webarena.py --provider deepseek --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 9999 --resume
```

### 3.6 Với full reset (go-browse style)

```bash
python run_webarena.py --provider deepseek --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 20 --full-reset-url "http://host:8888/reset"
```

### 3.7 Với hybrid exploration mode

```bash
# Hybrid: homepage BFS + depth>=1 callback discovery
python run_webarena.py --provider deepseek --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 20 --exploration-mode hybrid
```

### 3.8 Denylist URLs

```bash
# Chặn /logout và /wishlist
python run_webarena.py --provider deepseek --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 20 --denylist '/wishlist' '/customer/account/logout'
```

### 3.9 Transfer query

```bash
# Tự động evaluate transfer skills sau exploration
python run_webarena.py --provider deepseek --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 20 --transfer-query "purchase an item"
```

### 3.10 Full options

```bash
python run_webarena.py \
  --provider deepseek \
  --explorer-model deepseek-chat \
  --solver-model deepseek-reasoner \
  --root-url "http://192.168.1.31:7770/" \
  --out outputs/wa_run \
  --max-nodes 50 \
  --max-depth 6 \
  --max-steps 20 \
  --screenshot \
  --resume \
  --full-reset-url "http://host:8888/reset" \
  --exploration-mode hybrid \
  --transfer-query "purchase an item" \
  --denylist '/wishlist' '/customer/account/logout'
```

---

## 4. Build SFT dataset từ episodes

```bash
# Sau khi chạy exploration xong
python build_sft_dataset.py outputs/wa_run/episodes train.jsonl
```

**Output**: `train.jsonl` — dataset SFT format, sorted by difficulty (easy→hard).

---

## 5. Phân tích kết quả

### Phân tích frontier URLs

```bash
# Xem thống kê URLs đã explore
python analyze_frontier.py outputs/wa_run/frontier.jsonl
```

### Khôi phục checkpoint

```bash
# Khi checkpoint bị mất, recover từ episodes
python recover_checkpoint.py outputs/wa_run
```

### Xem log

```bash
# Log chi tiết từng node
cat outputs/wa_run/run.log

# Skills đã học
cat outputs/wa_run/skills.json

# Graph structure
cat outputs/wa_run/graph.json

# Curriculum tasks
cat outputs/wa_run/curriculum.json

# Transfer results
cat outputs/wa_run/transfer.json
```

---

## 6. So sánh baselines

```bash
# So sánh Flat baseline vs HSGE
python compare.py
```

---

## CLI Arguments Reference

| Argument | Mô tả | Default |
|----------|-------|---------|
| `--root-url` | Root URL của WebArena | `http://shop/home` |
| `--out` | Thư mục output | `outputs/wa_run` |
| `--allow` | Regex pattern cho phép URL | Tự động từ root-url |
| `--max-nodes` | Số node tối đa | `15` |
| `--max-depth` | Độ sâu tối đa | `6` |
| `--max-steps` | Số steps tối đa mỗi task | `15` |
| `--provider` | LLM provider (`deepseek`, `openai`, `custom`) | Từ env |
| `--model` | Model cho cả explorer + solver | Từ env |
| `--explorer-model` | Model riêng cho PageExplorer | Từ env |
| `--solver-model` | Model riêng cho Solver | Từ env |
| `--screenshot` | Bật screenshot (vision models) | `False` |
| `--timeout` | Browser timeout (ms) | `30000` |
| `--resume` | Resume từ checkpoint | `False` |
| `--transfer-query` | Transfer query để evaluate | `None` |
| `--denylist` | URL patterns để chặn | `[]` |
| `--full-reset-url` | URL reset server state | `None` |
| `--exploration-mode` | `bfs` (FIFO) hoặc `hybrid` | `bfs` |
| `--dry-run` | Chạy mock (không cần WebArena) | `False` |

---

## Output Files

Sau khi chạy exploration, thư mục output chứa:

| File | Mô tả |
|------|-------|
| `run.log` | Log chi tiết từng node |
| `frontier.jsonl` | Frontier snapshot mỗi node |
| `skills.json` | Skills đã được admit |
| `graph.json` | Hierarchical graph structure |
| `curriculum.json` | Curriculum tasks (easy→hard) |
| `transfer.json` | Transfer retrieval results |
| `checkpoint.json` | Checkpoint để resume |
| `adapted_skills.json` | Skills đã được adapt (nếu có) |
| `episodes/` | Thư mục chứa trajectories |
| `episodes/ep_NNNN/` | Mỗi episode là 1 thư mục |
| `episodes/ep_NNNN/episode_meta.json` | Metadata của episode |
| `episodes/ep_NNNN/episode.jsonl` | Steps của episode |
| `episodes/ep_NNNN/page_state/` | AXTree observations |
| `episodes/ep_NNNN/screenshots/` | Screenshots (nếu có) |
