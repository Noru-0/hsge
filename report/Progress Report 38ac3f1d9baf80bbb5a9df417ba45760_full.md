# Progress Report - Full Version

## Vietnamese Version

### 1. Tổng quan

Trong giai đoạn vừa qua, em bắt đầu bằng việc cải thiện một baseline dạng Go-Browse với U/V frontier scoring. Tuy nhiên, hướng này không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (**HSGE agent**): một agent khám phá phân cấp có thể phát hiện skill, kiểm định skill, khôi phục trạng thái exploration, tạo dữ liệu SFT, và đánh giá trên WebArena.

Mục tiêu chính không chỉ là tăng số lượng trajectory, mà là cải thiện chất lượng trajectory, khả năng khôi phục trạng thái, tính hợp lệ của action, và khả năng dùng dữ liệu thu được để fine-tune agent nhỏ hơn.

### 2. Timeline chung

| Date | Work | Outcome |
| --- | --- | --- |
| **1/6** | Cải thiện Go-Browse-like baseline bằng U/V frontier scoring. | Success rate tăng từ **22.4%** lên **25.5%** với U và **26.0%** với U+V. Tuy nhiên, hướng này không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (HSGE agent). |
| **4/6** | Thiết kế hướng HSGE agent theo ý tưởng thầy đưa ra. | Chuyển trọng tâm sang online skill discovery, verification-gated skill admission, hierarchical skill graph, curriculum và transfer. |
| **10/6** | Hoàn thiện offline baseline. | Có pipeline mock/offline để kiểm tra logic cơ bản trước khi chạy WebArena. |
| **16/6** | Tích hợp WebArena runtime. | Hỗ trợ online exploration, multi-provider LLM, screenshot, prefix trace, frontier filtering, login/account handling và logging. |
| **23/6** | Sửa các lỗi exploration lớn. | Fix prefix-derived task reset, stale-prefix accounting, early frontier exhaustion, empty reset observation. |
| **24/6** | Chuẩn hóa SFT data và action format. | Thêm action validation, lọc invalid examples, hỗ trợ `hsge_json` và WebArena bracket-action export. |
| **25/6** | Fine-tune và evaluate HSGE-18 LoRA. | Latest run: exploration **3h50m**, training **1h15m**, eval **4h**; WebArena Shopping đạt **26/184 pass = 14.13%**. |

### 3. Baseline Go-Browse + U/V

Vấn đề ban đầu là số lượng URL/node trên một website rất lớn. Nếu khám phá tuần tự toàn bộ frontier thì tốn nhiều thời gian và chi phí, trong khi nhiều node có cấu trúc hoặc giá trị huấn luyện tương tự nhau. Vì vậy, em thêm chiến lược ưu tiên node bằng hai điểm:

- **Uncertainty score (U):** đo mức độ không chắc chắn của model khi nhìn một node. Node có độ phân tán confidence cao được ưu tiên vì có khả năng chứa dữ liệu huấn luyện giá trị hơn.
- **Value score (V):** ưu tiên nhánh có tỷ lệ thành công cao, nhưng giảm dần điểm nếu nhánh đó đã được khai thác nhiều lần. Cách này giúp cân bằng giữa khai thác nhánh tốt và tránh lặp lại quá nhiều sibling URL.

Kết quả exploration:

| Strategy | Time | Nodes | Tasks | Trajectories | Training examples |
| --- | ---: | ---: | ---: | ---: | ---: |
| Only U | 6h18m | 6 | 103 | 491 (309/182) | 946 |
| U + V | 18h | 14 | 233 | 1199 (908/291) | 2649 |

Kết quả evaluation sau fine-tuning Qwen2.5-7B-Instruct:

| Strategy | Success/Total | Success Rate | Eval Time |
| --- | ---: | ---: | ---: |
| Baseline | 43/192 | 22.4% | 4h |
| Only U | 49/192 | 25.5% | 4h |
| U + V | 50/192 | 26.0% | 4h |

Kết quả này cho thấy U/V có cải thiện so với baseline, nhưng mức tăng vẫn còn khiêm tốn. Điều này cho thấy scoring frontier giúp ích, nhưng chất lượng action, grounding, task coverage và state restoration vẫn là các nút thắt lớn hơn.

Quan trọng hơn, sau khi báo cáo hướng này, baseline Go-Browse + U/V không được chọn làm hướng chính -> xây dựng một agent mới theo ý tưởng của thầy (HSGE agent). Vì vậy, phần U/V baseline được giữ như kết quả thử nghiệm ban đầu, còn trọng tâm chính chuyển sang HSGE agent.

### 4. HSGE Agent và WebArena Runtime

Sau baseline, em triển khai HSGE agent theo hướng hierarchical exploration. Ý tưởng chính là không chỉ thu trajectory độc lập, mà còn phát hiện các sub-trajectory lặp lại, gom cụm, trừu tượng hóa thành skill, kiểm định skill, rồi dùng skill/operator để hỗ trợ exploration và tạo task dài hơn.

Các phần chính đã triển khai:

- **Online exploration trên WebArena:** hệ thống có thể chạy trực tiếp với WebArena environment thay vì chỉ offline mock.
- **Multi-provider LLM support:** hỗ trợ DeepSeek, OpenAI và custom provider để tách explorer model, solver model và lookahead model.
- **Screenshot observation:** lưu screenshot theo từng step để debug và hỗ trợ future vision-based evaluation.
- **Logging và artifact đầy đủ:** mỗi run xuất `coverage.json`, `domain.json`, `frontier.jsonl`, `skills.json`, `skill_diagnostics.json`, `graph.json`, `metrics.json`, `episodes/`, screenshots và page-state accessibility trees.
- **Checkpoint/resume:** runtime có thể lưu trạng thái frontier, visited/queued URLs, prefix traces, skill state và graph state để resume.
- **Login/account handling:** thêm account hints và storage state để xử lý các task cần đăng nhập.

### 5. Frontier, Exploration và State Restoration

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

### 6. Skill Discovery và Quality Gates

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

### 7. Action Space và Training Data Pipeline

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

### 8. Evaluation và LoRA Fine-tuning

Giai đoạn mới nhất dùng `Qwen/Qwen2.5-7B-Instruct` và LoRA hai bước:

1. Fine-tune trên `training/train-single-18.jsonl`.
2. Continue cùng adapter trên `training/train-multi-18.jsonl`.

Evaluation dùng vLLM serve adapter HSGE-18, chạy trên WebArena Shopping với prompt/action adapter chuyển HSGE JSON action sang WebArena action. Một số patch cần thiết đã được thêm:

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
| Average score over scored tasks | 14.13% |
| Pass rate counting errors as failures | 13.90% |

Ba unhandled errors gồm:

- một page-load timeout;
- một evaluator assertion error;
- một temporary DNS failure tới Cloudflare Shopping URL.

So với các run trước bị dừng sớm hoặc nhiều lỗi runtime/action parsing, đây là evaluation hoàn chỉnh hơn và đo được gần toàn bộ Shopping benchmark. Tuy nhiên, performance vẫn thấp, chủ yếu do data coverage chưa đủ, grounding chưa mạnh, và skill reuse chưa hỗ trợ tốt long-horizon tasks.

### 9. Lỗi đã sửa và hạn chế còn lại

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

### 10. Next Steps

1. **Prefix recovery:** re-ground prefix action dựa trên label, role, text gần đó và source page context trước khi release URL.
2. **Loop/no-op handling:** phát hiện repeated click, combobox loop, hoặc action không đổi URL/AXTree để force retry hoặc terminate rõ ràng hơn.
3. **Exploration coverage:** chạy thêm exploration nhắm vào task families còn thiếu: scroll, hover, read-and-answer, filter/sort, cart management, account/order workflow, safe checkout.
4. **Dataset cleaning:** deduplicate single-turn samples, flag login redirects, balance task families, và tách train/dev rõ hơn.
5. **Skill reuse:** cải thiện verified skill retrieval và operator composition để skill không chỉ được admit mà còn thực sự hỗ trợ exploration.
6. **Re-evaluation:** fine-tune lại trên dataset sạch hơn và so sánh WebArena Shopping với mốc hiện tại **14.13%**.

---

## English Version

### 1. Overview

This phase started with improving a Go-Browse-like baseline using U/V frontier scoring. However, this direction was not selected as the main direction -> build a new agent based on my supervisor's ideas (**HSGE agent**): a hierarchical exploration agent that supports state recovery, online skill discovery, verification-gated skill admission, SFT dataset construction, and WebArena evaluation.

The goal was not only to collect more trajectories, but to improve trajectory quality, action validity, state recovery, and the usefulness of collected data for fine-tuning a smaller agent.

### 2. General Timeline

| Date | Work | Outcome |
| --- | --- | --- |
| **1/6** | Improved a Go-Browse-like baseline with U/V frontier scoring. | Success rate improved from **22.4%** to **25.5%** with U and **26.0%** with U+V. However, this direction was not selected as the main direction -> build a new agent based on my supervisor's ideas (HSGE agent). |
| **4/6** | Designed the HSGE agent direction based on my supervisor's ideas. | Shifted focus to online skill discovery, verification-gated admission, hierarchical skill graph, curriculum, and transfer. |
| **10/6** | Completed an offline baseline. | Validated the basic pipeline with mock/offline components before WebArena runs. |
| **16/6** | Integrated the WebArena runtime. | Added online exploration, multi-provider LLM support, screenshots, prefix traces, frontier filtering, login/account handling, and logging. |
| **23/6** | Fixed major exploration failures. | Fixed prefix-derived task reset, stale-prefix accounting, early frontier exhaustion, and empty reset observation handling. |
| **24/6** | Standardized SFT data and action formats. | Added action validation, invalid-example filtering, `hsge_json`, and WebArena bracket-action export. |
| **25/6** | Fine-tuned and evaluated HSGE-18 LoRA. | Latest run: exploration **3h50m**, training **1h15m**, eval **4h**; WebArena Shopping reached **26/184 pass = 14.13%**. |

### 3. Go-Browse + U/V Baseline

The original problem is that websites expose too many URLs/nodes to explore exhaustively. A better frontier strategy is needed to select high-value nodes under a limited exploration budget.

I added two scoring signals:

- **Uncertainty score (U):** prioritizes nodes where the model has uneven confidence across candidate tasks. These nodes may provide more useful training signal.
- **Value score (V):** prioritizes branches with higher parent success rate, while discounting branches that have already been explored too often.

Exploration results:

| Strategy | Time | Nodes | Tasks | Trajectories | Training examples |
| --- | ---: | ---: | ---: | ---: | ---: |
| Only U | 6h18m | 6 | 103 | 491 (309/182) | 946 |
| U + V | 18h | 14 | 233 | 1199 (908/291) | 2649 |

Evaluation after fine-tuning Qwen2.5-7B-Instruct:

| Strategy | Success/Total | Success Rate | Eval Time |
| --- | ---: | ---: | ---: |
| Baseline | 43/192 | 22.4% | 4h |
| Only U | 49/192 | 25.5% | 4h |
| U + V | 50/192 | 26.0% | 4h |

This shows that U/V scoring improves over the baseline, but the gain is still modest. The larger bottlenecks are action validity, grounding, state recovery, and task-family coverage.

More importantly, after this result, the Go-Browse + U/V direction was not continued as the main path. My supervisor wanted a new HSGE-style agent, so the U/V baseline is treated as an initial experiment, while the main work shifted to HSGE.

### 4. HSGE Agent and WebArena Runtime

After the baseline, I implemented a more complete HSGE agent for hierarchical exploration. Instead of treating each trajectory independently, the system now mines repeated sub-trajectories, clusters them, abstracts them into reusable skills, verifies those skills, and uses them to support future exploration and long-horizon task construction.

Implemented components:

- **Online WebArena exploration:** the system now runs against WebArena instead of only offline mocks.
- **Multi-provider LLM support:** supports DeepSeek, OpenAI, and custom providers, with separate explorer/solver/lookahead models.
- **Screenshot observations:** screenshots are saved per step for debugging and future vision support.
- **Detailed logging and artifacts:** each run can export coverage, domain summary, frontier snapshots, skills, diagnostics, graph state, metrics, episodes, screenshots, and accessibility trees.
- **Checkpoint/resume:** runtime state can be persisted and resumed, including frontier, visited/queued URLs, prefix traces, skill state, and graph state.
- **Login/account handling:** account hints and storage state were added for login-required tasks.

### 5. Frontier, Exploration, and State Restoration

A key issue in WebArena is that many pages cannot be reliably restored by direct URL navigation. URLs may depend on session state, login redirects, temporary state, or changing element IDs. To handle this, I added **prefix traces**.

A prefix trace records:

- source URL;
- target URL;
- action that discovered the target;
- replayable action path;
- checkpoint/resume metadata.

When a frontier URL is selected, the runtime can replay the prefix instead of only calling `goto(url)`. This helps recover pages such as search results, product pages, cart/wishlist pages, and login-derived pages.

Exploration improvements:

- Frontier selection moved beyond FIFO using U/V scores, parent success rate, sibling penalty, and a bounded top-score band.
- Callback-discovered URLs from real solver actions are preferred because they have replayable prefixes.
- If solver actions do not discover new URLs, the runtime falls back to filtered same-origin DOM links.
- Stale-prefix and empty-reset nodes are no longer counted as successfully processed.
- Bounded retry/release was added for stale prefixes and empty observations.
- Task proposal became more grounded in visible labels, affordances, task saturation, and progression controls.

One important bug fixed was that prefix-derived nodes were being reset back to the root page before task execution. After the fix, tasks on search-result pages begin from the correct search-result state.

### 6. Skill Discovery and Quality Gates

After the `Improve skill abstraction quality gates` commit, the skill lifecycle was strengthened to avoid admitting skills that are too specific, ungroundable, or non-executable.

Main changes:

- Segment successful trajectories into reusable sub-trajectory candidates.
- Canonicalize skills into general families such as `open_visible_item`, `submit_search_query`, `inspect_filter_sort`, `activate_state_change_control`, `fill_visible_field`, and `read_visible_detail`.
- Reject skills with noncanonical action templates, wrong slot types, value slots used as click targets, or overly domain-specific names/descriptions/templates.
- Add deterministic fallback SkillCards for important primitives.
- Add detailed verification diagnostics instead of only reporting `insufficient_successes`.
- Increase browser verification contexts and allow deterministic bootstrap skills with `k=1` when data is still sparse but the action is canonical and grounded.

Observed outcome:

- Discovery is no longer completely starved.
- Later runs admitted real skills, including `activate_state_change_control`.
- The main bottleneck has shifted from "no candidate skills" to "verification/grounding quality and limited skill reuse."

### 7. Action Space and Training Data Pipeline

Early runs revealed a mismatch between HSGE/BrowserGym actions and upstream WebArena actions. Invalid actions were entering training data, which taught the model syntax and behavior that the evaluator could not execute.

Issues found:

- `select_option()` mapped incorrectly to `type`;
- `fill()` submitted forms too early;
- missing `scroll`, `press`, and `hover`;
- unsupported actions such as `go_back`, tool calls, and natural-language commands;
- hallucinated BIDs, such as product names used instead of numeric element IDs;
- clicks on disabled buttons or static text;
- truncated thoughts with weak grounding.

Fixes implemented:

- Standardized canonical actions: `click`, `fill`, `type`, `press`, `scroll`, `hover`, `goto`, and `send_msg_to_user`.
- Validated that BIDs are numeric and present in the current accessibility tree.
- Rejected role-incompatible actions, such as filling a non-input element.
- Rejected disabled targets and unsupported actions.
- Added SFT validation/repair during dataset construction.
- Added multiple export formats:
  - `hsge_json`: primary HSGE solver format with JSON assistant output.
  - WebArena bracket actions: used for upstream WebArena evaluation.

Current `train-single-18.jsonl` data:

| Metric | Value |
| --- | ---: |
| Samples | 750 |
| Estimated size | ~14.2 MB / ~3.5M tokens |
| Unique page titles | 85 |
| Unique products | 109 |
| Unique categories | 15 |

The dataset is useful for action syntax and basic shopping behavior, but it remains imbalanced. Wishlist, search, compare, product-detail, and add-to-cart tasks dominate. Checkout, cart management, account/order workflows, read-and-answer, filter/sort, hover, and scroll tasks are underrepresented.

### 8. Evaluation and LoRA Fine-tuning

The latest training used `Qwen/Qwen2.5-7B-Instruct` with a two-stage LoRA workflow:

1. Fine-tune on `training/train-single-18.jsonl`.
2. Continue the same adapter on `training/train-multi-18.jsonl`.

Evaluation served the HSGE-18 adapter with vLLM and ran WebArena Shopping using an HSGE JSON prompt/action adapter. Required patches included:

- parsing JSON model output;
- converting `click('1424')` to `click [1424]`;
- converting `fill(...)` to `type [id] [text] [0]`;
- converting `send_msg_to_user(...)` to `stop [...]`;
- adding `action_splitter` to avoid WebArena render crashes;
- using `EVAL_MODEL` for the fuzzy evaluator instead of an old hardcoded model.

Latest result:

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
| Average score over scored tasks | 14.13% |
| Pass rate counting errors as failures | 13.90% |

The three unhandled errors were:

- one page-load timeout;
- one evaluator assertion error;
- one temporary DNS failure to the Cloudflare Shopping URL.

Compared with earlier halted or noisy runs, this is a more complete evaluation because it successfully ran almost the full Shopping benchmark. However, performance is still low, mainly because task coverage, grounding, and skill reuse are not yet strong enough for long-horizon WebArena tasks.

### 9. Fixed Issues and Current Limitations

Fixed issues:

- Prefix-derived nodes were reset incorrectly to the root page.
- Stale-prefix and empty-reset failures were counted as processed nodes.
- Frontier could terminate too early when solver actions discovered no new URLs.
- Training data contained invalid actions, hallucinated BIDs, disabled/static targets, and truncated thoughts.
- Evaluation could crash on HSGE JSON or quoted action outputs.

Current limitations:

- Exploration can still stop early when prefixes become stale and actions cannot be re-grounded.
- Grounding remains weak for combobox/select controls, changing BIDs, and repeated labels.
- The solver can still loop on no-op clicks or actions that do not change the URL/AXTree.
- Skill reuse is not yet strong enough to drive reliable long-horizon composition.
- The dataset is skewed toward easy tasks and lacks read, scroll, hover, checkout, account, and order-management tasks.
- Login state remains noisy; some samples start from login redirects.
- WebArena's strict action format makes validation and adapters necessary.

### 10. Next Steps

1. **Prefix recovery:** re-ground prefix actions using label, role, nearby text, and source-page context before releasing a URL.
2. **Loop/no-op handling:** detect repeated clicks, combobox loops, and actions that do not change URL/AXTree.
3. **Exploration coverage:** run targeted exploration for missing task families: scroll, hover, read-and-answer, filter/sort, cart management, account/order workflows, and safe checkout.
4. **Dataset cleaning:** deduplicate single-turn samples, flag login redirects, balance task families, and create cleaner train/dev splits.
5. **Skill reuse:** improve verified skill retrieval and operator composition so admitted skills actively improve exploration.
6. **Re-evaluation:** fine-tune again with cleaner data and compare WebArena Shopping results against the current **14.13%** score.
