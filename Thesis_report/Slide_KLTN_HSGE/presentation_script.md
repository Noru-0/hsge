# Kịch bản trình bày — Bảo vệ KLTN HSGE

**Ngân sách:** 15 phút trình bày + 15 phút hỏi đáp (thông báo bảo vệ đợt 04/2026).
Deck có **20 trang phần nội dung** (14 slide phải nói + 1 bìa cảm ơn + 5 trang mục lục
lướt qua) và **9 trang phụ lục PL1–PL8** đặt sau trang cảm ơn, chỉ bật khi được hỏi.

**Chia hai người:** Người 1 slide 1–8 (đặt vấn đề + phương pháp), Người 2 slide 9–14
(thực nghiệm + demo + kết luận). Điểm cắt sau slide 8, khi chuyển từ *"làm thế nào"*
sang *"đo được gì"*.

**Cách đọc kịch bản:**
- **Nói** = lời thoại, viết theo văn nói, đọc thẳng được.
- **Câu chốt** = câu duy nhất bắt buộc phải lọt tai Hội đồng ở slide đó.
- **Tránh** = chỗ dễ nói quá; nói sai một chữ ở đây là mất điểm tin cậy.
- `[lược nếu trễ]` = cắt được mà không gãy mạch.
- Cột "Trang" là **số slide hiện ở footer** (`n / 20`), không phải số trang PDF: deck
  dùng overlay nên `main.pdf` hiện có 74 trang. Nhảy nhanh thì dùng số footer.

---

## Bảng thời lượng

| Slide | Trang | Nội dung | Mốc | Thời lượng |
|---|---|---|---|---|
| 1 | 1 | Bìa | 0:00 | 0:30 |
| 2 | 4 | Bối cảnh, bài toán, thách thức | 0:30 | 1:15 |
| 3 | 5 | Mục tiêu và định vị | 1:45 | 1:15 |
| 4 | 7 | Tổng quan pipeline HSGE | 3:00 | 1:15 |
| 5 | 8 | Đồ thị hai tầng | 4:15 | 1:00 |
| 6 | 9 | Phát hiện skill → quy nạp operator | 5:15 | 1:15 |
| 7 | 10 | Sinh semantic task | 6:30 | 1:00 |
| 8 | 11 | Tinh lọc dữ liệu *(chuyển người)* | 7:30 | 1:00 |
| 9 | 13 | Thiết lập thực nghiệm | 8:30 | 0:45 |
| 10 | 14 | CH1 — thu được gì, chi phí bao nhiêu | 9:15 | 1:00 |
| 11 | 15 | CH2 — kết quả chính | 10:15 | 1:15 |
| 12 | 16 | CH2–CH3 — phân tích và so sánh | 11:30 | 1:15 |
| 13 | 17 | **Demo** | 12:45 | 1:15 |
| 14 | 19 | Kết luận | 14:00 | 1:00 |

Slide 3 dài thêm ~15--20 giây so với bản cũ (khối phạm vi \& ứng dụng đích); nếu trễ
thì lược đoạn ba nhóm ứng dụng.

Trang 3, 6, 12, 18 là mục lục đầu mỗi chương — bấm lướt, không dừng nói.
Trang 20 là trang cảm ơn; dừng ở đó và mời Hội đồng đặt câu hỏi.

---

## Slide 1 - Bìa (0:00, trang 1)

> Kính thưa Hội đồng. Em là Trương Bảo Kiệt, cùng bạn Hồ Tiến Phát, trình bày khóa
> luận *"Khám phá theo đồ thị kỹ năng phân cấp để tự động sinh dữ liệu huấn luyện cho
> tác nhân trí tuệ nhân tạo trên web"*, dưới sự hướng dẫn của PGS.TS. Nguyễn Văn Vũ.
>
> Bài trình bày gồm bốn phần: bài toán và định vị, phương pháp HSGE, kết quả thực
> nghiệm, và kết luận.

---

## Slide 2 - Bối cảnh, bài toán, thách thức (0:30, trang 4)

> **Web agent** là tác nhân AI nhận yêu cầu bằng ngôn ngữ tự nhiên rồi tự điều khiển
> trình duyệt để hoàn thành — ví dụ: *"Vào trang quản trị kiểm tra đơn hàng và cập nhật
> trạng thái"*. Muốn agent chạy được trong thực tế thì hiện nay phải gọi API của các mô
> hình lớn — rất đắt đỏ theo từng bước thao tác, độ trễ cao, và dữ liệu nội bộ phải gửi
> ra máy chủ bên ngoài.
>
> Hướng thay thế là dùng **mô hình ngôn ngữ nhỏ (SLM, dưới 10 tỷ tham số)**, chạy ngay
> cục bộ trên máy tính. Nhưng mô hình nhỏ không tự biết cách dùng một website lạ; ta
> phải fine-tune (tinh chỉnh) nó. Mà fine-tune thì cần dữ liệu **trajectory** — tức
> toàn bộ chuỗi trạng thái trang web và các thao tác bấm chuột, gõ phím thành công trên
> chính website đó. Dữ liệu này gần như không có sẵn. Gán nhãn thủ công bằng con người
> thì cực kỳ tốn kém: AutoWebGLM cần tới **20 người làm việc liên tục trong một tháng**.
>
> Vì vậy bài toán của khóa luận là: **tự động khám phá một website đang hoạt động và
> tự sinh ra dữ liệu huấn luyện cho website đó, hoàn toàn không dùng dữ liệu do con người
> gán nhãn.**
>
> Và xin nói rõ ngay phạm vi, như dòng thứ hai trong khung: đích nhắm là **một tập website
> cố định của một tổ chức** — trang quản trị, CMS, diễn đàn nội bộ của họ — **chứ không
> phải một model dùng chung cho mọi trang web**. Chuyện đó em sẽ nói kỹ hơn ở slide sau.
>
> `[lược nếu trễ]` Bốn thách thức kỹ thuật cốt lõi ở cột phải. Thứ nhất, **chi phí gán
> nhãn** thủ công quá lớn như vừa nói. Thứ hai, **tri thức môi trường** — mỗi website có
> luồng thao tác riêng, tri thức học được ở trang này không mang sang trang khác được.
> Thứ ba, **báo đỗ ảo**: agent tự sinh dữ liệu thì cũng tự chấm điểm cho mình, rất dễ
> tuyên bố xong trong khi chưa làm gì. Thứ tư, **tác vụ đa bước**: ghép các thao tác rời
> rạc thành một nhiệm vụ dài có ý nghĩa nghiệp vụ.

**Câu chốt:** nút thắt không phải mô hình, mà là **dữ liệu tương tác cho từng website cụ thể**.

**Câu chốt phụ (bắt buộc nói, đừng đợi bị hỏi):** phạm vi là **chuyên biệt hóa theo
website**, không phải agent vạn năng. Nói chủ động ở slide 2 thì slide 3 và PL2 chỉ còn
việc củng cố.

---

## Slide 3 - Mục tiêu và định vị (1:45, trang 5)

> Khóa luận đặt năm mục tiêu từ O1 đến O5: khám phá tự động, sinh semantic task đã kiểm
> chứng, tinh lọc thành dataset, fine-tune và đánh giá trên WebArena, và đúc kết kinh
> nghiệm vận hành.
>
> Bảng bên phải là định vị so với bốn công trình tiêu biểu gần nhất. AWM và SkillWeaver
> có khai thác kỹ năng, nhưng chỉ dùng ở thời điểm suy luận cho mô hình lớn — không
> huấn luyện lại mô hình nhỏ. NNetNav và Go-Browse có huấn luyện mô hình nhỏ, nhưng dữ
> liệu chỉ dừng ở mức từng trang đơn lẻ, thiếu cấu trúc kỹ năng được kiểm chứng.
>
> Khoảng trống nghiên cứu — khung đỏ dưới bảng — là chưa công trình nào kết hợp trọn vẹn
> ba khâu: **kiểm chứng kỹ năng → ghép thành tác vụ dài hạn → dùng chính dữ liệu đó huấn
> luyện mô hình nhỏ**. Đó là đóng góp mà khóa luận hướng tới.
>
> Khung dưới bên trái trả lời câu hỏi ở tiêu đề slide. Đầu vào là **một website đang chạy**,
> không cần một dòng nhãn nào của con người; đầu ra là **một agent chuyên biệt cho đúng
> website đó**, chạy cục bộ. Nói cách khác, **thứ tổng quát hóa ở đây là pipeline, không
> phải model** — pipeline chạy lại được trên website bất kỳ, còn model thì cố tình chuyên
> biệt.
>
> Ba nhóm ứng dụng nhóm em nhắm tới: **RPA cho hệ thống nội bộ hoặc legacy** — các quy
> trình lặp trên ERP, CMS, trang quản trị vốn không có API để tích hợp; **trợ lý vận hành
> on-prem** cho dữ liệu nhạy cảm, vì mô hình dưới 10 tỷ tham số chạy được ngay tại chỗ;
> và **kiểm thử E2E** — đây em xin nhấn mạnh là hướng **tiềm năng**, chưa thực nghiệm
> trong khóa luận, nhưng về cấu trúc thì operator có tiền điều kiện và kết quả chính là
> một dạng mô hình kiểm thử, còn semantic task chính là kịch bản kiểm thử.

**Câu chốt:** đóng góp nằm ở **tầng trừu tượng thứ hai** — kỹ năng đã kiểm chứng — chứ
không phải ở việc thu nhiều dữ liệu hơn.

**Tránh:** **không nói "khóa luận làm công cụ kiểm thử tự động"**. Bắt buộc có chữ
*"tiềm năng, chưa thực nghiệm"* trong cùng một câu — quyển báo cáo không có phần kiểm thử.

`[lược nếu trễ]` Bỏ đoạn ba nhóm ứng dụng, chỉ giữ câu "tổng quát hóa là pipeline, không
phải model".

---

## Slide 4 - Tổng quan pipeline HSGE (3:00, trang 7)

> Đây là toàn bộ phương pháp HSGE trên một hình, vận hành như một vòng lặp khép kín, tự
> động hoàn toàn.
>
> Bắt đầu từ **Frontier** — hàng đợi lưu các trang web cần khám phá. Chọn một trang, một
> agent đề xuất các tác vụ làm được ngay trên trang đó, rồi solver thử thao tác trên trình
> duyệt thật. Những trajectory giải thành công được đưa vào khâu phát hiện kỹ năng: cắt
> thành đoạn nhỏ, gom cụm các thao tác tương đồng, trừu tượng hóa thành thẻ kỹ năng, rồi
> quy nạp thành **Operator** có tiền điều kiện (Precondition) và kết quả (Effect).
>
> Các operator này được ghép chuỗi với nhau để sinh ra các **Semantic task** — tức tác vụ
> nhiều bước có ý nghĩa thực tế. Toàn bộ dữ liệu thu được đi qua hai cổng lọc chất lượng
> trước khi trở thành tập huấn luyện SFT. Và mỗi trang mới phát hiện lại quay về
> frontier để tiếp tục mở rộng.

**Câu chốt:** không phải thu thập rời rạc, mà **tích lũy tri thức có cấu trúc rồi
mới khai thác lại**.

---

## Slide 5 - Đồ thị hai tầng (4:15, trang 8)

> Tri thức khám phá được lưu trữ trong một đồ thị hai tầng.
>
> - **Tầng thấp (State Graph):** Lưu vết duyệt web thực tế gồm các trang đã ghé thăm và
>   hành động chuyển giữa chúng.
> - **Tầng cao (Operator Graph):** Mỗi operator là một kỹ năng chuẩn hóa với điều kiện
>   đầu vào và kết quả đầu ra. Hai operator được nối với nhau khi **kết quả của bước
>   trước thỏa mãn điều kiện đầu vào của bước sau**.
>
> *Ví dụ trực quan:* Kỹ năng "Tìm kiếm sản phẩm" sinh ra kết quả "Đang ở trang chi tiết".
> Kết quả này khớp đúng điều kiện cần của kỹ năng "Thêm vào giỏ hàng" $\rightarrow$ Hệ
> thống tự động ghép nối thành tác vụ mua hàng hoàn chỉnh.
>
> Nhờ cấu trúc này, tri thức thu được có tính **tái sử dụng và tái tổ hợp**, giúp sinh
> ra vô số tác vụ dài hạn mà không cần người viết kịch bản.

**Câu chốt:** tầng cao là thứ phân biệt HSGE với Go-Browse — bên đó chỉ có tầng thấp.

---

## Slide 6 - Phát hiện skill và quy nạp operator (5:15, trang 9)

> Khâu phát hiện kỹ năng chỉ chạy trên trajectory của các tác vụ **đã giải thành công**,
> qua bốn bước:
> 1. **Phân cắt:** Cắt chuỗi thao tác dựa trên thay đổi URL và sự biến động của **cây
>    trợ năng (AXTree)** — tức bản rút gọn văn bản của giao diện web chỉ chứa các nút
>    bấm, ô nhập liệu có thể tương tác.
> 2. **Gom cụm:** Gom các đoạn thao tác có chức năng tương tự nhau.
> 3. **Trừu tượng hóa:** Rút trích thành thẻ kỹ năng có tham số hóa (như từ khóa tìm kiếm).
> 4. **Kiểm chứng:** Cho chạy thử lại trong ngữ cảnh mới để xác nhận tính dùng lại được.
>
> Để nâng kỹ năng lên thành Operator, hệ thống áp dụng hai cổng chặn: **cổng chống trùng
> lặp** loại bỏ các mệnh đề vô nghĩa, và **cổng kiểm chứng thực tế** gỡ bỏ các kết quả
> không đúng trên phần lớn các lần chạy.
>
> `[lược nếu trễ]` Nhờ sự khắt khe này, từ 146 kỹ năng phát hiện được, hệ thống chắt lọc
> ra 57 operator thực sự chuẩn xác.

**Câu chốt:** "đã kiểm chứng" ở đây là **có cổng chặn đo được**, không phải nhãn tự
phong.

---

## Slide 7 - Sinh semantic task (6:30, trang 10)

> **Semantic task** — tức tác vụ nhiều bước có ngữ nghĩa nghiệp vụ hoàn chỉnh — được
> sinh từ hai nguồn:
> - **Từ dưới lên (Bottom-up):** Ghép chuỗi operator bằng duyệt đồ thị, mỗi chuỗi từ
>   hai operator trở lên sẽ tạo thành một nhiệm vụ dài kèm câu lệnh ngôn ngữ tự nhiên.
> - **Từ trên xuống (Top-down):** Gợi ý từ năng lực tổng quan của website (như chức năng
>   quản trị, đăng bài, mua sắm) khi đồ thị còn thưa.
>
> Về số liệu thực tế: trong **142 semantic task** đã thực thi, **130 tác vụ đến từ seed
> và 12 tác vụ đến từ ghép chuỗi operator**, đạt 71 tác vụ giải thành công. Kết quả này
> chứng minh cơ chế ghép chuỗi hoạt động đúng thiết kế, dù ở giai đoạn đầu tần suất ghép
> còn thưa.

**Câu chốt:** cơ chế ghép chuỗi được chứng minh là **khả thi**, chưa chứng minh được là
**đủ dày** để làm nguồn dữ liệu chính.

**Tránh:** đừng nói "semantic task chủ yếu sinh từ đồ thị operator" — số liệu ngược lại,
và Hội đồng có thể đã đọc Chương 5.

---

## Slide 8 - Kiểm định trực tuyến & Đóng gói SFT (7:30, trang 11) — *điểm chuyển người trình bày*

> Nguyên tắc chất lượng cốt lõi: **không bao giờ tin vào lời tự khai hoàn thành của
> agent.**
>
> Điểm khác biệt quan trọng là toàn bộ việc kiểm soát chất lượng được thực hiện **trực tuyến
> ngay trong vòng lặp khám phá**, không cần chờ đến khâu hậu kiểm ngoại tuyến:
> 1. **Inline LLM Judge:** Mỗi khi agent tự tuyên bố xong, LLM Judge độc lập lập tức chấm
>    lại trên trạng thái trang đích, loại bỏ ngay **801 episode (khoảng 27,4%)** báo đỗ ảo
>    (false positive) từ nguồn.
> 2. **Cổng hành động hữu hiệu (Effective Action):** Viết bằng mã để chặn các trường hợp
>    agent báo xong nhưng trang web không hề thay đổi trạng thái — điểm mù mà Judge không
>    thấy được.
>
> Nhờ dữ liệu trong kho `episodes/` đã hoàn toàn sạch từ quá trình khám phá, hệ thống tiến
> hành **đóng gói trực tiếp (Direct Build)** thành tập dữ liệu SFT mà không cần thêm bất kỳ
> khâu lọc hậu kỳ nào.
>
> Dữ liệu được đóng gói theo nguyên tắc **Prompt Parity**: mẫu câu lệnh lúc huấn luyện trùng
> khớp từng byte với câu lệnh solver nhìn thấy lúc chạy thật, chia train/val theo cấp task
> đảm bảo **0 mục tiêu trùng lặp**.

**Câu chốt:** kiểm định trực tuyến ngay từ nguồn giúp dữ liệu sạch tuyệt đối, cho phép đóng
gói trực tiếp tập SFT để huấn luyện mô hình.

---

## Slide 9 - Thiết lập thực nghiệm (8:30, trang 13)

> Thực nghiệm được tiến hành trên bốn website thuộc benchmark chuẩn quốc tế **WebArena**
> do nhóm tự triển khai (self-hosted): Shopping, Shopping Admin, GitLab và Reddit.
>
> Đánh giá mô hình trên **655 task chính thức**, chấm điểm tự động bằng bộ chấm của
> WebArena, giới hạn 15 bước mỗi task, nhiệt độ bằng 0 (temperature = 0 để đảm bảo tính
> tất định và công bằng).
>
> Quá trình khám phá gồm bốn đợt, khoảng 21 giờ mỗi website. Mô hình đích là **Qwen3.5-9B**
> được tinh chỉnh bằng kỹ thuật LoRA trong 1119 bước (khoảng 5 giờ tính toán).
>
> Bốn câu hỏi nghiên cứu (CH1 đến CH4) ở cột phải sẽ được giải đáp chi tiết trong các
> slide tiếp theo.

**Câu chốt:** đánh giá dùng **bộ chấm chính thức của benchmark**, không phải cơ chế kiểm
chứng nội bộ của nhóm.

---

## Slide 10 - CH1: thu được gì, chi phí bao nhiêu (9:15, trang 14)

> **Về quy mô dữ liệu (CH1):** Phễu khám phá duyệt qua **455 trang web**, ghi nhận **3981
> lượt thử**, trong đó **2117 lượt hợp lệ sau kiểm chứng** (đạt 53,2%). Từ đó thu được
> **146 kỹ năng**, quy nạp **57 operator**, và thực thi **142 semantic task**.
>
> Sau các cổng lọc chất lượng, hệ thống thu được **1760 trajectory sạch**, xuất ra
> **9007 mẫu huấn luyện SFT** hoàn toàn không tốn một giờ gán nhãn thủ công nào.
>
> **Về hiệu quả kinh tế:** Toàn bộ quá trình gọi API khám phá tốn **54,21 USD**, cộng
> **24,40 USD** tiền thuê GPU để fine-tune và đánh giá. Tính trung bình, mỗi trajectory
> thành công chỉ tốn **0,0308 USD (khoảng 3,1 cent)** — rẻ hơn công trình Go-Browse tới
> **3,3 lần**.
>
> `[lược nếu trễ]` Điểm đáng chú ý: rào cản chi phí không nằm ở khâu GPU huấn luyện hay
> đánh giá, mà nằm ở thời gian điều khiển trình duyệt lúc thu thập.

**Câu chốt:** cả chu trình cho bốn website tốn **dưới 80 đô la** và **không cần người gán
nhãn**.

---

## Slide 11 - CH2: kết quả chính (10:15, trang 15)

> **Về hiệu năng mô hình (CH2):** Trên 655 task chính thức của WebArena, mô hình sau
> fine-tune đạt tỷ lệ thành công **24,6%**, tăng **+11,3 điểm phần trăm** so với mức
> **13,3%** của chính mô hình nền chưa fine-tune.
>
> Vì hai mô hình được đo trên cùng tập đề thi và cùng bộ chấm, chúng em dùng **kiểm
> định thống kê McNemar theo cặp**: có tới **100 task chỉ mô hình sau fine-tune giải được**
> (so với 26 task của mô hình nền), đạt ý nghĩa thống kê cao với $p < 0{,}001$.
>
> Mức tăng này đạt ý nghĩa thống kê trên **toàn bộ 4/4 website** ($p \le 0{,}011$), trong
> đó Reddit có mức tăng ấn tượng nhất từ 6,6% lên 34,0%.
>
> `[lược nếu trễ]` Cơ sở dữ liệu của cả bốn website đều được khôi phục nguyên trạng trước
> mỗi lượt đo để đảm bảo không bị ảnh hưởng chéo giữa các lần chạy.

**Câu chốt:** so sánh với **chính mô hình nền trong cùng điều kiện** — đây là phép đo
sạch nhất khóa luận có.

---

## Slide 12 - CH2-CH3: phần tăng thuộc về năng lực nào (11:30, trang 16)

> Slide này trả lời câu hỏi cốt lõi: *Mô hình tiến bộ nhờ học đúng cú pháp hay thực sự
> biết cách suy luận hành động?*
>
> Trước hết, mô hình nền bị lỗi **hỏng định dạng đầu ra** (sinh câu chữ lan man hoặc sai
> cú pháp lệnh Python) ở **170 trên 655 phiên (26,0%)**. Sau khi fine-tune, tỷ lệ này
> giảm triệt để xuống chỉ còn **4 phiên (0,6%)**.
>
> Để đánh giá khách quan, chúng em bóc tách riêng trên **485 task mà mô hình nền không bị
> lỗi cú pháp**: tỷ lệ giải thành công của mô hình sau fine-tune vẫn tăng từ **17,9% lên
> 23,5% ($p = 0{,}003$)**. Điều này chứng minh tập dữ liệu tự sinh giúp mô hình cải thiện
> **cả hai năng lực**: vừa làm chủ giao diện hành động, vừa nâng cao khả năng lựa chọn
> đúng quyết định.
>
> **Định vị hệ thống (CH3):** Kết quả 24,6% vượt qua NNetNav-7B (19,1%), GPT-4o-mini
> (20,0%) và đạt mức **tương đương** với công trình SOTA Go-Browse-7B (22,6%, trong khoảng
> tin cậy $\pm 3{,}3\%$), nhưng với chi phí thu thập rẻ hơn 3,3 lần.

**Câu chốt:** phần tăng **không chỉ** là học đúng cú pháp; nhóm 485 task đã chứng minh
điều đó với p = 0,003.

**Tránh:** **không nói "vượt Go-Browse" hay "dẫn đầu"**. Quyển ghi rõ phát biểu đúng là
*ngang*; nói quá ở đây là tự tạo mâu thuẫn với chính báo cáo.

---

## Slide 13 - Demo (12:45, trang 17)

> Đây là video minh họa mô hình sau fine-tune giải trực tiếp một task WebArena thật.
>
> - **Đầu vào tinh gọn:** Mỗi bước mô hình chỉ nhận URL và cây trợ năng (AXTree) rút
>   gọn — **không dùng ảnh chụp màn hình**.
> - **Suy luận chuẩn xác:** Mô hình sinh ra cặp suy nghĩ (*thought*) phân tích tình huống
>   và hành động (*action*) tương ứng để thực thi trên trình duyệt.
>
> *(Chạy video. Chỉ tay vào màn hình: đây là bước agent đọc cây giao diện, suy luận tìm
> nút bấm, thao tác điền form/chuyển trang, và bước kết thúc khi tác vụ hoàn thành.)*
>
> Toàn bộ quá trình suy luận này chạy cục bộ trên một GPU, không gửi dữ liệu ra ngoài,
> và kết quả được chính benchmark WebArena xác nhận thành công.

**Cue kỹ thuật:** mở video trước ở tab riêng, **âm lượng = 0**. Chạy xong quay lại
trang 19 (slide 14). Nếu video lỗi: mô tả bằng lời trong 20 giây rồi đi tiếp — đừng sửa
trên bục.

---

## Slide 14 - Kết luận (14:00, trang 19)

> Tóm lại, khóa luận đã hoàn thành một pipeline khép kín từ khám phá website đến huấn
> luyện mô hình, thu được 146 kỹ năng, 57 operator, tạo ra tập dữ liệu 1760 trajectory
> sạch và nâng tỷ lệ thành công của mô hình 9B từ **13,3% lên 24,6%** trên WebArena hoàn
> toàn tự động với chi phí dưới 80 USD.
>
> Nhóm cũng thẳng thắn nhìn nhận hai hạn chế:
> 1. Tần suất ghép chuỗi operator sinh semantic task còn thưa (12/142 task).
> 2. **Thực nghiệm bóc tách (ablation study)** so sánh trực tiếp khám phá theo đồ thị
>    với khám phá phẳng vẫn là hướng cần thực hiện tiếp theo do giới hạn tài nguyên.
> 3. Về **phạm vi**: đóng góp là chuyên biệt hóa theo từng website; tổng quát hóa sang
>    ứng dụng khác (cross-app) nằm ngoài phạm vi khóa luận — và như PL1 cho thấy, đó là
>    bài toán hiện chưa ai giải được.
>
> Hướng phát triển tiếp theo gồm: bổ sung cơ chế tự phục hồi sau lỗi tương tác, khai thác
> dữ liệu thất bại bằng học tăng cường (RL/DPO), và chưng cất tri thức xuống các SLM siêu
> nhẹ 1–3B.
>
> Em xin kết thúc phần trình bày tại đây và kính mong nhận được câu hỏi, góp ý từ Hội đồng.

**Câu chốt:** chủ động nêu hạn chế trước khi bị hỏi — đặc biệt là ablation chưa chạy,
và nhắc lại phạm vi để không ai hiểu nhầm là nhóm hứa một agent vạn năng.

---

## Phụ lục PL1–PL8: câu hỏi nào bật trang nào

| Slide | Trang | Nội dung | Bật khi được hỏi về |
|---|---|---|---|
| PL1 | 22 | Tính hợp lệ của phép đánh giá | "Explore rồi test trên cùng app thì có hợp lệ không?" |
| PL2 | 23 | Hướng đến ai; pipeline mới là thứ tổng quát | "Có phải muốn model generalize cho mọi trang không?" |
| PL3 | 24 | Task khả thi, ngân sách bước, tiêu chuẩn hoàn thành | "Task LLM đề xuất có thật không?", "Sao 25 bước?", "Sao biết đã xong?" |
| PL4 | 25 | Bốn CH: số liệu và mức độ trả lời | "Thực nghiệm trả lời được mục tiêu chưa?" |
| PL5 | 26 | Chi phí chi tiết | "Chi phí đã tính đủ chưa?" |
| PL6 | 27 | Frontier hai tầng | "Khám phá không bị lạc bằng cách nào?" |
| PL7 | 28 | Nguyên nhân thất bại; đặc tính hai mô hình | "Điểm nghẽn còn lại ở đâu?" |
| PL8 | 29 | Thêm dữ liệu; đổi mô hình nền | "Thêm dữ liệu nữa có tốt hơn không?", "Sao không dùng mô hình khác?" |

---

## Câu hỏi dự kiến và hướng trả lời

### A. Sáu câu thầy phản biện đã hỏi

| Câu hỏi | Bật | Hướng trả lời |
|---|---|---|
| Explore trên app của họ rồi test bằng bộ test của họ trên chính app đó có hợp lệ không? Phải test app khác cùng lĩnh vực chứ? | **PL1** | Pipeline **chưa từng nhìn thấy** 655 task benchmark — task huấn luyện do agent tự đề xuất từ giao diện; CSDL khôi phục nguyên bản trước mỗi đợt đo; không trajectory nào được dùng lại lúc chấm. Cùng-website là **giao thức chuẩn** của cả dòng nghiên cứu: Go-Browse cũng khám phá 20 URL mỗi domain của WebArena rồi chấm trên chính 812 task WebArena. Còn test "app khác" là bài toán **ngoài miền** — chưa ai giải được: trên Online-Mind2Web, Go-Browse-7B chỉ 5,33% và NNetNav-7B 4,00%, đều thua GPT-4o-mini 9,33%. |
| Động lực hướng đến ai? Có phải muốn một model generalize cho mọi trang cùng lĩnh vực? | **Slide 3** trước, **PL2** sau | **Không.** Đích nhắm là chuyên biệt hóa cho *một* website cụ thể. Câu chốt: **thứ tổng quát hóa là pipeline, không phải model**. Người dùng đích là nhóm vận hành vài website cố định, cần agent chạy tại chỗ. Khả thi vì **dưới 20 đô la mỗi website** và không cần người gán nhãn. |
| Làm sao biết task do LLM đề xuất là hợp lý và làm được thật trên giao diện đó? | **PL3** khối 1 | Bộ đề xuất là một *agent* đọc trực tiếp cây trợ năng của trang thật, không đề xuất từ trí nhớ. Quan trọng hơn: **khả thi được chứng minh bằng thực thi, không bằng lời** — chỉ task có ít nhất một lượt giải thành công *và qua kiểm chứng* mới vào dataset. 637 task bị chính agent báo bất khả thi; 3981 lượt thử còn 2117 hợp lệ. |
| Vì sao ngân sách bước là 25? | **PL3** khối 2 | Chính xác là **15 bước cho task cục bộ, 25 cho semantic task nhiều bước**. Solver chiếm 85,5% trong 20.808 lượt gọi nên ngân sách bước *chính là* ngân sách kinh phí — đây trước hết là quyết định chi phí. Nhưng dữ liệu cho thấy nó **không bóp méo phép đo**: episode thành công có trung vị 6 bước, và **không episode nào** đạt mục tiêu rồi mới bị cắt vì hết bước. |
| Dựa vào đâu để biết task đã hoàn thành? | **PL3** khối 3 | **Ba lớp**, không phải hai: (i) solver tự khai hoặc vị từ tất định; (ii) LLM-as-Judge soi trạng thái trang đích → loại **801 lượt** báo đỗ ảo; (iii) cổng "hành động hữu hiệu" bằng mã → loại **104 trajectory**, nhóm lỗi mà judge *về nguyên tắc* không thấy được. Và 24,6% được chấm bằng **bộ chấm chính thức của WebArena**. |
| Thực nghiệm nhắm mục tiêu nào, đã trả lời được chưa? | **PL4** | CH1–CH4 đều có số liệu trả lời. Phần phải nói thật: **O2 và O4 mới hoàn thành một phần** — chỉ 12/142 semantic task từ ghép chuỗi, và **ablation đồ thị so với khám phá phẳng chưa chạy**. |

### B. Các câu khác

| Câu hỏi | Bật | Hướng trả lời |
|---|---|---|
| Đóng góp mới so với Go-Browse / NNetNav là gì? | Slide 3 | Kỹ năng được **kiểm chứng**, nâng thành operator có tiền điều kiện/kết quả, rồi **ghép chuỗi** thành task dài — hai cột mà cả hai công trình kia đều trống. Cộng thêm hai cổng chất lượng và prompt parity. |
| Sao không chứng minh được đồ thị tốt hơn khám phá phẳng? | Slide 14, PL4 | Đúng, đó là ablation quan trọng nhất và chưa chạy. Thiết kế đã có sẵn: cùng ngân sách episode và lượt gọi, chỉ đổi chiến lược khám phá. |
| Vì sao ghép chuỗi chỉ sinh 12/142 task? | Slide 7 | Cạnh operator cần kết quả khớp tiền điều kiện; sau hai cổng chống trùng lặp và kiểm chứng thực tế, đồ thị còn thưa. Hạn chế đã ghi trong Chương 5. |
| 24,6% có thấp quá không? | Slide 11 | So với chính mô hình nền cùng điều kiện là **+11,3 điểm, p<0,001, có ý nghĩa trên cả 4/4 website**. Benchmark này GPT-4 chỉ đạt ~14% khi công bố, người đạt 78%. 24,6% ngang nhóm mô hình mở tốt nhất dưới 10B. |
| Vì sao tin số liệu khi agent tự chấm? | PL3 | Không tin — ba lớp kiểm chứng; và phần đánh giá cuối dùng bộ chấm tự động của WebArena, không phải agent. |
| Chi phí đã tính đủ chưa? | PL5 | **54,21 API + 24,40 GPU = 78,61 đô la** cho cả bốn website; chưa tính hạ tầng WebArena tự host và công vận hành. Mỗi trajectory 0,0308 đô — rẻ hơn Go-Browse 3,3 lần. |
| Vì sao chọn Qwen3.5-9B mà không nhỏ hơn? | Slide 14, PL8 | Ngưỡng "chạy được trên máy phổ thông" là dưới 10B; chưng cất xuống 1–3B là hướng phát triển. PL8 có sẵn phép đo đổi mô hình nền sang Qwen-2.5-7B trên **cùng** tập dữ liệu. |
| Hệ thống này dùng để kiểm thử phần mềm được không? | PL2 | Về cấu trúc thì rất khớp: operator có **precondition/effect** chính là một dạng *test model*, semantic task là *test scenario*, trajectory đã kiểm chứng là *test script*. Nhưng phải nói rõ: khóa luận **chưa thực nghiệm** hướng này — đây là ứng dụng tiềm năng, không phải kết quả. |
| Điểm nghẽn còn lại ở đâu? | PL7 | Tầng thực thi: 85–96% episode thất bại có ít nhất một hành động bị trình duyệt từ chối. Fine-tune làm mô hình **bền bỉ** hơn chứ không **chính xác** hơn — tỷ lệ lỗi trên mỗi bước gần như không đổi. |
| Thêm dữ liệu nữa có tốt hơn không? | PL8 | Có, nhưng hiệu suất giảm nhanh: gần **gấp ba** dữ liệu của hai website chỉ đổi lấy **+2,1 điểm**. Nên hướng tiếp theo là sửa tầng thực thi, không phải nhân đôi dữ liệu. |

---

## Checklist trước khi lên

- [ ] Mở sẵn `main.pdf` ở chế độ toàn màn hình, kiểm tra nhảy được tới trang 22–29.
- [ ] Video demo mở sẵn ở tab riêng, **âm lượng 0**, đã thử phát một lần.
- [ ] Nhớ ba con số không được nói sai: **24,6% / 13,3% / +11,3 điểm**.
- [ ] Slide 2 phải nói ra chữ **"một tập website cố định"**; slide 3 phải nói chữ
      **"tiềm năng"** khi nhắc kiểm thử E2E.
- [ ] Nhớ hai chỗ **không được nói quá**: "ngang Go-Browse" (không phải *vượt*), và
      "ghép chuỗi mới khả thi" (không phải *đã đủ dày*).
- [ ] Người 2 nắm chắc mốc 8:30 — nếu người 1 trễ quá 1 phút thì lược
      `[lược nếu trễ]` ở slide 10 và 11.

---

## Nếu được 20 phút

Thêm bốn slide, theo thứ tự ưu tiên:

1. **Kéo PL7 (nguyên nhân thất bại) và PL6 (frontier hai tầng) vào phần nội dung** —
   cả hai đã dựng sẵn trong phụ lục, chỉ cần đổi chỗ.
2. **Ví dụ một semantic task** sinh từ chuỗi operator, kèm chuỗi tiền điều kiện/kết quả.
3. **Lộ trình nghiên cứu** (`fig_roadmap.pdf`, đã có trong `images/`), đặt ngay sau
   slide mục tiêu.
4. **Bài học vận hành** (Phụ lục E của quyển): chat template, prompt parity, chạy song
   song hai máy trên site sống.
