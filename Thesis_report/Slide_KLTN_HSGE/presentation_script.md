# Kịch bản trình bày — Bảo vệ KLTN HSGE

**Thời lượng:** 15 phút trình bày + 15 phút hỏi đáp.
**Cấu trúc deck:** 25 trang nội dung (18 slide thuyết trình chính + 1 slide cảm ơn/Q&A + mục lục) và 8 slide phụ lục (chỉ mở khi Hội đồng hỏi sâu).
**Phân chia:**
- **Người 1 (Slide 1–12):** Giới thiệu, Động lực, Phát biểu bài toán, Nghiên cứu liên quan, Phương pháp HSGE.
- **Người 2 (Slide 13–18):** Thiết lập thực nghiệm, Kết quả 3 Câu hỏi nghiên cứu (CH1, CH2, CH3), Kết luận & Hướng phát triển.
- **Điểm chuyển giao:** Sau Slide 12 (kết thúc phần Phương pháp, chuyển sang Thực nghiệm).

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

Kính thưa Hội đồng. Khóa luận của nhóm bắt nguồn từ **định hướng nghiên cứu** mà thầy hướng dẫn đặt ra: xây dựng một tác nhân có thể tự thực hiện các tác vụ trên web, hướng tới những ứng dụng thiết thực như tự động hóa quy trình nghiệp vụ và kiểm thử phần mềm.

Đây cũng là hướng đi đang được cộng đồng đặc biệt quan tâm. Những năm gần đây, sự bùng nổ của các Mô hình Ngôn ngữ Lớn (LLM) đã tạo ra bước ngoặt lớn về năng lực hiểu ngôn ngữ và suy luận logic.

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

## Slide 4 — Dữ liệu huấn luyện SLM lấy từ đâu?

Trước khi nói về thách thức, em xin làm rõ **dữ liệu huấn luyện đến từ đâu**.

Nhóm sử dụng kỹ thuật **chưng cất tri thức (knowledge distillation)**, trong đó **LLM mạnh đóng vai người thầy**: nó được gọi qua API để tự khám phá và tự thao tác trên **chính website mục tiêu**. Mỗi lần thầy giải xong một tác vụ, hệ thống thu được **một trajectory** — chính là *lời giải mẫu* cho tác vụ đó. Toàn bộ các lời giải mẫu này được đóng gói thành tập dữ liệu SFT, và **SLM học bắt chước** chúng qua fine-tune.

Cách làm này hợp lý ở ba điểm:
- **Về chi phí:** phí API chỉ trả **một lần duy nhất** trong giai đoạn tạo dữ liệu; khi triển khai thực tế, hệ thống chỉ còn chạy SLM cục bộ, không gọi API nữa.
- **Về nhãn:** người thầy tự ra **cả đề lẫn lời giải**, nên toàn bộ quy trình **không cần một nhãn con người nào**.
- **Về độ phù hợp:** tri thức chưng cất được gắn với **đúng giao diện và luồng nghiệp vụ** của website mục tiêu, chứ không phải kiến thức chung chung từ Internet.

**Nói ngắn gọn:** LLM *làm mẫu* cách thao tác, còn SLM học **bài toán chọn hành động kế tiếp** từ trạng thái trang hiện tại.

*(Nếu Hội đồng hỏi một mẫu SFT trông cụ thể ra sao — System/User/Assistant, prompt parity — mở **PL11**.)*

---

## Slide 5 — Ba hướng tiếp cận hiện nay

Cộng đồng nghiên cứu hiện nay đã tiếp cận bài toán theo ba hướng chính:

1. **Hướng (A) — Tri thức từ Internet (như Synatra, AgentTrek):** Sử dụng video, tài liệu hướng dẫn trên mạng để tổng hợp trajectory. Hạn chế là dữ liệu dễ bị lệch so với website thực tế và không áp dụng được cho hệ thống nội bộ.
2. **Hướng (B) — Skill dùng lúc suy luận (như AWM, SkillWeaver, ASI):** Trích xuất các workflow lặp lại rồi nhồi vào context prompt cho LLM lớn. Hướng này giúp tăng hiệu năng nhưng **không cập nhật trọng số cho mô hình nhỏ (SLM)**.
3. **Hướng (C) — Tự sinh từ môi trường (như NNetNav, Go-Browse):** Cho agent tự tương tác trên website thật để lấy dữ liệu train SLM. Tiêu biểu là **Go-Browse** đạt 21,7% (SOTA phân khúc <10B) nhờ mô hình hóa khám phá bằng tìm kiếm trên đồ thị.

Trong 3 hướng, **hướng (C) là hướng tiếp cận gần với mục tiêu khóa luận nhất** và được nhóm chọn làm mốc so sánh chính.

---

## Slide 6 — Hạn chế và khoảng trống nghiên cứu

Đối chiếu ba hướng vừa nêu, mỗi hướng đều còn một khoảng hở so với bài toán của khóa luận:

- **Hướng (A)** dựa vào tài liệu ngoài nên **lệch môi trường thật** và không tự chủ trong việc thu thập dữ liệu.
- **Hướng (B)** chỉ nạp workflow vào prompt của LLM lớn, **không cập nhật trọng số** nên không dùng được cho SLM cục bộ, và vẫn tin vào lời tự khai của agent.
- **Hướng (C)** gần bài toán nhất vì tự khám phá web thật, nhưng đồ thị chỉ **một tầng** nên tác vụ **bó trong từng trang**, và cũng chấm điểm bằng **lời tự khai** của chính agent.

**Khoảng trống nghiên cứu:** Chưa có công trình nào nối trọn ba mắt xích:
$$\text{Khám phá} \longrightarrow \text{Kiểm chứng / Ghép chuỗi} \longrightarrow \text{Huấn luyện SLM}$$

Đó chính là chỗ HSGE đứng vào, và các khoảng hở này sẽ được lấp lần lượt trong phần phương pháp sau đây.

---

## Slide 7 — Giải pháp HSGE và các đóng góp chính

Để lấp đầy khoảng trống nghiên cứu trên, khóa luận đề xuất phương pháp **HSGE (Hierarchical Skill-Graph Exploration)** với các đóng góp trọng tâm:

- **Về mặt Khoa học:**
  - Đề xuất mô hình **Đồ thị hai tầng**: kết hợp State Graph (tầng thấp) và Operator Graph (tầng cao) để tích lũy tri thức ngay trên website thật.
  - Cơ chế **Quy nạp operator & Ghép chuỗi đa bước**: tự động chuyển đổi skill thành tác vụ nghiệp vụ dài hạn, thay vì chỉ thao tác trong một trang.
  - Cơ chế **Kiểm định trực tuyến (Online Gates)**: loại bỏ dương tính giả ngay trong vòng lặp khám phá, không tin vào lời tự khai của agent.

- **Về mặt Thực tiễn:**
  - Xây dựng bộ dataset SFT sạch gồm **9.007 mẫu trên 4 website**, hoàn toàn không cần nhãn người.
  - Huấn luyện mô hình **HSGE-9B đạt 24,6% Task Success Rate**, vượt GPT-4o-mini và đạt SOTA phân khúc <10B.
  - Tối ưu chi phí API xuống mức **0,0308 USD/trajectory** (rẻ hơn 3,3 lần so với Go-Browse).

---

## Slide 8 — Tổng quan pipeline HSGE

Toàn bộ phương pháp vận hành như **một vòng lặp khép kín, lặp trên từng trang web**. Em xin mô tả **một vòng** diễn ra cụ thể như thế nào.

**Bước 1 — Chọn trang để khám phá.** Hệ thống duy trì một **Frontier** — hàng đợi ưu tiên các URL đã biết, khởi đầu chỉ có trang chủ của website. Mỗi vòng, agent lấy ra một URL và mở nó bằng **trình duyệt thật** (Playwright/Chromium); trạng thái trang được đọc dưới dạng **cây khả truy cập AXTree**, tức danh sách các phần tử kèm mã định danh mà agent có thể thao tác.

**Bước 2 — Sinh tác vụ ngay tại trang đó.** **Explorer** nhìn vào đúng trang đang mở và đề xuất tối đa **9 tác vụ cụ thể**, mỗi tác vụ được phân loại **INFO** (tra cứu thông tin), **NAV** (điều hướng) hoặc **MOD** (làm thay đổi trạng thái). Vì tác vụ sinh ra *từ chính giao diện đang thấy*, nó luôn khả thi trên website này — đây là điểm khác căn bản so với việc lấy kịch bản từ tài liệu ngoài.

**Bước 3 — Giải từng tác vụ và ghi lại vết.** **Solver** hoạt động theo cơ chế **ReAct**: mỗi bước nó nhận mục tiêu, AXTree hiện tại, lỗi của hành động trước và lịch sử, rồi sinh ra một cặp *suy luận + hành động* như `click`, `fill`, `goto`; hành động được thực thi thật trên trình duyệt và trang mới lại quay về làm đầu vào cho bước kế tiếp. Ngân sách **15 bước** cho tác vụ thường và **25 bước** cho tác vụ đa bước; hệ thống tự cắt sớm nếu agent lặp lại một thao tác vô ích. Chuỗi các bước này chính là **một trajectory**.

**Bước 4 — Kiểm chứng ngay lúc chạy, rồi mở rộng Frontier.** Mỗi tác vụ agent tự nhận là xong đều bị **LLM Judge soi lại trang đích** — không đạt thì bị hạ thành thất bại và **không** được đưa vào dữ liệu. Tác vụ đạt sẽ được **giải lại lần hai từ trang chủ**, để trajectory chứa cả phần điều hướng tới trang chứ không chỉ thao tác cuối. Sau đó, Frontier được nạp thêm: **những URL agent thực sự đã đi qua** khi giải tác vụ, cộng với **các liên kết khai thác trực tiếp trên trang**; mỗi *dạng URL* chỉ nhận tối đa 3 trang để hàng chục nghìn trang chi tiết cùng khuôn không làm ngập hàng đợi. Vòng lặp quay lại Bước 1 với trang tiếp theo.

**Bước 5 — Tích lũy tri thức và nâng cấp độ khó.** Song song, các trajectory thành công được **cắt đoạn, gom cụm**; một đoạn thao tác lặp lại đủ số lần sẽ được **trừu tượng hóa thành SkillCard**, rồi **quy nạp thành Operator** có tiền điều kiện và hiệu ứng tường minh. Khi hiệu ứng của operator này khớp tiền điều kiện của operator kia, hệ thống **ghép chuỗi** chúng thành **tác vụ đa bước có ngữ nghĩa** — thứ mà bước sinh tác vụ tại chỗ ở Bước 2 không bao giờ tạo ra được. Đây chính là đường phản hồi nét đứt trong hình: **đồ thị operator định hướng cho vòng khám phá tiếp theo**.

**Kết quả của vòng lặp này** trên 4 website: **455 trang** được khám phá, **3.981 lượt thử**, đọng lại **146 skill** và **57 operator**, **142 tác vụ đa bước**, và cuối cùng là **1.760 trajectory sạch** được đóng gói thành **9.007 mẫu SFT** — hoàn toàn không có nhãn con người ở bất kỳ khâu nào.

---

## Slide 9 — Đồ thị hai tầng

Cốt lõi biểu diễn tri thức của HSGE là **cấu trúc đồ thị hai tầng**:

- **Tầng thấp — State Graph:** Lưu vết duyệt web thực tế, với node là trạng thái trang DOM/URL và cạnh là các hành động điều hướng.
- **Tầng cao — Operator Graph:** Mỗi node là một Operator đại diện cho một kỹ năng chuẩn hóa gồm **Điều kiện đầu vào (Precondition)** và **Kết quả đạt được (Effect)**.

**Nguyên lý ghép nối:** Khi Effect của Operator A thỏa mãn Precondition của Operator B ($\text{Effect}_A \models \text{Pre}_B$), hệ thống tự động tạo một cạnh chuyển tiếp.
*Ví dụ:* Kỹ năng "Tìm kiếm sản phẩm" sinh ra kết quả "Đang ở trang chi tiết". Kết quả này thỏa mãn điều kiện cần của kỹ năng "Thêm vào giỏ hàng" $\rightarrow$ Hệ thống tự động ghép thành tác vụ mua hàng hoàn chỉnh.

Nhờ đó, tri thức thu được mang tính **tái sử dụng và tái tổ hợp** vượt bậc.

---

## Slide 10 — Phát hiện skill và quy nạp operator

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

## Slide 11 — Sinh Semantic Task từ chuỗi Operator

Để tạo ra các tác vụ dài hạn có ý nghĩa nghiệp vụ, HSGE kết hợp 2 cơ chế:

- **Bottom-up (Từ dưới lên):** Duyệt đồ thị Operator Graph bằng thuật toán tìm kiếm, tự động ghép các chuỗi $\ge 2$ operator thành một nhiệm vụ hoàn chỉnh kèm câu lệnh ngôn ngữ tự nhiên.
- **Top-down (Từ trên xuống):** Khởi tạo nhiệm vụ từ các chức năng hạt giống (seed) tổng quan của website khi đồ thị còn thưa.

**Kết quả thực thi:** Hệ thống sinh ra **142 tác vụ có ngữ nghĩa** (130 từ seed + 12 từ ghép chuỗi), đạt **71 tác vụ thành công** (tỷ lệ 50,0%). Kết quả này chứng minh cơ chế ghép chuỗi operator hoạt động hoàn toàn đúng thiết kế và khả thi trong thực tế.

---

## Slide 12 — Kiểm định trực tuyến & Đóng gói SFT

*(Điểm chuyển giao người trình bày)*

Nguyên tắc chất lượng của HSGE: **Tuyệt đối không tin vào lời tự khai của agent.**

Hệ thống thiết lập 2 cổng kiểm soát trực tuyến (Online Gates) ngay trong quá trình thu thập:
1. **Online LLM Judge:** Mỗi khi agent tuyên bố xong, LLM Judge độc lập lập tức thẩm định lại trên trạng thái DOM thực tế, loại bỏ ngay **801 lượt (27,4%)** dương tính giả từ nguồn.
2. **Effective Action Gate:** Kiểm tra bằng mã để loại bỏ các trường hợp agent báo xong nhưng trang web không hề có thay đổi trạng thái DOM (loại 104 trajectory).

Nhờ dữ liệu đã sạch từ gốc, hệ thống tiến hành **Build trực tiếp** thành **9.007 mẫu SFT** (8.554 train / 453 validation) mà không cần lọc hậu kỳ. Quá trình đóng gói đảm bảo nghiêm ngặt nguyên tắc **Prompt Parity** (khớp từng byte giữa lúc train và lúc suy luận) và **0 trùng lặp mục tiêu** giữa train và validation.

---

## Slide 13 — Thiết lập & Câu hỏi nghiên cứu

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

## Slide 14 — CH1: Tự động tạo tác vụ & Quy mô dữ liệu

Để trả lời **CH1**, Bảng 1 tổng hợp toàn bộ quy mô dữ liệu tự sinh của HSGE:

- **Quy mô khám phá:** Hệ thống duyệt qua **4 website, 455 URL**, thực hiện **3.981 lượt tương tác thử**.
- **Tri thức tích lũy:** Tự động thu hoạch **146 skill**, quy nạp thành **57 operator**, và sinh thành công **142 semantic task**.
- **Hiệu quả cổng lọc:** LLM Judge loại bỏ **801 lượt (27,4%)** dương tính giả và Effective Action Gate loại **104 trajectory** không đổi trạng thái.
- **Thu hoạch SFT:** Thu được **1.760 trajectory sạch** (tỷ lệ hợp lệ 53,2%), đóng gói thành **9.007 mẫu SFT** hoàn chỉnh.

**Kết luận CH1:** HSGE tự động sinh tác vụ có ý nghĩa và thu hoạch 9.007 mẫu SFT sạch hoàn toàn không cần nhãn con người.

---

## Slide 15 — CH2: So sánh hiệu năng với các hệ thống SOTA

"Để trả lời cho Câu hỏi nghiên cứu thứ hai, Bảng 2 trình bày bức tranh toàn cảnh so sánh hiệu năng của HSGE với các hệ thống State-of-the-art (SOTA) hiện hành trên benchmark WebArena.

_(Bấm Click 1 — hiện các mô hình baseline, làm mờ nhóm mô hình HSGE)_

- Đầu tiên, kết quả trọng tâm nằm ở phiên bản HSGE-9B. Khi tinh chỉnh trên mô hình 9 tỷ tham số, hệ thống đạt tỷ lệ hoàn thành 24,6% (tăng +11,3% so với mô hình gốc). Riêng trên các trang phức tạp như Shopping hay Reddit, tỷ lệ này lên tới 28,3% và 34,0%. Mặc dù con số 24,6% này cao hơn mức 20,0% của GPT-4o-mini hay 22,6% của Go-Browse-7B, nhưng do sự khác biệt về mô hình nền, chúng em không dùng kết quả này để so sánh hơn thua. Thay vào đó, đây là minh chứng rõ ràng nhất cho hiệu quả thực chất của phương pháp sinh dữ liệu.

_(Bấm Click 2 — hiện nhóm mô hình HSGE của khóa luận)_

- Tiếp theo, để kiểm chứng chất lượng tri thức, chúng em thực hiện phép thử chuyển giao chéo sang kiến trúc Qwen-2.5-7B. Chúng em thẳng thắn nhìn nhận mức hiệu năng 16,5% thu được vẫn chưa bắt kịp các phương pháp SOTA cùng phân khúc. Tuy nhiên, việc mô hình tăng gần gấp đôi năng lực (từ 8,3% lên 16,5%) đã khẳng định giá trị cốt lõi: tri thức sinh ra mang tính phổ quát, không hề bị "học vẹt" hay phụ thuộc vào một kiến trúc phần cứng duy nhất.
- Câu chốt: Tựu trung lại, quy trình fine-tuning này đã chứng minh khả năng giúp các tác nhân SLM chạy cục bộ, chi phí thấp bứt phá giới hạn của chính mình, đạt hiệu quả thực chất và tiệm cận mức hiệu năng của những hệ thống như GPT-4o-mini."

---

## Slide 16 — CH2: So sánh Base và Fine-tuning theo Website

Tuy nhiên, trong nghiên cứu khoa học, những con số tổng quan sẽ thiếu đi sức nặng nếu không được chứng minh tính vững chắc về mặt thống kê và giải thích được nguyên nhân sâu xa.

_(Bấm Click 1 — hiện Bảng 3: Hiệu năng Fine-tune theo 4 Website & McNemar)_

"Chuyển sang phân tích bản chất của sự cải thiện này. Bảng 3 trình bày chi tiết bức tranh hiệu năng của hệ thống qua từng giai đoạn huấn luyện (từ mô hình nền đến Pha 1 và Pha 2) trên từng website cụ thể. Để khẳng định những con số tăng trưởng ở Bảng 3 không phải do may mắn ngẫu nhiên, chúng em đã áp dụng kiểm định thống kê McNemar cho dữ liệu bắt cặp (paired data) – tức là so sánh trực tiếp kết quả đúng/sai của mô hình nền và mô hình sau fine-tune trên cùng một bộ tác vụ.

Kết quả kiểm định cho thấy mức tăng trưởng hiệu năng trên cả 4 website đều đạt ý nghĩa thống kê rất cao với $p \le 0,011$, riêng toàn bộ tập dữ liệu đạt mức $p < 0,001$. Ý nghĩa cốt lõi của kiểm định này nằm ở sự chênh lệch của các tác vụ độc quyền: phân tích thống kê chỉ ra rằng sau khi fine-tune, mô hình HSGE-9B đã giải quyết thành công tới 100 tác vụ mà mô hình nền hoàn toàn bất lực, trong khi ở chiều ngược lại, chỉ có 26 tác vụ mô hình nền làm được mà mô hình mới làm sai. Sự áp đảo này $(100 \text{ vs } 26)$ chứng minh sự thăng tiến về năng lực là thực chất.

_(Bấm Click 2 — hiện Kỷ luật cú pháp \& Năng lực ra quyết định)_

Để bóc tách xem sự thăng tiến đó đến từ đâu, chúng em nhận thấy mô hình đã học được 2 khía cạnh:
Thứ nhất là kỷ luật cú pháp: Lỗi định dạng đầu ra của mô hình giảm triệt để từ mức 26,0% xuống chỉ còn 0,6%.
Thứ hai, và là cốt lõi của bài toán, đó là sự gia tăng mạnh mẽ về năng lực ra quyết định. Để chứng minh mô hình thực sự 'thông minh hơn' chứ không chỉ 'gõ đúng lệnh hơn', chúng em đã thực hiện quá trình tinh chỉnh (fine-tuning) chia làm 2 pha.

- Ở Pha 2, chúng em chủ động tăng cường thêm dữ liệu chuyên biệt cho 2 domain, cụ thể là: bổ sung 1.856 mẫu cho Reddit và 2.410 mẫu cho Shopping Admin.
- Kết quả thu được vô cùng rõ rệt: Tại diễn đàn Reddit, tỷ lệ thành công nhảy vọt từ 20,8% (Pha 1) lên tới 34,0% (Pha 2). Tương tự, Shopping Admin cũng tăng từ 15,4% lên 21,4%.
- Hơn thế nữa, một phép thử loại trừ cuối cùng đã được thực hiện: nếu chỉ xét riêng trên tập 485 tác vụ mà mô hình gốc ban đầu vốn dĩ đã xuất đúng cú pháp lệnh, tỷ lệ thành công sau fine-tune vẫn tiếp tục tăng mạnh từ 17,9% lên 23,5%, và sự cải thiện này cũng hoàn toàn đạt ý nghĩa thống kê với $p = 0,003$.

_(Bấm Click 3 — hiện Khung Kết luận CH2)_

Câu chốt: Những kiểm định thống kê khắt khe và phép thử chia 2 pha này là minh chứng rõ ràng cho việc: mở rộng dữ liệu fine-tuning giúp mô hình làm chủ hoàn toàn kỷ luật cú pháp, đồng thời liên tục nâng cao mức trần hiệu năng và năng lực tư duy, lựa chọn hành động của tác nhân."

---

## Slide 17 — CH3: Hiệu quả chi phí trong tự động tạo dữ liệu

Trả lời **CH3** về tính khả thi kinh tế:

_(Bấm Click 1 — hiện Phân bổ mô hình theo vai trò Agent)_

"Thay vì sử dụng các LLM đắt đỏ nhất cho toàn bộ pipeline, hệ thống tự động chia nhỏ và phân công công việc cho các LLM khác nhau dựa trên độ phức tạp và yêu cầu của từng bước.

Cụ thể, các tác vụ đòi hỏi khả năng tư duy, phân tích không gian và thông tin đa phương thức (hình ảnh kèm văn bản) — bao gồm Seeder (khởi tạo ý tưởng khám phá), Explorer (định hướng duyệt web để phát hiện kỹ năng mới) và Solver (giải quyết tác vụ) — được giao cho mô hình GPT-5.6-luna (Vision) đảm nhiệm.

module Goal Solver (hoạt động thay cho Solver khi gặp task phức tạp, để nâng cao khả năng hoàn thành task) nên dùng mô hình mạnh hơn là mô hình GPT-5.6-terra.

Cuối cùng là module Detector (dùng trong bước phân đoạn hình thành skill khi khám phá) và Evaluator (đóng vai trò như giám khảo độc lập chấm lượt hai), được giao phó cho DeepSeek-v4-flash.

_(Bấm Click 2 — hiện Chi phí API toàn chu trình & Token)_

Chiến lược phân lớp này mang lại sự tối ưu về mặt kinh phí. Chi phí cho OpenAI API là 42,29 USD, và chi phí cho DeepSeek API ở khâu Judge và Skill chỉ tốn 11,92 USD. Tổng cộng, toàn bộ quá trình tự động sinh dữ liệu khép kín trên cả 4 website thực tế chỉ tiêu tốn 54,21 USD, tương đương chưa tới 14 USD cho mỗi website, trong đó module Solver tiêu tốn nhiều nhất với 22,25 USD (hơn 50%)

_(Bấm Click 3 — hiện So sánh hiệu quả chi phí với Go-Browse)_

Nhờ chiến lược dồn tải thông minh này — cụ thể là sử dụng GPT-5.6-luna thay vì GPT-4o đắt đỏ — hệ thống đã kéo giảm đơn giá token đầu vào xuống khoảng 12 lần. Kết quả là, chi phí trung bình để thu về một trajectory hoàn chỉnh và sạch sẽ chỉ vỏn vẹn 0,0308 USD.

Khi đối chiếu với công trình SOTA hiện tại là Go-Browse-7B — vốn đang tiêu tốn 0,1026 USD cho mỗi trajectory — phương pháp của HSGE không chỉ có chi phí rẻ hơn đến 3,3 lần. Như đã trình bày ở phần trước, dù chi phí sinh dữ liệu cực thấp, mô hình HSGE-9B vẫn xuất sắc đạt tỷ lệ thành công tiệm cận với các mô hình SOTA hiện tại, cho thấy được đây không phải là sự đánh đổi giữa hiệu năng và chi phí

_(Bấm Click 4 — hiện Khung Kết luận CH3)_

Câu chốt: Với đơn giá đột phá chỉ 0,0308 USD/trajectory đi kèm hiệu năng tiệm cận SOTA, kết quả này chứng minh một cách thuyết phục tính khả thi về mặt kỹ thuật và tài nguyên, cho phép các nhóm nghiên cứu và tổ chức nhỏ hoàn toàn có thể thiết kế các tác nhân chi phí thấp chạy cục bộ."

---

## Slide Mục lục phần Kết luận

"Tiếp theo, em xin đi vào phần 6: Kết luận và Hướng phát triển."

---

## Slide 18 — Kết luận: Đóng góp chính & Hướng phát triển

"Từ những kết quả thực nghiệm trên, em xin phép đi đến phần tổng kết toàn bộ nội dung khóa luận."

_(Bấm Click 1 — hiện Cột trái: Đóng góp chính)_

"Tựu trung lại, công trình nghiên cứu này đóng góp 3 giá trị cốt lõi:

- **Thứ nhất, về mặt Khoa học**: Thay vì phụ thuộc vào kịch bản cố định hay để mô hình tự do khám phá một cách hỗn loạn, nhóm đã đề xuất thành công kiến trúc Đồ thị hai tầng State-Operator kết hợp thuật toán quy nạp tự động. Kiến trúc này tạo nền tảng lý thuyết vững chắc cho việc biểu diễn tri thức giao diện và tự động ghép chuỗi thành các tác vụ đa bước phức tạp có tiền điều kiện rõ ràng.
- **Thứ hai, về mặt Thực tiễn**: Thành quả lớn nhất là một pipeline tự động hóa hoàn chỉnh. Bằng cách tận dụng hiệu quả các luồng đầu vào lai (hybrid) kết hợp cả văn bản và hình ảnh trong quá trình duyệt web, quy trình này đã khai phá trọn vẹn sức mạnh của việc thiết kế các tác nhân chi phí thấp dựa trên mô hình ngôn ngữ nhỏ. Minh chứng là hệ thống đã tự sinh được 9.007 mẫu SFT sạch, giúp huấn luyện mô hình HSGE-9B đạt tỷ lệ thành công 24,6%. Đặc biệt, toàn bộ quá trình này đạt mức tối ưu kinh tế ấn tượng với chi phí chỉ 0,0308 USD/trajectory, rẻ hơn 3,3 lần so với công trình SOTA Go-Browse.
- **Thứ ba, về Tài nguyên mở**: Nhóm đóng góp toàn bộ mã nguồn pipeline, bộ 9.007 mẫu SFT sạch và trọng số mô hình cho cộng đồng nghiên cứu, tạo cơ sở để tiếp tục tái lập và phát triển."

_(Bấm Click 2 — hiện Cột phải: Hướng phát triển tương lai)_

"Mặc dù đạt được những kết quả tích cực, nhóm nghiên cứu cũng thẳng thắn nhìn nhận các điểm nghẽn hiện tại và đề xuất 4 hướng phát triển chính trong tương lai:

- **Thứ nhất - Khôi phục lỗi tự động**: Môi trường web thực tế luôn tiềm ẩn nhiễu. Chúng em muốn trang bị cho tác nhân khả năng tự nhận thức, tự sửa lỗi và thử lại khi gặp các sự cố bất ngờ như timeout hay kẹt trang DOM.
- **Thứ hai - Tối ưu khám phá với Học tăng cường (RL)**: Thay vì duyệt web theo heuristics thuần túy, việc tích hợp RL sẽ giúp module Explorer tự học được các chiến lược tìm kiếm, định vị thông tin trên trang tối ưu và thông minh hơn.
- **Thứ ba - Học từ thất bại**: Những lần agent thao tác sai không phải là rác. Bằng phương pháp Preference Learning hay DPO, chúng em có thể tận dụng chính các trajectory thất bại này để dạy cho mô hình biết những hành vi nào cần tuyệt đối tránh.
- **Cuối cùng - Tổng quát hóa**: Mở rộng năng lực của pipeline khám phá để tác nhân có thể hoạt động trơn tru trên các nền tảng ứng dụng đa dạng ngoài miền (cross-domain) chứ không chỉ giới hạn ở các website đã thử nghiệm."

**Câu chốt toàn bài:** "Dạ, phần trình bày của nhóm đến đây là kết thúc. Em xin chân thành cảm ơn Thầy Cô trong Hội đồng đã dành thời gian theo dõi, và em xin phép được lắng nghe các câu hỏi cũng như ý kiến đóng góp quý báu từ Thầy Cô ạ!"

---

## Phụ lục — mở slide nào khi Hội đồng hỏi gì

Phụ lục không có số footer — cột "Trang" dưới đây là **số trang PDF** trong `main.pdf`.

| Slide | Trang | Nội dung                                            | Bật khi được hỏi về                                                    |
| ----- | ----- | --------------------------------------------------- | ---------------------------------------------------------------------- |
| PL1   | 58    | Tính hợp lệ của phép đánh giá                       | "Explore rồi test trên cùng app thì có hợp lệ không?"                  |
| PL2   | 59    | Hướng đến ai; pipeline mới là thứ tổng quát         | "Có phải muốn model generalize cho mọi trang không?"                   |
| PL3   | 60    | Task khả thi, ngân sách bước, tiêu chuẩn hoàn thành | "Task LLM đề xuất có thật không?", "Sao 25 bước?", "Sao biết đã xong?" |
| PL4   | 61    | Ba CH: số liệu và mức độ trả lời                    | "Thực nghiệm trả lời được mục tiêu chưa?"                              |
| PL5   | 62    | Chi phí chi tiết                                    | "Chi phí đã tính đủ chưa?"                                             |
| PL6   | 63    | Frontier hai tầng                                   | "Khám phá không bị lạc bằng cách nào?"                                 |
| PL7   | 64    | Nguyên nhân thất bại; đặc tính hai mô hình          | "Điểm nghẽn còn lại ở đâu?"                                            |
| PL8   | 65    | Thêm dữ liệu; đổi mô hình nền                       | "Thêm dữ liệu nữa có tốt hơn không?", "Sao không dùng mô hình khác?"   |
| PL9   | 66    | SkillCard & Operator, ví dụ 3-operator chain        | "Skill là gì, operator là gì, trông ra sao?"                           |
| PL10  | 67    | Bảng I/O của Explorer, Solver, Judge, Seeder        | "Explorer / Solver / Judge nhận gì, trả ra gì?"                         |
| PL11  | 68    | Dạng một mẫu dữ liệu SFT (System/User/Assistant)    | "Một mẫu dữ liệu SFT trông ra sao?", "Prompt parity"                   |
| PL12  | 69    | Biểu diễn tri thức: đồ thị hai tầng                 | "Đồ thị hai tầng State Graph & Operator Graph"                         |

---

## Câu hỏi dự kiến và hướng trả lời

### A. Sáu câu thầy phản biện đã hỏi

| Câu hỏi                                                                                                                       | Bật                            | Hướng trả lời                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Explore trên app của họ rồi test bằng bộ test của họ trên chính app đó có hợp lệ không? Phải test app khác cùng lĩnh vực chứ? | **PL1**                        | Pipeline **chưa từng nhìn thấy** 655 task benchmark — task huấn luyện do agent tự đề xuất từ giao diện; CSDL khôi phục nguyên bản trước mỗi đợt đo; không trajectory nào được dùng lại lúc chấm. Cùng-website là **giao thức chuẩn** của cả dòng nghiên cứu: Go-Browse cũng khám phá 20 URL mỗi domain của WebArena rồi chấm trên chính 812 task WebArena. Còn test "app khác" là bài toán **ngoài miền** — chưa ai giải được: trên Online-Mind2Web, Go-Browse-7B chỉ 5,33% và NNetNav-7B 4,00%, đều thua GPT-4o-mini 9,33%. |
| Động lực hướng đến ai? Có phải muốn một model generalize cho mọi trang cùng lĩnh vực?                                         | **Slide 3** trước, **PL2** sau | **Không.** Đích nhắm là chuyên biệt hóa cho _một_ website cụ thể. Câu chốt: **thứ tổng quát hóa là pipeline, không phải model**. Người dùng đích là nhóm vận hành vài website cố định, cần agent chạy tại chỗ. Khả thi vì **dưới 20 đô la mỗi website** và không cần người gán nhãn.                                                                                                                                                                                                                                         |
| Làm sao biết task do LLM đề xuất là hợp lý và làm được thật trên giao diện đó?                                                | **PL3** khối 1                 | Bộ đề xuất là một _agent_ đọc trực tiếp cây trợ năng của trang thật, không đề xuất từ trí nhớ. Quan trọng hơn: **khả thi được chứng minh bằng thực thi, không bằng lời** — chỉ task có ít nhất một lượt giải thành công _và qua kiểm chứng_ mới vào dataset. 637 task bị chính agent báo bất khả thi; 3981 lượt thử còn 2117 hợp lệ.                                                                                                                                                                                         |
| Vì sao ngân sách bước là 25?                                                                                                  | **PL3** khối 2                 | Chính xác là **15 bước cho task cục bộ, 25 cho semantic task nhiều bước**. Solver chiếm 85,5% trong 20.808 lượt gọi nên ngân sách bước _chính là_ ngân sách kinh phí — đây trước hết là quyết định chi phí. Nhưng dữ liệu cho thấy nó **không bóp méo phép đo**: episode thành công có trung vị 6 bước, và **không episode nào** đạt mục tiêu rồi mới bị cắt vì hết bước.                                                                                                                                                    |
| Dựa vào đâu để biết task đã hoàn thành?                                                                                       | **PL3** khối 3                 | **Ba lớp**, không phải hai: (i) solver tự khai hoặc vị từ tất định; (ii) LLM-as-Judge soi trạng thái trang đích → loại **801 lượt** dương tính giả khi tự đánh giá; (iii) cổng "hành động hữu hiệu" bằng mã → loại **104 trajectory**, nhóm lỗi mà judge _về nguyên tắc_ không thấy được. Và 24,6% được chấm bằng **bộ chấm chính thức của WebArena**.                                                                                                                                                                       |

| Thực nghiệm nhắm mục tiêu nào, đã trả lời được chưa? | **PL4** | CH1–CH3 đều có số liệu trả lời. Phần phải nói thật: **O2 và O4 mới hoàn thành một phần** — chỉ 12/142 semantic task từ ghép chuỗi, và **ablation đồ thị so với khám phá phẳng chưa chạy**. |

---

## Tóm tắt kiểm định McNemar (McNemar's Test)

### 1. McNemar là gì?

Kiểm định McNemar (**McNemar's test**) là một kiểm định thống kê phi tham số dùng để so sánh hai mô hình/phương pháp trên **cùng một tập đối tượng** (paired/dependent data), khi kết quả của mỗi đối tượng là dạng **nhị phân (Binary)**, chẳng hạn:

- Đúng / Sai (1 / 0)
- Thành công / Thất bại
- Có / Không

> **Điểm cốt lõi:** Hai kết quả phải có tính **ghép cặp (paired)** — tức là từng tác vụ/mẫu dữ liệu cụ thể đều được đánh giá bởi cả hai mô hình (Model A và Model B).

---

### 2. Khi nào áp dụng?

Kiểm định McNemar phù hợp khi thỏa mãn **3 điều kiện chính**:

| Điều kiện            | Mô tả chi tiết                                                                   |
| -------------------- | -------------------------------------------------------------------------------- |
| **Hai phương pháp**  | So sánh trực tiếp Model A (mô hình nền) với Model B (mô hình sau fine-tune).     |
| **Cùng tập dữ liệu** | Cả hai model đều được đánh giá trên cùng một tập $N$ tác vụ/mẫu thử nghiệm.      |
| **Kết quả nhị phân** | Đầu ra của mỗi tác vụ chỉ có 2 trạng thái: Thành công ($1$) hoặc Thất bại ($0$). |

#### Ví dụ thực tế trong đánh giá AI:

Giả sử có 100 tác vụ web (tasks) và cần so sánh:

- **Model A**: Mô hình nền trước fine-tuning (Base Model)
- **Model B**: Mô hình sau fine-tuning (HSGE Fine-tuned Model)

Mỗi tác vụ trả về kết quả nhị phân ($1 = \text{Thành công}$, $0 = \text{Thất bại}$). Ta dùng kiểm định McNemar để xác định xem sự tăng trưởng tỷ lệ thành công của Model B so với Model A có **nghĩa thống kê thực sự** hay chỉ do yếu tố ngẫu nhiên.

---

### 3. Bảng 2×2 của McNemar

Dữ liệu kết quả bắt cặp của $N$ tác vụ được tổng hợp thành **Bảng ma trận 2×2**:

|                            | **Model B Thành công (1)** | **Model B Thất bại (0)** |
| -------------------------- | :------------------------: | :----------------------: |
| **Model A Thành công (1)** |  $a$ (Cả A và B đều đúng)  | $b$ (A đúng nhưng B sai) |
| **Model A Thất bại (0)**   |  $c$ (A sai nhưng B đúng)  | $d$ (Cả A và B đều sai)  |

#### Giải thích các ô trong bảng:

- **$a$**: Tác vụ mà cả 2 mô hình đều làm đúng $\rightarrow$ _Không thể hiện sự khác biệt._
- **$d$**: Tác vụ mà cả 2 mô hình đều làm sai $\rightarrow$ _Không thể hiện sự khác biệt._
- **$b$**: Tác vụ Model A làm được nhưng Model B làm hỏng $\rightarrow$ _Bất đồng (Model A ưu thế)._
- **$c$**: Tác vụ Model A thất bại nhưng Model B giải thành công $\rightarrow$ _Bất đồng (Model B ưu thế — tác vụ độc quyền)._

> **Trọng tâm kiểm định:** McNemar chỉ tập trung phân tích **$b$ và $c$** (các phần tử bất đồng). Sự chênh lệch giữa $c$ và $b$ (ví dụ: $100 \text{ vs } 26$ tác vụ độc quyền) chính là yếu tố quyết định giá trị $p$-value.

---

### 4. Ý nghĩa của giá trị $p$-value

#### Phát biểu Giả thuyết:

- **Giả thuyết Không ($H_0$):** Hai mô hình có năng lực tương đương nhau ($P(b) = P(c)$).
- **Giả thuyết Đối ($H_1$):** Hai mô hình có năng lực khác nhau có ý nghĩa thống kê ($P(b) \neq P(c)$).

#### Tiêu chuẩn đánh giá:

Chọn mức ý nghĩa phổ biến $\alpha = 0,05$:

- **$p < 0,05$**: **Bác bỏ $H_0$** $\rightarrow$ Sự cải thiện hiệu năng của mô hình mới có **ý nghĩa thống kê rõ rệt** (không phải ngẫu nhiên).
- **$p \ge 0,05$**: **Chưa đủ bằng chứng bác bỏ $H_0$** $\rightarrow$ Sự khác biệt chưa đạt mức có ý nghĩa thống kê.

#### Ví dụ minh họa:

Nếu kết quả kiểm định trả về $p = 0,032$:

> Vì $0,032 < 0,05$, ta kết luận sự vượt trội của Model B so với Model A là **có ý nghĩa thống kê** với độ tin cậy $95\%$.

---

### 5. Khi nào KHÔNG nên dùng McNemar?

Không sử dụng kiểm định McNemar trong các trường hợp sau:

1. **Dữ liệu độc lập (Unpaired):** Model A và Model B được test trên hai tập dữ liệu khác nhau. _(Ví dụ: Model A test 100 task WebArena, Model B test 100 task Mind2Web khác)._
2. **Kết quả không phải nhị phân:** Kết quả đánh giá là dạng liên tục (định lượng) như điểm ROUGE, BLEU, thời gian phản hồi, hoặc latency.
3. **So sánh $> 2$ mô hình:** Muốn so sánh đồng thời 3 mô hình trở lên trong một phép thử đơn lẻ (khi đó nên dùng kiểm định _Cochran's Q_).

---

### B. Các câu khác

| Câu hỏi                                                                                                    | Bật                            | Hướng trả lời                                                                                                                                                                                                                                                                                                                |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Đóng góp mới so với Go-Browse / NNetNav là gì?                                                             | Slide 6–7                      | Kỹ năng được **kiểm chứng**, nâng thành operator có tiền điều kiện/kết quả, rồi **ghép chuỗi** thành task dài — hai cột mà cả hai công trình kia đều trống. Cộng thêm hai cổng chất lượng và prompt parity.                                                                                                                  |
| Sao không chứng minh được đồ thị tốt hơn khám phá phẳng?                                                   | Slide 18, PL4                  | Đúng, đó là ablation quan trọng nhất và chưa chạy. Thiết kế đã có sẵn: cùng ngân sách episode và lượt gọi, chỉ đổi chiến lược khám phá.                                                                                                                                                                                      |
| Vì sao ghép chuỗi chỉ sinh 12/142 task?                                                                    | Slide 11                       | Cạnh operator cần kết quả khớp tiền điều kiện; sau hai cổng chống trùng lặp và kiểm chứng thực tế, đồ thị còn thưa. Hạn chế đã ghi trong Chương 5.                                                                                                                                                                           |
| 24,6% có thấp quá không?                                                                                   | Slide 15                       | So với chính mô hình nền cùng điều kiện là **+11,3 điểm, p<0,001, có ý nghĩa trên cả 4/4 website**. Benchmark này GPT-4 chỉ đạt ~14% khi công bố, người đạt 78%. 24,6% ngang nhóm mô hình mở tốt nhất dưới 10B.                                                                                                              |
| Vì sao tin số liệu khi agent tự chấm?                                                                      | PL3                            | Không tin — ba lớp kiểm chứng; và phần đánh giá cuối dùng bộ chấm tự động của WebArena, không phải agent.                                                                                                                                                                                                                    |
| Chi phí đã tính đủ chưa?                                                                                   | PL5                            | **54,21 API + 24,40 GPU = 78,61 đô la** cho cả bốn website; chưa tính hạ tầng WebArena tự host và công vận hành. Mỗi trajectory 0,0308 đô — rẻ hơn Go-Browse 3,3 lần.                                                                                                                                                        |
| Hệ thống này dùng để kiểm thử phần mềm được không?                                                         | PL2                            | Về cấu trúc thì rất khớp: operator có **precondition/effect** chính là một dạng _test model_, semantic task là _test scenario_, trajectory đã kiểm chứng là _test script_. Nhưng phải nói rõ: khóa luận **chưa thực nghiệm** hướng này — đây là ứng dụng tiềm năng, không phải kết quả.                                      |
| Điểm nghẽn còn lại ở đâu?                                                                                  | PL7                            | Tầng thực thi: 85–96% episode thất bại có ít nhất một hành động bị trình duyệt từ chối. Fine-tune làm mô hình **bền bỉ** hơn chứ không **chính xác** hơn — tỷ lệ lỗi trên mỗi bước gần như không đổi.                                                                                                                        |
| Sao train từng bước mà không train nguyên trajectory? Train từng bước thì làm sao model làm được task dài? | Không có slide — xem **mục C** | Mẫu là một bước **nhưng không rời khỏi trajectory**: prompt mỗi bước có `# Goal` (câu lệnh task dài, giữ nguyên ở mọi bước) và `# History of Past Actions` (6 hành động gần nhất kèm kết quả). Không gộp cả chuỗi vì lúc chạy thật agent sinh **một** hành động rồi mới thấy trang tiếp theo — gộp là phá **prompt parity**. |
| Thêm dữ liệu nữa có tốt hơn không?                                                                         | PL8                            | Có, nhưng hiệu suất giảm nhanh: gần **gấp ba** dữ liệu của hai website chỉ đổi lấy **+2,1 điểm**. Nên hướng tiếp theo là sửa tầng thực thi, không phải nhân đôi dữ liệu.                                                                                                                                                     |

---

### C. Câu trả lời dài: "sao train từng bước, không train nguyên trajectory?"

**Câu trả lời ngắn (đọc thẳng được):**

> Thưa Thầy, hai cái đó không đối lập nhau. Một mẫu huấn luyện của nhóm em **là một bước,
> nhưng không phải một bước bị cắt rời khỏi trajectory**. Trong prompt của mỗi bước luôn
> có khối `# Goal` giữ nguyên câu lệnh của task dài, và khối `# History of Past Actions`
> liệt kê các hành động đã làm cùng kết quả của chúng. Nên cái model học là ánh xạ
> _(mục tiêu dài + tiến độ đã đi được + trang hiện tại) → hành động kế tiếp_, chứ không
> phải _(trang hiện tại) → hành động_.
>
> Còn lý do không gộp cả trajectory thành một mẫu là vì **lúc chạy thật không ai chạy như
> vậy**. Agent chạy theo vòng lặp: quan sát trang → sinh **một** hành động → trình duyệt
> trả về trang mới. Hành động thứ hai phụ thuộc vào trang do hành động thứ nhất tạo ra,
> mà trang đó chưa tồn tại tại thời điểm sinh. Bắt model sinh cả chuỗi một lượt là vi phạm
> đúng nguyên tắc **prompt parity** mà nhóm em vừa trình bày ở slide 12.

**Ví dụ cụ thể — nếu Hội đồng muốn thấy tận mắt.** Lấy task _"Tìm sản phẩm yoga mat rồi
thêm vào giỏ hàng"_. Trajectory này dài 4 bước, và nó tạo ra 4 mẫu huấn luyện. So sánh
mẫu **bước 1** với mẫu **bước 4**:

```
--- MẪU BƯỚC 1 -----------------      --- MẪU BƯỚC 4 -----------------
# Goal                                # Goal
Tìm sản phẩm "yoga mat" rồi           Tìm sản phẩm "yoga mat" rồi
thêm vào giỏ hàng                     thêm vào giỏ hàng        <-- Y HỆT

# Current Page                        # Current Page
URL: /                                URL: /yoga-mat-premium.html
<axtree trang chủ>                    <axtree trang chi tiết sản phẩm>

# Error Message from Last Action      # Error Message from Last Action
(none)                                (none)

# History of Past Actions             # History of Past Actions
(none)                                - fill('204', 'yoga mat') -> no change
                                      - press('204', 'Enter')
                                          -> now at /catalogsearch/result/?q=yoga+mat
                                      - click('619') -> now at /yoga-mat-premium.html

# Next Action ...                     # Next Action ...
--------------------------------      --------------------------------
Đáp án: fill('204','yoga mat')        Đáp án: click('842')   [nút Add to Cart]
```

**Điểm mấu chốt nằm ở mẫu bước 4.** Trang chi tiết sản phẩm đó xuất hiện trong rất nhiều
task khác nhau: có task chỉ hỏi giá, có task kiểm tra tồn kho, có task so sánh hai sản
phẩm. **Nhìn riêng cái trang thì không thể quyết định được phải bấm gì.** Thứ quyết định
là hai khối kia: `# Goal` nói mục tiêu cuối là _thêm vào giỏ_, còn `# History` nói _đã tìm
xong và đã mở đúng sản phẩm rồi_ — nên việc còn lại đúng là bấm Add to Cart. Model buộc
phải đọc cả ba khối mới sinh đúng hành động, và đó chính là cách nó học tính trạng thái
của một task dài.

Ba chi tiết kỹ thuật cần nói chính xác nếu bị hỏi tiếp:

- **`# History` hiển thị 6 hành động gần nhất**, không phải toàn bộ lịch sử (hằng số
  `_HISTORY_WINDOW` trong `hsge/webarena/agents.py`) — nói "toàn bộ" là nói sai.
- Mỗi dòng history có **kết quả thật của hành động** (`now at <url>` / `page changed` /
  `no change`), sinh bởi cùng một hàm `step_outcome()` mà solver lúc chạy thật dùng.
  Nhờ vậy model thấy được hành động nào vừa rồi **không làm gì cả**.
- Hành động bị trình duyệt từ chối vẫn nằm trong history (kèm lỗi) nhưng **không được
  dùng làm đáp án** — nó là cái sai, không phải cái cần bắt chước.

**Năng lực task dài đến từ dữ liệu, không từ định dạng mẫu:**

1. **Semantic task** ghép chuỗi operator — đây chính là nguồn sinh ra trajectory nhiều bước.
2. **Unprefixed sampling**: giải lại task từ trang gốc của site, nên trajectory chứa cả
   phần điều hướng. Không có cơ chế này thì 287 trong 465 trajectory chỉ dài đúng **một**
   bước.
3. **Curriculum**: mẫu sắp theo `difficulty` (LOCAL → UNPREFIXED → GOAL) — task ngắn trước,
   task dài sau.

Và phép đo cuối không phải bài toán một bước: 655 task WebArena đều đa bước, chấm bằng bộ
chấm của benchmark, episode thành công có trung vị 6 bước.

**Chỗ phải tự nhận, đừng để bị bắt:** khóa luận **không có hàm mục tiêu ở cấp trajectory**
— không RL, không reward tính trên cả chuỗi, không phạt riêng việc đi sai ở bước 2 làm hỏng
cả task. Model học bắt chước từng bước; tín hiệu "cả trajectory này thành công" vào dataset
**gián tiếp qua khâu lọc** (chỉ trajectory đã kiểm chứng mới được xuất). Đó đúng là hạn chế
và là lý do hướng phát triển là RL/DPO. Nhóm em đã lưu sẵn `trajectory_id`, `step_index`,
`total_steps` trong từng mẫu để bước sau gom batch theo trajectory mà không phải thu thập
lại dữ liệu.

---

## Checklist trước khi lên

- [ ] Mở sẵn `main.pdf` ở chế độ toàn màn hình, kiểm tra nhảy được tới **trang PDF 58–69** (phụ lục PL1–PL8).
- [ ] Video demo mở sẵn ở tab riêng, **âm lượng 0**, đã thử phát một lần.
- [ ] Nhớ ba con số không được nói sai: **24,6% / 13,3% / +11,3 điểm**.
- [ ] Slide 3 phải nói ra chữ **"một tập website cố định"**; slide 7 phải có chữ
      **"tiềm năng"** khi nhắc kiểm thử E2E.
- [ ] Nhớ hai chỗ **không được nói quá**: "ngang Go-Browse" (không phải _vượt_), và
      "ghép chuỗi mới khả thi" (không phải _đã đủ dày_).
- [ ] Người 2 nắm chắc mốc 10:00 — nếu người 1 trễ quá 1 phút thì lược
      `[lược nếu trễ]` ở slide 4 và 5.

---

## Nếu được 20 phút

Thêm bốn slide, theo thứ tự ưu tiên:

1. **Kéo PL7 (nguyên nhân thất bại) và PL6 (frontier hai tầng) vào phần nội dung** —
   cả hai đã dựng sẵn trong phụ lục, chỉ cần đổi chỗ.
2. **Ví dụ một semantic task** sinh từ chuỗi operator, kèm chuỗi tiền điều kiện/kết quả.
3. **Lộ trình nghiên cứu** (`fig_roadmap.pdf`, đã có trong `images/`), đặt ngay sau
   slide 7 (giải pháp & đóng góp).
4. **Bài học vận hành** (Phụ lục E của quyển): chat template, prompt parity, chạy song
