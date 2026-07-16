# Đề tài HSGE — ngữ cảnh & nguồn tư liệu cho báo cáo

Trạng thái: **chưa chốt dàn ý / tên đề tài / phạm vi chương** — cần xác nhận
với sinh viên (Kiết) và GVHD trước khi viết. File này gom sẵn nguyên liệu từ
repo để khi viết không phải đào lại.

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

## Điểm cần chốt trước khi viết (hỏi user/GVHD)

1. Tên đề tài chính thức (tiếng Việt) + tên ngắn cho gáy bìa; thông tin SV/MSSV/bộ môn.
2. Câu chuyện chính của khóa luận: (a) HSGE như phương pháp khám phá skill mới,
   (b) pipeline thu thập dữ liệu → SFT cho web agent, hay (c) cả hai? Điều này
   quyết định phát biểu bài toán C1 và phạm vi C3.
3. Có kịp chạy thêm thực nghiệm không (lặp eval nhiều seed, thêm site khác) —
   ảnh hưởng trực tiếp cách viết claim ở C4 (xem P0-1).
4. Làm 1 người hay nhóm; deadline nộp đợt nào (quy trình nộp: xem 01).
5. Ngôn ngữ báo cáo: mặc định tiếng Việt theo mẫu Khoa (thuật ngữ Anh giữ nguyên).
