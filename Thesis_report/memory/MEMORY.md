# Memory — Viết báo cáo KLTN cho HSGE Agent

Bộ nhớ dài hạn cho việc viết báo cáo khóa luận tốt nghiệp của đề tài HSGE
(Hierarchical Skill-Graph Exploration). **Đọc file này đầu tiên** ở mỗi session
viết report, rồi mở đúng file chủ đề cần dùng.

| File | Nội dung |
|---|---|
| [01-quy-dinh-khoa.md](01-quy-dinh-khoa.md) | Quy định chính thức của Khoa CNTT (ĐH KHTN): cấu trúc quyển, định dạng, đánh số, nộp bài |
| [02-huong-dan-gvhd.md](02-huong-dan-gvhd.md) | Hướng dẫn viết báo cáo hướng nghiên cứu (TS. Ngô Huy Biên — GVHD của thesis mẫu, dùng tham khảo): 6 chương, mạch logic từng chương, quy tắc trích dẫn |
| [03-latex-template.md](03-latex-template.md) | Cấu trúc template LaTeX thesis_v3: file layout, lệnh build, các điểm cần sửa khi tái sử dụng |
| [04-quy-trinh-ai.md](04-quy-trinh-ai.md) | Quy trình viết với AI đã được kiểm chứng (ChatGPT phản biện / Claude thực thi), đạo đức AI, xác minh trích dẫn, prompt phản biện 15 bước |
| [05-bai-hoc-review.md](05-bai-hoc-review.md) | Bài học từ các vòng review của thesis mẫu: lỗi reviewer hay bắt, pattern nhận xét của GVHD |
| [06-de-tai-hsge.md](06-de-tai-hsge.md) | Ngữ cảnh đề tài HSGE: bài toán, kết quả đã có, nguồn tư liệu trong repo, mapping vào từng chương |
| [07-dan-y-chi-tiet.md](07-dan-y-chi-tiet.md) | Dàn ý 6 chương: **C3 là bản ĐÃ GIAO** (cập nhật 12-08), các chương khác còn là dàn ý dự kiến; kèm trạng thái viết và rủi ro O2 (semantic task) đã giải quyết tới đâu |
| [08-citation-audit-ch2.md](08-citation-audit-ch2.md) | Kết quả xác minh citation Chương 1–2: claim nào từng sai và đã sửa, số liệu nào đã đúng, các mục còn treo trước khi nộp |
| [09-rubric-citation-audit-ch3.md](09-rubric-citation-audit-ch3.md) | Rà + **chấm điểm Chương 3** theo rubric Khoa (TC2 8,5 / TC3 7,5 / TC5 7,5 tính tới 12-08), audit citation, 7 khoản nợ xếp theo rủi ro, và **bảng quy ước thuật ngữ đã chốt** (đợt sửa văn phong 12-08); cập nhật 13-08: C4 cũng đã rà văn phong xong theo cùng checklist |
| [10-audit-c4-c6-phuluc.md](10-audit-c4-c6-phuluc.md) | **Cần bổ sung gì ở C4–C6 + phụ lục**: phụ lục còn nói theo 12 run phát triển trong khi C4 dùng 4 đợt chính thức (P0), lời hứa nào của C3 chưa được trả, số học GOAL 63≠66, và thống kê văn phong từng chương |
| [11-cham-diem-rubric-toan-quyen.md](11-cham-diem-rubric-toan-quyen.md) | **Chấm điểm toàn quyển theo rubric Khoa (18-08)**: điểm từng tiêu chí + căn cứ, 8 nhóm số liệu lệch pha giữa C4/C5/C6 đã sửa, số operator/skill đếm lại từ run log, và 5 khoản nợ trước bảo vệ |

## Nguồn gốc

Đúc kết từ `Thesis_report/thesis_v3/` (thesis mẫu về autoscaling microservices,
GVHD của mẫu là TS. Ngô Huy Biên — GVHD của nhóm HSGE là **PGS.TS. Nguyễn Văn
Vũ**) và `Thesis_report/KLTN/` (hướng dẫn chính thức của Khoa, slide do chính
thầy Vũ soạn). Khi cần chi tiết nguyên gốc, quay lại file nguồn dẫn trong từng
ghi chú. Thông tin đề tài đã chốt (tên, nhóm, tiếng Anh, câu chuyện chính):
xem đầu file 06.

## Quy ước cập nhật

- Mỗi khi có quyết định mới (dàn ý được chốt, nhận xét mới của GVHD, đổi cấu
  trúc chương...), cập nhật đúng file chủ đề và giữ index này khớp.
- Ghi chú viết bằng tiếng Việt (đối tượng phục vụ là báo cáo tiếng Việt);
  code/docs của repo HSGE vẫn giữ tiếng Anh theo convention.
