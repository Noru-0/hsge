# Progress Report - Full Version

## 1. Tổng quan

Trong giai đoạn vừa qua, em bắt đầu bằng việc cải thiện một baseline dạng Go-Browse với U/V frontier scoring. Tuy nhiên, hướng này không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (**HSGE agent**): một agent khám phá phân cấp có thể phát hiện skill, kiểm định skill, khôi phục trạng thái exploration, tạo dữ liệu SFT, và đánh giá trên **WebArena Shopping domain** bằng metric **SR (success rate)**.

Mục tiêu chính không chỉ là tăng số lượng trajectory, mà là cải thiện chất lượng trajectory, khả năng khôi phục trạng thái, tính hợp lệ của action, và khả năng dùng dữ liệu thu được để fine-tune agent nhỏ hơn.

## 2. Timeline chung

| Date | Work | Outcome |
| --- | --- | --- |
| **1/6** | Cải thiện Go-Browse-like baseline bằng U/V frontier scoring. | Success rate tăng từ **22.4%** lên **25.5%** với U và **26.0%** với U+V. Tuy nhiên, hướng này không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (HSGE agent). |
| **4/6** | Thiết kế hướng HSGE agent theo ý tưởng thầy đưa ra. | Chuyển trọng tâm sang online skill discovery, verification-gated skill admission, hierarchical skill graph, curriculum và transfer. |
| **10/6** | Hoàn thiện offline baseline. | Có pipeline mock/offline để kiểm tra logic cơ bản trước khi chạy WebArena. |
| **16/6** | Tích hợp WebArena runtime. | Hỗ trợ online exploration, multi-provider LLM, screenshot, prefix trace, frontier filtering, login/account handling và logging. |
| **23/6** | Sửa các lỗi exploration lớn. | Fix prefix-derived task reset, stale-prefix accounting, early frontier exhaustion, empty reset observation. |
| **24/6** | Chuẩn hóa SFT data và action format. | Thêm action validation, lọc invalid examples, hỗ trợ `hsge_json` và WebArena bracket-action export. |
| **25/6** | Fine-tune và evaluate HSGE-18 LoRA trên **WebArena Shopping domain**. | Latest run: exploration **3h50m**, training **1h15m**, eval **4h**; metric chính là **SR**, đạt **26/184 pass = 14.13%**. |

## 3. Baseline Go-Browse + U/V

Vấn đề ban đầu là số lượng URL/node trên một website rất lớn. Nếu khám phá tuần tự toàn bộ frontier thì tốn nhiều thời gian và chi phí, trong khi nhiều node có cấu trúc hoặc giá trị huấn luyện tương tự nhau. Vì vậy, em thêm chiến lược ưu tiên node bằng hai điểm:

- **Uncertainty score (U):** đo mức độ không chắc chắn của model khi nhìn một node. Node có độ phân tán confidence cao được ưu tiên vì có khả năng chứa dữ liệu huấn luyện giá trị hơn.
- **Value score (V):** ưu tiên nhánh có tỷ lệ thành công cao, nhưng giảm dần điểm nếu nhánh đó đã được khai thác nhiều lần. Cách này giúp cân bằng giữa khai thác nhánh tốt và tránh lặp lại quá nhiều sibling URL.

Kết quả exploration trên **WebArena Shopping domain**:

| Strategy | Time | Nodes | Tasks | Trajectories | Training examples |
| --- | ---: | ---: | ---: | ---: | ---: |
| Only U | 6h18m | 6 | 103 | 491 (309/182) | 946 |
| U + V | 18h | 14 | 233 | 1199 (908/291) | 2649 |

Kết quả evaluation sau fine-tuning Qwen2.5-7B-Instruct, chạy trên **WebArena Shopping domain** với metric **SR (success rate)**:

| Strategy | Success/Total | SR | Eval Time |
| --- | ---: | ---: | ---: |
| Baseline | 43/192 | 22.4% | 4h |
| Only U | 49/192 | 25.5% | 4h |
| U + V | 50/192 | 26.0% | 4h |

Kết quả này cho thấy U/V có cải thiện so với baseline, nhưng mức tăng vẫn còn khiêm tốn. Điều này cho thấy scoring frontier giúp ích, nhưng chất lượng action, grounding, task coverage và state restoration vẫn là các nút thắt lớn hơn.

Quan trọng hơn, sau khi báo cáo hướng này, baseline Go-Browse + U/V không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (HSGE agent). Vì vậy, phần U/V baseline được giữ như kết quả thử nghiệm ban đầu, còn trọng tâm chính chuyển sang HSGE agent.

## 4. HSGE Agent và WebArena Runtime

Sau baseline, em triển khai HSGE agent theo hướng hierarchical exploration. Ý tưởng chính là không chỉ thu trajectory độc lập, mà còn phát hiện các sub-trajectory lặp lại, gom cụm, trừu tượng hóa thành skill, kiểm định skill, rồi dùng skill/operator để hỗ trợ exploration và tạo task dài hơn.

Các phần chính đã triển khai:

- **Online exploration trên WebArena:** hệ thống có thể chạy trực tiếp với WebArena environment thay vì chỉ offline mock.
- **Multi-provider LLM support:** hỗ trợ DeepSeek, OpenAI và custom provider để tách explorer model, solver model và lookahead model.
- **Screenshot observation:** lưu screenshot theo từng step để debug và hỗ trợ future vision-based evaluation.
- **Logging và artifact đầy đủ:** mỗi run xuất `coverage.json`, `domain.json`, `frontier.jsonl`, `skills.json`, `skill_diagnostics.json`, `graph.json`, `metrics.json`, `episodes/`, screenshots và page-state accessibility trees.
- **Checkpoint/resume:** runtime có thể lưu trạng thái frontier, visited/queued URLs, prefix traces, skill state và graph state để resume.
- **Login/account handling:** thêm account hints và storage state để xử lý các task cần đăng nhập.

## 5. Frontier, Exploration và State Restoration

Một vấn đề lớn khi khám phá WebArena là nhiều URL không thể khôi phục đúng bằng direct navigation. Ví dụ: URL có thể phụ thuộc session, redirect login, chứa state tạm thời, hoặc element ID thay đổi sau khi reset browser. Vì vậy, em thêm cơ chế **prefix trace**.

Prefix trace lưu lại:

- URL nguồn;
- URL đích;
- action dẫn tới URL đích;
- chuỗi action có thể replay;
- metadata để checkpoint/resume.

Khi một URL được chọn lại từ frontier, runtime ưu tiên replay prefix thay vì chỉ `goto(url)`. Điều này giúp task bắt đầu đúng trạng thái trang hơn, đặc biệt với search result page, product page, cart/wishlist, hoặc các trang sau login.

Các cải tiến exploration quan trọng:

- Frontier selection không còn FIFO thuần. Runtime dùng U/V score, parent success rate, sibling penalty và top-score band để tránh kẹt vào một nhánh stale.
- Callback-discovered URLs từ hành động thực tế của solver được ưu tiên vì có prefix trace.
- Nếu solver không tạo URL mới, runtime fallback sang same-origin DOM links đã lọc theo allow/deny/depth/visited/queued.
- Stale-prefix và empty-reset node không còn bị tính là đã processed/visited thành công.
- Runtime có bounded retry/release cho prefix stale và empty observation.
- Task proposal được grounded hơn theo visible affordances, visible labels, task saturation và progression controls.

Một lỗi quan trọng đã được sửa là prefix-derived node bị reset về root page trước khi chạy task. Sau fix, các task trên search-result page bắt đầu đúng từ search-result state, không còn chạy nhầm từ homepage.

## 6. Skill Discovery và Quality Gates

Sau commit `Improve skill abstraction quality gates`, phần skill lifecycle được cải thiện mạnh hơn. Mục tiêu là tránh admit các skill quá cụ thể, không ground được, hoặc không execute được.

Các thay đổi chính:

- Segment trajectory thành các candidate sub-trajectories có khả năng tái sử dụng.
- Canonicalize skill thành các family tổng quát như `open_visible_item`, `submit_search_query`, `inspect_filter_sort`, `activate_state_change_control`, `fill_visible_field`, `read_visible_detail`.
- Reject skill nếu action template không canonical, slot type sai, dùng value slot làm click target, hoặc description/template quá domain-specific.
- Thêm deterministic fallback SkillCard cho một số primitive quan trọng.
- Thêm verification diagnostics chi tiết thay vì chỉ báo `insufficient_successes`.
- Tăng số browser verification contexts và cho phép bootstrap skill deterministic với `k=1` khi data còn ít nhưng action đã canonical và groundable.

Kết quả quan sát được:

- Sau các fix, hệ thống không còn bị starve hoàn toàn ở bước discovery.
- Một số run đã admit được skill thật, ví dụ `activate_state_change_control`.
- Bottleneck hiện tại chuyển từ "không có skill candidate" sang "verification/grounding chưa đủ mạnh và skill reuse chưa tạo được nhiều long-horizon composition".

## 7. Action Space và Training Data Pipeline

Một vấn đề lớn trong các run đầu là mismatch giữa action format của HSGE/BrowserGym và WebArena. Một số action không hợp lệ vẫn lọt vào training data, làm model học sai format hoặc output action không execute được.

Các lỗi đã phát hiện:

- `select_option()` map sai sang `type`;
- `fill()` tự động submit sớm;
- thiếu `scroll`, `press`, `hover`;
- action không hỗ trợ như `go_back`, tool calls, natural-language commands;
- hallucinated BID như dùng product name thay vì numeric element ID;
- click vào disabled button hoặc static text;
- thought bị truncate, làm mất grounding.

Các cải tiến đã làm:

- Chuẩn hóa canonical action space: `click`, `fill`, `type`, `press`, `scroll`, `hover`, `goto`, `send_msg_to_user`.
- Validate BID phải numeric và tồn tại trong current accessibility tree.
- Reject role-incompatible actions, ví dụ fill vào non-input element.
- Reject disabled target và unsupported action.
- Repair/validate SFT data khi build dataset.
- Hỗ trợ nhiều export format:
  - `hsge_json`: format chính cho HSGE solver, assistant output dạng JSON.
  - WebArena bracket action: dùng khi chạy upstream WebArena eval.

Dataset `train-single-18.jsonl` hiện có:

| Metric | Value |
| --- | ---: |
| Samples | 750 |
| Estimated size | ~14.2 MB / ~3.5M tokens |
| Unique page titles | 85 |
| Unique products | 109 |
| Unique categories | 15 |

Dataset này hữu ích để học action syntax và behavior cơ bản, nhưng còn mất cân bằng. Các task như wishlist, search, compare, product detail, add-to-cart chiếm nhiều; trong khi checkout, cart management, order/account workflow, read-and-answer, filter/sort, hover/scroll còn thiếu.

## 8. Evaluation và LoRA Fine-tuning

Giai đoạn mới nhất dùng `Qwen/Qwen2.5-7B-Instruct` và LoRA hai bước:

1. Fine-tune trên `training/train-single-18.jsonl`.
2. Continue cùng adapter trên `training/train-multi-18.jsonl`.

Evaluation dùng vLLM serve adapter HSGE-18, chạy trên **WebArena Shopping domain** với prompt/action adapter chuyển HSGE JSON action sang WebArena action. Metric chính là **SR (success rate)**. Một số patch cần thiết đã được thêm:

- parse JSON model output;
- convert `click('1424')` thành `click [1424]`;
- convert `fill(...)` thành `type [id] [text] [0]`;
- convert `send_msg_to_user(...)` thành `stop [...]`;
- thêm `action_splitter` để WebArena không crash khi render invalid action;
- dùng `EVAL_MODEL` cho fuzzy evaluator thay vì hardcoded model cũ.

Kết quả mới nhất:

| Metric | Result |
| --- | ---: |
| Exploration time | 3h50m |
| Training time | 1h15m |
| Evaluation time | 4h |
| Total tasks | 187 |
| Scored tasks | 184 |
| Pass | 26 |
| Fail | 158 |
| Unhandled errors | 3 |
| SR over scored tasks | 14.13% |
| SR counting errors as failures | 13.90% |

Ba unhandled errors gồm:

- một page-load timeout;
- một evaluator assertion error;
- một temporary DNS failure tới Cloudflare Shopping URL.

So với các run trước bị dừng sớm hoặc nhiều lỗi runtime/action parsing, đây là evaluation hoàn chỉnh hơn trên **WebArena Shopping domain** và đo được gần toàn bộ Shopping benchmark. Tuy nhiên, **SR** vẫn thấp, chủ yếu do data coverage chưa đủ, grounding chưa mạnh, và skill reuse chưa hỗ trợ tốt long-horizon tasks.

## 9. Lỗi đã sửa và hạn chế còn lại

Các lỗi quan trọng đã sửa:

- Prefix-derived nodes bị reset sai về root page.
- Stale-prefix/empty-reset bị tính nhầm là processed node.
- Frontier rỗng quá sớm khi solver không tạo URL mới.
- Training data chứa invalid action, hallucinated BID, disabled/static target, truncated thought.
- Evaluation crash khi model output HSGE JSON hoặc quoted action không parse được.

Hạn chế hiện tại:

- Exploration vẫn có thể dừng sớm khi prefix stale và không re-ground được.
- Grounding yếu với combobox/select controls, BID thay đổi, repeated labels.
- Solver còn loop với no-op clicks hoặc action không làm thay đổi URL/AXTree.
- Skill reuse chưa đủ mạnh để tạo long-horizon task composition đáng tin cậy.
- Dataset còn lệch về task dễ, thiếu task đọc thông tin, scroll/hover, checkout, account/order.
- Login state còn nhiễu; một số sample bắt đầu từ login redirect.
- WebArena action format strict nên validation/adapter vẫn rất quan trọng.

## 10. Next Steps

1. **Prefix recovery:** re-ground prefix action dựa trên label, role, text gần đó và source page context trước khi release URL.
2. **Loop/no-op handling:** phát hiện repeated click, combobox loop, hoặc action không đổi URL/AXTree để force retry hoặc terminate rõ ràng hơn.
3. **Exploration coverage:** chạy thêm exploration nhắm vào task families còn thiếu: scroll, hover, read-and-answer, filter/sort, cart management, account/order workflow, safe checkout.
4. **Dataset cleaning:** deduplicate single-turn samples, flag login redirects, balance task families, và tách train/dev rõ hơn.
5. **Skill reuse:** cải thiện verified skill retrieval và operator composition để skill không chỉ được admit mà còn thực sự hỗ trợ exploration.
6. **Re-evaluation:** fine-tune lại trên dataset sạch hơn và so sánh trên **WebArena Shopping domain** bằng metric **SR**, với mốc hiện tại **14.13%**.
