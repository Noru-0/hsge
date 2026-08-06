# Chương 2 — kết quả xác minh citation (2026-08-07)

Ba agent đã tra cứu trực tiếp arXiv/ACL/OpenReview/HuggingFace cho toàn bộ
28 citation của Chương 2. File này ghi lại **cái gì đã sai và đã sửa**, cùng
**các mục còn treo** — để không phải tra lại, và để không vô tình khôi phục
lại các phát biểu sai.

## Đã sửa (từng sai, nay đúng)

| Chỗ | Sai gì | Đã thành |
|---|---|---|
| §2.3 AWM | "thiếu cổng kiểm chứng chất lượng độc lập" — **trái sự thật**: AWM online có LLM chấm nhị phân episode trước khi trích workflow | Nói đúng: có bộ chấm, nhưng chỉ xét kết quả episode, không thực thi lại workflow |
| §2.3 AWM | "lưu dưới dạng văn bản phẳng" — thực ra hybrid NL + action thực thi được | "chuỗi bước tuyến tính, không có precondition/effect tường minh" |
| §2.3 Synapse | Phê "thiếu cơ chế lọc fluke" — **sai loại**: exemplar của Synapse là thao tác mẫu do người làm, không phải rollout của agent | Phê đúng chỗ: phụ thuộc demo người, bộ nhớ không tự mở rộng |
| §2.3 Synapse | "lưu toàn bộ trajectory" | Thực tế lưu sau khi lược chi tiết không liên quan (state abstraction) |
| §2.4 Synatra | "hàng trăm nghìn" trajectory — **sai một bậc độ lớn** | 100 nghìn bản mẫu, ~0,031 USD/mẫu |
| §2.4 AgentTrek | VLM nghiệm chứng "từng thao tác" | Nghiệm chứng ở mức **toàn quỹ đạo** |
| §2.4 NNetNav | gọi rollout là "thiếu cấu trúc" — chính paper viết ngược lại ("in a structured manner") | Giữ ý đúng: không tích lũy tri thức **giữa các episode** |
| §2.4 PAE | "đề xuất tác vụ giới hạn trong ngữ cảnh cục bộ" | Thực ra còn thô hơn: chỉ dựa ngữ cảnh tĩnh (tên website / demo), không nhìn trang |
| §2.5 Qwen | Qwen3.5-9B quy cho báo cáo kỹ thuật Qwen3 — **Qwen3 không có bản 9B** (0.6/1.7/4/8/14/32B) | Cite blog Qwen3.5 (`qwen2026qwen35`), giữ `yang2025qwen3` cho dòng Qwen3 |
| §2.5 SLM | "chi phí triển khai thấp hơn 10–30 lần", "tinh chỉnh vài giờ" — mất điều kiện | 7B so với 70–175B, xét độ trễ/năng lượng/FLOPs; PEFT tốn vài **GPU-hour** |
| bib AgentOccam | cite là arXiv preprint | Thực tế **ICLR 2025 poster** |
| bib WebRL | thiếu tác giả **Wenyi Zhao**, sai thứ tự | Đã bổ sung, đúng thứ tự |

## Số liệu đã xác minh ĐÚNG (không cần tra lại)

WebArena 812 task / GPT-4 14,41% / người 78,24%; NNetNav 16,3% trên trọn 812
task; InSTA 150.000 website; Go-Browse 21,7% với Qwen-2.5-7B, SOTA <10B tại
thời điểm công bố, **đã được nhận ở ICLR 2026** (không phải preprint);
WebShop 1,18 triệu sản phẩm + 12.087 chỉ dẫn; Mind2Web 2.000+ task/137 site,
đánh giá offline trên snapshot; SteP 14,9%→33,5%; AgentOccam 43,1%;
LoRA giảm 10.000 lần tham số (so với GPT-3 175B + Adam).

## Còn treo — cần làm trước khi nộp

1. **NNetNav venue**: nhiều dấu hiệu là COLM 2025 (OpenReview `fQcUZMPIvu`)
   nhưng agent bị chặn không mở được PDF. Mở tay
   `https://openreview.net/pdf?id=fQcUZMPIvu`, nếu đúng thì đổi sang
   `@inproceedings` + booktitle COLM. Hiện để preprint, `year=2025`.
   Ghi chú nhắc việc nằm ở dạng comment `%` trong `references.bib` (KHÔNG
   để trong trường `note`, vì `note` bị in ra PDF — xem [[03-latex-template]]).
2. **Claim "SOTA <10B" của Go-Browse có thể đã cũ**: arXiv:2604.07776
   (Lù & Reddy, 04/2026) báo mô hình 9B đạt **41,5%** trên WebArena. Câu văn
   hiện có kèm "tại thời điểm công bố" nên vẫn đúng, nhưng hội đồng có thể
   biết con số này — và nó cao hơn hẳn kết quả HSGE hiện tại (xem
   [[phase-a-seed-goal-validated]] và mục P0-1 trong [[05-bai-hoc-review]]).
3. **Paper nên cân nhắc bổ sung** (đã xác minh tồn tại, chưa đưa vào):
   Learn-by-interact (ICLR 2025, arXiv:2501.10893) — gần HSGE nhất ở bước
   backward construction; Explorer (Findings ACL 2025) — 94K trajectory,
   mốc quy mô cho §2.4.2; Pan et al. COLM 2024 (arXiv:2404.06474) — tiền lệ
   cho cổng kiểm chứng tự động, hiện §2.4 chưa cite gì về khâu *verification*.
4. **Qwen3.5-9B là mô hình đa phương thức** (image-text-to-text, có vision
   tower). Nếu pipeline SFT chỉ huấn luyện trên prompt axtree dạng text thì
   nên nói rõ trong Chương 4, phòng khi hội đồng hỏi tại sao chọn VLM cho
   agent quan sát bằng text.
