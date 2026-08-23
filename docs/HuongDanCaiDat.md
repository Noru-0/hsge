# Hướng dẫn cài đặt môi trường — HSGE

## 1. Hệ điều hành & cấu hình tối thiểu

- **Hệ điều hành**: Windows 10/11, macOS 13+, Linux (Ubuntu 22.04+ / CentOS 8+).
- **Cấu hình tối thiểu**:
  - **CPU**: 4 nhân, **RAM**: 8 GB, **Ổ cứng**: 10 GB trống.
  - **GPU**: Không bắt buộc cho mock pipeline (chạy hoàn toàn trên CPU). Để fine-tune mô hình (LoRA Qwen3.5-9B) và phục vụ mô hình (vLLM), cần GPU NVIDIA VRAM ≥ 24 GB (vd. RTX 4090 / A10G / A100).
  - Để chạy real WebArena exploration run: cần kết nối mạng ổn định và API key cho các dịch vụ LLM (OpenAI / DeepSeek).

## 2. Công cụ & phiên bản

| Công cụ | Phiên bản | Ghi chú |
|---|---|---|
| Python | ≥ 3.10 (khuyến nghị 3.12) | Ngôn ngữ chính cho toàn bộ dự án |
| Conda | ≥ 23.x | Quản lý môi trường ảo (Miniconda khuyến nghị) |
| Git | ≥ 2.30 | Quản lý mã nguồn |
| Playwright | (cài qua pip) | Trình duyệt điều khiển tự động cho WebArena real run |
| Node.js | ≥ 18 | Cần thiết để Playwright cài đặt Chromium |
| LLaMA-Factory / vLLM | (môi trường riêng) | Dùng cho quy trình fine-tuning LoRA và phục vụ inference |

**Thư viện Python chính** (xem `requirements.txt`):

- `numpy` (≥ 1.24) — Phụ thuộc duy nhất cho mock pipeline kiểm thử tất định.
- `sentence-transformers` (≥ 2.2) — Embedder chuẩn hóa mệnh đề (Predicate Registry).
- `openai` (≥ 1.0), `anthropic` (≥ 0.39) — Backend giao tiếp LLM thực tế (GPT-5.6 luna/terra, Claude, DeepSeek).
- `gymnasium` (≥ 0.29), `browsergym-core`, `browsergym-webarena` — Môi trường WebArena runtime.
- `pyyaml` — Đọc tập tin cấu hình `config.yaml`.
- `python-dotenv` — Đọc các biến môi trường bí mật từ `.env`.
- `pillow` — Xử lý hình ảnh (chụp ảnh màn hình & phủ mảng đánh số Set-of-Marks - SoM).
- `requests` — Gửi yêu cầu HTTP (reset database, kiểm tra dịch vụ).
- `pytest` (≥ 7.0) — Bộ kiểm thử đơn vị tự động (hơn 45 tập tin kiểm thử trong `hsge/tests/`).

## 3. Cài đặt môi trường

### 3.1. Cài đặt Python & Conda

Tải và cài đặt **Miniconda** (khuyến nghị):
```
https://docs.anaconda.com/miniconda/
```

Sau khi cài đặt xong, mở **Anaconda Prompt** (Windows) hoặc terminal (macOS/Linux).

### 3.2. Tạo và kích hoạt môi trường Conda

```bash
conda create -n hsge python=3.12 -y
conda activate hsge
```

### 3.3. Cài đặt gói `hsge` ở chế độ Editable

Thực hiện lệnh từ **thư mục gốc của dự án** (thư mục chứa `hsge/`, `config.yaml`, `run_webarena.py`):

```bash
pip install -e .
```

Lệnh này cài đặt package `hsge` ở chế độ **editable**, giúp Python import trực tiếp các module `hsge.*` từ bất kỳ script nào ở thư mục gốc.

### 3.4. Cài đặt phụ thuộc cho Real Pipeline (WebArena, LLM thật)

```bash
pip install -r requirements.txt
playwright install chromium
```

## 4. Cấu hình biến môi trường & Tập tin cấu hình

### 4.1. Tập tin môi trường `.env` (Bí mật & URL)

Tạo tập tin `.env` tại thư mục gốc dự án (bên cạnh `config.yaml`). Tập tin này chứa thông tin bí mật và URL địa chỉ web, tuyệt đối **không commit vào Git**:

```bash
# LLM Provider (openai | deepseek)
OPENAI_API_KEY=sk-your-openai-key-here
OPENAI_BASE_URL=https://api.openai.com/v1

DEEPSEEK_API_KEY=sk-your-deepseek-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# Provider & Model mặc định
LLM_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-v4-pro
OPENAI_MODEL=gpt-5.6-luna

# URL các website WebArena (thay bằng IP/port instance thật của bạn)
WA_SHOPPING=http://your-host:7770
WA_SHOPPING_ADMIN=http://your-host:7780/admin
WA_REDDIT=http://your-host:9999
WA_GITLAB=http://your-host:8023
WA_WIKIPEDIA=http://your-host:8888
WA_MAP=http://your-host:3000
WA_HOMEPAGE=http://your-host:4399

# Tài khoản đăng nhập mặc định cho benchmark WebArena
WA_ACCOUNT_SHOPPING_USERNAME=emma.lopez@gmail.com
WA_ACCOUNT_SHOPPING_PASSWORD=Password.123
WA_ACCOUNT_ADMIN_USERNAME=admin
WA_ACCOUNT_ADMIN_PASSWORD=admin1234
WA_ACCOUNT_REDDIT_USERNAME=MarvelsGrantMan136
WA_ACCOUNT_REDDIT_PASSWORD=test1234
WA_ACCOUNT_GITLAB_USERNAME=byteblaze
WA_ACCOUNT_GITLAB_PASSWORD=hello1234
```

### 4.2. Tập tin cấu hình `config.yaml` & Quy tắc ưu tiên

Các tham số chạy không phải bí mật được quản lý trong `config.yaml`.
Thứ tự ưu tiên cấu hình: **CLI flag > config.yaml > .env > built-in default**.

**Phân bổ mô hình LLM theo vai trò (Role-based LLM Allocation)**:

```yaml
llm:
  provider: deepseek
  temperature: 0.2

  agents:
    site_seeder:             # Trích xuất năng lực website từ trang chủ
      provider: openai
      model: gpt-5.6-luna
      reasoning_effort: medium
      verbosity: medium
      temperature: 1
    page_explorer:           # Đề xuất tác vụ khám phá trên mỗi trang
      provider: openai
      model: gpt-5.6-luna
      reasoning_effort: medium
      verbosity: medium
      vision: true           # Ảnh chụp màn hình kèm Set-of-Marks (SoM)
      som: true
      image_detail: low
      temperature: 1
    solver:                  # Ra quyết định hành động từng bước (Local task)
      provider: openai
      model: gpt-5.6-luna
      reasoning_effort: medium
      verbosity: medium
      vision: true
      som: true
      image_detail: low
      temperature: 1
    solver_goal:             # Thực thi tác vụ GOAL nhiều bước phức tạp
      provider: openai
      model: gpt-5.6-terra
      temperature: 1
    trajectory_segmenter:    # Cắt vết tương tác thành các đoạn kỹ năng
      model: deepseek-v4-pro
    skill_abstractor:        # Trừu tượng hóa tên và tham số skill card
      model: deepseek-v4-pro
    skill_verifier:          # Kiểm chứng điều kiện thực thi skill
      model: deepseek-v4-pro
    operator_inducer:        # Quy nạp toán tử precondition/effect
      model: deepseek-v4-pro
    episode_judge:            # Chấm độc lập trạng thái kết thúc episode
      model: deepseek-v4-pro
    thought_reannotator:      # Viết lại chuỗi suy nghĩ cho tập SFT
      model: deepseek-v4-pro
```

## 5. Kiểm tra cài đặt

### 5.1. Mock pipeline (Không tốn API key & trình duyệt)

Chạy từ thư mục gốc dự án:

```bash
conda activate hsge
python explore.py
python demo.py
```

*Kết quả kỳ vọng*: Script chạy thành công, hiển thị vòng lặp khám phá (frontier expansion, skill discovery, goal-conditioned episode) và chuyển giao skill giữa các môi trường mô phỏng.

### 5.2. Bộ kiểm thử đơn vị (Pytest Suite)

```bash
python -m pytest hsge/tests/ -q
```

*Kết quả kỳ vọng*: Tất cả 45+ bài test kiểm thử đơn vị pass thành công (100% PASSED).

### 5.3. Dry-run WebArena Runtime

```bash
python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2
```

*Kết quả kỳ vọng*: Chương trình khởi tạo môi trường giả lập (fake browser + scripted LLM), thực thi toàn bộ luồng wiring mà không gây tốn chi phí API hay cần instance thật, sinh ra các tập tin kết quả `skills.json`, `operators.json`, `graph.json`, `predicates.json`.

## 6. Lưu ý quản lý kho mã nguồn

- Dự án **tuyệt đối không đính kèm** thư viện cài đặt, cache build, log chạy hoặc dữ liệu trung gian trong Git.
- Thư mục `.auth/` (chứa session state đăng nhập trình duyệt) và các thư mục đầu ra `outputs/` đã được đưa vào `.gitignore`.
- Quá trình fine-tuning LoRA và serving vLLM nên được chạy trên **các môi trường Python độc lập** để tránh xung đột phiên bản thư viện (tham khảo `docs/14_vast_ai_training_eval_tutorial.md`).

## 7. Xử lý lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `ModuleNotFoundError: No module named 'hsge'` | Chưa cài package `hsge` ở chế độ editable | Chạy `pip install -e .` từ thư mục gốc |
| `ModuleNotFoundError: No module named 'numpy'` | Chưa cài đặt `numpy` trong venv | `pip install numpy` |
| `openai.BadRequestError: 400 ... temperature` | Các mô hình GPT-5.x/o-series chỉ hỗ trợ `temperature=1` | Cấu hình `temperature: 1` cho role dùng GPT-5.x |
| `playwright install chromium` lỗi | Thiếu Node.js v18+ hoặc lỗi mạng | Cài Node.js ≥ 18, kiểm tra mạng và chạy lại |
| `KeyError: 'WA_SHOPPING'` | Thiếu khai báo URL trong tập tin `.env` | Kiểm tra lại tập tin `.env` và bổ sung đầy đủ biến `WA_*` |
| `Connection refused` khi chạy real run | WebArena Docker container chưa hoạt động | Khởi động lại các container WebArena tương ứng |
| Xung đột thư viện giữa LLaMA-Factory và vLLM | Cài chung tất cả công cụ vào cùng 1 venv | Tạo 3 venv riêng biệt cho: Explorer, Training, và Serving/Eval |
