# Kịch bản trình bày — Bảo vệ KLTN HSGE

**Thời lượng:** 15 phút trình bày + 15 phút hỏi đáp.
**Cấu trúc deck:** 26 trang nội dung (19 slide thuyết trình chính + 1 slide cảm ơn/Q&A + mục lục) và 8 slide phụ lục (chỉ mở khi Hội đồng hỏi sâu).
**Phân chia:** 
- **Người 1 (Slide 1–13):** Giới thiệu, Động lực, Phát biểu bài toán, Nghiên cứu liên quan, Phương pháp HSGE.
- **Người 2 (Slide 14–19):** Thiết lập thực nghiệm, Kết quả 3 Câu hỏi nghiên cứu (CH1, CH2, CH3), Kết luận & Hướng phát triển.
- **Điểm chuyển giao:** Sau Slide 13 (kết thúc phần Phương pháp, chuyển sang Thực nghiệm).

---

## Slide 1 — Bìa

Kính thưa Thầy Cô trong Hội đồng. Em là Trương Bảo Kiệt, cùng bạn Hồ Tiến Phát, xin phép được báo cáo khóa luận tốt nghiệp với đề tài: **“Khám phá theo đồ thị kỹ năng phân cấp để tự động sinh dữ liệu huấn luyện cho tác nhân trí tuệ nhân tạo trên web”**, dưới sự hướng dẫn của PGS.TS. Nguyễn Văn Vũ.

Bài trình bày của nhóm gồm sáu nội dung chính:
1. Động lực của khóa luận
2. Phát biểu bài toán và thách thức
3. Nghiên cứu liên quan và khoảng trống
4. Phương pháp đề xuất HSGE
5. Kết quả thực nghiệm và đánh giá
6. Kết luận và hướng phát triển

**Sau đây, em xin bắt đầu với động lực thúc đẩy nghiên cứu.**

---

## Slide 2 — Động lực của khóa luận

Kính thưa Hội đồng. Những năm gần đây, sự bùng nổ của các **Mô hình Ngôn ngữ Lớn (LLM)** đã tạo ra bước ngoặt lớn về năng lực hiểu ngôn ngữ và suy luận logic.

Dựa trên nền tảng đó, cộng đồng nghiên cứu đã phát triển các **tác nhân tự hành (LLM-based Agent)**, nổi bật nhất là **Web Agent** — có khả năng nhận chỉ thị bằng ngôn ngữ tự nhiên từ người dùng, tự động lập kế hoạch và tương tác với trình duyệt để hoàn thành các tác vụ thực tế.

Tuy nhiên, việc sử dụng LLM làm Web Agent bộc lộ những hạn chế rõ rệt:
- **Về mặt hiệu năng:** Đặt một LLM tổng quát vào một website cụ thể chưa từng thấy, mô hình lập tức lúng túng vì thiếu tri thức về cấu trúc và luồng nghiệp vụ của trang đích. Minh chứng là trên bộ chuẩn **WebArena**, trong khi **con người đạt 78,24%**, thì agent dùng **GPT-4 chỉ đạt 14,41%**.
- **Về mặt triển khai thực tế:** Việc liên tục gọi API các LLM thương mại lớn gặp phải ba rào cản nghiêm ngặt: **chi phí cộng dồn rất cao, độ trễ mạng lớn, và rủi ro rò rỉ dữ liệu riêng tư** khi phải gửi thông tin nội bộ ra máy chủ bên ngoài.

Để giải quyết triệt để các rào cản trên, hướng đi bền vững là sử dụng các **Mô hình Ngôn ngữ Nhỏ (SLM <10B) chạy cục bộ (on-premise)**: vừa bảo mật dữ liệu, vừa tiết kiệm chi phí và phản hồi nhanh. Thế nhưng, do giới hạn tham số, SLM lại càng không thể tự hiểu môi trường nếu không được huấn luyện $\rightarrow$ vì vậy, **fine-tune chuyên biệt hóa cho từng website là yêu cầu bắt buộc**.

Từ đó, nút thắt cốt lõi của bài toán dịch chuyển từ *kích thước mô hình* sang **dữ liệu huấn luyện**: *Lấy dữ liệu tương tác ở đâu để fine-tune SLM cho từng website cụ thể mà không tốn chi phí gán nhãn thủ công?*

---

## Slide 3 — Phát biểu bài toán và phạm vi

Từ động lực trên, nhóm xin phát biểu bài toán một cách chặt chẽ:

- **Về bài toán đặt ra:**
  - **Đầu vào:** Một website mục tiêu đang vận hành và **một LLM mạnh gọi qua API**, với **0 nhãn con người** và không có sẵn kịch bản mẫu.
  - **Mục tiêu:** Mượn năng lực của LLM để tự động khám phá website và tổng hợp dữ liệu huấn luyện chất lượng cao cho SLM.
  - **Đầu ra:** Một tập dữ liệu SFT sạch cùng một mô hình **SLM <10B chuyên biệt** cho chính website đó.

- **Về phạm vi & ứng dụng đích:**
  - Mỗi website sẽ tạo ra một tác nhân chuyên biệt chạy **tại chỗ (on-premise)** nhằm bảo mật dữ liệu.
  - Ngân sách gọi API phục vụ khám phá được giới hạn ở mức **nhóm nghiên cứu nhỏ**.
  - Khóa luận hướng đến việc **tổng quát hóa ở mức pipeline (quy trình)** chứ không tạo ra một mô hình đơn lẻ dùng chung cho mọi website.
  - Việc huấn luyện giới hạn ở **SFT/LoRA**, không dùng học tăng cường.

- **Định hướng giải pháp:** Dùng **LLM mạnh** tự động khám phá chính website mục tiêu, sinh trajectory để fine-tune **SLM cục bộ**.

---

## Slide 4 — Dữ liệu huấn luyện SLM: lấy từ đâu và có dạng gì?

Trước khi nói về thách thức, em xin làm rõ hai điều mà toàn bộ khóa luận xoay quanh: **dữ liệu huấn luyện được lấy từ đâu**, và **nó có hình dạng cụ thể như thế nào**.

- **Về nguồn dữ liệu:** Nhóm **mượn năng lực của LLM mạnh** để đóng vai người tạo dữ liệu. LLM được gọi qua API sẽ tự khám phá và tự thao tác trên **chính website mục tiêu**. Mỗi lần LLM giải xong một tác vụ, hệ thống thu được **một trajectory** — tức là chuỗi xen kẽ giữa *quan sát trạng thái trang* và *hành động* mà nó đã thực hiện. Toàn bộ các trajectory này được **chưng cất (distill)** thành tập dữ liệu SFT để dạy lại cho SLM. Điểm quan trọng về mặt kinh tế: chi phí API chỉ phải trả **một lần duy nhất trong giai đoạn tạo dữ liệu**; khi triển khai thực tế, hệ thống chỉ còn chạy SLM cục bộ, không gọi API nữa.

- **Về dạng dữ liệu:** Mỗi **bước tương tác** trở thành **một mẫu SFT** theo đúng định dạng hội thoại:
  - **System:** khai báo tập hành động cho phép và định dạng đầu ra JSON.
  - **User:** mục tiêu của tác vụ, trang hiện tại (URL và cây khả truy cập **AXTree**), lỗi của hành động liền trước, và lịch sử các hành động đã làm.
  - **Assistant:** đúng một hành động kế tiếp kèm suy luận, dạng `{"thought": ..., "action": "click('12')"}`.
  
  Như vậy một trajectory sẽ sinh ra nhiều mẫu nối tiếp nhau, và prompt lúc huấn luyện được giữ **khớp hoàn toàn** với prompt lúc suy luận.

**Nói ngắn gọn:** LLM đóng vai *làm mẫu* cách thao tác trên website, còn SLM học **bài toán chọn hành động kế tiếp** từ trạng thái trang hiện tại.

---

## Slide 5 — Bốn thách thức cốt lõi của bài toán

Để hiện thực hóa định hướng trên mà không cần con người can thiệp, hệ thống phải đối mặt với **bốn thách thức cốt lõi (T1 đến T4)**:

1. **T1 — Thu thập dữ liệu chất lượng cao:** Dữ liệu do agent tự do khám phá rất dễ bị **lặp lại, vô nghĩa hoặc không hợp lệ**. Thách thức là làm sao tự sinh được các mẫu vừa hợp lệ về mặt kỹ thuật, vừa phong phú, đa dạng cho quá trình SFT.
2. **T2 — Thiếu tri thức về môi trường:** Việc lấy tri thức từ tài liệu ngoài Internet dễ bị **lệch môi trường** (chỉ đạt 6% so với 16% khi học trực tiếp). Do đó, agent bắt buộc phải **tự động khám phá và tích lũy tri thức trực tiếp trên website thật**.
3. **T3 — Sàng lọc trajectory tự sinh:** Khi không có con người giám sát, agent vừa thực hiện vừa tự chấm điểm nên rất dễ bị **dương tính giả (tự nhận hoàn thành khi chưa xong)**. Dữ liệu sai này sẽ dạy cho mô hình hành vi gian dối, vì vậy cần cơ chế sàng lọc bằng **tín hiệu khách quan**.
4. **T4 — Tạo tác vụ có ngữ nghĩa:** Các tác vụ tự sinh đơn lẻ thường chỉ dừng lại ở thao tác 1 trang. Trong khi đó, nghiệp vụ thực tế đòi hỏi chuỗi hành động dài qua nhiều trang, đòi hỏi hệ thống phải có khả năng **tự động ghép chuỗi thành tác vụ đa bước có ngữ nghĩa**.

---

## Slide 6 — Ba hướng tiếp cận hiện nay

Cộng đồng nghiên cứu hiện nay đã tiếp cận bài toán theo ba hướng chính:

1. **Hướng (A) — Tri thức từ Internet (như Synatra, AgentTrek):** Sử dụng video, tài liệu hướng dẫn trên mạng để tổng hợp trajectory. Hạn chế là dữ liệu dễ bị lệch so với website thực tế và không áp dụng được cho hệ thống nội bộ.
2. **Hướng (B) — Skill dùng lúc suy luận (như AWM, SkillWeaver, ASI):** Trích xuất các workflow lặp lại rồi nhồi vào context prompt cho LLM lớn. Hướng này giúp tăng hiệu năng nhưng **không cập nhật trọng số cho mô hình nhỏ (SLM)**.
3. **Hướng (C) — Tự sinh từ môi trường (như NNetNav, Go-Browse):** Cho agent tự tương tác trên website thật để lấy dữ liệu train SLM. Tiêu biểu là **Go-Browse** đạt 21,7% (SOTA phân khúc <10B) nhờ mô hình hóa khám phá bằng tìm kiếm trên đồ thị.

Trong 3 hướng, **hướng (C) là hướng tiếp cận gần với mục tiêu khóa luận nhất** và được nhóm chọn làm mốc so sánh chính.

---

## Slide 7 — Hạn chế và khoảng trống nghiên cứu

Đối chiếu lại 3 hướng tiếp cận với 4 thách thức T1–T4:

- **Hạn chế của hướng (A) & (B):** Hướng (A) vướng **T1, T2** do phụ thuộc tài liệu ngoài. Hướng (B) chỉ nạp prompt cho LLM lớn, không giải quyết bài toán train SLM cục bộ.
- **Hạn chế của hướng (C):** Go-Browse có đồ thị nhưng **chỉ dừng ở 1 tầng (State Graph)**, các task đề xuất bị bó hẹp trong từng trang riêng lẻ $\rightarrow$ vướng **T4**. Đồng thời, cả (B) và (C) vẫn tin vào lời tự khai của agent $\rightarrow$ vấn đề dương tính giả **T3** vẫn còn nguyên.

- **Khoảng trống nghiên cứu:** Chưa có công trình nào kết nối trọn vẹn chu trình 3 mắt xích:
  $$\text{Khám phá} \longrightarrow \text{Kiểm chứng / Ghép chuỗi} \longrightarrow \text{Huấn luyện SLM}$$

- **Câu hỏi nghiên cứu của khóa luận:**
  *Làm thế nào để tự động sinh dữ liệu huấn luyện ngay trên website mục tiêu với **0 nhãn con người**, giúp một **SLM cục bộ đạt hiệu năng tiệm cận hoặc vượt LLM lớn** trên chính các trang đó?*

---

## Slide 8 — Giải pháp HSGE và các đóng góp chính

Để lấp đầy khoảng trống nghiên cứu trên, khóa luận đề xuất phương pháp **HSGE (Hierarchical Skill-Graph Exploration)** với các đóng góp trọng tâm:

- **Về mặt Khoa học:**
  - Đề xuất mô hình **Đồ thị hai tầng**: kết hợp State Graph (tầng thấp) và Operator Graph (tầng cao) để giải quyết **T2**.
  - Cơ chế **Quy nạp operator & Ghép chuỗi đa bước**: tự động chuyển đổi skill thành tác vụ nghiệp vụ dài hạn nhằm giải quyết **T4**.
  - Cơ chế **Kiểm định trực tuyến (Online Gates)**: loại bỏ triệt để dương tính giả ngay trong vòng lặp khám phá để giải quyết **T3**.

- **Về mặt Thực tiễn:**
  - Xây dựng bộ dataset SFT sạch gồm **9.007 mẫu trên 4 website** hoàn toàn không cần nhãn người (**T1**).
  - Huấn luyện mô hình **HSGE-9B đạt 24,6% Task Success Rate**, vượt GPT-4o-mini và đạt SOTA phân khúc <10B.
  - Tối ưu chi phí API xuống mức **0,0308 USD/trajectory** (rẻ hơn 3,3 lần so với Go-Browse).

---

## Slide 9 — Tổng quan pipeline HSGE

Toàn bộ phương pháp HSGE vận hành như một quy trình tự động hóa khép kín:

1. **Frontier:** Duy trì hàng đợi các trang web đã phát hiện để điều phối agent đi khám phá.
2. **Explorer & Solver:** Thực hiện tương tác trực tiếp trên trình duyệt thật (Playwright/Chromium) để thu thập các trajectory thô.
3. **Skill Discovery & Operator Induction:** Cắt nhỏ trajectory, gom cụm, trừu tượng hóa và quy nạp thành các **Operator** có Precondition và Effect tường minh.
4. **Semantic Task Generation:** Ghép chuỗi các operator để sinh ra các tác vụ đa bước có ngữ nghĩa nghiệp vụ.
5. **Online Curation & SFT Packaging:** Dữ liệu được lọc trực tuyến qua 2 cổng chất lượng trước khi đóng gói chuẩn xác thành tập huấn luyện SFT.

Các trang web mới phát hiện lại được quay vòng nạp vào Frontier, tạo thành một vòng lặp liên tục mở rộng tri thức.

---

## Slide 10 — Đồ thị hai tầng

Cốt lõi biểu diễn tri thức của HSGE là **cấu trúc đồ thị hai tầng**:

- **Tầng thấp — State Graph:** Lưu vết duyệt web thực tế, với node là trạng thái trang DOM/URL và cạnh là các hành động điều hướng.
- **Tầng cao — Operator Graph:** Mỗi node là một Operator đại diện cho một kỹ năng chuẩn hóa gồm **Điều kiện đầu vào (Precondition)** và **Kết quả đạt được (Effect)**.

**Nguyên lý ghép nối:** Khi Effect của Operator A thỏa mãn Precondition của Operator B ($\text{Effect}_A \models \text{Pre}_B$), hệ thống tự động tạo một cạnh chuyển tiếp.
*Ví dụ:* Kỹ năng "Tìm kiếm sản phẩm" sinh ra kết quả "Đang ở trang chi tiết". Kết quả này thỏa mãn điều kiện cần của kỹ năng "Thêm vào giỏ hàng" $\rightarrow$ Hệ thống tự động ghép thành tác vụ mua hàng hoàn chỉnh.

Nhờ đó, tri thức thu được mang tính **tái sử dụng và tái tổ hợp** vượt bậc.

---

## Slide 11 — Phát hiện skill và quy nạp operator

Khâu quy nạp tri thức chỉ thực hiện trên các trajectory đã chạy thành công, qua 4 bước:

1. **Phân cắt (Segmentation):** Cắt chuỗi hành động dựa trên sự thay đổi URL và độ biến động cây trợ năng (AXTree).
2. **Gom cụm (Clustering):** Gom cụm phi tham số dựa trên độ tương đồng ngữ nghĩa.
3. **Trừu tượng hóa (Abstraction):** Rút trích thành thẻ kỹ năng (SkillCard) có tham số hóa.
4. **Kiểm chứng (Verification):** Chạy thử nghiệm lại skill trong ngữ cảnh mới để xác thực tính ổn định.

Để nâng cấp Skill thành Operator, hệ thống áp dụng 2 cổng chặn nghiêm ngặt:
- **Cổng chống trùng lặp:** Loại bỏ các effect lặp lại precondition vô nghĩa.
- **Cổng Grounding:** Gỡ bỏ các effect sai trên $\ge 50\%$ số lần chạy.

Kết quả: từ **146 skill** phát hiện được, hệ thống tinh lọc thành **57 operator** thực sự chuẩn xác và đáng tin cậy.

---

## Slide 12 — Sinh Semantic Task từ chuỗi Operator

Để tạo ra các tác vụ dài hạn có ý nghĩa nghiệp vụ, HSGE kết hợp 2 cơ chế:

- **Bottom-up (Từ dưới lên):** Duyệt đồ thị Operator Graph bằng thuật toán tìm kiếm, tự động ghép các chuỗi $\ge 2$ operator thành một nhiệm vụ hoàn chỉnh kèm câu lệnh ngôn ngữ tự nhiên.
- **Top-down (Từ trên xuống):** Khởi tạo nhiệm vụ từ các chức năng hạt giống (seed) tổng quan của website khi đồ thị còn thưa.

**Kết quả thực thi:** Hệ thống sinh ra **142 tác vụ có ngữ nghĩa** (130 từ seed + 12 từ ghép chuỗi), đạt **71 tác vụ thành công** (tỷ lệ 50,0%). Kết quả này chứng minh cơ chế ghép chuỗi operator hoạt động hoàn toàn đúng thiết kế và khả thi trong thực tế.

---

## Slide 13 — Kiểm định trực tuyến & Đóng gói SFT

*(Điểm chuyển giao người trình bày)*

Nguyên tắc chất lượng của HSGE: **Tuyệt đối không tin vào lời tự khai của agent.**

Hệ thống thiết lập 2 cổng kiểm soát trực tuyến (Online Gates) ngay trong quá trình thu thập:
1. **Online LLM Judge:** Mỗi khi agent tuyên bố xong, LLM Judge độc lập lập tức thẩm định lại trên trạng thái DOM thực tế, loại bỏ ngay **801 lượt (27,4%)** dương tính giả từ nguồn.
2. **Effective Action Gate:** Kiểm tra bằng mã để loại bỏ các trường hợp agent báo xong nhưng trang web không hề có thay đổi trạng thái DOM (loại 104 trajectory).

Nhờ dữ liệu đã sạch từ gốc, hệ thống tiến hành **Build trực tiếp** thành **9.007 mẫu SFT** (8.554 train / 453 validation) mà không cần lọc hậu kỳ. Quá trình đóng gói đảm bảo nghiêm ngặt nguyên tắc **Prompt Parity** (khớp từng byte giữa lúc train và lúc suy luận) và **0 trùng lặp mục tiêu** giữa train và validation.

---

## Slide 14 — Thiết lập & Câu hỏi nghiên cứu

*(Người thứ 2 bắt đầu phần Thực nghiệm)*

Kính thưa Hội đồng, để đánh giá toàn diện hiệu quả của HSGE, phần thực nghiệm tập trung giải đáp **3 câu hỏi nghiên cứu cốt lõi**:
- **CH1:** Hệ thống có tự động sinh ra các tác vụ có ý nghĩa và quy mô dữ liệu chất lượng hay không?
- **CH2:** Năng lực của SLM sau khi fine-tune được cải thiện thế nào so với mô hình nền và các SOTA?
- **CH3:** Quá trình tự động sinh dữ liệu đạt hiệu quả chi phí kinh tế ra sao?

**Thiết lập thực nghiệm:**
- **Môi trường & Benchmark:** 655 tác vụ chính thức trên 4 website tự triển khai (self-hosted) của **WebArena** (Shopping, Shopping Admin, GitLab, Reddit).
- **Mô hình & Huấn luyện:** Mô hình nền **Qwen3.5-9B-Instruct** được tinh chỉnh bằng LoRA qua 3 epoch để tạo ra **HSGE-9B**.
- **Đánh giá:** Sử dụng bộ chấm Task Success Rate (SR) chính thức của WebArena với cùng prompt và cùng ngân sách bước.

---

## Slide 15 — CH1: Tự động tạo tác vụ & Quy mô dữ liệu

Để trả lời **CH1**, Bảng 1 tổng hợp toàn bộ quy mô dữ liệu tự sinh của HSGE:

- **Quy mô khám phá:** Hệ thống duyệt qua **4 website, 455 URL**, thực hiện **3.981 lượt tương tác thử**.
- **Tri thức tích lũy:** Tự động thu hoạch **146 skill**, quy nạp thành **57 operator**, và sinh thành công **142 semantic task**.
- **Hiệu quả cổng lọc:** LLM Judge loại bỏ **801 lượt (27,4%)** dương tính giả và Effective Action Gate loại **104 trajectory** không đổi trạng thái.
- **Thu hoạch SFT:** Thu được **1.760 trajectory sạch** (tỷ lệ hợp lệ 53,2%), đóng gói thành **9.007 mẫu SFT** hoàn chỉnh.

**Kết luận CH1:** HSGE tự động sinh tác vụ có ý nghĩa và thu hoạch 9.007 mẫu SFT sạch hoàn toàn không cần nhãn con người.

---

## Slide 16 — CH2: So sánh hiệu năng với các hệ thống SOTA

Để trả lời **CH2**, Bảng 2 so sánh hiệu năng của HSGE với các mô hình thương mại và mô hình mã nguồn mở:

- **Hiệu năng tổng thể:** HSGE-9B đạt **24,6% Task SR** trên toàn bộ 655 task của WebArena, tăng **+11,3 điểm phần trăm** so với mức 13,3% của mô hình nền Qwen3.5-9B.
- **Vượt mô hình thương mại:** Kết quả 24,6% của HSGE-9B vượt qua mô hình đóng **GPT-4o-mini (20,0%)**.
- **Vượt trội phân khúc <10B:** HSGE-9B vượt xa Qwen-2.5-7B-Instruct (8,3%) và NNetNav-7B (19,1%), đồng thời đạt mức **tương đương SOTA Go-Browse-7B (22,6%)**.
- **Khả năng chuyển giao dữ liệu:** Dùng tập dữ liệu HSGE để fine-tune mô hình **Qwen-2.5-7B** giúp nâng hiệu năng từ **8,3% lên 16,5%** (tăng gần gấp đôi), chứng minh giá trị độc lập của bộ dữ liệu tự sinh.

---

## Slide 17 — CH2: So sánh Base và Fine-tuning theo Website

Bóc tách sâu hơn về sự cải thiện trong CH2 qua Bảng 3:

- **Tăng trưởng toàn diện:** Cả 4 website đều ghi nhận mức tăng trưởng vượt bậc có ý nghĩa thống kê rất cao theo kiểm định McNemar ($p < 0,011$), tiêu biểu như Reddit tăng từ 6,6% lên **34,0%** ($p < 0,001$).
- **Kỷ luật cú pháp:** Lỗi định dạng lệnh giảm triệt để từ **26,0% xuống chỉ còn 0,6%**.
- **Nâng cao năng lực ra quyết định:** Ngay cả trên tập 485 task mà mô hình gốc vốn đã xuất đúng cú pháp, tỷ lệ thành công sau fine-tune vẫn tiếp tục tăng từ **17,9% lên 23,5%** ($p = 0,003$), đồng thời giải thành công thêm **100 task độc quyền** mà mô hình nền bất lực.
- **Mở rộng dữ liệu Pha 2:** Bổ sung dữ liệu chuyên biệt ở Pha 2 giúp Reddit tăng từ 20,8% lên 34,0% và Shopping Admin tăng từ 15,4% lên 21,4%.

**Kết luận CH2:** Fine-tuning giúp SLM làm chủ cả kỷ luật cú pháp lẫn năng lực ra quyết định, và việc mở rộng dữ liệu giúp liên tục nâng cao mức trần hiệu năng.

---

## Slide 18 — CH3: Hiệu quả chi phí trong tự động tạo dữ liệu

Trả lời **CH3** về tính khả thi kinh tế:

- **Chiến lược định tuyến mô hình:** HSGE tối ưu chi phí bằng cách phân bổ mô hình theo vai trò: dùng mô hình thị giác GPT-5.6-luna cho Explorer/Solver, GPT-5.6-terra cho Goal Solver, và DeepSeek-chat cho Evaluator/Judge.
- **Tổng chi phí:** Toàn bộ quá trình khám phá trên 4 website chỉ tiêu tốn **54,21 USD** (chưa tới 14 USD cho mỗi website).
- **Đơn giá trên mẫu thành công:** Chi phí chỉ **0,0308 USD cho mỗi trajectory sạch**, giảm tiêu hao token khoảng 12 lần.
- **So sánh với SOTA:** So với mức 0,1026 USD/trajectory của Go-Browse-7B, HSGE **rẻ hơn 3,3 lần**.

**Kết luận CH3:** Chi phí 0,0308 USD/trajectory chứng minh tính khả thi cao về mặt kỹ thuật và tài nguyên cho các nhóm nghiên cứu và tổ chức nhỏ.

---

## Slide 19 — Kết luận: Đóng góp chính & Hướng phát triển

Tổng kết lại, khóa luận mang lại 3 giá trị cốt lõi:

1. **Về Khoa học:** Đề xuất kiến trúc đồ thị 2 tầng (State Graph $\leftrightarrow$ Operator Graph), thuật toán phát hiện skill, quy nạp operator và cơ chế ghép chuỗi semantic task.
2. **Về Thực tiễn:** Xây dựng pipeline tự động hóa hoàn chỉnh, sinh **9.007 mẫu SFT sạch**, huấn luyện **HSGE-9B đạt 24,6% Task SR** với chi phí **rẻ hơn 3,3 lần** so với Go-Browse.
3. **Về Tài nguyên mở:** Công khai toàn bộ mã nguồn pipeline, bộ dataset SFT và trọng số mô hình HSGE-9B.

**Bốn hướng phát triển tiếp theo:**
- **Khôi phục lỗi tự động:** Tự sửa lỗi và thử lại khi gặp sự cố giao diện (timeout, kẹt DOM).
- **Tối ưu khám phá với RL:** Áp dụng Học tăng cường giúp Explorer tự học chiến lược duyệt web tối ưu.
- **Học từ thất bại:** Tận dụng các trajectory lỗi thông qua DPO hoặc Preference Learning.
- **Tổng quát hóa ngoài miền:** Mở rộng pipeline sang các website phức tạp hơn ngoài WebArena.

Em xin chân thành cảm ơn Quý Thầy Cô trong Hội đồng đã chú ý lắng nghe. Nhóm chúng em rất mong nhận được những câu hỏi và ý kiến đóng góp quý báu từ Hội đồng!
