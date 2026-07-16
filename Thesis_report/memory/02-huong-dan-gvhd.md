# Hướng dẫn viết báo cáo hướng nghiên cứu — TS. Ngô Huy Biên (tham khảo)

⚠️ **Lưu ý vai trò (cập nhật 2026-07-17)**: TS. Ngô Huy Biên là GVHD của
**thesis mẫu**, KHÔNG phải GVHD của nhóm HSGE. GVHD của nhóm là **PGS.TS.
Nguyễn Văn Vũ** — tác giả slide hướng dẫn chính thức của Khoa (xem
01-quy-dinh-khoa.md, phần văn phong & cấu trúc 5 chương). Tài liệu dưới đây
vẫn là khung viết khóa luận hướng nghiên cứu rất tốt (mạch logic từng chương,
quy tắc trích dẫn), nhưng khi mâu thuẫn với yêu cầu của thầy Vũ thì theo thầy
Vũ; các mục "GVHD đã trao đổi trực tiếp" phải lấy từ trao đổi với thầy Vũ.

Nguồn: `Thesis_report/thesis_v3/review_GVHD/huong_dan_rp.md` (bản đầy đủ) và
`Thesis_report/thesis_v3/Qua_trinh_viet_report/Huong-Dan-Viet-Bao-Cao.md`
(bản tương tự). Đây là hướng dẫn cho khóa luận **hướng nghiên cứu**.

## Nguyên tắc cứng

- **KHÔNG** chép từ nguồn tiếng Việt (kể cả chép rồi sửa vài từ), **KHÔNG**
  dịch lại từ nguồn tiếng Anh.
- Tài liệu tham khảo theo chuẩn **IEEE**; chỉ dùng sách, bài báo, tài liệu của
  trường/viện nghiên cứu. **KHÔNG** Wikipedia, **KHÔNG** trang tin tức.
- Mỗi tài liệu trong danh mục phải được trích dẫn trong bài.
- Link mã nguồn/phần mềm để ở **footnote** tại trang đề cập, không đưa vào
  danh mục tham khảo.
- Hạn chế tối đa mã nguồn và ảnh chụp màn hình trong báo cáo.
- Bắt buộc viết bằng **LaTeX** (có thể dùng Overleaf, chỉnh từ biểu mẫu của Khoa).

## Cấu trúc 6 chương + số trang gợi ý

| Chương | Nội dung | Trang |
|---|---|---|
| 1 | Mở đầu | ~10 |
| 2 | Các công trình liên quan | ~10 |
| 3 | Giải pháp đề xuất | ~15 |
| 4 | Thực nghiệm | ~15 |
| 5 | Thảo luận | ~10 |
| 6 | Kết luận | ~5 |

Trước đó: trang bìa, lời cảm ơn, bảng thuật ngữ/viết tắt/ký hiệu, mục lục,
danh sách hình, danh sách bảng, tóm tắt. Sau cùng: phụ lục.

## Chương 1 — Mở đầu

- **WHY**: bối cảnh; các vai trò & quy trình (roles, business workflows) và vấn
  đề họ gặp; vì sao cần giải quyết — nhu cầu/lợi ích thực tế, **có dẫn chứng**
  (số liệu khảo sát tin cậy / sản phẩm thương mại / minh chứng tổ chức / số
  lượng bài báo quan tâm).
- **Phát biểu bài toán**: bài toán cụ thể, đầu vào, đầu ra mong muốn; mô tả
  hình thức nếu được; tiêu chí đánh giá đầu ra.
- **Mục tiêu & yêu cầu**: đề tài giải quyết vấn đề mới / khắc phục điểm yếu
  giải pháp có sẵn / báo cáo kinh nghiệm thực nghiệm? Sản phẩm cần đạt? Phải
  bao gồm tối thiểu các mục tiêu GVHD đã trao đổi trực tiếp.
- **Phạm vi**: những gì liên quan nhưng không đi sâu.
- **Mạch logic chuẩn (có đề xuất mới)**: Vì vấn đề P (dẫn chứng số liệu) nên có
  S1, S2. S1, S2 có hạn chế L1, L2. Đề tài đề xuất NEW_S giải quyết L1, L2.
  Thực nghiệm NEW_S thu được R1, R2, thể hiện L1, L2 được giải quyết/giảm thiểu
  (dẫn chứng bằng tiêu chí đánh giá).
- **Mạch logic khi chưa có đề xuất mới**: thử nghiệm S1, S2 → kết quả R1, R2 →
  S1, S2 giải quyết được một phần P (P1, P2), L1, L2 cần xử lý tiếp → khuyến
  nghị S1 dùng trong hoàn cảnh C1, S2 trong C2. Trường hợp này cần **số lượng
  lớn thực nghiệm** và tài liệu hóa chi tiết quá trình thử sai kèm dữ liệu.

## Chương 2 — Công trình liên quan

- Gom bài báo theo **chủ đề**, trong mỗi chủ đề trình bày **từ cũ đến mới**;
  mỗi bài chỉ liệt kê ngắn gọn ý tưởng.
- **Mạch logic**: "A giải quyết vấn đề bằng cách... Tuy nhiên... B giải quyết
  bằng cách... Tuy nhiên... C đưa ra bộ dữ liệu/tiêu chí đánh giá... Tuy nhiên..."
  (mỗi mục phải có câu critique/hạn chế, không chỉ mô tả — review vòng 1 của
  thesis mẫu từng bị chê "giống khảo sát tài liệu" vì thiếu câu đánh giá).

## Chương 3 — Giải pháp đề xuất

- Từ bài báo tham khảo + suy luận → giả thuyết (giải pháp đề xuất); có thể chọn
  giải pháp có sẵn để thử nghiệm nếu chưa có đề xuất riêng; chọn giải pháp dựa
  trên kết quả thử sai qua các bản mẫu; trình bày chi tiết giải pháp được chọn.
- Nội dung: kiến trúc tổng quan (sơ đồ + diễn giải từng thành phần), thuật toán
  (**mã giả**), cấu trúc dữ liệu (mã nguồn/ký hiệu toán/sơ đồ hình thức),
  quy trình (sơ đồ + diễn giải).

## Chương 4 — Thực nghiệm

- Chứng minh/lý giải vì sao giải pháp đề xuất tốt hơn giải pháp có sẵn (hoặc
  phân tích điểm mạnh/yếu và khuyến nghị ứng dụng nếu không có giải pháp mới).
- Nội dung: **môi trường** (thông số cụ thể), **dữ liệu đầu vào**, **phương
  pháp** (các bước), **kết quả** — phải làm rõ cái gì có sẵn (framework, thư
  viện, dữ liệu) vs. cái gì đề tài tạo thêm/chỉnh sửa, **đánh giá** (công cụ,
  độ đo, quá trình đo, cách tính, kết quả thể hiện điều gì, nhận xét),
  đánh giá định tính và lợi ích thực tế nếu có (tiết kiệm thời gian/chi phí,
  kèm dữ liệu).

## Chương 5 — Thảo luận

- Trọng tâm: **báo cáo kinh nghiệm** về các vấn đề kỹ thuật phát sinh khi thực
  nghiệm và cách xử lý; chi tiết để ở Phụ lục, báo cáo chỉ nêu ý chính.
- Vấn đề lặp lại nhiều lần → đúc kết thành **best practice**.
- Có thể mô tả các thử nghiệm thất bại.
- Mẫu câu: "Các kết quả đánh giá có số liệu như sau… Kết quả này thể hiện rằng…"

## Chương 6 — Kết luận

- Sản phẩm nổi bật (kiến trúc, thuật toán, hệ thống, dữ liệu, mô hình huấn
  luyện, công cụ, mã nguồn mở rộng...); đánh giá kết quả so với mục tiêu ban
  đầu; phương hướng phát triển (vấn đề tồn đọng + hướng giải quyết tổng quát).
- **Tập trung vào ưu điểm**; không tập trung hạn chế, không biện minh
  (nhân lực, thời gian).

## Phụ lục

- Bản mô tả chi tiết thiết kế giải pháp; dữ liệu và số liệu chi tiết đánh giá.

## Pattern nhận xét của GVHD (từ nhật ký thesis mẫu — `nhan-xet-GVHD.md`)

1. **Chuỗi cấu trúc nghiên cứu**: inputs → algorithms → outputs → problems →
   proposed solutions → experiments. Trong đó inputs→problems là của nghiên cứu
   **có sẵn**; proposed solutions có thể của nghiên cứu khác hoặc của đề tài;
   experiments là của **riêng** đề tài. Phải trả lời được từng ô của chuỗi này.
2. **Phân biệt nghiên cứu nền (Y) và giải pháp thực nghiệm (X)**: nếu thực
   nghiệm giải pháp X có sẵn, phải trình bày X sinh ra để giải quyết vấn đề của
   nghiên cứu Y nào.
3. **Mạch lạc, rõ ràng**: không dùng ký hiệu tự đặt kiểu "Vấn đề P" mà người
   đọc chưa được định nghĩa; đọc lại toàn bộ để chỉnh readability.
