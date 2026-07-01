Thưa thầy,

Nhóm em xin gửi thầy báo cáo tiến độ cho 01/07/2026 ạ.

Tuần này nhóm em đã giải quyết được vấn đề Pre-condition / Post-condition matching giữa các Operator mà em định nhờ thầy tham mưu, bằng cách chuyển sang embedding-based similarity.

Điểm chính:

- **Semantic Task đã xuất hiện** – Curriculum tạo đúng nhờ Operator Graph chính xác.
- Tỷ lệ task pass tăng từ **~46% → 82.8%** nhờ cải thiện Solver Agent (retry + LLM-as-Judge).
- Đã xác định nguyên nhân finetuning thấp tuần trước (Thought yếu, grounding combobox/select, BID thay đổi, repeated labels).
- Đang crawl dataset song song 3 domain (Shopping, Reddit, Wiki).

Tuần tới: hoàn thành crawl, cải thiện training data, fine-tune & evaluate lại.

Chi tiết nhóm em đính kèm bên dưới. Nhóm em mong nhận được góp ý của thầy ạ.

Em cảm ơn thầy.
