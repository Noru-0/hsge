# Progress Report - Full Version

**Cập nhật đến:** 01/07/2026

## 1. Tổng quan

Trong tuần này, em tập trung sửa HSGE agent ở ba phần chính:

1. Làm rõ và siết chặt logic **trajectory → skill → predicate → operator → curriculum**.
2. Cải thiện Solver để làm được nhiều task đúng hơn và tạo trajectory sạch hơn.
3. Sửa các bug exploration làm agent chạy sai page, mất frontier, lặp action hoặc tạo graph/curriculum không đáng tin cậy.

Báo cáo chỉ dùng hai run Shopping để so sánh:

- **Run 18:** trạng thái trước khi thực hiện các cải tiến chính của tuần này.
- **Run 25:** trạng thái sau khi cập nhật Solver, skill discovery, predicate verification, operator graph và curriculum.

Hai run có thời lượng và số node khác nhau, vì vậy phần so sánh tập trung vào **độ tin cậy của logic và chất lượng kết quả**, không dùng tổng số task hay tổng số node để kết luận run nào tốt hơn.

## 2. Timeline chung

| Date | Work | Outcome |
| --- | --- | --- |
| **1/6** | Cải thiện Go-Browse-like baseline bằng U/V frontier scoring. | Success rate tăng từ **22.4%** lên **25.5%** với U và **26.0%** với U+V. Hướng này sau đó không được chọn làm hướng chính. |
| **4/6** | Thiết kế HSGE agent theo ý tưởng thầy đưa ra. | Chuyển trọng tâm sang online skill discovery, verification-gated skill admission, hierarchical skill graph, curriculum và transfer. |
| **10/6** | Hoàn thiện offline baseline. | Có pipeline mock/offline để kiểm tra logic cơ bản trước khi chạy WebArena. |
| **16/6** | Tích hợp WebArena runtime. | Hỗ trợ online exploration, multi-provider LLM, screenshot, prefix trace, frontier filtering, login/account handling và logging. |
| **23/6** | Sửa các lỗi exploration lớn. | Fix prefix-derived task reset, stale-prefix accounting, early frontier exhaustion và empty reset observation. |
| **24/6** | Chuẩn hóa SFT data và action format. | Thêm action validation, lọc invalid examples, hỗ trợ `hsge_json` và WebArena bracket-action export. |
| **25/6** | Fine-tune và evaluate HSGE-18 LoRA trên WebArena Shopping. | Exploration **3h50m**, training **1h15m**, evaluation **4h**; đạt **26/184 = 14.13% SR** trên scored tasks. |
| **29/6** | Sửa visited-node, observability, prefix recovery và operator/curriculum logic. | Node metrics trung thực hơn; skill execution verification được tách khỏi planning-effect verification. |
| **30/6** | Cải thiện Solver prompt, segmentation/clustering và LLM judge; chạy Shopping run 25. | Solver ổn định hơn; skill/operator/curriculum được tạo theo verified predicate effects thay vì ghép task một cách rộng. |
| **1/7** | Tổng hợp và phân tích run 18 so với run 25. | Xác định rõ tiến bộ của Solver và bottleneck còn lại ở effect learning, state-changing skill và long-horizon curriculum. |

## 3. So sánh Run 18 và Run 25

### 3.1 Kết quả chính

| Metric | Run 18 | Run 25 | Ý nghĩa |
| --- | ---: | ---: | --- |
| Processed nodes | 82 | 10 | Run 25 ngắn hơn và bị dừng giữa node 11; không so sánh coverage tuyệt đối. |
| Tasks proposed | 356 | 123 | Run 25 tạo nhiều task trên mỗi node hơn. |
| Solved / completed tasks | 250/308 = **81.2%** | 101/122 = **82.8%** | Tỷ lệ tổng tăng nhẹ, nhưng độ ổn định và một số task family tăng rõ hơn. |
| Task errors | 14 | **0** | Solver/runtime không còn làm mất task vì exception trong run 25. |
| Node errors | 115 | **0** | Run 18 có nhiều lỗi, đặc biệt khi quota hết ở cuối run; run 25 không có node error. |
| Invalid/empty episodes | 9 | 3 | Dữ liệu sinh ra sạch hơn, nhưng vẫn chưa bằng 0. |
| Verified skills | 6 | 6 | Số lượng bằng nhau; khác biệt chính nằm ở cách hiểu và sử dụng skill. |
| Mined operators | 18 | **3** | Run 25 chỉ tạo operator khi skill có effect đủ tin cậy. |
| Skills trong high-level graph | 24 | **3** | Run 18 đưa cả task-specific operator vào graph; run 25 giữ graph nhỏ và chặt hơn. |
| Composition edges | 144 | **3** | Run 18 nối quá rộng; run 25 chỉ nối dựa trên predicate precondition/effect. |
| Curriculum tasks | 1,076 | **3** | Run 18 bị combinatorial explosion; run 25 chỉ sinh task có reachable verified goal. |

Run 18 từng tạo 1.076 curriculum tasks, gồm 24 task difficulty 1, 146 task difficulty 2 và 906 task difficulty 3. Con số này nhìn lớn nhưng không phản ánh curriculum tốt. Graph chứa nhiều skill quá cụ thể như:

- `click_peipu_joystick_mobile`;
- `open_indoor_pet_camera`;
- `open_loopacell_ag13_lr44`;
- `click_sports_outdoors`;
- `click_beauty_personal_care`.

Các skill này được nối với nhau quá dễ dàng, tạo ra hàng trăm chuỗi không có đủ bằng chứng rằng bước trước thực sự tạo state cần cho bước sau.

Run 25 đi theo hướng ngược lại. Trong 6 verified skills:

- 3 skill thực thi được nhưng chưa chứng minh được state effect;
- 3 skill có verified effect và được đưa vào operator graph;
- curriculum chỉ sinh 3 task difficulty 1 có goal predicate cụ thể.

Vì vậy, điểm cải thiện quan trọng của run 25 không phải là “tạo nhiều curriculum hơn”, mà là **không tạo curriculum giả khi chưa có đủ bằng chứng**.

## 4. Logic tạo Skill, Predicate và Curriculum

Flow hiện tại có thể hiểu đơn giản như sau:

```text
Solver hoàn thành task
        ↓
Trajectory được chia thành các đoạn hành vi nhỏ
        ↓
Các đoạn giống nhau được gom thành cluster
        ↓
Cluster được trừu tượng hóa thành SkillCard
        ↓
Quan sát trước/sau action tạo precondition và effect
        ↓
Skill được chạy lại để kiểm định
        ↓
Skill có verified effect trở thành Operator
        ↓
Operator nối được với nhau mới tạo Curriculum
```

### 4.1 Tạo skill

Mỗi task Solver làm thành công tạo ra một trajectory gồm các action và observation. Hệ thống không dùng nguyên trajectory dài làm một skill, mà xử lý theo các bước:

1. **Chia trajectory thành đoạn nhỏ.** Ví dụ một task search có thể được tách thành `fill(search box)` và `click(Search)`; một task mở sản phẩm được tách quanh action click làm URL đổi sang product page.
2. **Gắn ý nghĩa cho từng đoạn.** LLM đặt subgoal ngắn như `submit search query`, `open visible item` hoặc `inspect menu options`.
3. **Gom các đoạn giống nhau.** Clustering dùng subgoal, action signature và observed effect; các action đều là `click` nhưng có mục đích khác nhau không nên nằm chung cluster.
4. **Trừu tượng hóa.** LLM chuyển các ví dụ cụ thể thành SkillCard tổng quát với tên, mô tả, slot và action template.
5. **Kiểm tra chất lượng.** Skill bị reject nếu tên/template quá task-specific, action không canonical, slot sai loại hoặc selector không ground được vào page.
6. **Chạy lại để verify.** Skill phải bind được slot và thực thi thành công trong browser context thật trước khi được admit.

Ví dụ:

```text
Các trajectory cụ thể:
  fill('Search', 'camera') → click('Search')
  fill('Search', 'tea')    → press('ENTER')

Skill tổng quát:
  submit_search_query(search_field, query, submit_control)
```

Điểm khác biệt so với run 18 là hệ thống không còn coi những hành vi như “click đúng một sản phẩm cụ thể” là reusable skill chỉ vì action đó từng thành công.

### 4.2 Tạo predicate

Predicate là cách biểu diễn ngắn gọn state của website. Ví dụ:

- `results_shown`: trang đang hiển thị kết quả tìm kiếm;
- `view:detail`: đang ở trang chi tiết;
- `item_selected`: một item cụ thể đã được mở/chọn;
- `cart_nonempty`: cart đã có sản phẩm;
- `has_filter_or_sort`: trang có filter hoặc sort control.

Với mỗi action, runtime lưu hai state:

```text
State trước action  = URL + AXTree + predicates trước
State sau action    = URL + AXTree + predicates sau
Effect của action   = predicates sau - predicates trước
```

Ví dụ:

```text
Trước click product:
  {results_shown, view:collection}

Sau click product:
  {results_shown, view:collection, item_selected, view:detail}

Observed effect:
  {item_selected, view:detail}
```

Predicate không chỉ được lấy từ mô tả do LLM viết. Hệ thống yêu cầu predicate phải có evidence trong URL/AXTree và phải xuất hiện nhất quán trong các trajectory của cluster. Khi verify skill trong browser, effect dự đoán cũng phải thực sự xuất hiện sau action.

Đây là thay đổi quan trọng so với run 18. Trước đây operator có thể được tạo từ task/subgoal text và được nối khá rộng. Trong run 25, skill chỉ trở thành planner-ready nếu có **observed effect** và effect đó vượt qua verification.

### 4.3 Hai mức skill sau verification

Run 25 tách skill thành hai mức:

**Execution-verified skill**

- bind được selector/value;
- action chạy được trong browser;
- chưa chứng minh được state thay đổi ổn định;
- được giữ trong SkillLibrary để tiếp tục thu evidence;
- chưa được dùng để plan curriculum.

**Planner-ready skill**

- action chạy được;
- có precondition/effect rõ ràng;
- effect được quan sát và verify trong browser context;
- được chuyển thành Operator và đưa vào graph.

Run 25 có 6 verified skills nhưng chỉ 3 planner-ready operators. Ba skill còn lại gồm `inspect_menu_options`, `inspect_feedback_indicator` và `activate_state_change_control` chưa có đủ planning effect nên không được phép làm graph phình ra.

### 4.4 Tạo curriculum

Mỗi Operator có dạng:

```text
Preconditions ──skill──> Effects
```

Hai operator chỉ nối được khi effect của operator trước đáp ứng precondition của operator sau. Curriculum planner bắt đầu từ predicates của root state, sau đó tìm chuỗi operator ngắn nhất để đạt một goal predicate chưa có sẵn.

Run 18 nối skill quá rộng và sinh mọi tổ hợp đến difficulty 3, dẫn đến 1.076 tasks. Run 25 chỉ sinh ba task có verified reachable goal:

- dùng skill để đạt `has_filter_or_sort`;
- dùng skill để đạt `results_shown`;
- dùng skill để đạt `view:detail`.

Run 25 chưa có difficulty-2 curriculum. Đây là hạn chế hiện tại, nhưng cũng là kết quả trung thực: graph chưa học được một chuỗi effect đủ chắc để tạo long-horizon task.

## 5. Solver làm task tốt hơn

### 5.1 Prompt và action grounding rõ hơn

Solver hiện nhận goal, AXTree hiện tại, tài liệu action space đầy đủ và lịch sử action gần nhất. Task được gắn nhóm `[INFO]`, `[NAV]` hoặc `[MOD]`, giúp Solver phân biệt task chỉ cần đọc thông tin, task cần điều hướng và task cần thay đổi state.

Action phải qua validation trước khi browser execute:

- action phải thuộc canonical action space;
- BID phải là số và tồn tại trong AXTree hiện tại;
- target phải phù hợp với action, ví dụ chỉ `fill` vào input;
- disabled/static target bị reject;
- `goto()` tự bịa hoặc cross-origin bị chặn.

### 5.2 Retry và loop handling tốt hơn

Mỗi task có tối đa ba solve attempts. Solver phát hiện:

- cùng action trên cùng URL lặp nhiều lần;
- action cycle không tạo state mới;
- nhiều scroll liên tiếp nhưng observation không đổi;
- invalid action liên tiếp;
- click timeout nhưng navigation thực tế đã xảy ra.

Nhờ vậy Solver ít bị kẹt trong no-op loop và không tiếp tục ghi trajectory dài nhưng vô ích.

### 5.3 Success checking tốt hơn

Với task có symbolic goal, Solver kiểm tra trực tiếp predicate đích. Với natural-language task, câu trả lời phải có evidence trong page đã quan sát. State-changing task khó nhận biết do Magento cập nhật bằng AJAX được kiểm tra thêm bằng LLM judge dựa trên action và final state.

Kết quả quan sát được từ hai run:

| Task family | Run 18 | Run 25 |
| --- | ---: | ---: |
| Search | 44/59 = **74.6%** | 14/15 = **93.3%** |
| Feedback/read information | 22/28 = **78.6%** | 21/24 = **87.5%** |
| Other navigation/information tasks | 67/82 = **81.7%** | 31/34 = **91.2%** |
| Analysis | 23/25 = **92.0%** | 23/24 = **95.8%** |
| State change | 92/109 = **84.4%** | 10/22 = **45.5%** |

Solver cải thiện rõ nhất ở search, đọc thông tin và navigation. Run 25 làm được các task như tìm price/SKU/review count, kiểm tra stock, đổi sort, chuyển grid/list, mở category/product và add-to-cart.

State-changing task chưa cải thiện đồng đều. Wishlist, compare và một số AJAX controls vẫn thất bại nhiều. Vì vậy kết luận đúng là: **Solver ổn định và làm tốt hơn nhiều ở phần lớn task đọc/điều hướng/search, nhưng state-changing controls vẫn là bottleneck chính.**

Số `tasks_solved` là kết quả của internal exploration judge, không phải WebArena benchmark SR.

## 6. Các bug đã sửa trong tuần

| Bug trước đây | Cách sửa | Kết quả trong Run 25 |
| --- | --- | --- |
| Node bị tính visited trước khi load/process thành công. | Chỉ cập nhật visited/processed sau khi `_process_node()` hoàn tất. | Node metrics không còn tăng vì stale hoặc failed node. |
| Task trên prefix-derived node bị reset về root page. | Trước mỗi task, replay prefix hoặc khôi phục đúng actual node URL. | Task được chạy trên đúng search/category/product state. |
| BID trong prefix bị stale sau browser reset. | Lưu role/name/fingerprint và semantic re-ground target; có bounded retry và direct-goto fallback. | Run 25 có 73 semantic re-ground events, 18 direct-goto fallbacks và chỉ 1 prefix-unavailable node. |
| Query URL khác nhau bị gộp hoặc đánh dấu visited sai. | Chỉ bỏ tracking parameters; giữ query có ý nghĩa như search/sort/filter. | Search và sort result pages được xem là state/node riêng. |
| Solver sinh action không hợp lệ hoặc click sai loại element. | Canonical action validation, numeric BID check, role/disabled validation. | Task errors giảm từ 14 xuống 0. |
| Solver lặp click/scroll nhưng page không đổi. | Repeated-transition, cycle và scroll-saturation detection. | Trajectory ngắn và sạch hơn, giảm no-op loop. |
| Thought bị truncate hoặc không đủ grounding cho SFT. | Sửa thought repair và lưu pre/post action evidence. | Training example giữ được lý do chọn target và state transition. |
| Task-specific skill/operator làm graph phình lớn. | Bỏ task-specific proposal; canonicalize skill; chỉ tạo operator từ verified effect. | Graph giảm từ 24 xuống 3 planning skills; curriculum giảm từ 1.076 xuống 3 grounded tasks. |
| Skill chạy được bị hiểu nhầm là skill dùng được cho planning. | Tách execution-verified và planner-ready. | 3 effectless skills không được đưa vào OperatorGraph. |
| Khó biết bug nằm ở frontier, skill hay planner. | Thêm structured events, metrics, skill diagnostics và curriculum diagnostics. | Run 25 có thể truy vết prefix, cluster, verification, operator và reachable goal riêng. |

Run 18 có 115 node errors và 129 tổng errors, nhưng nhiều lỗi ở cuối run đến từ OpenAI `429 insufficient_quota`. Vì vậy không nên xem toàn bộ chênh lệch error là do code fix. Điểm chắc chắn hơn là run 25 không có task exception, node exception hoặc invalid-action crash trong phần đã chạy.

## 7. Hạn chế còn lại

- Run 25 vẫn có 3 invalid/empty episodes.
- Prefix semantic recovery còn 4 trường hợp ambiguous target và một prefix-unavailable node.
- Wishlist, compare, repeated label và combobox/select controls còn yếu.
- Một số cluster vẫn trộn các click khác mục đích; nhiều planner-ready skills cùng mang tên `open_visible_item` nhưng effects khác nhau.
- Persistent cart/session làm predicate như `cart_nonempty` bị bão hòa, nên action add-to-cart về sau có thể không tạo effect mới.
- Curriculum mới chỉ có difficulty 1; chưa có verified two-step chain.
- LLM judge cho state-changing task có khả năng tạo false positive và cần được audit thêm.

## 8. Kết luận và bước tiếp theo

Tiến bộ chính của tuần này là chuyển HSGE từ cách tạo nhiều skill/operator/curriculum nhưng khó tin cậy sang một pipeline chặt hơn:

- Solver tạo trajectory ổn định hơn;
- skill phải tổng quát, ground được và execute được;
- predicate phải đến từ state transition có evidence;
- effect phải được verify trước khi skill trở thành operator;
- curriculum chỉ được sinh từ reachable verified effects.

Run 25 chưa tạo được long-horizon curriculum, nhưng graph nhỏ và trung thực hơn run 18. Đây là nền tảng phù hợp để tiếp tục cải thiện thay vì fine-tune từ các trajectory hoặc skill chain nhiễu.

Các bước tiếp theo:

1. Tách cluster theo target intent và observed effect để `open product`, `change state`, `wishlist` và `navigation` không bị gom chung chỉ vì đều dùng `click`.
2. Reset hoặc theo dõi cart count/event để tránh predicate state bị bão hòa.
3. Cải thiện grounding cho wishlist, compare, combobox và repeated labels.
4. Yêu cầu acceptance test có ít nhất một verified curriculum chain difficulty 2, ví dụ `search → open result` hoặc `open item → add to cart`.
5. Audit LLM-judged state-changing episodes trước khi dùng để build SFT dataset.
6. Chạy lại một exploration dài hơn sau các fix và chỉ khi dữ liệu sạch mới fine-tune/re-evaluate bằng WebArena SR.
