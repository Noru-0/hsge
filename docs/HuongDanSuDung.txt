# Hướng dẫn chạy và sử dụng — HSGE

## 1. Điều kiện trước khi chạy

- Đã hoàn thành **Hướng dẫn cài đặt** (tạo môi trường Conda, cài thư viện qua `pip install -e .` và `pip install -r requirements.txt`).
- Đã kích hoạt môi trường: `conda activate hsge`.
- **Mọi lệnh đều phải chạy từ thư mục gốc của dự án** (thư mục chứa `hsge/`, `config.yaml`, `explore.py`, `run_webarena.py`).

## 2. Chạy Mock Pipeline (Không cần API key & Browser thật)

Các tập tin script mô phỏng nằm trực tiếp ở thư mục gốc dự án. Bạn có thể chạy ngay để kiểm thử logic pipeline mà không tốn chi phí API hay tài nguyên trình duyệt.

### 2.1. Vòng lặp khám phá đầy đủ (Exploration Loop)

```bash
python explore.py
```

Thực thi vòng lặp khám phá tự động: Mở rộng biên (frontier) → Phát hiện kỹ năng (skill discovery) → Soạn thảo chuỗi toán tử → Xác minh tiền/hậu điều kiện.

### 2.2. Kịch bản thử nghiệm theo miền ứng dụng

```bash
python demo.py                  # Phát hiện → Phân cụm → Trừu tượng hóa → Xác minh → Chuyển giao skill
python demo_shopping.py         # Miền Mua sắm: Lập kế hoạch → Thực thi → Xác minh đơn đặt hàng
python demo_purchase.py         # Lập kế hoạch + Curriculum (Học toán tử & tiền điều kiện)
```

### 2.3. So sánh các mô hình Baseline

```bash
python compare.py               # So sánh cặp baseline (Flat vs HSGE)
python compare_three_way.py     # So sánh 3 baseline: Flat vs AWM vs HSGE trên cùng dữ liệu đầu vào
```

### 2.4. Chạy bộ kiểm thử đơn vị tự động (Pytest)

```bash
python -m pytest hsge/tests/ -q
```

Hoặc chạy riêng lẻ từng tập tin test kiểm thử thành phần:

```bash
python hsge/tests/test_clustering.py
python hsge/tests/test_segmentation.py
python hsge/tests/test_operators.py
python hsge/tests/test_solver.py
python hsge/tests/test_resume.py
python hsge/tests/test_build_sft_dataset.py
```

---

## 3. Chạy Real WebArena Exploration (`run_webarena.py`)

### 3.1. Chuẩn bị môi trường & Cấu hình

- Tập tin `.env` đã khai báo đầy đủ API key (`OPENAI_API_KEY`, `DEEPSEEK_API_KEY`) và danh sách URL WebArena (`WA_SHOPPING`, `WA_REDDIT`, ...).
- Đã cài đặt trình duyệt Playwright Chromium: `playwright install chromium`.
- WebArena Docker container tương ứng đang chạy và có thể truy cập được.
- Thứ tự ưu tiên cấu hình: **CLI flag > config.yaml > .env > built-in default**.

### 3.2. Thực thi khám phá trên các website WebArena

```bash
# 1. Dry-run (Kiểm tra dây nối wiring, giả lập browser & LLM script - không tốn chi phí)
python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2

# 2. Read-only Smoke Test (Chỉ cho phép tác vụ INFO/NAV, chặn MOD/UNKNOWN - an toàn cho site dùng chung)
python run_webarena.py --read-only --max-nodes 2 --max-steps 4

# 3. Chạy 4 đợt thu thập chính thức trên 4 website (Mỗi đợt 1 site, chạy song song giữa các site)
python run_webarena.py --site shopping       --out outputs/wa_run_20_shopping
python run_webarena.py --site reddit         --out outputs/wa_run_20_reddit
python run_webarena.py --site gitlab         --out outputs/wa_run_20_gitlab
python run_webarena.py --site shopping_admin --out outputs/wa_run_20_shopping_admin

# 4. Nối lại đợt chạy bị ngắt (Resume từ node checkpoint gần nhất)
python run_webarena.py --site shopping --out outputs/wa_run_20_shopping --resume

# 5. Ghi đè cấu hình LLM Provider / Model từ CLI
python run_webarena.py --provider deepseek --model deepseek-v4-pro
```

> **Lưu ý vận hành quan trọng**:
> - **Song song theo website thì được, song song trên cùng 1 website thì không**: 4 đợt chạy trên 4 site khác nhau có thể thực thi đồng thời. Tuy nhiên, 2 worker chạy chung trên 1 site sẽ ghi đè trạng thái của nhau.
> - **Cờ `--resume`**: Nếu một đợt bị dừng đột ngột (do hết hạn mức API hoặc sự cố mạng), chỉ cần thêm `--resume` vào đúng lệnh cũ để tiếp tục.

### 3.3. Bảng tham số CLI quan trọng

| Tham số CLI | Ý nghĩa & Mô tả | Giá trị mặc định |
|---|---|---|
| `--site` | Tên website mục tiêu (`shopping`, `reddit`, `gitlab`, `shopping_admin`) | Từ `config.yaml` |
| `--root-url` | URL gốc của trang web (ghi đè `--site`) | `null` |
| `--out` | Thư mục lưu trữ kết quả đợt chạy | `outputs/wa_run` |
| `--allow` | Biểu thức chính quy (Regex) các URL được phép truy cập | Tự động suy ra từ Root URL |
| `--denylist` | Regex các URL bị chặn (vd: logout, phân trang, đăng xuất) | `"logout\|\?p=\|..."` |
| `--max-nodes` | Ngân sách tổng số node trang web cần khám phá | `500` |
| `--max-depth` | Độ sâu tối đa trong cây khám phá | `300` |
| `--max-steps` | Ngân sách số bước tối đa cho Local Solver mỗi episode | `15` |
| `--goal-max-steps` | Ngân sách số bước tối đa cho Task GOAL nhiều bước | `25` |
| `--max-tasks` | Số lượng tác vụ đề xuất bởi PageExplorer tại mỗi node | `9` |
| `--maturity` | Số lần tái xuất hiện để một cụm vết chuyển thành Skill/Operator | `2` |
| `--unprefixed-sampling` | Bật giải lại task đã xong từ trang chủ (đảm bảo đầy đủ navigation) | `true` |
| `--verify-episodes` | Bật Judge đánh giá lại độc lập mọi episode tự nhận thành công | `true` |
| `--plan-subgoals` | Phân rã tác vụ GOAL thành chuỗi mục tiêu con (subgoals) | `true` |
| `--use-site-seed` | Trích xuất seed năng lực trang web từ trang chủ để dẫn dắt GOAL task | `true` |
| `--mine-hrefs` | Khai thác liên kết `<a href>` vào hàng đợi frontier để tránh kiệt nguồn | `true` |
| `--headed` | Mở cửa sổ trình duyệt thực tế (dùng khi debug giao diện) | `false` |
| `--read-only` | Chế độ đọc (Chỉ làm task INFO/NAV, cấm sửa đổi cơ sở dữ liệu) | `false` |
| `--dry-run` | Chạy mô phỏng giả lập kiểm tra luồng logic | `false` |
| `--resume` | Nối lại đợt chạy bị ngắt từ điểm kiểm tra cuối cùng | `false` |

### 3.4. Phân bổ mô hình LLM theo vai trò trong `config.yaml`

Hệ thống cho phép cấu hình mô hình LLM chuyên biệt cho từng vai trò trong `config.yaml` nhằm tối ưu chi phí và hiệu năng:

```yaml
llm:
  provider: deepseek
  temperature: 0.2
  agents:
    site_seeder:             # Trích xuất seed năng lực website từ trang chủ
      provider: openai
      model: gpt-5.6-luna
      temperature: 1
    page_explorer:           # Đề xuất task tại từng node (Vision + Set-of-Marks)
      provider: openai
      model: gpt-5.6-luna
      vision: true
      som: true
      image_detail: low
      temperature: 1
    solver:                  # Ra quyết định hành động (Local Solver)
      provider: openai
      model: gpt-5.6-luna
      vision: true
      som: true
      image_detail: low
      temperature: 1
    solver_goal:             # Giải các task GOAL chuỗi dài phức tạp
      provider: openai
      model: gpt-5.6-terra
      temperature: 1
    trajectory_segmenter:    # Cắt đoạn vết chạy
      model: deepseek-v4-pro
    skill_abstractor:        # Trừu tượng hóa skill card
      model: deepseek-v4-pro
    skill_verifier:          # Kiểm chứng điều kiện skill
      model: deepseek-v4-pro
    operator_inducer:        # Quy nạp toán tử (Precondition / Effect)
      model: deepseek-v4-pro
    episode_judge:            # Chấm lại chất lượng episode độc lập
      model: deepseek-v4-pro
    thought_reannotator:      # Viết lại chuỗi suy nghĩ chất lượng cao cho SFT
      model: deepseek-v4-pro
```

### 3.5. Cấu trúc kết quả đầu ra (`outputs/wa_run_XX/`)

Sau khi đợt khám phá kết thúc, toàn bộ dữ liệu tạo phẩm được ghi nhận định kỳ sau mỗi node:

| Tập tin / Thư mục | Nội dung & Mục đích |
|---|---|
| `skills.json` | Danh sách các kỹ năng (SkillCards) đã kiểm chứng thành công |
| `operators.json` | Danh sách các toán tử lập kế hoạch (Precondition / Effect) |
| `graph.json` | Đồ thị toán tử phân cấp (Các cạnh nối Effect → Precondition) |
| `predicates.json` | Cơ sở dữ liệu mệnh đề đã được chuẩn hóa id (Predicate Registry) |
| `nodes.json` | Danh sách vết khám phá và kết quả task theo từng node |
| `summary.json` | Tổng hợp chỉ số đợt chạy (tỷ lệ thành công, số node, ngân sách) |
| `run_log.jsonl` | Nhật ký sự kiện chi tiết theo từng dòng |
| `episodes/` | Thư mục chứa từng episode tương tác chi tiết |
| `episodes/ep_XXXX/episode_meta.json` | Mục tiêu task, kết quả chấm, reward, lý do dừng |
| `episodes/ep_XXXX/episode.jsonl` | Chi tiết hành động, suy nghĩ và quan sát theo từng bước |
| `episodes/ep_XXXX/page_state/` | Cây AXTree, ảnh chụp màn hình thô và ảnh phủ nhãn SoM |

---

## 4. Quy trình đóng gói & Tinh lọc dữ liệu SFT (SFT Dataset Curation)

Quy trình tinh lọc dữ liệu bao gồm 4 bước nghiêm ngặt nhằm đảm bảo nguyên tắc **Prompt Parity** và **ngăn ngừa rò rỉ dữ liệu (data leakage)**.

### 4.1. (Tùy chọn) Chấm lại Episode & Tinh chỉnh suy nghĩ

*Lưu ý*: Nếu tùy chọn `verify_episodes: true` đã được bật trong lúc chạy `run_webarena.py`, thành phần `episode_judge` đã chấm lại ngay trong vòng lặp thu thập. Bước này chỉ áp dụng cho các đợt chạy cũ:

```bash
# Kiểm tra lại các episode tự tuyên bố thành công bằng mô hình Judge
python judge_episodes.py outputs/wa_run_20_shopping

# Re-annotate chuỗi suy nghĩ từng bước theo cấu trúc chuẩn (State / Subgoal / Reflection)
python reannotate_thoughts.py outputs/wa_run_20_shopping
```

### 4.2. Trích xuất tập dữ liệu SFT cho từng trang

```bash
python build_sft_dataset.py outputs/wa_run_20_shopping/episodes       training_data/train_shopping.jsonl       --require-judge
python build_sft_dataset.py outputs/wa_run_20_reddit/episodes         training_data/train_reddit.jsonl         --require-judge
python build_sft_dataset.py outputs/wa_run_20_gitlab/episodes         training_data/train_gitlab.jsonl         --require-judge
python build_sft_dataset.py outputs/wa_run_20_shopping_admin/episodes training_data/train_shopping_admin.jsonl --require-judge
```

Cờ `--require-judge` đảm bảo chỉ giữ lại các episode đã được Judge xác nhận thành công (hoặc các task infeasible hợp lệ), loại bỏ hoàn toàn các trường hợp báo thành công giả.

### 4.3. Hợp nhất dữ liệu từ 4 website WebArena

Do mỗi đợt chạy tự đánh số episode độc lập từ `ep_0000`, script hợp nhất sẽ bổ sung tiền tố tên miền (domain prefix) vào ID vết tương tác trước khi nối tập tin:

```bash
python training/merge_datasets.py \
       training_data/train_reddit.jsonl \
       training_data/train_shopping.jsonl \
       training_data/train_gitlab.jsonl \
       training_data/train_shopping_admin.jsonl \
       -o training_data/train_all.jsonl
```

### 4.4. Phân chia tập Train/Validation theo Task (Bảo vệ rò rỉ dữ liệu)

```bash
python training/prepare_dataset.py training_data/train_all.jsonl --name all --out-dir training/data/all
```

Script này thực hiện phân chia tập huấn luyện (train) và tập kiểm định (validation) theo **cặp (website, nội dung mục tiêu)**. Điều này đảm bảo tuyệt đối không có mục tiêu nào trong tập validation từng xuất hiện trong tập train, ngăn chặn việc mô hình bị rò rỉ dữ liệu và làm ảo chỉ số `eval_loss`.

---

## 5. Fine-tuning, Serving & Đánh giá mô hình (WebArena Benchmark)

> **Nguyên tắc môi trường ảo độc lập**: 3 công đoạn này bắt buộc phải chạy trên **3 môi trường ảo (venv/conda) độc lập** để tránh xung đột thư viện giữa LLaMA-Factory và vLLM:
> 1. `venv_train`: Chứa `llamafactory` dùng cho fine-tuning LoRA.
> 2. `venv_serve`: Chứa `vllm` để phục vụ mô hình inference.
> 3. `hsge` (hoặc `venv_eval`): Môi trường chạy bộ công cụ đánh giá chính thức WebArena.

### 5.1. Huấn luyện LoRA bằng LLaMA-Factory

```bash
# Huấn luyện mô hình Qwen3.5-9B với LoRA (sử dụng template qwen3_5_nothink)
llamafactory-cli train training/qwen35_9b_lora_all.yaml
```

### 5.2. Trộn trọng số Adapter LoRA vào Mô hình gốc

```bash
# Trộn adapter vào weights mô hình gốc
llamafactory-cli export training/merge_lora_all.yaml

# Hoặc sử dụng script helper PEFT:
python training/merge_lora_peft.py <model_goc> <thu_muc_adapter> <model_da_tron>
```

### 5.3. Phục vụ mô hình bằng vLLM Engine

```bash
# Phục vụ mô hình đã fine-tune (Tắt chế độ suy nghĩ <think> để giữ Prompt Parity)
bash training/serve_vllm.sh <path_to_merged_model>
```

### 5.4. Đánh giá chính thức trên Benchmark WebArena

Đánh giá được thực thi song song trên 4 máy độc lập tương ứng với 4 website WebArena:

```bash
# Khởi chạy đánh giá tự động qua 9 chặng kiểm soát (Gated Steps)
bash training/bootstrap_eval_box.sh --site shopping --site-url http://your-host:7770
```

### 5.5. Theo dõi, thu thập & Phân tích vết chạy đánh giá

```bash
# 1. Theo dõi tiến độ đánh giá các tác vụ
python training/eval_status.py outputs/eval/*/finetuned

# 2. Thu thập tập tin kết quả về máy trung tâm (Kiểm tra mã băm checksum)
bash training/collect_eval_results.sh --host <host> --port <port> --site <site>

# 3. Phân tích nguyên nhân thất bại của agent
python training/analyze_eval_traces.py outputs/eval/*/finetuned --examples 3
```

---

## 6. Dừng, Khởi động lại & Khôi phục môi trường

### 6.1. Dừng chương trình

- Trong terminal: Nhấn `Ctrl + C`.
- Nếu chạy ở chế độ `--headed`: Đóng trực tiếp cửa sổ trình duyệt Chromium.

### 6.2. Khởi động lại và Reset Trạng thái

```bash
# 1. Tiếp tục đợt chạy bị ngắt (Khuyên dùng)
python run_webarena.py --site shopping --out outputs/wa_run_20_shopping --resume

# 2. Reset toàn bộ dữ liệu đợt chạy (Nếu muốn chạy lại từ đầu)
rm -rf outputs/wa_run_20_shopping

# 3. Xóa cache phiên đăng nhập (Khi thông tin tài khoản bị hết hạn)
rm -rf .auth/
```

> **Cảnh báo khôi phục Cơ sở dữ liệu WebArena (Reset Database)**:
> Trước khi thực hiện đánh giá đối sánh giữa **Mô hình nền (Base Model)** và **Mô hình Fine-tuned**, bạn bắt buộc phải khôi phục lại cơ sở dữ liệu gốc của container WebArena. Nếu không reset database, các thao tác dữ liệu do mô hình trước để lại sẽ làm sai lệch kết quả chấm điểm của mô hình sau.

---

## 7. Kiểm tra nhanh chương trình (Sanity Check)

### 7.1. Kiểm tra Mock Pipeline

```bash
conda activate hsge
python explore.py
```
*Kỳ vọng*: Script chạy hoàn tất không xuất hiện lỗi, in ra danh sách các skill discovered, verified và composed.

### 7.2. Kiểm tra WebArena Dry-Run

```bash
python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2
```
*Kỳ vọng*: Khởi tạo thư mục `/tmp/wa_dry` chứa đầy đủ 6 tập tin kết quả JSON (`skills.json`, `operators.json`, `graph.json`, ...).

---

## 8. Xử lý sự cố thường gặp

| Hiện tượng / Thông báo lỗi | Nguyên nhân gốc rễ | Cách xử lý đề xuất |
|---|---|---|
| `conda: command not found` | Chưa cài Conda hoặc chưa chạy `conda init` | Tải Miniconda, chạy `conda init bash/zsh/powershell` |
| `ModuleNotFoundError: No module named 'hsge'` | Chưa cài đặt gói `hsge` ở dạng editable | Chạy `pip install -e .` tại thư mục gốc |
| `playwright` Executable doesn't exist | Chưa tải xuống trình duyệt Chromium | Chạy `playwright install chromium` |
| `BadRequestError: 400 ... temperature` | GPT-5.x/o-series không hỗ trợ `temperature != 1` | Đặt `temperature: 1` cho các role dùng mô hình GPT-5.x trong `config.yaml` |
| WebArena connection refused | Container WebArena chưa được khởi chạy | Kiểm tra `docker ps`, khởi động lại container WebArena |
| Data leakage khi fine-tune | Chia tập train/val theo episode thay vì theo task | Sử dụng `python training/prepare_dataset.py` để chia tập theo task |
| Sai lệch định dạng khi Inference | vLLM bật chế độ `<think>` trong khi tập SFT không có | Tắt chế độ think trong vLLM bằng script `training/serve_vllm.sh` |
