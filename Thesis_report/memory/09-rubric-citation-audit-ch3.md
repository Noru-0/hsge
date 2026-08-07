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

## Đánh giá tổng thể

Phần đóng góp của Chương 3 vào rubric: **TC2 ~7,5/10** (kiến trúc + hình +
lý giải tốt, mất điểm ở mã giả và tham số/dẫn chứng), **TC3 ~7/10** (đóng góp
có thật nhưng chương không tự phát biểu điểm mới), **TC5 ~7/10** (mạch lạc,
đủ hình/bảng, nhưng câu dài, thuật ngữ lệch, thiếu con trỏ dẫn chứng).
Không có lỗi nào thuộc nhóm "phải sửa mới nộp được"; tất cả đều là sửa cộng
điểm, phần lớn tốn dưới nửa ngày.
