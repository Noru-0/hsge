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

## Kết quả thực nghiệm đã có (tính đến 2026-07-15)

- **Pipeline SFT 3 giai đoạn**: judge_episodes → reannotate_thoughts →
  build_sft_dataset (train.jsonl, 370 examples / 352 train / 18 val,
  `training/train_12.jsonl`).
- **LoRA fine-tune Qwen3.5-9B** (LLaMA-Factory, template `qwen3_5_nothink`,
  3 epochs, train_loss 0.32 / eval_loss 0.24) trên vast.ai A100-80GB.
- **Eval chính thức WebArena GitLab 180 task** (BrowserGym, prompt của Solver
  thật): **baseline 10/180 = 5.56% vs finetuned 12/180 = 6.67%** (+1.1pp,
  ~20% relative). ⚠️ Sample nhỏ, n=1 mỗi task — báo cáo phải trình bày là tín
  hiệu định hướng, không phải kết luận (xem 05-bai-hoc-review.md mục P0-1).
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
3. Yêu cầu riêng của thầy Vũ về cấu trúc chương (slide Khoa của thầy cho phép
   5 chương Introduction → Related Work → Proposed Approach → Results →
   Conclusions; hướng dẫn thầy Biên là 6 chương tách Experiments/Discussion) —
   chốt số chương trước khi lập dàn ý.
4. Danh sách thực nghiệm bổ sung trong 25 ngày: lặp eval để có mean±CI?
   ablation graph-explore vs. flat baseline? thêm site ngoài GitLab?
