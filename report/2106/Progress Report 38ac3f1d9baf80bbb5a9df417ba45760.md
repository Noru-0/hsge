# Progress Report

## Vietnamese Version

### Tóm tắt

Trong giai đoạn vừa qua, em bắt đầu từ baseline Go-Browse + U/V. Tuy nhiên, hướng này không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (**HSGE agent**): một pipeline WebArena có chọn frontier, khôi phục trạng thái bằng prefix trace, phát hiện skill, kiểm định skill, tạo dữ liệu SFT, và đánh giá LoRA trên WebArena Shopping.

### Timeline chung

| Date | Work |
| --- | --- |
| **1/6** | Thử nghiệm Go-Browse-like baseline với U/V frontier scoring. Kết quả có cải thiện nhẹ. Tuy nhiên, hướng này không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (HSGE agent). |
| **4/6** | Thiết kế và bắt đầu triển khai HSGE agent: online skill discovery, verification-gated admission, hierarchical skill graph, curriculum/transfer idea. |
| **10/6** | Hoàn thiện offline baseline để kiểm tra pipeline cơ bản trước khi chạy WebArena. |
| **16/6** | Tích hợp WebArena runtime: online exploration, multi-provider LLM, screenshot, prefix trace, frontier filtering, login/account handling. |
| **23-24/6** | Sửa lỗi exploration và data quality: prefix replay, stale frontier, action validation, SFT export format. |
| **25/6** | Fine-tune LoRA và đánh giá HSGE-18 trên WebArena Shopping. |

### Kết quả chính

- **Baseline Go-Browse + U/V:** thêm cơ chế chọn node bằng Uncertainty và Value score. So với baseline, success rate tăng từ **22.4%** lên **25.5%** với U và **26.0%** với U+V. Tuy nhiên, hướng này không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (HSGE agent).
- **WebArena runtime:** bổ sung online exploration, multi-provider LLM, screenshot observation, logging, login/account handling, frontier filtering theo URL template, và checkpoint/resume.
- **State restoration:** thêm prefix trace để replay chuỗi action dẫn tới URL, giúp xử lý các trang không thể khôi phục tốt bằng direct URL.
- **Skill discovery:** cải thiện segmentation, abstraction, canonical skill families, verification diagnostics, và quality gates để tránh skill quá cụ thể hoặc không execute được.
- **Training pipeline:** chuẩn hóa action space, lọc action sai/hallucinated BID, hỗ trợ export `hsge_json` và WebArena bracket action.
- **Latest LoRA eval:** fine-tune `Qwen2.5-7B-Instruct` bằng single-turn + multi-turn HSGE data, đánh giá trên WebArena Shopping đạt **26/184 scored tasks = 14.13%**.
- **Latest runtime:** exploration mất **3h50m**, training mất **1h15m**, evaluation mất **4h**.

### Số liệu đáng chú ý

| Experiment | Result |
| --- | ---: |
| Baseline eval | 43/192, 22.4% |
| Only U eval | 49/192, 25.5% |
| U + V eval | 50/192, 26.0% |
| HSGE first exploration | 20 nodes, 109 tasks, 92/109 positive trajectories; early-stopped due to runtime/action errors |
| `train-single-18.jsonl` | 750 samples, ~3.5M tokens |
| Latest WebArena Shopping eval | 26 pass / 184 scored, 14.13% |
| Latest run time | Exploration 3h50m, training 1h15m, eval 4h |

### Data / Training / Evaluation

- **Data:** dữ liệu chính hiện tại là `train-single-18.jsonl` với **750 samples**, khoảng **14.2 MB / 3.5M tokens**, gồm **85 page titles**, **109 products**, và **15 categories**. Dữ liệu có thêm multi-turn version để train tiếp sau single-turn.
- **Training:** fine-tune `Qwen2.5-7B-Instruct` bằng LoRA theo 2 bước: train trên single-turn data trước, sau đó continue trên multi-turn data. Thời gian training mới nhất: **1h15m**.
- **Evaluation:** chạy WebArena Shopping bằng HSGE JSON action adapter sang WebArena action format. Kết quả mới nhất: **187 tasks**, **184 scored**, **26 pass**, **158 fail**, **3 unhandled errors**, average score **14.13%**. Thời gian eval: **4h**.
- **Exploration data collection:** latest exploration run mất **3h50m**. Dữ liệu thu được vẫn thiên về các task dễ như search, wishlist, compare, product detail, add-to-cart; còn thiếu checkout, order/account workflow, read-and-answer, filter/sort, hover/scroll.
- **Note:** HSGE first exploration là run thử nghiệm ban đầu và đã dừng sớm do lỗi runtime/action-format/grounding, nên số liệu này phản ánh pipeline cơ bản hoạt động nhưng chưa phải một run hoàn chỉnh.

### Vấn đề đã phát hiện và sửa

- Sửa mapping/action format giữa HSGE và WebArena, đặc biệt `fill`, `type`, `scroll`, `hover`, `press`, và `send_msg_to_user`.
- Chặn các training examples không hợp lệ: action không hỗ trợ, BID không tồn tại, click vào disabled/static element, thought bị cắt cụt.
- Sửa lỗi prefix-derived node bị reset về root page trước khi chạy task.
- Không còn tính stale-prefix hoặc empty-reset node là node đã xử lý thành công.
- Thêm DOM-link fallback khi solver không tạo URL mới, giảm early stopping do frontier rỗng.

### Hạn chế hiện tại

- Exploration vẫn có thể dừng sớm khi prefix trace bị stale hoặc không re-ground được action.
- Grounding còn yếu với combobox/select controls, BID thay đổi, và label trùng lặp.
- Skill reuse chưa mạnh; skill đã được admit nhưng chưa tạo ra nhiều long-horizon composition.
- Training data còn lệch về task đơn giản như search, wishlist, compare, product detail, add-to-cart; thiếu checkout, order/account workflow, read-and-answer, filter/sort, hover/scroll.
- Login state và WebArena action format vẫn là nguồn lỗi trong evaluation.

### Next steps

1. Cải thiện prefix recovery bằng re-ground action theo label, role, và context.
2. Thêm no-op/loop detection cho repeated clicks và combobox/select controls.
3. Chạy exploration mới để tăng coverage cho task families còn thiếu.
4. Làm sạch dataset: deduplicate, flag login redirects, balance task types.
5. Fine-tune lại và re-evaluate trên WebArena Shopping, so sánh với mốc hiện tại **14.13%**.

---

## English Version

### Summary

This phase started with a Go-Browse + U/V baseline. However, this direction was not selected as the main direction -> build a new agent based on my supervisor's ideas (**HSGE agent**): a WebArena pipeline with frontier scoring, state recovery, skill discovery, verified skill admission, SFT data generation, and LoRA evaluation.

### General Timeline

| Date | Work |
| --- | --- |
| **1/6** | Tested a Go-Browse-like baseline with U/V frontier scoring. It improved slightly, but this direction was not selected as the main direction -> build a new agent based on my supervisor's ideas (HSGE agent). |
| **4/6** | Designed and started implementing the HSGE agent: online skill discovery, verification-gated admission, hierarchical skill graph, curriculum/transfer idea. |
| **10/6** | Completed an offline baseline to validate the basic pipeline before WebArena runs. |
| **16/6** | Integrated the WebArena runtime: online exploration, multi-provider LLM, screenshots, prefix traces, frontier filtering, and login/account handling. |
| **23-24/6** | Fixed exploration and data-quality issues: prefix replay, stale frontier handling, action validation, and SFT export formats. |
| **25/6** | Fine-tuned LoRA and evaluated HSGE-18 on WebArena Shopping. |

### Main Progress

- **Go-Browse + U/V baseline:** added node selection using Uncertainty and Value scores. Evaluation improved from **22.4%** baseline success to **25.5%** with U and **26.0%** with U+V. However, this direction was not selected as the main project direction because my supervisor wanted a new HSGE-style agent.
- **WebArena runtime:** added online exploration, multi-provider LLM support, screenshot observations, logging, login/account handling, URL-template frontier filtering, and checkpoint/resume.
- **State restoration:** added prefix traces to replay the action path that reached a URL, improving recovery for pages that cannot be restored reliably by direct navigation.
- **Skill discovery:** improved segmentation, abstraction, canonical skill families, verification diagnostics, and quality gates to reject over-specific or non-executable skills.
- **Training pipeline:** standardized the action space, filtered invalid actions and hallucinated BIDs, and added both `hsge_json` and WebArena bracket-action export.
- **Latest LoRA eval:** fine-tuned `Qwen2.5-7B-Instruct` on single-turn and multi-turn HSGE data. WebArena Shopping evaluation reached **26/184 scored tasks = 14.13%**.
- **Latest runtime:** exploration took **3h50m**, training took **1h15m**, and evaluation took **4h**.

### Key Metrics

| Experiment | Result |
| --- | ---: |
| Baseline eval | 43/192, 22.4% |
| Only U eval | 49/192, 25.5% |
| U + V eval | 50/192, 26.0% |
| HSGE first exploration | 20 nodes, 109 tasks, 92/109 positive trajectories; early-stopped due to runtime/action errors |
| `train-single-18.jsonl` | 750 samples, ~3.5M tokens |
| Latest WebArena Shopping eval | 26 pass / 184 scored, 14.13% |
| Latest run time | Exploration 3h50m, training 1h15m, eval 4h |

### Data / Training / Evaluation

- **Data:** the current main dataset is `train-single-18.jsonl` with **750 samples**, about **14.2 MB / 3.5M tokens**, covering **85 page titles**, **109 products**, and **15 categories**. A multi-turn version is also used for the second training stage.
- **Training:** fine-tuned `Qwen2.5-7B-Instruct` with LoRA in two stages: first on single-turn data, then continued on multi-turn data. Latest training time: **1h15m**.
- **Evaluation:** ran WebArena Shopping using an HSGE JSON action adapter into WebArena action format. Latest result: **187 tasks**, **184 scored**, **26 pass**, **158 fail**, **3 unhandled errors**, average score **14.13%**. Evaluation time: **4h**.
- **Exploration data collection:** latest exploration run took **3h50m**. The collected data is still skewed toward easier tasks such as search, wishlist, compare, product detail, and add-to-cart; checkout, order/account workflows, read-and-answer, filter/sort, hover, and scroll remain underrepresented.
- **Note:** HSGE first exploration was an initial test run and stopped early due to runtime/action-format/grounding errors, so the numbers show the basic pipeline working but should not be treated as a complete run.

### Fixed Issues

- Fixed HSGE/WebArena action-format mismatch, especially for `fill`, `type`, `scroll`, `hover`, `press`, and `send_msg_to_user`.
- Filtered invalid training examples: unsupported actions, missing/non-numeric BIDs, disabled/static targets, and truncated thoughts.
- Fixed prefix-derived nodes being reset back to the root page before task execution.
- Stale-prefix and empty-reset nodes are no longer counted as successfully processed.
- Added DOM-link fallback when solver navigation does not discover new URLs, reducing frontier-exhaustion failures.

### Current Limitations

- Exploration can still stop early when prefix traces become stale and actions cannot be re-grounded.
- Grounding remains weak for combobox/select controls, changing BIDs, and repeated labels.
- Skill reuse is still limited; admitted skills are not yet driving strong long-horizon composition.
- Training data is skewed toward simple tasks such as search, wishlist, compare, product detail, and add-to-cart. Checkout, order/account workflows, read-and-answer tasks, filter/sort, hover, and scroll remain underrepresented.
- Login state and WebArena action-format strictness remain important evaluation failure sources.

### Next Steps

1. Improve prefix recovery by re-grounding actions using label, role, and local context.
2. Add no-op and loop detection for repeated clicks and combobox/select controls.
3. Run another exploration pass focused on missing task families.
4. Clean the dataset through deduplication, login-redirect tagging, and task balancing.
5. Fine-tune again and re-evaluate on WebArena Shopping against the current **14.13%** baseline.
