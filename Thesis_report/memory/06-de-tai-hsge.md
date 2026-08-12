# Đề tài HSGE — ngữ cảnh & nguồn tư liệu cho báo cáo

Trạng thái: **đã chốt thông tin cơ bản (2026-07-17)**, chưa chốt dàn ý chi tiết.
File này gom sẵn nguyên liệu từ repo để khi viết không phải đào lại.

## Thông tin đã chốt (user xác nhận 2026-07-17)

- **Tên đề tài (tiếng Việt)**: "Mô hình ngôn ngữ nhỏ cho tác nhân trí tuệ nhân
  tạo trên web". Cần đề xuất bản tiếng Anh chính thức (gợi ý: "Small Language
  Models for Web AI Agents") + tên ngắn cho gáy bìa — xác nhận với GVHD.
- **Nhóm 2 người**: Trương Bảo Kiệt (22127223) và Hồ Tiến Phát (22127321).
- **GVHD**: PGS.TS. Nguyễn Văn Vũ — ⚠️ KHÁC GVHD của thesis mẫu (TS. Ngô Huy
  Biên). Thầy Vũ chính là tác giả slide hướng dẫn chính thức của Khoa
  (`KLTN/Huong-dan-viet-va-trinh-bay-Khoa-luan-2023-1.pdf`) → slide đó là
  nguồn sát yêu cầu của thầy nhất; hướng dẫn của thầy Biên (file 02) dùng làm
  tham khảo tốt nhưng không mặc nhiên là yêu cầu bắt buộc.
- **Bộ môn**: Công nghệ Phần mềm.
- **Ngôn ngữ báo cáo**: **tiếng Anh** (xem hệ quả bên dưới).
- **Câu chuyện chính**: xây dựng **pipeline khám phá dữ liệu (explore data)
  dựa trên ý tưởng GRAPH**, tự khám phá các **SEMANTIC TASK** trên web, để
  **train SLM (small language model) tốt hơn**. Tức là: HSGE đóng vai trò
  data-collection engine; đích đến là SLM làm web agent. Phát biểu bài toán C1
  và phạm vi C3 xoay quanh trục này (skill/operator graph là phương tiện sinh
  semantic task + trajectory chất lượng, không phải đích tự thân).
- **Thuật ngữ chốt (2026-07-17)**: *low-level task* = task theo trang do
  PageExplorer đề xuất (INFO/NAV/MOD) — nguyên liệu exploration; *semantic
  task* = task sinh từ **Operator Graph** (chain operator → composed goal
  task). Không gọi task của PageExplorer là semantic task.
- **Phạm vi đánh giá**: official WebArena trên **4 site: Shopping, Shopping
  Admin, GitLab, Reddit** (GitLab đã có số; 3 site còn lại bổ sung sau).
- **Thực nghiệm bổ sung**: còn ~25 ngày (đến ~2026-08-11), user nói sẽ kịp chạy
  thêm — ưu tiên theo 05-bai-hoc-review.md: lặp eval nhiều lần/seed để có
  thống kê (fix P0-1), có thể thêm ablation (train từ data khám-phá-graph vs.
  data thu ngẫu nhiên/flat) để chứng minh giá trị của pipeline graph.

## Hệ quả của việc viết tiếng Anh

- Template thesis_v3 đang Việt hóa caption (`\chaptername=Chương`...) — cần bỏ
  các `\renewcommand` đó, dùng mặc định English (Chapter/Figure/Table/Contents).
- Trang bìa/phụ bìa theo mẫu Khoa: kiểm tra với giáo vụ/GVHD xem bìa ghi song
  ngữ hay tiếng Anh (mẫu Khoa hiện là tiếng Việt).
- Văn phong học thuật tiếng Anh: META-PROMPT trong 04-quy-trinh-ai.md áp dụng
  trực tiếp được (nó vốn viết cho English academic writing).
- Quy tắc chống đạo văn vẫn nguyên: không chép từ paper gốc, trích dẫn IEEE.

## Đề tài là gì

HSGE (Hierarchical Skill-Graph Exploration): scaffold nghiên cứu cho web agent
tự khám phá website, phát hiện **skill tái sử dụng đã được kiểm chứng**, nâng
skill thành **operator** (precondition/effect) để lập kế hoạch và **compose**
thành task dài hạn; đồng thời thu thập trajectory → xây dataset SFT → fine-tune
LLM nhỏ. Chạy được cả trên mock backend (deterministic, không cần API key) lẫn
WebArena thật (BrowserGym).

## Kết quả thực nghiệm CHÍNH THỨC (chốt 2026-08-12) — dùng bộ số này

Đợt 4 website, 655 task chính thức, mỗi task chạy 1 lần, cùng prompt/ngân sách
15 bước/bộ chấm (`gpt-4-turbo` thay cho `gpt-4-1106-preview` đã ngừng).
Nguồn: `outputs/eval/eval_{base,finetuned}/<site>/*/summary.json`.

| site | nền | fine-tune | Δ | p (McNemar) |
|---|---|---|---|---|
| shopping | 37/187 = 19,8% | 53/187 = 28,3% | +8,6 | 0,012 |
| reddit | 7/106 = 6,6% | 22/106 = 20,8% | +14,2 | 0,005 |
| gitlab | 20/180 = 11,1% | 33/180 = 18,3% | +7,2 | 0,012 |
| shopping_admin | 23/182 = 12,6% | 28/182 = 15,4% | +2,7 | **0,383 (ko ý nghĩa)** |
| **tổng** | **87/655 = 13,3%** | **136/655 = 20,8%** | **+7,5** | **<0,001** |

- Số nền của shopping/shopping_admin là **bản đã điều chỉnh của user** (thô
  47 và 29 → 37 và 23; loại các thành công giả: fallback `report_infeasible`
  trùng nhãn infeasible, form điền mà chưa submit, đoán bừa "0" trùng đáp án).
  Thô toàn cục = 103/655 = 15,7%. Cả hai bản đều được ghi trong C4 §4.4.2.
- **Phân tách quan trọng nhất**: nền chết vì đầu ra không phân giải được ở
  **170/655 (26,0%)** phiên, finetuned 2/655. Trên đúng 170 task đó: nền 0,
  finetuned 35. Trên 485 task nền chạy sạch: 87 vs 101 → **p = 0,120, chưa
  đạt ý nghĩa**. Tức 35/49 task tăng thêm thuộc về tuân thủ định dạng.
  → Không được phát biểu "pipeline dạy agent thao tác web giỏi hơn"; phát biểu
  đúng là "dạy được tính kỷ luật của giao diện hành động, phần còn lại mới là
  tín hiệu, cần ablation đồ thị vs phẳng".
- Số cũ **"GitLab nền 5,6% (10/180)" đã chết** — thay bằng 11,1% của đợt sạch.
- LoRA Qwen3.5-9B, LLaMA-Factory, template `qwen3_5_nothink`, 3 epoch/804
  bước, chọn `checkpoint-536` (epoch 2, eval_loss 0,4343), 4288 mẫu train.
- Kỹ thuật phụ đã làm và đáng đưa vào Chương 5 (kinh nghiệm/best practice):
  two-machine parallel eval trên site sống dùng phân loại task read-only/write;
  ba venv tách biệt (transformers@main vs vLLM pin); tìm chat template đúng
  bằng grep registry; bug "prompt-fidelity" khi test model served; hàng loạt
  bug thật từ live run đã fix (stuck-loop Solver, frontier starvation, node
  error resilience, task dedup 46%, structured INFO/NAV/MOD...).
- Các run thật: wa_run_02 (reddit, 57/500 nodes — frontier starvation),
  wa_run_07 (phân tích failure 38.6%), wa_run_09 (chất lượng operator, synonym
  0.570 < 0.6) — số liệu tốt cho phần phân tích/thảo luận.

## Nguồn tư liệu trong repo (mapping sơ bộ vào chương)

| Chương | Nguồn chính |
|---|---|
| C1 Mở đầu | README.md, docs/02_architecture.md; bối cảnh web agent + WebArena (cite paper WebArena, BrowserGym) |
| C2 Liên quan | Các baseline trong repo: flat_baseline, AWM (Agent Workflow Memory); paper trong `Thesis_report/thesis_v3/`: 2507.17128v2.pdf, 2510.02585v1.pdf (kiểm tra liên quan); SOTA web agent cần tìm thêm |
| C3 Giải pháp | .claude/rules/architecture.md (pipeline discovery → segmentation → clustering → abstraction → verification → operators → chaining), docs/superpowers/specs/*.md (design docs từng phần), schema.py (cấu trúc dữ liệu), operators.py (BFS planner — mã giả) |
| C4 Thực nghiệm | training/README.md, docs/14_vast_ai_training_eval_tutorial.md, docs/superpowers/specs/2026-07-15-qwen35-9b-sft-gitlab-eval-design.md, .claude/memory/changelog.md (số liệu chính xác từng run), outputs/ |
| C5 Thảo luận | docs/10–14 (session reports: wiring, vision/auth, bug fixes, exploration log, tutorial), .claude/memory/bugs.md — đây là mỏ "báo cáo kinh nghiệm" đúng ý GVHD |
| C6 Kết luận | Đối chiếu sản phẩm (scaffold + runtime + dataset + model + tutorial) với mục tiêu |
| Phụ lục | Chi tiết thiết kế, bảng số liệu run, config |

## Điểm còn mở (hỏi tiếp user/GVHD)

1. Tên đề tài tiếng Anh chính thức + tên ngắn cho gáy bìa (đề xuất rồi xin
   GVHD duyệt).
2. Deadline nộp đợt nào / lịch bảo vệ (quy trình nộp: xem 01) — user mới nói
   "còn ~25 ngày" cho thực nghiệm.
3. Cấu trúc chương: **đã chọn 6 chương** (dàn ý v1 ở file 07) vì user muốn
   nhấn mạnh Discussion thành chương riêng — cần thầy Vũ xác nhận (slide Khoa
   của thầy mô tả khung 5 chương nhưng không cấm tách Discussion).
4. Danh sách thực nghiệm bổ sung trong 25 ngày — đã rõ một phần: eval 4 site
   (Shopping/Shopping Admin/GitLab/Reddit) là bắt buộc; còn cân nhắc: lặp
   eval để có mean±CI (ưu tiên #1 theo 05/P0-1), ablation graph-explore vs.
   flat-explore, judge/reannotation on/off.
