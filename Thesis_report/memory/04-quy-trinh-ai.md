# Quy trình viết báo cáo với AI (đã kiểm chứng bởi nhóm thesis mẫu)

Nguồn: `Thesis_report/thesis_v3/Qua_trinh_viet_report/qua-trinh-viet.md` (báo cáo
quy trình đầy đủ), `prompt-15-buoc.md`, `AI-Ethics-Checklist.md`,
`Citation-Verification-Guide.md`, `META-PROMPT-AcademicWriting.md`,
`Claude-Cowork-cho-NghienCuu.md`. GVHD **biết và khuyến khích** quy trình này
(chính thầy gợi ý dùng ChatGPT/Claude trong nhận xét 1).

## Nguyên tắc phân vai

- **ChatGPT = phản biện** (phân tích nhận xét GVHD thành hướng dẫn chi tiết;
  đọc bản đã sửa để xác nhận + đề xuất thêm).
- **Claude Code = thực thi** (brainstorm dàn ý, viết nháp, sửa .tex, build PDF).
- Tách vai Viết vs. Phản biện giữa 2 AI khác nhau → không tự chấm bài mình.
- **Sinh viên chắt lọc & quyết định** ở mọi bước; tự tay viết lại đề xuất được
  chọn thành file hướng dẫn (vd `de-xuat-dot-2.md`) trước khi đưa Claude sửa.

## Vòng chỉnh sửa điển hình

1. GVHD nhận xét định hướng (tín hiệu khởi động).
2. ChatGPT Pass 1: upload PDF + nhận xét → bản phân tích ưu tiên hóa
   (lưu thành `phan-tich-dot-N.md`).
3. Claude thực thi từng khuyến nghị trên .tex, build PDF sau mỗi thay đổi.
4. ChatGPT Pass 2: upload PDF mới → **xác nhận trước** những gì đã cải thiện,
   **rồi mới đề xuất thêm**, phân loại ưu tiên A/B/C.
5. Sinh viên chắt lọc → còn điểm cần sửa thì quay lại bước 3; đạt thì gửi GVHD.

Nhóm mẫu chạy 2 vòng chính; các kiểu sửa phổ biến: đổi thuật ngữ toàn cục
(7+ file), thêm roadmap đầu chương + transition cuối chương, tách câu >35 từ,
sửa diagram TikZ, sửa lỗi build.

## 5 giai đoạn tạo báo cáo từ đầu

1. **Dàn ý**: Claude brainstorm (input: chủ đề, hướng dẫn GVHD, bài báo chính)
   → sinh viên chỉnh & chốt.
2. **Nháp đầu tiên** (từng chương): cung cấp cho Claude dàn ý đã chốt + bài báo
   tham khảo + dữ liệu thực nghiệm + yêu cầu GVHD/Khoa + link codebase.
3. **Phản biện**: 2 pass ChatGPT như trên.
4. **Chỉnh sửa**: thảo luận kế hoạch với Claude trước → thực thi → sinh viên
   kiểm tra PDF trực quan (AI không thấy lỗi layout/diagram chồng lấp).
5. **Build & lưu phiên bản**: build sạch (xem 03-latex-template.md), commit Git
   mô tả rõ từng đợt sửa.

## Prompt phản biện 15 bước (`prompt-15-buoc.md`)

Prompt "anonymous reviewer" dán vào Claude kèm toàn bộ source LaTeX: 01 khái
niệm chính → 02 phát biểu bài toán → 03 giải pháp hiện có (kèm tìm kiếm web,
đánh dấu BỎ SÓT) → 04 research gaps → 05 phân loại đóng góp → 06 người đọc làm
được gì → 07 phê bình đóng góp → **08 phê bình thực nghiệm (quan trọng nhất:
biến phụ thuộc có được báo cáo? số run khớp? định nghĩa nhất quán? so sánh công
bằng? diễn giải khớp bảng số? có suy luận thống kê?)** → 09 khái quát hóa →
10 tính mới cốt lõi → 11 so SOTA (tìm kiếm) → 12 baseline thương mại →
13 phù hợp baseline/benchmark → 14 cơ sở lý thuyết → 15 accept/reject + lộ
trình 10 cải tiến xếp theo hiệu quả/công sức. Mẹo: chạy 2–3 lần, chạy lại sau
mỗi đợt sửa, tùy chỉnh bước 08 theo đặc thù đề tài.

## Đạo đức AI (checklist rút gọn)

- AI là công cụ, không phải tác giả; sinh viên chịu trách nhiệm toàn bộ nội dung.
- Không bịa/chỉnh số liệu thực nghiệm; dữ liệu chỉ từ run thật.
- Không upload dữ liệu cá nhân chưa anonymize; không liệt kê AI làm đồng tác giả.
- AI viết nháp → sinh viên đọc, hiểu, viết lại bằng giọng của mình (chống đạo văn).

## Xác minh trích dẫn (bắt buộc, chống hallucination)

Mọi citation do AI đề xuất: (1) tra Google Scholar/DOI.org; (2) không tìm thấy
→ loại; (3) đối chiếu paper có thực sự nói điều đang trích không → sửa hoặc
loại. Giảm rủi ro bằng cách chủ yếu cite 5–10 bài gốc đã đọc kỹ.

## META-PROMPT hữu ích (`META-PROMPT-AcademicWriting.md`)

Template prompt: draft section (kèm yêu cầu hedge language, tránh "Obviously/
Clearly", kết bằng câu chuyển tiếp, và yêu cầu AI chỉ ra 3 chỗ cần verify);
chỉnh văn phong 5 tiêu chí kiểu track-changes (clarity/tone/cohesion/precision/
citation placement). Lưu ý: template này viết cho tiếng Anh/APA — báo cáo HSGE
là tiếng Việt/IEEE, cần điều chỉnh khi dùng.
