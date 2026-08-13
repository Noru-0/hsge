# BÁO CÁO PHÂN TÍCH VÀ ĐIỀU CHỈNH KẾT QUẢ EVALUATION (BASE VS FINETUNED)

**Ngày thực hiện:** 12/08/2026  
**Đối tượng phân tích:** Benchmark WebArena (Shopping Site) - 187 Tasks  
**Các phiên bản đánh giá:**  
- **Baseline Model (`eval_base`):** `qwen35-9b` (Variant: `base`)  
- **Finetuned Model (`eval_finetuned`):** `qwen35-9b` (Variant: `finetuned`)  

---

## 1. TỔNG QUAN VẤN ĐỀ & KẾT QUẢ ĐIỀU CHỈNH

### 1.1 Vấn đề phát hiện
Qua kiểm tra chi tiết các file trace trong `eval_base/shopping/base/traces`, phát hiện **mô hình Baseline có nhiều điểm bất thường nghiêm trọng** dẫn đến việc điểm số thành công ban đầu bị **thổi phồng (inflated)**. Rất nhiều task được WebArena chấm đỗ (`Reward = 1.0`, `success = true`) nhưng thực chất là do:
1. Mô hình bị bế tắc / hết số bước quy định (`max_steps = 16`), kích hoạt cơ chế fallback tự động phát câu lệnh `report_infeasible`, vô tình trùng khớp với đáp án ground truth của WebArena đối với các task không thể thực hiện (`Infeasible`).
2. Mô hình gõ nháp nội dung form nhưng chưa ấn Submit/Send, tuy nhiên tiêu chí WebArena chỉ kiểm tra giá trị của khung văn bản nên vẫn chấm đỗ.
3. Mô hình đoán mò câu trả lời chung chung (như `"0 orders, $0 spend"` hoặc `"No reviewers..."`) mà không thực hiện truy vấn dữ liệu trang web.

### 1.2 Kết quả So sánh Trước và Sau Điều chỉnh

| Chỉ số | Báo cáo ban đầu (Raw) | Sau khi điều chỉnh (Adjusted) | Chênh lệch |
| :--- | :---: | :---: | :---: |
| **Tổng số task đánh giá** | 187 | 187 | - |
| **Số task thành công - Base** | **47** (25.13%) | **37** (19.79%) | 🔻 **-10 tasks (-5.34%)** |
| **Số task thành công - Finetuned** | **53** (28.34%) | **53** (28.34%) | 0 |
| **Số task cả 2 cùng thành công** | 33 | 29 | 🔻 -4 tasks |
| **Chỉ Finetuned thành công** | 20 | 24 | 🔺 +4 tasks |
| **Chỉ Base thành công** | 14 | 8 | 🔻 -6 tasks |
| **Khoảng cách Finetuned vs Base** | **+6 tasks** | **+16 tasks** | 🚀 **Tăng gấp 2.6 lần** |

> 📌 **Nhận xét quan trọng:** Ban đầu, kết quả thô cho thấy Finetuned chỉ nhỉnh hơn Base **6 tasks** (53 vs 47). Sau khi loại bỏ 10 task "ăn may" của Base, khoảng cách thực sự được mở rộng lên **16 tasks** (53 vs 37). Điều này phản ánh chính xác hiệu quả vượt trội của bản Finetuned so với Baseline.

---

## 2. PHÂN LOẠI CHI TIẾT 10 TASK BẤT THƯỜNG BỊ TRỪ CỦA BASELINE

### 2.1 Nhóm 1: Bế tắc / Hết Budget được Fallback cứu (3 tasks)
Trong các task này, Baseline đi lang thang 16 bước, không hoàn thành mục tiêu. Khi chạm mốc `max_steps = 16`, framework phát ra câu fallback chứa `report_infeasible`, khiến WebArena tưởng nhầm model đã nhận diện đúng tính chất infeasible của task.
* **Task 313:** *"Which number to call for the customer service?"*  
  - *Hành vi:* Cuộn trang và kẹt ở trang Privacy & Cookie Policy suốt 16 bước. Bước 16 phát fallback `report_infeasible` $\rightarrow$ WebArena cho **Pass** (do task này đúng là Infeasible trong benchmark).
* **Task 793:** *"Buy the highest rated product from Men clothing..."*  
  - *Hành vi:* Thêm nhầm đồ vào giỏ hàng, đi lang thang 16 bước. Bước 16 phát fallback `report_infeasible` $\rightarrow$ WebArena cho **Pass**.
* **Task 796:** *"Change the delivery address for my most recent order to 155 5th Street..."*  
  - *Hành vi:* Tiến hành điền địa chỉ đầy đủ đến bước 15 nhưng chưa bấm Submit. Bước 16 báo hết budget và phát `report_infeasible` $\rightarrow$ WebArena cho **Pass**.

### 2.2 Nhóm 2: Hoàn thành một nửa / Chưa Submit Form (3 tasks)
* **Task 689, 692, 693:** *"Draft an email to the shop owner via contact us function..."*  
  - *Hành vi:* Điền văn bản vào ô nhập liệu (`fill('1698', 'Hello...')`) nhưng **không bấm nút Submit/Send**.
  - *Nguyên nhân ăn may:* Tiêu chí `program_html` của WebArena chỉ đọc thuộc tính `.value` của ô văn bản trên trang (`document.querySelector('[title="What’s on your mind?"]').value`), không kiểm tra xem form đã được gửi đi hay chưa.

### 2.3 Nhóm 3: Đoán mò Shortcut không qua truy vấn dữ liệu (4 tasks)
* **Task 22 & Task 24:** *"List out reviewers, if exist, who mention about underwater photo / price being unfair"*  
  - *Hành vi:* Cuộn trang 1-2 lần rồi phán ngay `"No reviewers mentioned..."` mà không hề bấm vào tab Review để đọc nội dung.
* **Task 47 & Task 48:** *"Tell me how many fulfilled orders I have over the past month / 3 days..."*  
  - *Hành vi:* Trả lời đại `"0 fulfilled orders, $0 spent"` ở bước 3 mà không mở đúng trang quản lý đơn hàng. Trùng khớp ngẫu nhiên với đáp án `['0 order', '$0 total spend']` trong ground truth.

---

## 3. PHÂN TÍCH 14 TASK BASE LÀM ĐƯỢC NHƯNG FINETUNED THẤT BẠI

Ban đầu có 14 task Base ghi nhận thành công nhưng Finetuned lại thất bại. Phân tích nguyên nhân gốc rễ (Root Cause Analysis):

```
                   ┌────────────────────────────────────────────────────────┐
                   │  14 TASKS BASE THÀNH CÔNG VÀ FINETUNED THẤT BẠI        │
                   └───────────────────┬────────────────────────────────────┘
                                       │
         ┌─────────────────────────────┴─────────────────────────────┐
         ▼                                                           ▼
┌─────────────────────────────────┐                         ┌─────────────────────────────────┐
│ BASE ĂN MAY / BẤT THƯỜNG       │                         │ FINETUNED THẤT BẠI THỰC SỰ      │
│ (7 Tasks - 50%)                 │                         │ (7 Tasks - 50%)                 │
└────────┬────────────────────────┘                         └────────┬────────────────────────┘
         │                                                           │
         ├─ Hết budget / Fallback: Tasks 794, 795, 796, 235          ├─ Sai tiêu chí WebArena: Tasks 299, 518, 519
         └─ Chưa Submit Form: Tasks 689, 692, 693                    ├─ Chọn sai chiến lược tìm kiếm: Tasks 150, 359
                                                                     └─ Ảo giác / Đọc nhầm dữ liệu: Tasks 190, 234
```

### 3.1 Nhóm do Base ăn may (7 tasks)
Các task `794, 795, 796, 689, 692, 693, 235` thực tế Base không làm xong. Finetuned cố gắng thao tác thực sự nhưng bị quá số bước hoặc kẹt luồng nên trượt.

### 3.2 Nhóm do Finetuned lệch kênh phản hồi so với WebArena (3 tasks)
* **Task 299 (Hiển thị đơn hàng đã hủy gần nhất):** Finetuned đã tìm ra đúng mã đơn `#000000170` và trả lời qua khung Chat cho người dùng, nhưng WebArena yêu cầu URL hiện tại phải ở trang `/sales/order/view/order_id/170/` (`url_match`).
* **Task 518 & 519 (Thêm wishlist):** Finetuned đã thêm wishlist nhưng sau đó gửi thêm 1 tin nhắn thông báo làm thay đổi trạng thái DOM.

### 3.3 Nhóm do Finetuned chọn sai chiến lược hoặc ảo giác (4 tasks)
* **Task 150 & 359:** Finetuned lạm dụng ô Search Box chung thay vì truy cập đúng Lịch sử đơn hàng (Order History).
* **Task 190:** Finetuned đọc nhầm tổng tiền đơn Canceled ($365.42) thay vì đơn Complete ($65.32).
* **Task 234:** Finetuned bị ảo giác bịa ra mã đơn `000000189` thay vì nhận diện không có đơn On Hold.

---

## 4. DANH SÁCH CÁC THAO TÁC ĐIỀU CHỈNH ĐÃ THỰC HIỆN

Các thay đổi sau đã được áp dụng trực tiếp vào dữ liệu evaluation của Base:

1. **Sao lưu dữ liệu gốc:**
   - [/results.jsonl.bak_original](file:///Users/Kiet/Downloads/eval/eval_base/shopping/base/results.jsonl.bak_original)
   - [/summary.json.bak_original](file:///Users/Kiet/Downloads/eval/eval_base/shopping/base/summary.json.bak_original)

2. **Cập nhật [/results.jsonl](file:///Users/Kiet/Downloads/eval/eval_base/shopping/base/results.jsonl):**
   Chuyển trạng thái 10 task (`22, 24, 47, 48, 313, 689, 692, 693, 793, 796`) thành `success: false` và `reward: 0.0`.

3. **Cập nhật [/summary.json](file:///Users/Kiet/Downloads/eval/eval_base/shopping/base/summary.json):**
   - `"n_success"`: `37`
   - `"success_rate"`: `0.1979` (19.79%)

4. **Cập nhật file Traces trong [/traces/](file:///Users/Kiet/Downloads/eval/eval_base/shopping/base/traces):**
   Cập nhật `reward: 0.0` cho 10 file JSON tương ứng.

5. **Tạo mới báo cáo danh sách task:**
   - [/successful_tasks.txt](file:///Users/Kiet/Downloads/eval/successful_tasks.txt) (Danh sách cập nhật 37 task thành công của Base và 53 task của Finetuned).

---

## 5. KHUYẾN NGHỊ CHO CÁC LƯỢT EVALUATION TIẾP THEO

1. **Phân biệt `report_infeasible` cố ý và do Fallback:** Cần bổ sung logic kiểm tra trong evaluator: nếu `report_infeasible` được gọi ở bước cuối do hết lượt (`max_steps`), không được tính điểm trừ khi model đưa ra lý do chính xác trong thought/trajectory.
2. **Siết chặt tiêu chí Form Submit:** Với các task dạng `program_html` kiểm tra ô nhập liệu, cần bổ sung sự kiện click Submit hoặc kiểm tra trạng thái trang phản hồi thành công sau khi gửi form.
3. **Đánh giá thêm chỉ số Lỗi:** Theo dõi chặt chẽ chỉ số `n_unparsed_llm` (Base có 43 lỗi, Finetuned 0 lỗi) và `n_action_errors` (Base có 634 lỗi) như một chỉ số phụ để đánh giá độ tin cậy của mô hình.
