# Rà Chương 3 theo rubric + audit citation (2026-08-07)

Đối tượng: `thesis_hsge_vi/Chapter3/chapter3.tex` (467 dòng, ~15 trang).
Rubric: `KLTN/Khoa-CNTT-Tieu-chi-va-bieu-mau-cham-diem-tot-nghiep-v4-...pdf`,
bảng **hướng nghiên cứu** (TC1 15%, TC2 20%, TC3 20%, TC4 10%, TC5 20%,
TC6 15%, TC7 10% cộng). Chương 3 chịu tác động chính ở TC2/TC3/TC5.

## Citation — đã xác minh

9 `\cite` trong chương, **cả 9 entry .bib đều đúng** (tác giả/tiêu đề/venue/
năm/trang) và **dùng đúng ngữ cảnh**: `sutton1999options`, `fikes1971strips`,
`kulis2012dpmeans`, `reimers2019sbert`, `yao2023react`, `hu2022lora`,
`zheng2024llamafactory`, `kwon2023vllm`, `qwen2026qwen35`.

Ngoại lệ: `qwen2026qwen35` là blog công ty (02/2026) — không xác minh được
bằng nguồn thứ ba và **thiếu ngày truy cập** (quy định Khoa: link web phải
ghi ngày truy cập).

## Citation — còn thiếu (4 chỗ)

| Dòng | Phát biểu | Nên cite |
|---|---|---|
| 42 | "mô hình hóa website như một POMDP" | Kaelbling, Littman & Cassandra 1998 — **chưa có trong .bib**; cả Ch2 cũng không cite POMDP |
| 42, tab:actions | axtree làm quan sát + không gian hành động 10 lệnh | `zhou2024webarena` + `dechezelles2025browsergym` — **đã có trong .bib nhưng Ch3 không cite lần nào**; đang trình bày như thể là của HSGE |
| §3.6.1 | dùng LLM mạnh hơn chấm lại episode | Zheng et al. 2023 (LLM-as-a-judge, MT-Bench) — chưa có trong .bib |
| 364 | xếp dữ liệu dễ→khó thành curriculum | Bengio et al. 2009 (Curriculum Learning, ICML) — chưa có trong .bib |

## Claim thực nghiệm thiếu con trỏ dẫn chứng (4 chỗ)

Ch3 nói "thực nghiệm cho thấy…" mà không trỏ đi đâu, **dù Chương 5 có sẵn
số liệu** — chỉ cần thêm `Mục~\ref{...}`:

| Ch3 | Nội dung | Bằng chứng nằm ở |
|---|---|---|
| 129 | LLM không tuân thủ quy ước gắn thẻ | §5.3.1 (89%) → `sec:disc-guardrails` |
| 131 | đề xuất thoái hóa thành menu điều hướng | §5.2.2 (46%) → `sec:disc-exploration` |
| 147 | cảnh báo văn bản không đủ, phải hard stop | §5.3.2 → `sec:disc-guardrails` |
| 206–209 | 0,570 / 0,606 | §5.4.2 → `sec:disc-operators` |

Rubric TC5 mức <5 ghi thẳng: "Nội dung thiếu dẫn chứng, minh chứng được xem
là sai hoặc không đáng tin cậy."

## Lỗi cấu trúc / nội dung

1. **Lời hứa gãy**: dòng 175 hẹn "đánh đổi… sẽ được thảo luận chi tiết tại
   Chương 5" — **Chương 5 không có mục đó** (chỉ 1 dòng trong bảng best
   practice, dòng 290). Đây đúng chỗ hội đồng sẽ soi: P1 nói "kiểm chứng
   trước khi tái sử dụng" nhưng trên website thật cổng thực-thi-lại bị bỏ,
   chỉ còn độ lặp + kết quả episode.
2. **Mâu thuẫn liên chương**: Ch3 dòng 129 ghi `k = 6` (max_tasks), phụ lục
   `tab:app-params` ghi `max_tasks = 9` ("giá trị đã dùng").
3. **Ch3 không tham chiếu phụ lục lần nào** — trong khi `app:design-params`
   (bảng tham số) và `app:prompts` (toàn bộ prompt) chính là phần Ch3 mô tả.
4. **Chỉ 1 mã giả** (`alg:frontier`). GVHD yêu cầu "thuật toán (mã giả)";
   đóng góp lõi — ghép chuỗi operator → semantic task (§3.5.3) và pipeline
   phát hiện skill (§3.4) — hiện chỉ có văn xuôi.
5. **Không có câu nào nói rõ cái mới của HSGE so với nền vay mượn**
   (options/STRIPS/ReAct/DP-means/SBERT). Xem pattern GVHD #2 trong
   [02-huong-dan-gvhd](02-huong-dan-gvhd.md): phải phân biệt nghiên cứu nền Y
   và giải pháp X.

## Lỗi văn phong (TC5)

- **Lệch giọng giữa hai nửa chương**: §3.1–3.4 câu dài, đặc; §3.5–3.8 ngắn,
  phẳng. 24 câu ≥ 45 âm tiết (~30 từ), dài nhất 71/66/63/63/60/58; 5 đoạn
  > 200 âm tiết, dài nhất 325 (dòng 147).
- **Thuật ngữ không nhất quán**: "graph" 21 lần vs "đồ thị" 13 lần, kể cả
  trong tiêu đề §3.3 "Khám phá có định hướng theo graph" trong khi §3.2 dùng
  "đồ thị". `tomluoc.tex` vừa được chuẩn hóa sang "đồ thị", Ch3 thì chưa.
- **Tiếng Anh chưa chú thích và không có trong bảng thuật ngữ** (vi phạm quy
  ước của user, xem [05-bai-hoc-review](05-bai-hoc-review.md)): tautology
  (216), vocabulary-aware (210), goal task (262), subgoal (333), predicate
  registry (233), instruction-tuning (346), backend (407), serving (388).
- Typo "Kavniệm" → "Khái niệm" (dòng 71) — **đã sửa 2026-08-07**.
- Label định nghĩa nhưng không nơi nào tham chiếu: `sec:method-solver`,
  `sec:method-skills`, `sec:method-sft`, `sec:method-impl`,
  `sec:method-overview`.

## Đã sửa (2026-08-07, cùng ngày audit)

Hạng mục 1–4 trong danh sách đề xuất đã làm xong, build sạch (0 error,
0 undefined, 0 dấu `??`, 123 trang):

1. Thêm 4 cross-ref sang Chương 5 (`sec:disc-guardrails` ×2,
   `sec:disc-exploration`, `sec:disc-operators`); thêm 4 tham chiếu
   `app:design-params` (trước đó Ch3 không trỏ phụ lục lần nào); ghi rõ
   `k = 6` là mặc định còn các lượt chạy dùng `k = 9`, bổ sung maturity = 2
   và ngưỡng predicate 0,6 vào thân bài.
2. Thêm 3 entry `.bib` mới (`kaelbling1998pomdp`, `bengio2009curriculum`,
   `zheng2023judge`) + cite `zhou2024webarena`/`dechezelles2025browsergym`
   cho axtree & action space, kèm một câu nói thẳng đây là quy ước kế thừa
   chứ không phải đóng góp của khóa luận. Thêm ngày truy cập cho
   `qwen2026qwen35`. Ch3 giờ có 14 citation (trước: 9).
3. Chuẩn hóa "graph" → "đồ thị" trong Ch3 (kể cả tiêu đề §3.3); giữ
   "operator graph"/"(graph)" ở dạng chú thích tiếng Anh một lần. Chú thích
   8 thuật ngữ: tautology, vocabulary-aware, predicate registry, goal task,
   subgoal, instruction-tuning, backend, serving.
4. Tách câu/đoạn dài: đoạn > 200 âm tiết 5 → 2 (hai đoạn còn lại là danh
   sách roadmap và itemize P1–P3); câu ≥ 45 âm tiết 24 → 17; câu ≥ 55 âm
   tiết 6 → 1 (câu còn lại là liệt kê (i)–(iv), để nguyên cho dễ đọc).

## Chuẩn hóa "graph" toàn quyển (2026-08-07)

Quét nốt các chương còn lại: Ch1 ×1, Ch2 ×1, Ch5 ×1, Ch6 ×8, `appendix1.tex`
×10, `glossary.tex` ×2, và tiêu đề ngắn `\caption[Graph hai tầng]` của
`fig:twolevel` (lệch với tiêu đề đầy đủ, hiện ra ở Danh sách hình).

Quy ước đã chốt: **"đồ thị"** là từ chính; "operator graph" → **"đồ thị toán
tử"**; "skill graph" → **"đồ thị kỹ năng"**. Chỉ giữ chú thích tiếng Anh
`(graph)` đúng **một lần** ở lần xuất hiện đầu tiên trong Chương 1, và
`(operator graph)` một lần ở §3.2.3 — đúng quy ước thuật ngữ của user; hai
chỗ chú thích lặp trong Chương 3 đã bị bỏ.

**Cố ý không sửa:**
- `Appendix/decuongchitiet.tex` (~14 chỗ) — đây là **đề cương chi tiết đã có
  chữ ký GVHD**, mục 8 cấu trúc quyển (xem [01-quy-dinh-khoa](01-quy-dinh-khoa.md)).
  Sửa câu chữ của nó là sửa nội dung đã được duyệt và ký.
- `Chapter4/chapter4.tex` dòng 49 — nằm trong comment `%` của khung chưa viết.
- `graph.py`, "Hierarchical Skill-Graph Exploration", "Graphical User
  Interface" — tên file và tên riêng.

⚠️ **Còn nợ**: hai hình `Figures/fig_pipeline.pdf` ("Induction operator +
operator graph") và `Figures/fig_roadmap.pdf` vẫn còn chữ "graph" bên trong.
**Không tìm thấy file nguồn sinh hình** trong repo — chỉ có PDF đã render
(20/07). Muốn sửa phải vẽ lại. Đây là loại lỗi chỉ người mở PDF mới thấy,
đúng cảnh báo trong [05-bai-hoc-review](05-bai-hoc-review.md).

## Mã giả §3.4 và §3.5.3 (2026-08-07)

Đã thêm 2 thuật toán, viết bám sát code thật chứ không phác theo văn xuôi:

- `alg:discovery` (§3.4) ← `segmentation._candidate_boundaries` /
  `_merge_trivial_nav` / `segment_trajectory`, `clustering.OnlineClusterer`,
  `library.observe` + `_try_admit`. Có ghi rõ pipeline chỉ chạy trên quỹ đạo
  **thành công** (`runtime.py:802` — `if success:` mới gọi `on_trajectory`).
- `alg:semantic` (§3.5.3) ← `operators.OperatorGraph.all_chains` (DFS có
  chặn `min_len`/`max_len`/`max_paths`, thứ tự tất định, chuỗi con cũng được
  phát ra) + `runtime._goal_tasks` (ngân sách mỗi node, `_attempted_chains`,
  chọn `reached()` khi operator cuối terminal và có `terminal_goal`, ngược
  lại là solver + judge; backup `plan()` khi đồ thị quá thưa).

Sửa kèm trong `main.tex`: `\ALG@name` → "Thuật toán" (trước đó caption ra
"Algorithm" tiếng Anh giữa quyển tiếng Việt), `\numberwithin{algorithm}
{chapter}` (trước đó đánh số 1,2,3 trong khi Hình/Bảng đánh 3.1, 3.2),
`\algorithmicrequire/ensure` → "Đầu vào/Đầu ra". Giờ là Thuật toán 3.1–3.3,
cả ba đều được tham chiếu trong thân bài.

⚠️ **Bài học kỹ thuật**: `\textsc{}` với chữ tiếng Việt có dấu bị vỡ dưới font
encoding T5 ("P HÂN X Ử"). Tên thủ tục trong mã giả phải để ASCII —
đúng cách `alg:frontier` vốn đã làm.

⚠️ **Lỗ hổng mới phát hiện**: `runtime.py` còn một nguồn sinh GOAL task thứ
ba là **seed capabilities** (`self.site_seed`, lấp phần ngân sách còn dư khi
chuỗi operator không đủ) — **Chương 3 không mô tả cơ chế này ở đâu cả**, dù
theo [[phase-a-seed-goal-validated]] nó đã được dùng trong run
`wa_seed_shopping`. `alg:semantic` cố ý viết đúng phạm vi mà chương mô tả
(ghép chuỗi + backup terminal). Cần quyết định: hoặc viết thêm một tiểu mục
cho seed, hoặc nói rõ nó nằm ngoài phạm vi báo cáo.

Còn lại: câu phát biểu điểm mới so với nền vay mượn (TC3), và việc lớn nhất
là viết mục ở Chương 5 cho đánh đổi kiểm chứng skill mà §3.4.4 đang hứa.

## Đánh giá tổng thể

Phần đóng góp của Chương 3 vào rubric: **TC2 ~7,5/10** (kiến trúc + hình +
lý giải tốt, mất điểm ở mã giả và tham số/dẫn chứng), **TC3 ~7/10** (đóng góp
có thật nhưng chương không tự phát biểu điểm mới), **TC5 ~7/10** (mạch lạc,
đủ hình/bảng, nhưng câu dài, thuật ngữ lệch, thiếu con trỏ dẫn chứng).
Không có lỗi nào thuộc nhóm "phải sửa mới nộp được"; tất cả đều là sửa cộng
điểm, phần lớn tốn dưới nửa ngày.

## Chấm lại Chương 3 (2026-08-12, bản sau khi đồng bộ code + cắt gọn)

Chốt trên commit `84184a0`. Ghi chú: bản chấm trước đó trong file này được
viết trên một trạng thái **đang sửa dở** (818 dòng, 3 thuật toán) — số liệu
dưới đây thay thế nó.

Đối tượng: `chapter3.tex` **817 dòng** (bản audit 2026-08-07: 467), tương ứng
**trang 22–57 của PDF = 36 trang**. Build sạch: 15 citation, 46 `\ref` đều
phân giải, 0 dấu `??`. Cấu trúc: 8 mục, 16 tiểu mục, 6 hình, 2 bảng,
**2 thuật toán**.

### Việc đã làm trong đợt này (2026-08-12)

Hai đợt sửa liên tiếp, cùng ngày:

**(a) Đồng bộ với code.** Chương 3 trước đó mô tả một phiên bản pipeline cũ.
Mười nhóm sai lệch đã sửa, nặng nhất là hai chỗ **mâu thuẫn trực tiếp với
Chương 4**: thiếu hẳn cơ chế lấy mẫu không tiền tố (C4 báo cáo cả nhóm
UNPREFIXED mà C3 chưa từng định nghĩa → thêm §3.3.4), và ghi sai phép chia
train/val là theo trajectory trong khi code chia theo (site, goal). Còn lại:
cổng grounding của effect, trần template cho tier-0, loại task COMPOSITE,
chốt novelty + chế độ bám subgoal của solver, judge chạy inline, ba bộ lọc
khâu dựng dataset, `scroll`/`hover`/`noop` + `goto` tương đối,
checkpoint/resume. Phụ lục: bảng tham số +8 dòng, 4 prompt cập nhật theo code,
thêm prompt `site_seeder` và `goal_planner`.

**(b) Cắt gọn theo yêu cầu user.** Thêm **§3.3.5 "Một phiên được chấm thành
công như thế nào"** (gom ba cơ chế `reached` tất định / tự tuyên bố + cổng mã
cho MOD-COMPOSITE / judge inline, trước đó nằm rải ở ba mục và không chỗ nào
phát biểu trọn vẹn — đây là câu hỏi user hỏi thẳng). Bỏ §3.6.1 cũ (nội dung
chuyển vào §3.3.5), gộp §3.4.1–3.4.3, xoá Thuật toán 3, xoá đoạn backend mô
phỏng ở §3.8, xoá Hình `fig_curation`.

**Bỏ hẳn bước viết lại suy nghĩ (thought re-annotation) khỏi toàn quyển** —
đây là phát hiện đáng nhớ nhất của đợt này: kiểm `training_data/train.jsonl`
cho thấy **0/4288 mẫu** mang định dạng `State:/Reflection:`, tức bước này
**chưa từng được chạy** cho tập huấn luyện thật. Mô tả nó trong báo cáo là một
claim không có dữ liệu đỡ. Đã gỡ ở C1 (danh sách đóng góp), C3, C4 (ablation
(c) đổi thành cổng hành động hữu hiệu), C5 (threats), C6 (2 chỗ) và phụ lục
(bảng script, bảng vai trò LLM, prompt, lệnh runbook).

### Điểm quy đổi

**TC2 8,5/10 — TC3 7,5/10 — TC5 7,5/10** (bản 2026-08-07: 7,5 / 7 / 7).

- **TC2 (phương pháp, 20%)**: pipeline mô tả trọn vẹn và **khớp code đã chạy
  thật**; §3.3.5 làm rõ tiêu chí thành công, vốn là phần "phương pháp đánh
  giá" mà rubric đòi. Trần 8,5 chứ không cao hơn vì mục "có căn cứ, dẫn
  chứng" bị 9 câu số liệu không truy nguyên được kéo xuống (xem nợ #1).
- **TC3 (đóng góp, 20%)**: đóng góp có thật và nay được mô tả trung thực hơn
  (bỏ claim không có dữ liệu, công bố các cổng lọc). Vẫn 7,5 vì chương không
  tự phát biểu điểm mới (nợ #3).
- **TC5 (báo cáo viết, 20%)**: cộng điểm ở cấu trúc (hết tiểu mục mồ côi, hết
  hình mâu thuẫn với chữ), trừ điểm ở câu văn (xem nợ #5). Hai lực triệt tiêu
  nhau nên giữ 7,5.

### Còn nợ, xếp theo rủi ro trước hội đồng

1. **9 câu mang số liệu run phát triển, không có ở bất kỳ chương nào khác**:
   58/158 node, 49% INFO, 118 phiên, 287/465, effect accuracy 0,0, 136 lần bỏ
   cuộc & 23% & 39% Reddit, 10/57, 29/56 (chỉ "465" là có mặt ở C5). Chúng
   được dùng làm lý lẽ thiết kế nhưng không trỏ đi đâu → đúng mô tả TC5 mức
   <5 ("nội dung thiếu dẫn chứng"). **Đợt sửa 2026-08-12 làm vấn đề này nặng
   thêm**, vì phần lớn số mới thêm thuộc loại đó. Cách rẻ nhất vẫn là một bảng
   phụ lục "số liệu chẩn đoán từ các run phát triển" rồi trỏ tới.
2. **Lời hứa §3.4.2 vẫn gãy**: "đánh đổi ... thảo luận chi tiết tại
   Chương 5", nhưng C5 không có mục nào bàn việc bỏ cổng thực-thi-lại khi
   kiểm chứng skill trên website thật. Nặng hơn: trên website thật
   `verify_k=0`, nghĩa là cổng kiểm chứng **không hề chạy**, chỉ còn ngưỡng độ
   chín — trong khi P1 tuyên bố "kiểm chứng trước khi tái sử dụng". Đây là
   chỗ chương tự mâu thuẫn với nguyên tắc của chính nó.
3. **Ch3 không tự phát biểu điểm mới** (TC3): chương chỉ nói cái gì *không*
   phải đóng góp (axtree/action space kế thừa từ WebArena + BrowserGym); phần
   định vị nằm ở §2.6 và §1.4, người đọc Ch3 không thấy.
4. **Độ dài 36 trang** so với gợi ý ~18–22 của dàn ý. Phần dôi ra chủ yếu là
   "bài học từ run thật" vốn thuộc Chương 5 → trùng lặp hai chương.
5. **Văn phong đi lùi**: 108/307 câu ≥ 40 âm tiết (35%; bản 08-07: 53/323 =
   16%), 33 đoạn > 130 từ, dài nhất 226. Nguyên nhân: văn mới viết trong đợt
   đồng bộ code đặc và dài câu hơn mặt bằng cũ của chương.
6. **Bảng thuật ngữ (`glossary.tex`, 32 mục) thiếu**: subgoal, seed / site
   seeder, goal task, tautology, predicate registry, COMPOSITE, lấy mẫu không
   tiền tố (unprefixed), grounding.
7. `Figures/fig_pipeline.pdf` còn nhãn **"Cổng chất lượng (judge, viết lại)"**
   bên trong ảnh, không có file nguồn để sửa (cùng loại nợ với "graph" trong
   hình, ghi ở mục trên).

Tham số Ch3 ↔ `tab:app-params` khớp hoàn toàn (k=6 mặc định/9 đã dùng, c=3
tầng 1, c=8 tầng 0, maturity 2, predicate\_sim 0,6, goal\_max\_steps cho lượt
không tiền tố, +8 tham số mới bổ sung ngày 12-08).

## Đợt rà văn phong Chương 3 (2026-08-12 12:15)

User phản hồi: "từ chương 3 thì từ ngữ còn AI và kiểu dịch từ tiếng Anh sang
tiếng Việt quá". Đã sửa từng mục §3.1→§3.8, **chỉ đụng câu chữ** — số liệu,
`\ref`, `\cite`, mã giả, bảng giữ nguyên. Build sạch (157 trang, 0 error,
0 undefined, 7 overfull — bằng trước khi sửa).

**Bốn dấu hiệu "dịch máy" đã nhận diện và xử lý** (dùng lại làm checklist cho
C4–C6):

1. Danh từ hóa + calque: "chịu trách nhiệm phân cắt", "đóng vai trò như một
   bản tuần tự hóa", "Điều này dẫn đến", "Cơ chế này đảm bảo rằng", "được biên
   dịch thành tập dữ liệu", "Việc X là không khả thi do…".
2. **"sẽ" làm thì hiện tại** khi mô tả cơ chế — dấu hiệu dịch thẳng thì tương
   lai/simple present của tiếng Anh. C3: 54 → 14 (14 chỗ còn lại là điều kiện
   hoặc tương lai thật).
3. **Thuật ngữ đôi trong cùng một chương** — dấu hiệu rõ nhất của bản dịch
   nửa vời. C3 trước khi sửa: agent 16 / tác nhân 14, task 36 / tác vụ 83,
   trajectory 16 / quỹ đạo 39, pipeline 16 / chuỗi xử lý 3.
4. Từ đao to búa lớn: "kiến tạo nên", "thoái hóa thành", "ồ ạt", "dừng một
   cách ồn ào" (dịch literal của *noisily*).

**Quy ước thuật ngữ 12-08 (agent→tác nhân, task→tác vụ, ...) — ĐÃ ĐẢO NGƯỢC
13-08.** User quyết định lại: mọi từ đã có trong `glossary.tex` thì **giữ
tiếng Anh xuyên suốt thân bài**, không dịch sang tiếng Việt nữa — kể cả
những từ "nổi bật và hay dùng" như agent/task, chứ không chỉ skill/operator/
episode/pipeline như trước. Lý do: đọc tự nhiên hơn, và khớp cách
skill/operator/frontier/episode/pipeline/node/prompt/... vốn đã luôn giữ
tiếng Anh mà không ai thấy cộm.

| Khái niệm | Từ dùng (từ 13-08) | Ghi chú |
|---|---|---|
| agent | **agent** | trước đó "tác nhân" (12-08→13-08) |
| task | **task** | trừ tên nhãn `INFO/NAV/MOD/COMPOSITE/GOAL`; trước đó "tác vụ" |
| trajectory | **trajectory** | trước đó "quỹ đạo" |
| fine-tune/fine-tuning | **fine-tune** (động từ) / **fine-tuning** (danh từ/quá trình) | trước đó "tinh chỉnh" |
| semantic task | **semantic task** | trước đó "tác vụ ngữ nghĩa" |
| goal task | **goal task** | trước đó "tác vụ mục tiêu" |
| low-level task | **low-level task** | trước đó "tác vụ mức thấp/bậc thấp" |
| web agent | **web agent** | trước đó "tác nhân web" |
| accessibility tree | **accessibility tree** | trước đó "cây trợ năng" |
| precondition / effect | **precondition / effect** | **ngoại lệ**: giữ song ngữ ở lần định nghĩa đầu tiên (Chương 1, §1.1), tiếng Anh thuần các chỗ khác |
| serving | **serving** | trước đó "phục vụ suy luận"/"triển khai suy luận" |
| merge | **merge** | trước đó "hợp nhất" |
| execution layer | **execution layer** | trước đó "tầng thực thi" |
| predicate registry | **predicate registry** | trước đó "sổ đăng ký mệnh đề" |
| reward function | **reward function** | trước đó "hàm phần thưởng" |
| episode | **episode** | không đổi — đã tiếng Anh từ trước; "phiên làm việc" = session đăng nhập, giữ nguyên |
| pipeline, skill, operator, frontier, node, prompt, judge, seed, subgoal, grounding, tautology, trace, curriculum, instance, benchmark, baseline, best practice, chat template, option, runtime, self-host, unprefixed sampling, workflow, world model, wrap-up call | **giữ nguyên tiếng Anh** | không đổi — chưa bao giờ bị dịch |
| induction | **quy nạp** | không đổi — KHÔNG có trong glossary.tex nên không thuộc phạm vi đảo ngược này |
| "đồ thị" (graph) | **đồ thị** | không đổi — "graph" KHÔNG phải headword trong glossary.tex, quy ước dịch riêng (memory 09, đợt 07-08) vẫn giữ nguyên |

Nguyên tắc chung (không đổi): thuật ngữ đã có trong `glossary.tex` thì
**không chú thích lại** mỗi lần dùng (quy ước user ở
[05-bai-hoc-review](05-bai-hoc-review.md)).

**Tiến độ đảo ngược** (theo dõi để không sót chương): C1 xong (13-08 08:48).
C2, C3, C4, C5, C6, Phụ lục 1 còn phải làm — quy mô ước tính ban đầu ~650+
chỗ toàn quyển (agent ~89, task ~348, trajectory ~99, fine-tune ~86, effect
27, precondition 13, accessibility tree 9, serving 8, predicate registry 3,
execution layer 3, merge 2, reward function 1 — đếm trước khi sửa C1).

**Tác động lên các khoản nợ đang mở:** nợ #5 (văn phong) đỡ được một phần —
câu ≥ 40 âm tiết 62 → 46 theo cách đếm tự động, nhưng đây là **tác dụng phụ**
của việc gọn câu, chưa phải đợt tách câu có chủ đích, nên vẫn để nợ #5 mở.
Chương ngắn đi 3 trang (36 → 33), nợ #4 (độ dài) nhích một chút. Các nợ #1,
#2, #3, #6, #7 **chưa đụng tới**.

**Chưa làm**: C4, C5, C6 vẫn còn nguyên lỗi cùng loại — C6 nặng nhất
("agent" 12 lần / "tác nhân" 0, "task" 21 / "tác vụ" 0). User muốn đọc lại C3
rồi mới quyết.

**Cập nhật 2026-08-13**: C4 đã rà xong (thuật ngữ hóa ra đã sạch từ đợt đồng bộ
run 20 trước đó; chỉ còn 4 dấu hiệu dịch máy ở §4.1.4, §4.6.2, "Tổng kết
chương" + 6 chú tiếng Anh dư bị chuyển vào glossary). Chi tiết: xem entry
2026-08-13 08:26 trong `.claude/memory/changelog.md`.

C5 cũng đã rà, nhưng hóa ra **đã sạch từ trước** — không có 4 dấu hiệu dịch
máy, chỉ 3 điểm nhỏ (2 chú tiếng Anh dư + 1 đoạn dài gộp ý). Chi tiết: entry
2026-08-13 08:30 trong changelog. Bài học rút ra: không phải chương nào cũng
cần cùng mức sửa — nên chẩn đoán trước rồi mới quyết mức độ, thay vì áp mù
quáng cùng một lượng sửa cho mọi chương.

C6 cũng đã rà (2026-08-13 08:34) — ghi chú cũ "C6 nặng nhất: agent 12 lần /
tác nhân 0" đã **lỗi thời**, đợt đồng bộ thuật ngữ C4–C6 (`eb0ef76`, trước
phiên này) đã sửa hết rồi. Chỉ còn 2 điểm nhỏ: 1 câu bị động, 1 câu kết tự
tin hơn số liệu thật (đã hạ giọng khớp cách bảng O4 diễn đạt). Cả C4/C5/C6
giờ đã rà xong; chỉ C1/C2 còn ở mức "chỉ tách câu dài" (chưa áp checklist 4
dấu hiệu dịch máy) — nhưng user chỉ yêu cầu "từ chương 3" nên chưa đụng.


## Nợ #3 và #5 đã đóng (2026-08-12 19:46)

**Nợ #3 — điểm mới so với nền vay mượn.** Đã thêm §3.2 `sec:method-novelty`
"Nền tảng kế thừa và điểm mới của HSGE", đặt ngay sau Tổng quan để người chấm
thấy sớm. Gồm: bảng 5 nền tảng (options, STRIPS, ReAct, DP-means, sentence
embedding) × 3 cột (nền / dùng ở đâu / HSGE thêm gì); hai thành phần không kế
thừa từ khung nào (hai nguồn sinh tác vụ ngữ nghĩa chạy song song, bộ cổng
chất lượng đặt trong vòng lặp); và một đoạn tự giới hạn — đây là đóng góp
*thiết kế*, còn thực nghiệm chỉ đo được toàn pipeline, chỉ riêng tác động của
tập dữ liệu là đo tách bạch được.

Đoạn tự giới hạn đó là có chủ đích: rubric TC3 thưởng cho việc phát biểu đóng
góp, nhưng bài học review #4 (thổi phồng đóng góp) phạt nặng hơn nếu phát biểu
vượt quá bằng chứng. Viết cả hai vế cùng lúc là cách rẻ nhất để lấy điểm TC3
mà không mở ra một câu hỏi phản biện.

**Nợ #5 — câu dài.** Trọng tâm đã dời khỏi C3 sau các đợt trước, nên đợt này
làm cả quyển. Kết quả (câu ≥ 40 âm tiết, bỏ bảng/mã giả):

| | trước | sau |
|---|---|---|
| C1 | 20/91 = 21% | 13/103 = **12%** |
| C2 | 31/134 = 23% | 21/150 = **14%** |
| C3 | 42/395 = 10% | 37/418 = **8%** |
| C4 | 37/248 = 14% | 25/268 = **9%** |
| C5 | 18/307 = 5% | giữ nguyên |
| C6 | 19/50 = **38%** | 3/65 = **4%** |
| **toàn quyển** | 167/1225 = 13% | **117/1311 = 8%** |

Không một phát biểu hay con số nào bị đổi; chỉ tách câu và bỏ danh từ hóa.
117 câu còn lại phần lớn là liệt kê có cấu trúc (bốn nhãn task, ba chốt chặn,
danh sách tham số) — đọc trôi, không nên tách thêm.

**Còn lại**: nợ #1 (số run phát triển mồ côi), nợ #7 (ba hình có chữ sai bên
trong: `fig_pipeline` còn nhãn "viết lại", `fig_roadmap` còn "graph"/
"fine-tune", `fig_frontier` còn "tier" — nguồn YAML nằm ở
`Thesis_report/.drawio-tmp/` cho 5 hình khác, ba hình này phải vẽ lại).
