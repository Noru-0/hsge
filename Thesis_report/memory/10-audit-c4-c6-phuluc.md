# Rà chương sau (C4–C6 + phụ lục) — cần bổ sung gì (2026-08-12)

Rà sau đợt sửa văn phong Chương 3, để trả lời câu hỏi của user: "tôi phải bổ
sung những gì ở các chương sau?". Cách rà: trích mọi `\ref` từ C3 trỏ ra
ngoài chương, kiểm từng đích xem lời hứa có được trả không; rồi đối chiếu số
liệu giữa C4 và phụ lục.

Tất cả `\label` đều tồn tại, **0 undefined ref** — vấn đề không nằm ở
cross-ref gãy mà ở **nội dung tại đích**.

## P0 — Phụ lục còn nói theo bộ run CŨ, lệch hẳn với Chương 4

Đây là lỗi nặng nhất tìm được, đúng loại reviewer bắt (xem P0 #3 ở
[05-bai-hoc-review](05-bai-hoc-review.md)): số liệu phụ lục không khớp chương
thực nghiệm.

`Appendix/appendix1.tex` §`app:runs-explore` báo cáo **12 run phát triển**
(run 1–9 Reddit, run 10–12 GitLab) và mở đầu bằng "Bảng này báo cáo **mọi**
run khám phá đứng sau dữ liệu đã thu". Nhưng Chương 4 (`tab:runs`) báo cáo
**4 đợt khám phá chính thức trên 4 website** (shopping, reddit, gitlab,
shopping\_admin, mỗi đợt ~21 giờ) — bốn đợt này **không có trong bảng phụ
lục**. §`app:repro-artifacts` cũng viết "các artifact đứng sau Chương 4:
**mười hai thư mục run**".

Ba hệ quả cụ thể phải sửa:

1. **Mâu thuẫn thẳng về goal task ghép.** §`app:runs-goal` viết "Không có
   goal task ghép nào được thử trong cả mười hai run ... bộ đếm đều bằng
   không", trong khi C4 `tab:runs` ghi **6 chuỗi operator đã thử** (shopping
   5, gitlab 1). Cả hai đều đúng *trong phạm vi bộ run của mình*, nhưng đọc
   liền nhau thì đối nhau.
2. **Câu kết luận về dataset đã sai.** Vẫn §`app:runs-goal`: "các trajectory
   dùng để fine-tune **hoàn toàn** đến từ task mức thấp, phạm vi một trang" —
   sai với `tab:dataset` của C4: 2201 mẫu \texttt{UNPREFIXED} (độ khó 2) và 6
   mẫu độ khó 3.
3. **Phạm vi run không được nói rõ.** Phụ lục cần một câu mở đầu phân biệt
   "12 run phát triển (Reddit/GitLab, dùng để chẩn đoán và sửa pipeline)" với
   "4 đợt thu thập chính thức (4 website, số liệu của Chương 4)".

## P1 — Lời hứa của C3 mà chương sau chưa trả

| C3 | Hứa gì | Trạng thái ở đích |
|---|---|---|
| §3.4.2 (d.390) | "Chương 5 bàn về cái giá của lựa chọn [bỏ cổng thực-thi-lại khi kiểm chứng skill]" | **CHƯA CÓ**. C5 không có tiểu mục nào; chỉ có 1 dòng "Kiểm chứng rồi mới thu nhận" trong bảng `tab:practices`. Đây là nợ #2 của [09](09-rubric-citation-audit-ch3.md), vẫn mở |
| §3.2.1 (d.91) | "bổ sung scroll/hover/noop là sửa chữa từ số liệu lần chạy thật (§4.6)" | **LỆCH NGUỒN**. §4.6 có số của *lượt đánh giá* mô hình đã tinh chỉnh (2285 lỗi hành động / 655 phiên, timeout Playwright), không phải số của *run phát triển* đã thúc đẩy sửa (3305/4115). Người đọc lần theo `\ref` sẽ không thấy con số C3 nhắc |
| §3.5.4 (d.583) | "tỷ trọng hai nguồn goal task báo cáo ở §4.2" | **ĐÃ TRẢ ĐỦ** — C4 §4.2: 57 lượt từ seed, 6 từ ghép chuỗi, kèm nhận xét |
| §3.3.2/3.3.3 → `sec:disc-guardrails` | 89% không tuân thủ thẻ; chốt chặn hai mức | **ĐÃ TRẢ** (C5 §5.3.1, §5.3.2) |
| §3.3.1 → `ch:discussion` | frontier cạn kiệt | **ĐÃ TRẢ** (C5 §5.2.1: 57/500 node) |
| §3.5.1 → `sec:disc-operators` | 0,570 / 0,606 | **ĐÃ TRẢ** (C5 §5.4.2) |

## P1 — Số học GOAL trong C4 không cộng khớp

`tab:runs`: GOAL = 25 thành công + 25 thất bại + 16 bất khả thi = **66
episode**. Nguồn: 57 năng lực seed + 6 chuỗi operator = **63**. Riêng
Shopping Admin: 15 episode GOAL nhưng chỉ 12 seed + 0 chuỗi.

Nhiều khả năng chênh 3 là do **thử lại** (`task_retries`) hoặc do tác vụ
terminal-goal của shopping, tức hai dòng "đã thử" đếm *số năng lực/chuỗi
riêng biệt* còn ba dòng kết cục đếm *số lượt chạy*. Nhưng câu văn "66 task
GOAL ... trong đó 57 ... và chỉ 6 ..." đang đọc như một phép chia hết. **Cần
một câu nói rõ hai cách đếm**, hoặc sửa số.

## P2 — Sáu con số của run phát triển vẫn mồ côi (nợ #1 của [09](09-rubric-citation-audit-ch3.md))

Chỉ xuất hiện đúng một lần trong C3, không có ở bất kỳ chương/phụ lục nào:
58/158 node, 49% INFO, 118 episode kẹt, 287/465 quỹ đạo một bước, 10/57
`goto` ngoài miền, 29/56 rò rỉ tập kiểm định. (Ngược lại, 136 lần bỏ cuộc và
effect 0,0 thì đã có mặt ở C4/C5/C6.) Cách sửa rẻ nhất: một bảng phụ lục "số
liệu chẩn đoán từ các run phát triển" — và bảng này cũng chính là chỗ giải
quyết luôn P0 ở trên (tách bạch 12 run phát triển với 4 đợt chính thức).

## P2 — Văn phong: C6 nặng nhất quyển

Đo sau khi C3 đã sửa (bỏ bảng/mã giả, đếm theo từ):

| | Câu ≥ 40 âm tiết | "sẽ" | agent/tác nhân | task/tác vụ | episode/phiên |
|---|---|---|---|---|---|
| C3 (đã sửa) | 46/389 = 11% | 14 | 0 / thống nhất | 0 / thống nhất | thống nhất |
| C4 | 40/239 = **16%** | 11 | 0 / 11 | **77 / 10** | 34 / 21 |
| C5 | 33/292 = 11% | 21 | 3 / 7 | 35 / 21 | 9 / 18 |
| C6 | 18/50 = **36%** | 0 | **12 / 0** | **21 / 0** | 6 / 1 |

C6 chỉ 50 câu mà 36% dài ≥ 40 âm tiết, và dùng thuần tiếng Anh cho agent/task
— ngược hẳn quy ước đã chốt ở [09](09-rubric-citation-audit-ch3.md). C4 cũng
lệch mạnh (task 77 / tác vụ 10). Sửa theo đúng bảng quy ước đó.

## P2 — Bảng thuật ngữ cần bổ sung (nợ #6, nay thêm mục mới)

8 mục cũ còn thiếu: subgoal, seed / site seeder, goal task, tautology,
predicate registry, COMPOSITE, lấy mẫu không tiền tố, grounding. Sau đợt sửa
C3 cần thêm bản tiếng Việt đã chốt để C4–C6 dùng lại: **tác vụ mục tiêu**
(goal task), **sổ đăng ký mệnh đề** (predicate registry), **quy nạp
operator** (operator induction).

---

## Đã xử lý (2026-08-12, cùng ngày rà)

| Hạng mục | Trạng thái |
|---|---|
| P0 phụ lục lệch bộ run | **Xong** — tách "Bốn đợt thu thập chính thức" / "Mười hai run phát triển", nói rõ số liệu hai bộ không cộng gộp |
| P0 mâu thuẫn goal task ghép | **Xong** — viết lại `app:runs-goal` theo run 20: 7 chuỗi đã thử, 4 đạt, bảng liệt kê cả bảy |
| P1 số học GOAL 63 ≠ 66 | **Xong, và không phải lỗi cộng**: 4 ô cột Shopping Admin trong `tab:runs` là số cũ (skill 12→13, op 6→5, chuỗi 0→1, seed 12→14). Sau khi sửa: 7 + 59 = 66 khớp cả bốn website |
| P1 lời hứa §3.4.2 gãy (nợ #2) | **Xong** — §5.4.1 `sec:disc-verify`; §3.4.2 nay trỏ thẳng vào mục đó |
| P2 mục phụ lục để trống | **Xong** — bảng đối chiếu cặp 655 tác vụ + mã số 28 tác vụ bị tinh chỉnh làm hỏng |
| P2 bảng thuật ngữ (nợ #6) | **Xong** — 32 → 40 mục |
| P2 văn phong C4–C6 | **Xong** — agent/task/trajectory/fine-tune/phiên: 0 chỗ lẫn ở C4, C5, C6; C5 câu ≥ 40 âm tiết 32 → 18 |
| P1 §3.2.1 trỏ §4.6 lệch nguồn số | **Chưa** — vẫn thuộc nợ #1 (số của run phát triển không có chỗ trú) |

**Sự thật quan trọng phát hiện khi đối chiếu log** (không có trong bất kỳ ghi
chú nào trước đó): bốn đợt `wa_run_20_*` **đều bị ngắt** sau khoảng hai giờ
rưỡi vì tài khoản OpenAI hết hạn mức (HTTP 429), rồi được **nối lại từ
checkpoint** — 5 lần nối tổng cộng, Shopping Admin 2 lần — và chạy tiếp tới
08-11 02:57, tổng ≈ 21 giờ. Con số "21 giờ" của C4 vì vậy **đúng**; nhưng hai
câu "không lần nào phải can thiệp tay" ở C5/C6 thì sai và đã sửa. Đây cũng là
lần duy nhất cơ chế khôi phục ở §3.8 được dùng thật ngoài phép thử, nên nó
được ghi vào C4 như bằng chứng.

**Bẫy đọc dữ liệu, ghi lại để khỏi vấp lại**: `run_log.jsonl` chứa `run_error`
ở *giữa* file rồi mới tới `run_resume` và phần còn lại. Đếm sự kiện theo loại
rồi kết luận "run kết thúc lúc X" là sai — phải xét **thứ tự dòng** và đếm cả
`run_resume`. Tôi đã suýt báo cáo nhầm rằng C4 phóng đại thời lượng 21 giờ.

## Còn lại (chưa làm)

1. **Nợ #1** — sáu số của run phát triển vẫn mồ côi trong C3 (58/158 node,
   49% INFO, 118 episode kẹt, 287/465, 10/57, 29/56) và §3.2.1 trỏ sang §4.6
   là số của lượt đánh giá chứ không phải số đã thúc đẩy sửa lỗi. Cách rẻ
   nhất vẫn là một bảng "số liệu chẩn đoán từ run phát triển" trong
   Mục~`app:runs-dev`.
2. **Nợ #3** — C3 chưa tự phát biểu điểm mới so với nền vay mượn.
3. **Nợ #5** — C3 còn 42/392 câu ≥ 40 âm tiết; C4 còn 40/243 (16%), cao nhất
   trong các chương đã rà.
4. **C1 và C2 chưa rà**: C2 còn "agent" 22 lần / "tác nhân" 0, C1 còn
   "fine-tune" 10 lần — nay lệch với C3–C6 đã thống nhất. User mới chỉ yêu
   cầu "từ chương 3", nên chưa tự ý sửa.
5. `Figures/fig_pipeline.pdf` vẫn còn nhãn sai bên trong ảnh (nợ #7).
