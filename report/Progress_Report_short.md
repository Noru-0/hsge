# Progress Report

## Tóm tắt

Trong giai đoạn vừa qua, em bắt đầu từ baseline Go-Browse + U/V. Tuy nhiên, hướng này không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (**HSGE agent**): một pipeline chạy explore/eval trên **WebArena Shopping domain**, có chọn frontier, khôi phục trạng thái bằng prefix trace, phát hiện skill, kiểm định skill, tạo dữ liệu SFT, và đánh giá bằng metric **SR (success rate)**.

## Timeline chung

| Date | Work |
| --- | --- |
| **1/6** | Thử nghiệm Go-Browse-like baseline với U/V frontier scoring. Kết quả có cải thiện nhẹ. Tuy nhiên, hướng này không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (HSGE agent). |
| **4/6** | Thiết kế và bắt đầu triển khai HSGE agent: online skill discovery, verification-gated admission, hierarchical skill graph, curriculum/transfer idea. |
| **10/6** | Hoàn thiện offline baseline để kiểm tra pipeline cơ bản trước khi chạy WebArena. |
| **16/6** | Tích hợp WebArena runtime: online exploration, multi-provider LLM, screenshot, prefix trace, frontier filtering, login/account handling. |
| **23-24/6** | Sửa lỗi exploration và data quality: prefix replay, stale frontier, action validation, SFT export format. |
| **25/6** | Fine-tune LoRA và đánh giá HSGE-18 trên **WebArena Shopping domain**, dùng **SR (success rate)** làm metric chính. |

## Kết quả chính

- **Baseline Go-Browse + U/V:** thêm cơ chế chọn node bằng Uncertainty và Value score. So với baseline, success rate tăng từ **22.4%** lên **25.5%** với U và **26.0%** với U+V. Tuy nhiên, hướng này không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (HSGE agent).
- **WebArena runtime:** bổ sung online exploration, multi-provider LLM, screenshot observation, logging, login/account handling, frontier filtering theo URL template, và checkpoint/resume.
- **State restoration:** thêm prefix trace để replay chuỗi action dẫn tới URL, giúp xử lý các trang không thể khôi phục tốt bằng direct URL.
- **Skill discovery:** cải thiện segmentation, abstraction, canonical skill families, verification diagnostics, và quality gates để tránh skill quá cụ thể hoặc không execute được.
- **Training pipeline:** chuẩn hóa action space, lọc action sai/hallucinated BID, hỗ trợ export `hsge_json` và WebArena bracket action.
- **Latest LoRA eval:** fine-tune `Qwen2.5-7B-Instruct` bằng single-turn + multi-turn HSGE data, đánh giá trên **WebArena Shopping domain** đạt **SR = 26/184 scored tasks = 14.13%**.
- **Latest runtime:** exploration mất **3h50m**, training mất **1h15m**, evaluation mất **4h**.

## Số liệu đáng chú ý

| Experiment | Result |
| --- | ---: |
| Baseline eval | 43/192, 22.4% |
| Only U eval | 49/192, 25.5% |
| U + V eval | 50/192, 26.0% |
| HSGE first exploration | 20 nodes, 109 tasks, 92/109 positive trajectories; early-stopped due to runtime/action errors |
| `train-single-18.jsonl` | 750 samples, ~3.5M tokens |
| Latest WebArena Shopping eval | SR = 26 pass / 184 scored = 14.13% |
| Latest run time | Exploration 3h50m, training 1h15m, eval 4h |

## Data / Training / Evaluation

- **Data:** dữ liệu chính hiện tại là `train-single-18.jsonl` với **750 samples**, khoảng **14.2 MB / 3.5M tokens**, gồm **85 page titles**, **109 products**, và **15 categories**. Dữ liệu có thêm multi-turn version để train tiếp sau single-turn.
- **Training:** fine-tune `Qwen2.5-7B-Instruct` bằng LoRA theo 2 bước: train trên single-turn data trước, sau đó continue trên multi-turn data. Thời gian training mới nhất: **1h15m**.
- **Evaluation:** chạy trên **WebArena Shopping domain** bằng HSGE JSON action adapter sang WebArena action format. Metric chính là **SR (success rate)**. Kết quả mới nhất: **187 tasks**, **184 scored**, **26 pass**, **158 fail**, **3 unhandled errors**, **SR = 14.13%**. Thời gian eval: **4h**.
- **Exploration data collection:** latest exploration run chạy trên **WebArena Shopping domain**, mất **3h50m**. Dữ liệu thu được vẫn thiên về các task dễ như search, wishlist, compare, product detail, add-to-cart; còn thiếu checkout, order/account workflow, read-and-answer, filter/sort, hover/scroll.
- **Note:** HSGE first exploration là run thử nghiệm ban đầu và đã dừng sớm do lỗi runtime/action-format/grounding, nên số liệu này phản ánh pipeline cơ bản hoạt động nhưng chưa phải một run hoàn chỉnh.

## Vấn đề đã phát hiện và sửa

- Sửa mapping/action format giữa HSGE và WebArena, đặc biệt `fill`, `type`, `scroll`, `hover`, `press`, và `send_msg_to_user`.
- Chặn các training examples không hợp lệ: action không hỗ trợ, BID không tồn tại, click vào disabled/static element, thought bị cắt cụt.
- Sửa lỗi prefix-derived node bị reset về root page trước khi chạy task.
- Không còn tính stale-prefix hoặc empty-reset node là node đã xử lý thành công.
- Thêm DOM-link fallback khi solver không tạo URL mới, giảm early stopping do frontier rỗng.

## Hạn chế hiện tại

- Exploration vẫn có thể dừng sớm khi prefix trace bị stale hoặc không re-ground được action.
- Grounding còn yếu với combobox/select controls, BID thay đổi, và label trùng lặp.
- Skill reuse chưa mạnh; skill đã được admit nhưng chưa tạo ra nhiều long-horizon composition.
- Training data còn lệch về task đơn giản như search, wishlist, compare, product detail, add-to-cart; thiếu checkout, order/account workflow, read-and-answer, filter/sort, hover/scroll.
- Login state và WebArena action format vẫn là nguồn lỗi trong evaluation.

## Next steps

1. Cải thiện prefix recovery bằng re-ground action theo label, role, và context.
2. Thêm no-op/loop detection cho repeated clicks và combobox/select controls.
3. Chạy exploration mới để tăng coverage cho task families còn thiếu.
4. Làm sạch dataset: deduplicate, flag login redirects, balance task types.
5. Fine-tune lại và re-evaluate trên **WebArena Shopping domain**, so sánh bằng metric **SR** với mốc hiện tại **14.13%**.
