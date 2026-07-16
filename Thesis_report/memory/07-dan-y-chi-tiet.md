# Dàn ý chi tiết báo cáo (v1 — 2026-07-17, chưa gửi GVHD duyệt)

Đề tài: **Small Language Models for Web AI Agents** (tên tiếng Anh đề xuất,
chờ chốt) — "Mô hình ngôn ngữ nhỏ cho tác nhân trí tuệ nhân tạo trên web".
Báo cáo viết **tiếng Anh**. Cấu trúc **6 chương** (Intro / Related Work /
Method / Experiments / Discussion / Conclusion) — chọn 6 thay vì 5 vì user
muốn nhấn mạnh Discussion thành chương riêng; ⚠️ cần xác nhận với thầy Vũ.

Trọng tâm theo yêu cầu user: **Chương 3 (Method), Chương 5 (Discussion),
Chương 6 (Conclusion)** viết đậm; Chương 4 dựng khung trước, các mục đánh dấu
`[TO ADD]` sẽ bổ sung khi có thực nghiệm mới (~25 ngày tới).

Narrative xuyên suốt (nhắc lại ở Abstract, C1, C6): *LLM lớn làm web agent tốt
nhưng đắt; SLM rẻ nhưng yếu vì thiếu dữ liệu huấn luyện chất lượng; chúng tôi
xây pipeline khám phá website dựa trên GRAPH, tự phát hiện SEMANTIC TASK đã
được kiểm chứng, tạo dataset SFT, và cho thấy SLM 9B được fine-tune cải thiện
trên benchmark WebArena chính thức.*

---

## Front matter

- Title page / phụ bìa theo mẫu Khoa (hỏi giáo vụ về bìa tiếng Anh/song ngữ).
- Acknowledgments; Glossary & abbreviations (SLM, LLM, SFT, LoRA, HSGE, axtree,
  MDP, option, operator, WebArena, BrowserGym... — dùng script glossary có sẵn).
- Chapter summaries (decuong); ToC; List of Figures/Tables.
- **Abstract** (100–300 từ, 5 phần theo slide thầy Vũ): context/problem 1–2 câu
  → objective 1 câu → method 1–2 câu → results 1–2 câu (hedge đúng mức, xem 05)
  → conclusion 1–2 câu.

## Chapter 1 — Introduction (~8–10 trang)

Roadmap đánh số đầu chương; transition cuối chương (áp dụng cho MỌI chương).

- **1.1 Context and motivation** — hook thực tế (một tác vụ web lặp lại: tạo
  issue GitLab, quản lý repo...); web agent là gì; hiện trạng: agent chạy trên
  LLM proprietary lớn → chi phí API, độ trễ, privacy, không tự chủ; SLM
  (≤~10B, chạy local) là hướng thay thế nhưng success rate thấp. Dẫn chứng
  bằng số liệu có kiểm chứng (WebArena: human ~78% vs GPT-4 ~14% — verify số
  từ paper gốc; giá API vs self-host). KHÔNG nêu số kết quả của đề tài ở đây.
- **1.2 Problem statement** — Input: một website không có annotation + một SLM
  pretrained. Output: SLM đã fine-tune hoàn thành task ngôn ngữ tự nhiên trên
  site đó. Formal hóa: web env như (PO)MDP (observation = accessibility tree,
  action space click/fill/goto...); bài toán con trọng tâm: **tự động sinh
  cặp (goal, trajectory) chất lượng cao không cần người gán nhãn**. Tiêu chí
  đánh giá: task success rate trên benchmark WebArena (evaluator chính thức).
- **1.3 Challenges** — (i) exploration trên site thật: bùng nổ trạng thái,
  trang trùng lặp, side effects; (ii) sinh task **có ngữ nghĩa** thay vì click
  ngẫu nhiên; (iii) kiểm chứng chất lượng trajectory (agent tự chấm bài mình);
  (iv) task dài hạn cần compose nhiều kỹ năng; (v) giới hạn của SLM.
- **1.4 Objectives and contributions** — liệt kê khớp chuỗi thách thức:
  (1) pipeline khám phá dựa trên **two-level graph** (skill → operator →
  chained goal task); (2) cơ chế sinh + kiểm chứng **semantic task** (LLM
  proposal, judge, thought reannotation); (3) dataset SFT + SLM Qwen3.5-9B
  fine-tuned; (4) đánh giá trên WebArena GitLab chính thức; (5) báo cáo kinh
  nghiệm & best practices vận hành agent trên site thật. Contribution box:
  phân tách rõ cái có sẵn (WebArena, BrowserGym, LLaMA-Factory, Qwen) vs. cái
  đề tài tạo ra.
- **1.5 Scope** — 1 site family (WebArena self-host, GitLab là site đánh giá);
  SFT/LoRA (không RL); SLM cỡ 9B; tiếng Anh; không xử lý CAPTCHA/login ngoài
  phạm vi benchmark.
- **1.6 Thesis organization** — kèm **hình Big Picture** (pipeline tổng quan
  từ website → graph exploration → semantic tasks → dataset → SLM → eval).

## Chapter 2 — Background and Related Work (~10 trang)

Mỗi mục: gom theo chủ đề, cũ → mới, mỗi công trình 2–4 câu, **kết bằng câu
critique** ("However, ...") — tránh lỗi "giống khảo sát tài liệu".

- **2.1 Background** — web agent formulation (obs/action space, axtree);
  benchmark & môi trường: WebArena, BrowserGym; agent loop kiểu
  ReAct/CoT; SFT & LoRA (ngắn gọn, đủ để C3.7 đứng được).
- **2.2 LLM-based web agents** — các agent trên WebArena và tương tự (baseline
  gốc, các phương pháp prompting/planning). *However*: phụ thuộc LLM lớn
  proprietary, chi phí cao, không cải thiện được model.
- **2.3 Skill/workflow discovery and memory for agents** — options framework
  ⟨I, π, β⟩; Agent Workflow Memory (AWM) và các hướng induce workflow/skill.
  *However*: memory phẳng, skill không được verify, không compose có cấu trúc.
- **2.4 Automatic data generation for agent training** — các pipeline sinh
  instruction/trajectory cho web agent (khảo sát & verify citation: NNetNav,
  OS-Genesis, Synatra... — PHẢI verify từng paper theo quy trình 04). *However*:
  exploration phẳng/ngẫu nhiên → task nông, ít kiểm chứng chất lượng.
- **2.5 Small language models as agents / distillation** — xu hướng SLM agent,
  distill từ model lớn. *However*: nghẽn ở chất lượng dữ liệu, không phải
  thuật toán train.
- **2.6 Positioning** — bảng so sánh các trục: exploration có cấu trúc graph?
  task có verify? có compose dài hạn? train SLM? → khoảng trống mà HSGE lấp.
- Nguồn cần đọc/kiểm tra: 2 paper PDF trong `Thesis_report/thesis_v3/`
  (2507.17128v2, 2510.02585v1 — xem có liên quan không), paper WebArena,
  BrowserGym, AWM; tìm SOTA 2024–2026 bằng web search khi viết.

## Chapter 3 — Proposed Method (~18–22 trang) ★ TRỌNG TÂM

Nguồn chính: `.claude/rules/architecture.md`, `docs/superpowers/specs/*`,
`hsge/` source. Quy tắc: sơ đồ + diễn giải từng thành phần; thuật toán = mã
giả; hạn chế code thật; link repo để footnote.

- **3.1 Overview** — nhắc lại problem setup; **kiến trúc tổng quan** (hình):
  Exploration loop → Skill discovery → Operator graph → Goal-task generation →
  Data curation → SFT. Ba design principles: (P1) *verify trước khi tái sử
  dụng* (skill/task/trajectory đều qua cổng kiểm chứng); (P2) *graph thay vì
  flat* (hai tầng: trang–trạng thái & kỹ năng–operator); (P3) *semantic task
  do LLM đề xuất, có phân loại và khử trùng lặp*.
- **3.2 Two-level graph formalism** — định nghĩa & ký hiệu: low-level graph
  (page states + trajectory edges); high-level graph (skill = option ⟨I, π, β⟩,
  initiation/effect edges, skill→skill composition edges); operator =
  ⟨preconditions, effects⟩ trên NL predicates được chuẩn hóa embedding;
  terminal predicate. Đây là phần "GRAPH" của câu chuyện — viết kỹ.
- **3.3 Graph-guided exploration** —
  - Frontier: priority queue 2 tier (tier 0 = URL agent thực sự đi tới;
    tier 1 = href mining) + **URL templating** với per-template cap (chống
    flood trang trùng dạng) + content dedup bằng axtree hash. Mã giả frontier
    loop. Lý do thiết kế: frontier starvation từ run thật (kể ở C5).
  - **Semantic task proposal** (PageExplorer): LLM đề xuất task cụ thể theo
    trang, phân loại cấu trúc INFO/NAV/MOD, negative context + dedup sitewide,
    read-only mode, thứ tự cắt (INFO bị cắt trước). Đây là phần "SEMANTIC
    TASK" — nêu rõ vì sao task LLM-proposed ≠ random walk.
  - **Solver**: action space 10 hành động, history có outcome, phát hiện kẹt
    (same-target + no-progress → warn → hard stop), wrap-up call, infeasible
    là kết cục hạng nhất. Mã giả solve loop.
- **3.4 Skill discovery pipeline** — segmentation (cut = URL change + axtree
  similarity drop, LLM arbitration, merge nav 1-step); streaming clustering
  (cosine-threshold/DP-means, không cần biết trước số cluster); abstraction
  (cluster → parameterized SkillCard); verification (admit khi ≥k lần thành
  công ở ngữ cảnh held-out). Mỗi bước 1 hình nhỏ hoặc 1 ví dụ chạy thật.
- **3.5 From skills to operators and composed goal tasks** — operator
  induction bằng LLM (vocabulary-aware để tái dùng predicate, anti-tautology
  gate `eff − pre`); predicate registry (canonical id, threshold, vì sao
  embedding-only thất bại — số liệu 0.570/0.606 từ wa_run_09); BFS planning;
  **operator chaining** (`all_chains` DFS bounded) → mỗi chain ≥2 operator
  thành 1 composed GOAL task với instruction sinh tự động — đây chính là cơ
  chế tạo **long-horizon semantic task**. Verify: deterministic khi có
  terminal predicate, self-graded + offline judge khi không.
- **3.6 Data curation for SFT** — 3 pass offline: judge (LLM re-verify các
  episode tự nhận thành công); thought reannotation (state/reflection/subgoal/
  completion-check, replay segmentation offline; subgoal chỉ ở target, không ở
  prompt — tránh train/serve mismatch); dataset builder (**prompt parity** với
  Solver thật: cùng SYSTEM, cùng axtree cap, cùng outcome-annotated history;
  loại step lỗi; giữ infeasible; curriculum ordering; metadata trajectory).
  Nhấn mạnh nguyên tắc: *dữ liệu train nhìn thấy đúng cái model sẽ thấy lúc
  inference*.
- **3.7 SLM fine-tuning and serving** — LoRA trên Qwen3.5-9B (LLaMA-Factory,
  template nothink — lý do: data không có <think>), split theo trajectory
  (chống leak), merge + vLLM serving, tắt thinking khi inference.
- **3.8 Implementation** — bảng module ↔ vai trò; seam mock/real backend
  (giá trị: test deterministic không cần API); per-role LLM routing. Ngắn gọn,
  chi tiết đẩy xuống Appendix A.

## Chapter 4 — Experiments (~8 trang khung, sẽ nở ra) — bổ sung sau

- **4.1 Experimental setup** — môi trường: WebArena self-host (GitLab qua
  tunnel), vast.ai A100-80GB; model theo role (bảng từ config.yaml); tham số
  run (max_nodes/steps/tasks, maturity...); công cụ đánh giá: BrowserGym
  scored envs + evaluator chính thức, replay terminal action.
- **4.2 Data collection results** — số liệu các run (wa_run_02/07/09/12):
  nodes, tasks proposed/solved/infeasible, skills admitted, operators, chains;
  dataset cuối: 370 examples (352 train / 18 val). Bảng + 1–2 ví dụ semantic
  task/skill tiêu biểu.
- **4.3 Fine-tuning results** — loss (0.32 train / 0.24 eval), thời gian/chi
  phí (bảng từ docs/14).
- **4.4 Main evaluation: official WebArena GitLab (180 tasks)** — protocol
  (kể cả two-machine read/write split + reset giữa sweep); kết quả hiện có:
  baseline 10/180 (5.56%) vs finetuned 12/180 (6.67%), +1.1pp (~20% relative).
  **Trình bày là tín hiệu định hướng** — hedge theo 05/P0-1, ghi rõ n=1.
- **4.5 [TO ADD] Statistical repeats** — chạy lặp ≥3–5 lần (hoặc nhiều seed)
  cho baseline & finetuned → mean ± SD, 95% CI, test phi tham số. Ưu tiên #1.
- **4.6 [TO ADD] Ablations** — (a) **graph-explore data vs. flat-explore
  data** (cùng budget LLM/episode — thực nghiệm "đinh" chứng minh giá trị
  pipeline); (b) có/không judge pass; (c) có/không thought reannotation;
  (d) [nếu kịp] site thứ hai (reddit/shopping) để xem transfer.
- **4.7 Analysis** — breakdown theo loại task, ví dụ thành công/thất bại định
  tính, failure taxonomy (nối sang C5).

## Chapter 5 — Discussion (~10–12 trang) ★ TRỌNG TÂM

Dạng "báo cáo kinh nghiệm + best practice" — mỏ tư liệu: docs/10–14,
`.claude/memory/bugs.md`, changelog. Mỗi mục: vấn đề gặp thật → chẩn đoán →
giải pháp → bài học khái quát. Chi tiết dài đẩy xuống Appendix, chương giữ ý chính.

- **5.1 Interpreting the results** — vì sao cải thiện khiêm tốn (352 examples,
  9B model, 1 site); cái pipeline thực sự đóng góp (dữ liệu có cấu trúc, có
  kiểm chứng) vs. cái chưa chứng minh được; trả lời từng RQ nếu C3 đặt RQ.
- **5.2 Exploring live websites is an engineering problem** — frontier
  starvation (run reddit dừng 57/500 nodes) → href mining + template caps;
  46% task trùng lặp → dedup + negative context; trang lỗi/timeout → node
  error resilience, fail-soft; site chia sẻ trạng thái → read-only mode,
  reset kỷ luật, cấm task xóa account.
- **5.3 LLM agents need structural guardrails, not prompt nudges** — [TAG]
  convention thất bại (89% không có bracket) → structured output; warning
  chống kẹt không đủ (model click link chết hết 15 bước) → hard stop theo
  same-target + no-progress; INFO task tự lộ đáp án; vision call rỗng → retry
  text-only. Bài học: *đo hành vi thật rồi mới thiết kế cơ chế*.
- **5.4 Verified structure beats raw scale in operator induction** — operator
  tautological (3/4 ở wa_run_09) → anti-tautology gate; embedding-only không
  gộp được synonym (0.570 < 0.6 < 0.606 false pair) → vocabulary-aware
  induction; grounding check chất lượng operator.
- **5.5 Training and serving SLMs: pitfalls** — chat template & thinking mode
  (nothink); "prompt-fidelity bug" (test prompt xấp xỉ → tưởng train hỏng);
  venv isolation (transformers@main vs vLLM pin); judge pass bắt "tự chấm bài
  mình"; prompt parity train ↔ inference.
- **5.6 Best practices (distilled)** — bảng ngắn: verify-then-admit; prompt
  parity; fail-soft mọi browser op; persist artifact mỗi node (interrupt-safe);
  two-machine eval với phân loại read/write; log mọi event ra jsonl.
- **5.7 Threats to validity & limitations** — internal (n nhỏ, n=1/task,
  LLM-judge bias), external (1 site, 1 model size), construct (success-rate
  evaluator). Trung thực nhưng ngắn — phần "hạn chế" chính thức không nằm ở
  Kết luận (theo hướng dẫn).

## Chapter 6 — Conclusion (~4–5 trang) ★ TRỌNG TÂM

- **6.1 Summary of contributions and products** — liệt kê sản phẩm cụ thể:
  (1) HSGE pipeline (mã nguồn, mock + real backend); (2) bộ semantic task +
  trajectory dataset SFT; (3) SLM Qwen3.5-9B fine-tuned; (4) kết quả benchmark
  chính thức; (5) bộ kinh nghiệm/best practices + tutorial tái lập
  (docs/14, training/README). Nhắc lại thông điệp chính.
- **6.2 Objectives vs. achievements** — bảng đối chiếu từng mục tiêu ở 1.4
  với kết quả đạt được (tập trung ưu điểm, không biện minh).
- **6.3 Future directions** — data scaling (nhiều site, transfer.py đã có
  khung); RL/DPO trên trajectory đã verify; model nhỏ hơn (≤3B); online
  skill retrieval lúc inference (hiện subgoal chỉ dùng lúc train); benchmark
  rộng hơn (WebArena full, các site ngoài benchmark).

## Appendices

- **A** — Detailed design: module map, data schema (Step/SubTrajectory/
  SkillCard/Task), per-role LLM config.
- **B** — Prompts: EXPLORER_SYS, SOLVER_SYS + ACTIONS_DOC, judge, reannotator,
  operator inducer (nguyên văn — minh bạch, khỏi chép vào thân bài).
- **C** — Run statistics chi tiết (bảng per-run, per-node), số liệu đánh giá
  đầy đủ 180 task.
- **D** — Reproducibility guide: lệnh từng bước (thu data → judge → reannotate
  → build → train → serve → eval), repo URL (footnote trong thân bài), checksum
  /release tag nếu công bố.
- **E** — (nếu cần) Nhật ký kinh nghiệm chi tiết cho C5.

---

## Việc viết theo thứ tự đề xuất

1. C3 (Method) — tư liệu sẵn 100%, viết được ngay.
2. C5 (Discussion) — tư liệu sẵn (docs 10–14, bugs.md), viết song song C3.
3. C1 + C6 (cùng narrative, viết sau khi C3/C5 định hình).
4. C2 (cần vòng đọc + verify citation).
5. C4 khung trước, điền số khi thực nghiệm bổ sung xong.
6. Front matter + Appendix cuối cùng.

Checklist mỗi chương khi viết: roadmap đầu chương, transition cuối chương,
không ký hiệu tự đặt chưa định nghĩa, mọi hình/bảng được tham chiếu, câu
<35 từ, mỗi công trình liên quan có câu critique, mọi citation đã verify.
