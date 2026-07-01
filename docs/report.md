# Báo cáo: Giải pháp cho vấn đề Pre-condition / Post-condition trong việc nối Operator

> **Tóm tắt:** Vấn đề về matching Pre-condition và Post-condition giữa các Operator – vốn là câu hỏi em định nhờ thầy tham mưu – đã được giải quyết bằng phương pháp so sánh Embedding. Kết quả: Curriculum được tạo đúng, và **Semantic Task** đã xuất hiện – mở đường cho việc finetuning SLM hiệu quả. Ngoài ra, tỷ lệ task pass cũng tăng từ **~46% (309/660)** lên **82.8% (101/122)** nhờ cải thiện Solver Agent với cơ chế retry và LLM-as-Judge.

---

## 1. Bối cảnh: Agent HSGE và flow Explore

### 1.1 Mục tiêu của agent

HSGE (Hierarchical Skill Graph Exploration) là một agent có khả năng **tự động khám phá các task SEMANTIC (có ý nghĩa, dài hơi) trên bất kỳ web domain nào**, sau đó thực thi các task đó để tạo dữ liệu training cho các mô hình ngôn ngữ nhỏ (SLM). Khác với các agent flat exploration truyền thống chỉ tạo ra các task đơn giản trên một trang (như "tìm kiếm", "lọc"), HSGE hướng tới các task phức hợp, nhiều bước như "tìm SSD 1TB rẻ nhất, thêm vào giỏ hàng, và báo cáo tổng tiền".

### 1.2 Tổng quan flow Explore

```
┌──────────────┐     ┌────────────────┐     ┌─────────────────┐
│  Flat        │────▶│  Segmentation  │────▶│  Clustering      │
│  Exploration │     │  (chia nhỏ     │     │  (nhóm các       │
│  (thu thập   │     │   trajectory   │     │   sub-trajectory │
│   trajectory)│     │   thành các    │     │   tương tự)      │
│              │     │   sub-goal)    │     │                  │
└──────────────┘     └────────────────┘     └────────┬─────────┘
                                                     │
                                                     ▼
┌──────────────┐     ┌────────────────┐     ┌─────────────────┐
│  Curriculum  │◀────│  Operator      │◀────│  Abstraction    │
│  Generation  │     │  Graph         │     │  (tạo SkillCard │
│  (sinh task  │     │  (nối skill    │     │   từ cluster,   │
│   semantic   │     │   qua pre/post │     │   gán pre/post  │
│   đa bước)   │     │   condition)   │     │   condition)    │
└──────────────┘     └────────────────┘     └────────┬─────────┘
                                                     │
                                                     ▼
                                             ┌─────────────────┐
                                             │  Verification   │
                                             │  (kiểm tra skill│
                                             │   trong context │
                                             │   mới, ≥k lần)  │
                                             └─────────────────┘
```

Các khái niệm chính:

| Khái niệm | Ý nghĩa | Vai trò trong việc tạo Semantic Trajectory |
|---|---|---|
| **Skill** | Một hành vi tái sử dụng được, có tham số (vd: `submit_search_query`, `open_visible_item`) | Là "viên gạch" cơ bản để xây dựng task phức hợp |
| **Operator** | Skill được biểu diễn dưới dạng planning operator với Pre-condition và Effect | Cho phép lập kế hoạch tự động: skill A → skill B nếu effect của A thỏa mãn pre-condition của B |
| **Curriculum** | Tập các task được sinh ra bằng cách lập kế hoạch (planning) từ trạng thái ban đầu đến goal predicate | Tạo ra các task có độ khó tăng dần, bao gồm cả task dài hơi (purchase chain) |
| **Semantic Task** | Task có ý nghĩa, nhiều bước, được sinh tự động từ Operator Graph | Là dữ liệu training chất lượng cao cho SLM |

---

## 2. Vấn đề đã dự định nhờ thầy tham mưu

### 2.1 Vấn đề Pre-condition và Post-condition để nối các Operator

Để tạo được Operator Graph – đồ thị kết nối các skill với nhau theo quan hệ "skill A → skill B nếu effect của A thỏa mãn pre-condition của B" – cần xác định được **Pre-condition** (điều kiện cần để thực thi skill) và **Post-condition/Effect** (kết quả skill tạo ra) cho mỗi skill.

#### Cách tiếp cận ban đầu (đã bị loại bỏ):

1. **Hardcode một danh sách Pre-condition và Post-condition phổ biến** (vd: `has_search_input`, `results_shown`, `view:collection`, …) và dùng rule-based regex để trích xuất chúng từ page state.

   **Hạn chế:** Danh sách hardcode không bao quát được hết các tình huống thực tế. Các predicate được định nghĩa cứng không đủ linh hoạt để mô tả chính xác trạng thái trước/sau khi thực hiện skill trên các domain khác nhau.

2. **So sánh Pre-condition và Post-condition do LLM tạo bằng logic thông thường** (so khớp chính xác chuỗi predicate).

   **Hạn chế nghiêm trọng:** Pre-condition và Post-condition được LLM sinh ra sau khi đã quan sát trạng thái trước và sau khi thực hiện skill. Tuy nhiên, LLM khác nhau (hoặc cùng LLM ở các lần gọi khác nhau) có thể tạo ra các predicate **có cùng ý nghĩa nhưng khác tên**. Ví dụ:
   - `has_search_box` vs `has_search_input` vs `search_available`
   - `item_in_cart` vs `cart_has_items` vs `cart_nonempty`

   Việc so sánh exact-match không nhận ra được sự tương đương này, dẫn đến **không tạo được Operator Graph đúng → không có Curriculum đúng → không tạo được SEMANTIC TASK**.

### 2.2 Hệ quả

- Các skill không được nối với nhau đúng cách
- Planner (BFS) không tìm được đường đi từ trạng thái ban đầu đến goal predicate
- Curriculum chỉ tạo ra các task đơn giản, ngắn (1-2 bước), không có task dài hơi
- **Semantic Task không xuất hiện**

---

## 3. Giải pháp đã sử dụng

### 3.1 So sánh Embedding cho Pre-condition và Post-condition

Thay vì so sánh exact-match, chúng em chuyển sang sử dụng **embedding-based matching** thông qua `PredicateRegistry` và `PredicateOntology`:

#### Cơ chế hoạt động:

```
┌──────────────────────┐
│  Predicate mới       │
│  (do LLM tạo ra      │
│   từ quan sát        │
│   trước/sau skill)   │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  encoding thành      │
│  embedding vector    │
│  (dùng Embedder)     │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│  So sánh cosine similarity với các           │
│  predicate đã biết trong PredicateRegistry   │
│  • similarity_floor = 0.55 (ngưỡng tối thiểu)│
│  • top_k = 5 (lấy 5 ứng viên gần nhất)       │
│  • Chỉ so sánh nếu structurally_compatible   │
│    (cùng arity, argument types, scope,       │
│     persistence, không opposite names)       │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────┐
│  Nếu similarity đủ   │
│  cao → coi là        │
│  equivalent/entails  │
│  → dùng chung        │
│  predicate ID        │
└──────────────────────┘
```

#### Chi tiết kỹ thuật:

1. **`PredicateRegistry.nearest()`**: Khi có một predicate mới (do LLM extract từ trajectory), hàm `nearest()` sẽ:
   - Encode predicate thành vector embedding (dùng `Embedder.encode()`)
   - Tính cosine similarity với tất cả predicate đã biết trong registry
   - Chỉ giữ lại những predicate có similarity ≥ `similarity_floor` (0.55)
   - Chỉ so sánh những predicate structurally compatible (cùng số lượng và kiểu arguments, cùng scope, cùng persistence)
   - Lọc bỏ các cặp có tên trái ngược (vd: `empty` vs `nonempty`)

2. **`PredicateRegistry.entails()`**: Kiểm tra quan hệ ngữ nghĩa giữa hai predicate:
   - Nếu có quan hệ `equivalent` với confidence ≥ 0.90 → coi là giống nhau
   - Nếu có quan hệ `implies` với confidence ≥ 0.85 → predicate A kéo theo predicate B

3. **Ontology canonicalization**: Hệ thống tự động xây dựng ontology các predicate, học các quan hệ `equivalent`, `implies`, `implied_by` giữa chúng qua thời gian.

### 3.2 Lợi ích của Embedding matching

- **Không phụ thuộc vào tên chính xác**: `has_search_input`, `search_available`, `has_search_box` đều được nhận ra là cùng một khái niệm
- **Học được quan hệ ngữ nghĩa**: Hệ thống tự động phát hiện `results_shown` → `has_filter_or_sort` là có liên quan
- **Mở rộng được**: Khi thêm domain mới, LLM tạo ra predicate mới, hệ thống tự động map vào ontology hiện có

---

## 4. Kết quả

### 4.1 Kết quả chính: Operator Graph đúng → Semantic Task xuất hiện

Đây là hệ quả trực tiếp của việc chuyển sang embedding matching cho Pre-condition/Post-condition. Nhờ Operator Graph được tạo đúng, Curriculum đã sinh ra được Semantic Task – task phức hợp nhiều bước có ý nghĩa thực sự:

**Semantic Task được tạo:**

> *"Find a 1 TB portable SSD, sort the results by lowest price, open the cheapest suitable item, confirm that it is in stock, select the 1 TB option, add one unit to the cart, and report the cart subtotal."*

Task này dài **7 bước** (difficulty = 7), sử dụng 7 skill khác nhau được nối với nhau qua pre/post-condition:

```
submit_search_query → inspect_filter_sort → open_visible_item
    → read_visible_detail → activate_named_control
    → activate_state_change_control → inspect_record_status
```

Kết quả thực thi: **success**, final answer chính xác: *"The selected 1 TB portable SSD is in the cart with quantity 1; the cart subtotal is $79.99."*

### 4.2 Ý nghĩa đối với finetuning

- **Semantic Task xuất hiện** → dữ liệu training cho SLM có chất lượng cao hơn hẳn so với task đơn giản
- Task dài hơi (multi-step) giúp SLM học được cách lập kế hoạch và thực thi chuỗi hành động
- Training data đa dạng về độ khó (từ 1 đến 7+ bước) → SLM có khả năng generalizes tốt hơn

### 4.3 Kết quả phụ: Tỷ lệ task pass tăng đáng kể nhờ cải thiện Solver Agent

Bên cạnh kết quả chính ở trên, tỷ lệ task thực thi thành công cũng tăng đột phá. **Đây không phải là hệ quả của việc sửa embedding matching**, mà đến từ việc cải thiện **Solver Agent** (agent chịu trách nhiệm thực thi task) với hai cơ chế mới:

1. **Cơ chế Retry**: Khi một task thất bại, Solver Agent được phép thử lại nhiều lần thay vì dừng ngay.
2. **LLM-as-Judge**: Sau mỗi lần thất bại, một LLM judge phân tích lý do task làm sai và cung cấp feedback chi tiết cho các lần retry sau, giúp Solver Agent điều chỉnh chiến lược.

Nhờ hai cải tiến này, tỷ lệ pass đã tăng từ:
- **~46% (309/660)** ở các run trước
- Lên **82.8% (101/122)** ở Run 25

**Tổng quan Run 25:**

| Chỉ số | Giá trị |
|---|---|
| Run | `wa_shopping_run_25` |
| Thời gian | 1h 17m 17s |
| Domain | Shopping |
| Số nodes | 58 |
| Tổng số tasks | 122 |
| Số tasks pass | **101 / 122 = 82.8%** |
| API cost | 2.9usd (OpenAI GPT-4o) + 0.4usd (DeepSeek V4 Flash) |

**Chi tiết theo task family:**

| Task family | Run 25 |
|---|---|
| Search | 14/15 = **93.3%** |
| Feedback / read information | 21/24 = **87.5%** |
| Other navigation / information tasks | 31/34 = **91.2%** |
| Analysis | 23/24 = **95.8%** |
| State change | 10/22 = **45.5%** |

### 4.4 Kế hoạch tiếp theo

Do logic đã ổn định, hiện đang tiến hành **crawl dataset cho 3 domain song song**:

1. **Shopping** (WebArena)
2. **Reddit** (WebArena)
3. **Wiki** (WebArena)

Quá trình chạy có thể kéo dài do đang call API (GPT-4o, DeepSeek) khá nhiều để hỗ trợ tạo Semantic Task.

---

## 5. Các vấn đề phụ đã được giải quyết

### 5.1 Lý do finetuning tuần trước cho kết quả không tốt

Khi phân tích kỹ, nhóm đã xác định được các nguyên nhân khiến kết quả finetuning trước đó không đạt yêu cầu:

1. **Thought cho training data chưa tốt**: Phần suy luận (thought) trong trajectory không đủ chi tiết, không giúp SLM học được cách reasoning trước khi hành động.

2. **Grounding yếu với combobox/select controls**: Các action liên quan đến `combobox`, `select` dropdown thường bị sai BID (Browser ID) do UI động, dẫn đến SLM không thực thi được đúng action.

3. **BID thay đổi**: Browser ID của các element thay đổi giữa các lần load trang, khiến SLM dựa vào BID cũ không còn chính xác.

4. **Repeated labels**: Nhiều element có cùng label/text (vd: nhiều nút "Add to Cart"), SLM không phân biệt được nên chọn sai element.

Các vấn đề này đang được xử lý để đảm bảo dữ liệu training cho đợt finetuning tiếp theo có chất lượng tốt hơn.

---

## 6. Kết luận

Vấn đề Pre-condition / Post-condition matching – vốn em định nhờ thầy tham mưu – đã được giải quyết thành công bằng phương pháp **embedding-based similarity** thay vì exact-match hay hardcode. Kết quả cho thấy:

- ✅ Operator Graph được tạo đúng → Curriculum chính xác
- ✅ **Semantic Task đã xuất hiện** – minh chứng cho việc hệ thống có thể tự động tạo ra task phức hợp, có ý nghĩa
- ✅ Tỷ lệ task pass đạt **82.8%** (tăng từ ~46%) nhờ cải thiện Solver Agent (retry + LLM-as-Judge)
- ✅ Đang tiến hành crawl dataset trên 3 domain để chuẩn bị cho finetuning SLM

Em xin cảm ơn thầy đã quan tâm, và em rất mong nhận được góp ý từ thầy ạ.
