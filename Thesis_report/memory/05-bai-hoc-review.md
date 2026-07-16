# Bài học từ các vòng review của thesis mẫu

Nguồn: `Thesis_report/thesis_v3/review/` (review1/2 + fix-list + master-checklist
+ additional-experiments, cùng bản PDF trong `review_GVHD/`) và
`Qua_trinh_viet_report/{nhan-xet-GVHD,phan-tich-dot-1,de-xuat-dot-2}.md`.
Đây là các lỗi **reviewer thật đã bắt** ở thesis mẫu (cùng Khoa, cùng dạng
đề tài thực nghiệm) — dùng làm checklist phòng ngừa cho báo cáo HSGE.

## Lỗi nghiêm trọng (P0) reviewer hay bắt — áp dụng thẳng cho HSGE

1. **Thiếu tính hợp lệ thống kê (n=1)**: mỗi cấu hình chỉ chạy 1 lần → mọi
   delta nhỏ nằm trong nhiễu. Yêu cầu: lặp ≥5 lần/cell, báo mean ± SD + 95% CI,
   test phi tham số trước khi tuyên bố khác biệt; hedge mọi delta không
   significant. ⚠️ HSGE hiện có kết quả 5.56% vs 6.67% (10/180 vs 12/180) —
   chính xác loại claim sẽ bị soi; phải trình bày là "tín hiệu, chưa kết luận"
   hoặc chạy thêm seed/lặp.
2. **Nhãn kịch bản không đúng bản chất** (gọi là "constrained" nhưng thực ra
   không constrained): mô tả điều kiện thực nghiệm phải đúng cái thực sự thay
   đổi; tái tạo đúng điều kiện của paper gốc khi so sánh.
3. **Khuyến nghị tự mâu thuẫn giữa các chương** (§5 nói A, §6 nói ngược A, cả
   hai lệch dữ liệu): đồng bộ Abstract/Thảo luận/Kết luận về một phát biểu
   nhất quán với số liệu.
4. **Thổi phồng đóng góp**: nếu bản chất là replication/đo đạc/khuyến nghị vận
   hành thì viết đúng như vậy ("empirical comparison", "experience report");
   không ngụ ý general superiority. Nên có bảng phân tách claim vs. bằng chứng.
5. **Thiếu reproducibility package**: cần section ghi rõ repo URL, dữ liệu raw,
   config, lệnh phân tích, hướng dẫn tái lập 1 lệnh. HSGE có sẵn lợi thế:
   repo + config.yaml + outputs/ + docs/14 tutorial.
6. **Citation sai/không tồn tại, reference [0], "Hình ??"**: audit mọi
   reference (title/venue/năm/DOI), rebuild để resolve cross-ref.

## Lỗi mức cao (P1–P3)

- Kết quả **trái với paper gốc** mà không chẩn đoán nguyên nhân: nếu kết quả
  ngược kỳ vọng, phải cô lập từng yếu tố (one-factor-at-a-time) hoặc ít nhất
  nêu giả thuyết + cách kiểm chứng.
- **So sánh không công bằng** (các phương pháp chạy ở nhịp/điều kiện khác nhau)
  — với HSGE: baseline vs finetuned phải cùng prompt, cùng task set, cùng
  trạng thái site (đã có kinh nghiệm reset GitLab giữa các sweep).
- Cột dữ liệu vô dụng (luôn cùng giá trị), diễn giải không khớp bảng số —
  đối chiếu ngược từng câu diễn giải với bảng.

## Pattern nhận xét GVHD về readability (phan-tich-dot-1 → 7 khuyến nghị)

1. Mở Chương 1 bằng **hook thực tế** (ví dụ cụ thể, đời thường).
2. **Trì hoãn thuật ngữ** — Chương 1 chỉ giới thiệu khái niệm ở mức nhóm.
3. **Bỏ ký hiệu tự đặt** (P, L1–L4, R1–R2...) — thay bằng mô tả văn bản.
4. **Không nêu kết quả số cụ thể quá sớm** ở Chương 1.
5. **Roadmap đánh số đầu mỗi chương** ("Chương này gồm: (1)... (2)...").
6. **Transition 1–2 câu cuối mỗi chương** dẫn sang chương sau.
7. **Hình Big Picture** tổng quan lộ trình nghiên cứu cuối Chương 1.

Vòng 2 (de-xuat-dot-2): thêm câu critique cuối mỗi mục related work (tránh
"giống khảo sát tài liệu"); tách câu >35 từ; nâng cấp diagram (flowchart phân
nhánh theo RQ). Lỗi trực quan (node TikZ chồng lấp) chỉ người kiểm tra PDF
phát hiện được — luôn mở PDF soát bằng mắt sau khi Claude sửa.

## Quy trình làm việc với GVHD

- GVHD nhận xét **định hướng** (không phải fix-list) qua email/tin nhắn —
  lưu nhật ký lại (như `nhan-xet-GVHD.md`) để theo dõi và đưa vào phụ lục
  quy trình nếu cần.
- GVHD mong đợi sinh viên chủ động dùng AI để "giải mã" nhận xét rồi báo lại
  kết quả.
