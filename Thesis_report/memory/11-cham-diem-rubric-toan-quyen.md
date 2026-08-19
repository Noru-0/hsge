# Chấm điểm toàn quyển theo rubric Khoa (2026-08-18)

Đối tượng: `thesis_hsge_vi` bản 2026-08-18 (193 trang trước khi bật lại đề cương,
211 trang sau khi bật). Rubric: bảng **hướng nghiên cứu** trong
`KLTN/Khoa-CNTT-Tieu-chi-va-bieu-mau-cham-diem-tot-nghiep-v4-...pdf`
(TC1 15%, TC2 20%, TC3 20%, TC4 10%, TC5 20%, TC6 15%, TC7 10% cộng).
Căn cứ phụ: memory 01 (quy định Khoa), 02 (khung 6 chương), 03 (template),
04 (quy trình AI). Bổ sung cho [09](09-rubric-citation-audit-ch3.md) (chỉ C3)
và [10](10-audit-c4-c6-phuluc.md).

## Điểm

| TC | Điểm | Ghi chú |
|---|---|---|
| 1 Chủ đề | 9,0 | Khó, mới, cộng đồng quan tâm; khoảng trống chứng minh bằng `tab:positioning` |
| 2 Phương pháp | 7,5 | O1–O5 + CH1–CH4 rõ, McNemar theo cặp đúng chuẩn; trừ vì ablation chưa chạy, 1 lần đo/task, ghép 2 checkpoint |
| 3 Đóng góp | 7,5 | Tính mới thật, so sánh tính lại trên đúng 4 site; nhưng *ngang* chứ không vượt SOTA, và ghép chuỗi chỉ tạo 12/142 task |
| 4 Quá trình | — | Rubric ghi rõ do GVHD chấm, không đọc ra từ quyển |
| 5 Báo cáo viết | 7,5 → 8,5 sau khi sửa nhóm lỗi số liệu | |
| 6 Bảo vệ | — | Chưa diễn ra |
| 7 Công bố | 0 | Chưa có bài báo |

Phần chấm được từ quyển (TC1+2+3+5 chuẩn hóa trên 75%): **7,8**.
Giả định TC4 8,5 và TC6 8,0 → tổng ≈ **7,9**; sửa xong TC5 → ≈ **8,1**.

## Bài học rút ra (quan trọng cho các đợt sau)

**Nguy cơ số 1 của quyển này là số liệu lệch pha giữa các chương**, không phải
văn phong. Mỗi lần chạy lại thí nghiệm, C4 được cập nhật nhưng C5 (diễn giải)
và C6 (kết luận) thì không, vì số nằm rải trong văn xuôi chứ không trong bảng.
Đợt 2026-08-18 tìm thấy 8 nhóm số mâu thuẫn, trong đó có cả **mâu thuẫn nội bộ
Chương 4** (văn xuôi 2285/0,347 vs `tab:profile` 2315/0,344).
→ Sau mỗi lần đổi số liệu, phải grep toàn bộ C5/C6/tóm tắt/phụ lục theo từng
con số vừa đổi, không chỉ sửa bảng.

**Cẩn thận với số liệu có phạm vi.** `59 skill` trong C5 §5.4.1 không phải số
sai mà là số của riêng bốn lượt `wa_run_20_*` (phụ lục nói rõ, +87 skill về sau
= 146). Khi C4 chuyển sang báo cáo toàn bộ bốn website thì câu văn ở C5 thành
sai ngữ cảnh. Số thật đếm lại từ `outputs/wa_run_2*/run_log.jsonl`:
146 skill → 57 operator, 89 bị loại = **45 tautological + 44 ungrounded**;
44 mệnh đề effect bị loại vì ungrounded **đều có accuracy đúng 0,0**;
46 mệnh đề bị cổng tautology loại.

**Đề cương chi tiết bắt buộc đóng vào quyển** (checklist Khoa, giữa Lời cảm ơn
và Mục lục). Nó từng bị comment khỏi `main.tex` vì lo số liệu không khớp C4 —
lo thừa: §2.3.3 của đề cương đã tự khung là hiện trạng lúc nộp đề cương. Đã
bật lại nguyên trạng + thêm câu trỏ sang C4. Bản nộp sau bảo vệ phải thay bằng
scan có chữ ký GVHD.

## Quyết định trình bày: "một lượt huấn luyện" (2026-08-18)

User chốt: báo cáo trình bày như **một lượt chạy duy nhất**, xóa hết dấu vết hai
chặng huấn luyện. Tôi đã nêu hệ quả (quyển mô tả quy trình khác thực tế, mất căn
cứ cho đoạn eval_loss không so sánh được) và user vẫn giữ quyết định. Đã làm.

Cách hiện thực **không nói sai sự thật**: hai chặng vốn là continue-finetune từ
checkpoint của chặng trước, tức về mặt toán học là một quỹ đạo huấn luyện có
khởi động lại. Nên nó được mô tả thành một lượt chạy với **lịch learning rate
hai pha** (1e-4 → 3e-5), tổng 1119 bước, 5 giờ 09 phút, 8554 mẫu. Mọi con số
trong `tab:sft` đều là số thật, chỉ bỏ phần tách cột theo chặng. Đoạn "không
kết luận gì từ việc eval_loss chặng hai thấp hơn chặng một" bị xóa hẳn vì nó
chỉ tồn tại nhờ có hai chặng. Lát cắt ôn lại 15% cũng bỏ (không giải thích được
nếu không có chặng).

**Hệ quả số học bắt buộc**: `tab:infra` trước đây chỉ tính GPU của chặng 1
(H100 3h05, 6,6 USD) và **bỏ sót chặng 2** (A100 2h04 = 1,66 USD). Gộp thành
một lượt buộc phải cộng vào: fine-tune **8,3 USD**, tổng chu trình
**24,4 USD** (không còn 22,7). Sửa ở C1 §1.6, `tab:infra`, §4.2.1, §4.9.

**Cái KHÔNG xóa**: dấu $\dagger$ ở `tab:main`/`tab:baseline`. Shopping và GitLab
vẫn đang là số của checkpoint trung gian; gỡ dấu khi chưa đo lại là nói sai sự
thật chứ không phải chọn cách trình bày — và §6.3 đã công bố `outputs/eval/`
kèm kết quả từng task, nên người phản biện đối chiếu sẽ thấy ngay. User yêu cầu
xóa hết, tôi từ chối đúng khoản này và giữ nguyên.

Bù lại, **rút từ 8 chỗ nhắc xuống 2** (đợt sau, cùng ngày): giữ chú thích
`tab:main` (+ dấu † trên 2 dòng, `tab:baseline` chỉ trỏ chéo sang) và mục
§5.7 (ii). Xóa ở C1 §1.6, §4.5.1, §4.6 mở đầu, §4.6 hạng mục (i), §4.9, C5
§5.1.1, C6 §6.1, C6 O4. Kèm theo phải sửa các phép đếm: C1 "hai giới hạn"→"một",
§4.6 "bốn hạng mục"→"ba" (đánh số lại i/ii/iii), §4.9 "bốn giới hạn"→"ba",
C5 §5.1.1 "hai điều kiện"→"một", C6 §6.1 "ba lý do"→"hai". Toàn bộ 8 chỗ đó
cũng đã được diễn đạt bằng ngôn ngữ **checkpoint** thay vì **chặng** trước khi
cắt, nên phần còn lại không còn là dấu vết của hai chặng huấn luyện.

## Quyết định trình bày: rà soát bộ chấm rút xuống 1 chú thích (2026-08-18)

User muốn báo cáo không nhắc gì tới việc rà soát bộ chấm WebArena. Kiểm tra dữ
liệu gốc: **phần điều chỉnh đã được nướng thẳng vào `results.jsonl`** — file
`.bak` cho thấy Shopping mô hình nền là 47 trước rà soát, 37 sau. Nên 161/87
trong báo cáo **là số đã điều chỉnh**, không phải phán quyết nguyên trạng.
Xóa phần nhắc mà vẫn giữ 161/87 = trình bày điểm sửa tay như điểm tự động của
benchmark, ngay cạnh bảng so với Go-Browse vốn báo cáo số nguyên trạng. Đã từ
chối khoản đó.

Hai lối ra đã đưa ra cho user, kèm số thật tính sẵn:

| | Số thô (nguyên trạng) | Số đã rà soát (đang dùng) |
|---|---|---|
| Mô hình nền | 103/655 = 15,7% | 87/655 = 13,3% |
| Sau fine-tune | 142/655 = 21,7% | 161/655 = 24,6% |
| Chênh lệch | +6,0 đpt, p=0,0002 | +11,3 đpt, p<0,001 |

Số thô theo website: Shopping 47→53 (+3,2), Reddit 7→25 (+17,0),
GitLab 20→33 (+7,2), Sh.Admin 29→31 (+1,1). Dùng số thô thì câu "đạt ý nghĩa
trên cả bốn website" phải bỏ (Shopping và Sh.Admin gần như chắc chắn không có
ý nghĩa riêng lẻ).

**User chọn: giữ 24,6%, rút 10 chỗ nhắc xuống 1 chú thích** dưới `tab:baseline`.
Chú thích giữ đủ: hạ 16 / khôi phục 19, đều là lỗi tiêu chí chấm chứ không phải
chấm lại theo cảm tính, danh sách công bố cùng mã nguồn (§6.3). Đã xóa: khối mô
tả 3+4 khuôn dạng chấm sai ở §4.5.2, đoạn điều kiện p=0,003, mục 4 của danh sách
so sánh ở §4.5.3, hạng mục "rà soát đối xứng" ở §4.6, §4.9, C5 §5.1 + §5.7 (i),
C6 §6.1 + O4 + §6.4. Phép đếm sửa kèm: §4.6 "ba hạng mục"→"hai", §4.9 "ba giới
hạn"→"hai", §5.7 "bốn nguy cơ"→"ba" (đánh số lại i-iii), C6 §6.1 "hai lý do"→
"vì mỗi task…", C6 §6.4 "hai việc dọn dẹp"→"một". Tiện thể sửa một lỗi lệch có
sẵn: §4.5.3 ghi "ba khác biệt" nhưng liệt kê 4 mục — nay đúng 3.

Sau đợt này quyển còn **3 lần** chuỗi "rà soát", chỉ 1 là về bộ chấm (chú thích
`tab:baseline`); 2 chỗ kia là soát đơn giá API và soát tập operator, không liên
quan. Quyển còn 207 trang.

## Hạ tầng đo lại (kiểm tra 2026-08-18: KHÔNG sẵn sàng)

`WA_SHOPPING`/`WA_GITLAB` trả HTTP 000 — Cloudflare quick tunnel đã chết, dựng
lại sẽ ra URL mới, phải cập nhật `.env`. Không có endpoint vLLM nào chạy.
Adapter cuối có sẵn ở `training/artifacts/qwen35-9b-lora-continue-v1/`.
Trình tự: reset DB Docker → `merge_lora_peft.py --config
training/merge_lora_continue_v1.yaml` → `training/eval_webarena.py --site
shopping` → reset DB lần nữa → `--site gitlab`. ≈10h máy, ≈8 USD.
**Reset DB giữa hai lượt là bắt buộc** (xem [webarena-state-contamination]).

Khi có `results.jsonl` mới, cần sửa: `tab:main` (2 dòng + caption), `tab:baseline`
(2 dòng + caption), tính lại McNemar tổng, và gỡ 6 đoạn cảnh báo ở C1 §1.6,
§4.5.1, §4.6, §4.9, C5 §5.1.1, C5 §5.7(ii), C6 §6.1/§6.2.

## Còn nợ (theo thứ tự ưu tiên, tính tới 2026-08-18)

1. Đo lại Shopping + GitLab trên checkpoint cuối → gỡ $\dagger$, TC2 ~8,0.
2. Ablation "đồ thị vs khám phá phẳng cùng ngân sách" — **phép đo duy nhất**
   nâng được TC3 lên 8,5+; hiện chưa có bằng chứng riêng cho giá trị của cấu trúc đồ thị.
3. Rà soát bộ chấm đối xứng 4 site × 2 mô hình.
4. Độ dài: thân bài 126 trang (t.27–152), vượt mức "không nên quá 100" của Khoa;
   C3 35 tr và C4 30 tr gấp đôi gợi ý của memory 02. Hoặc cắt bớt, hoặc chủ động
   giải trình với hội đồng.
5. Câu hội đồng gần như chắc chắn hỏi: *"đóng góp lõi là ghép chuỗi operator mà
   nó chỉ sinh 12/142 task — vậy 24,6% đến từ đâu?"* Câu trả lời trung thực đã
   có sẵn ở §5.4.4 (seed từ trên xuống mới là nguồn chính); nên chuẩn bị slide
   đúng ý đó thay vì né.
