# Kịch bản trình bày — Bảo vệ KLTN HSGE

**Ngân sách:** 15 phút trình bày + 15 phút hỏi đáp (thông báo bảo vệ đợt 04/2026).
Deck có **21 trang phần nội dung** (15 slide phải nói + 1 bìa cảm ơn + 5 trang mục lục
lướt qua) và **9 trang phụ lục PL1–PL8** đặt sau trang cảm ơn, chỉ bật khi được hỏi.

**Chia hai người:** Người 1 slide 1–10 (đặt vấn đề + phương pháp), Người 2 slide 11–15
(thực nghiệm + kết luận). Điểm cắt sau slide 10, khi chuyển từ _"làm thế nào"_
sang _"đo được gì"_.

**Cách đọc kịch bản:**

- **Nói** = lời thoại, viết theo văn nói, đọc thẳng được.
- **Câu chốt** = câu duy nhất bắt buộc phải lọt tai Hội đồng ở slide đó.
- **Tránh** = chỗ dễ nói quá; nói sai một chữ ở đây là mất điểm tin cậy.
- `[lược nếu trễ]` = cắt được mà không gãy mạch.
- Cột "Trang" là **số slide hiện ở footer** (`n / 21`), không phải số trang PDF: deck
  dùng overlay nên `main.pdf` hiện có 81 trang. Nhảy nhanh thì dùng số footer.

---

## Bảng thời lượng

| Slide | Trang | Nội dung                                     | Mốc   | Thời lượng |
| ----- | ----- | -------------------------------------------- | ----- | ---------- |
| 1     | 1     | Bìa                                          | 0:00  | 0:30       |
| 2     | 4     | Bối cảnh — khoảng cách hiệu năng trên web    | 0:30  | 0:45       |
| 3     | 5     | Thách thức dữ liệu & các nghiên cứu trước    | 1:15  | 0:50       |
| 4     | 6     | Hạn chế của các phương pháp trước & bài toán | 2:05  | 0:50       |
| 5     | 7     | Giải pháp HSGE & các đóng góp chính          | 2:55  | 0:50       |
| 6     | 9     | Tổng quan pipeline HSGE                      | 3:45  | 1:10       |
| 7     | 10    | Đồ thị hai tầng                              | 4:55  | 1:00       |
| 8     | 11    | Phát hiện skill → quy nạp operator           | 5:55  | 1:10       |
| 9     | 12    | Sinh semantic task                           | 7:05  | 1:00       |
| 10    | 13    | Tinh lọc dữ liệu _(chuyển người)_            | 8:05  | 1:00       |
| 11    | 15    | Thiết lập & Câu hỏi nghiên cứu               | 9:05  | 0:55       |
| 12    | 16    | CH1 — Tự động tạo tác vụ & Quy mô dữ liệu    | 10:00 | 1:10       |
| 13    | 17    | CH2 — So sánh hiệu năng SOTA                 | 11:10 | 1:10       |
| 14    | 18    | CH2 — So sánh Base và Fine-tuning            | 12:20 | 0:50       |
| 14b   | 19    | CH3 — Hiệu quả chi phí tự sinh dữ liệu       | 13:10 | 0:40       |
| 15    | 20    | Kết luận: Đóng góp chính & Hướng phát triển  | 13:50 | 1:10       |

Phần đặt vấn đề nay trải trên **bốn** slide (2–5) thay vì hai, mỗi slide một nhịp:
bối cảnh → thách thức dữ liệu và công trình liên quan → hạn chế và bài toán → giải pháp.
Tổng phần này vẫn ~2:55; nếu trễ thì lược slide 3 xuống còn nhóm (B) và (C), và lược
đoạn ba nhóm ứng dụng ở slide 5.

Trang 3, 8, 14, 19 là mục lục đầu mỗi chương — bấm lướt, không dừng nói.
Trang 21 là trang cảm ơn; dừng ở đó và mời Hội đồng đặt câu hỏi.

---

## Slide 1 - Bìa (0:00, trang 1)

> Kính thưa Hội đồng. Em là Trương Bảo Kiệt, cùng bạn Hồ Tiến Phát, trình bày khóa
> luận _"Khám phá theo đồ thị kỹ năng phân cấp để tự động sinh dữ liệu huấn luyện cho
> tác nhân trí tuệ nhân tạo trên web"_, dưới sự hướng dẫn của PGS.TS. Nguyễn Văn Vũ.
>
> Bài trình bày gồm bốn phần: bài toán và định vị, phương pháp HSGE, kết quả thực
> nghiệm, và kết luận.

---

## Slide 2 - Bối cảnh: khoảng cách hiệu năng trên tác vụ web (0:30, trang 4)

> Kính thưa Hội đồng, sự phát triển của các **Mô hình Ngôn ngữ Lớn (LLM)** đã tạo tiền đề
> chuyển từ chatbot trả lời thụ động sang **AI Agent tự hành**, trong đó **Web Agent** là
> hướng nổi bật nhất: tác nhân nhận lệnh bằng ngôn ngữ tự nhiên rồi tự điều khiển trình
> duyệt để hoàn thành công việc — ví dụ _"vào hệ thống nội bộ kiểm tra đơn hàng và xuất
> báo cáo"_.
>
> Nhưng thực tế còn cách kỳ vọng khá xa. Trên **WebArena** — bộ chuẩn mô phỏng các website
> thật — agent dùng **GPT-4** chỉ hoàn thành **14,41%** số tác vụ, trong khi con người đạt
> **78,24%**. Nghĩa là năng lực _tổng quát_ của một mô hình lớn vẫn chưa đủ; muốn dùng
> được, phải **chuyên biệt hóa** theo đúng môi trường triển khai.
>
> Thêm nữa, cách phổ biến hiện nay là gọi **API của LLM lớn thương mại**, và cách này có ba
> rào cản: chi phí tích lũy theo từng bước thao tác, độ trễ mạng, và quan trọng nhất là
> **rủi ro riêng tư** khi dữ liệu nội bộ phải gửi ra ngoài.
>
> Hướng bền vững là dùng **mô hình ngôn ngữ nhỏ, dưới 10 tỷ tham số**, chạy cục bộ ngay tại
> tổ chức. Nhưng mô hình nhỏ vốn không biết cách vận hành trên một website lạ, nên **bắt
> buộc phải fine-tune**. Và đó là lúc nút thắt dịch chuyển: từ chỗ _thiếu mô hình đủ mạnh_
> sang chỗ **thiếu dữ liệu huấn luyện cho đúng website đó**.

**Câu chốt:** Nút thắt của Web Agent không nằm ở kiến trúc mô hình, mà nằm ở **dữ liệu tương tác thực tế cho từng website cụ thể**.

**Tránh:** không nói "LLM không làm được web" — con số đúng là _14,41% so với 78,24% của
con người trên WebArena_, tức là làm được nhưng còn xa mức dùng được.

---

## Slide 3 - Thách thức dữ liệu và các nghiên cứu trước (1:15, trang 5)

> Vậy dữ liệu huấn luyện — tức các **trajectory**, chuỗi thao tác bấm, gõ, chuyển trang
> thành công — lấy ở đâu ra?
>
> Cách cổ điển là **gán nhãn thủ công**, và nó rất đắt: hệ thống AutoWebGLM cần **20 người
> gán nhãn làm việc suốt một tháng** cho khoảng mười nghìn trajectory. Dữ liệu tổng hợp thì
> rẻ hơn hẳn — Synatra cho thấy mỗi mẫu chỉ tốn khoảng **3%** chi phí một mẫu do người tạo
> — nhưng rẻ mà không bám môi trường thật thì cũng không dùng được: mô hình huấn luyện từ
> tài liệu ngoại tuyến chỉ đạt **6%** trên WebArena, so với **16%** của phương pháp học
> trực tiếp từ chính website đích.
>
> Cột phải là ba hướng nghiên cứu trước đây. **Nhóm (A) — tri thức gián tiếp:** Synatra và
> AgentTrek chuyển các bài hướng dẫn trên Internet thành mẫu huấn luyện, AgentTrek còn
> replay lại trên trình duyệt thật để kiểm chứng.
>
> **Nhóm (B) — bộ nhớ và kỹ năng phục vụ lúc suy luận:** AWM trích các workflow lặp lại từ
> lịch sử rồi nhét vào prompt, nâng tỷ lệ hoàn thành trên WebArena từ **23,5% lên 35,5%**;
> SkillWeaver để agent tự khám phá và đóng gói kỹ năng thành các API tái sử dụng được.
>
> **Nhóm (C) — tự khám phá để sinh dữ liệu huấn luyện cho mô hình nhỏ**, gần khóa luận nhất:
> NNetNav khám phá website rồi gán nhãn hồi tố, mô hình 8B đạt **16,3%**; Go-Browse mô hình
> hóa việc khám phá thành **bài toán tìm kiếm trên đồ thị** website, mô hình 7B đạt
> **21,7%** — mức tốt nhất của phân khúc dưới 10 tỷ tham số tại thời điểm công bố.
>
> Kết quả của Go-Browse củng cố đúng tiền đề của khóa luận: **khám phá có cấu trúc cho dữ
> liệu tốt hơn các chuỗi rollout rời rạc**.

**Câu chốt:** Ba hướng trước đã chứng minh **tự động sinh dữ liệu là khả thi**, và hướng
khám phá có cấu trúc là hướng cho kết quả tốt nhất.

`[lược nếu trễ]` Bỏ nhóm (A), vào thẳng (B) và (C).

---

## Slide 4 - Hạn chế của các phương pháp trước và bài toán đặt ra (2:05, trang 6)

> Nhưng mỗi hướng đều còn một khoảng trống.
>
> **Nhóm (A)** bị chặn bởi đúng một thứ: lượng tài liệu hướng dẫn sẵn có. Quy trình nội bộ
> chưa ai viết ra, hay website vừa triển khai, thì nằm ngoài tầm với.
>
> **Nhóm (B)** — kỹ năng chỉ sống trong prompt của một mô hình lớn, **không hề cập nhật
> tham số** của mô hình, nên không giúp gì cho bài toán mô hình nhỏ chạy cục bộ. Thêm nữa,
> workflow của AWM là chuỗi bước tuyến tính, **không có tiền điều kiện và kết quả tường
> minh**, nên không thể ghép chuỗi bằng thuật toán lập kế hoạch; và khâu kiểm chứng chỉ xét
> _kết quả episode_, chứ **không chạy lại** kỹ năng để xác nhận nó thật sự tái dùng được.
>
> **Nhóm (C)** — NNetNav **không tích lũy** tri thức giữa các episode, mỗi lần lại bắt đầu
> từ con số không. Go-Browse có đồ thị, nhưng **chỉ một tầng**: node là URL, cạnh là
> trajectory, phía trên không có tầng trừu tượng nào. Hệ quả là bộ đề xuất task của
> Go-Browse được yêu cầu tường minh chỉ tìm những việc **làm được ngay trên trang hiện tại**
> — task sinh ra bị bó trong một trang.
>
> Từ đó, câu hỏi bài toán của khóa luận là: **Làm sao tận dụng LLM để tự động sinh dữ liệu
> huấn luyện trên một tập website mục tiêu, hoàn toàn không cần nhãn con người, nhằm giúp mô
> hình nhỏ chạy cục bộ đạt hiệu năng tiệm cận hoặc vượt LLM lớn trên chính các trang đó?**
>
> `[lược nếu trễ]` Bốn thách thức cốt lõi phải vượt qua chính là bốn hạn chế vừa nêu: chi
> phí gán nhãn tay; tri thức môi trường không tích lũy được; **dương tính giả khi agent tự
> đánh giá**; và việc ghép các hành động rời rạc thành tác vụ đa bước có ý nghĩa nghiệp vụ.
>
> Khung đỏ cuối slide là khoảng trống nghiên cứu: chưa công trình nào nối trọn ba khâu
> **kiểm chứng kỹ năng → ghép thành tác vụ dài → dùng chính dữ liệu đó huấn luyện mô hình
> nhỏ**.

**Câu chốt:** Khoảng trống không phải là "thu được nhiều dữ liệu hơn", mà là **thiếu một
tầng kỹ năng đã kiểm chứng, ghép chuỗi được**.

**Tránh:** không nói các công trình trước "sai" hay "kém" — cách nói đúng là mỗi hướng
giải quyết _một phần_ của bài toán, và ba khâu đó chưa được nối liền.

---

## Slide 5 - Giải pháp HSGE và các đóng góp chính (2:55, trang 7)

> Để giải quyết bài toán trên, khóa luận đề xuất giải pháp **HSGE (Hierarchical Skill-Graph Exploration)** nhằm tự động hóa toàn chu trình từ website đến mô hình SLM cục bộ.
>
> Về **đóng góp khoa học (kiến trúc & thuật toán)** ở cột trái:
>
> - Thứ nhất, đề xuất **mô hình biểu diễn đồ thị hai tầng**: kết hợp State Graph ghi vết duyệt web ở tầng thấp với Operator Graph biểu diễn kỹ năng ở tầng cao.
> - Thứ hai, xây dựng **thuật toán quy nạp operator và ghép chuỗi đa bước**: tự động trích xuất các kỹ năng lặp lại, kiểm chứng và ghép chuỗi thành tác vụ có ngữ nghĩa.
>
> Về **đóng góp thực tiễn (sản phẩm & dữ liệu)** ở cột phải, đề tài bàn giao **năm sản phẩm chính**:
>
> - Thứ nhất, **Pipeline HSGE**: hệ thống tự động khám phá, quy nạp operator và sinh tác vụ có ngữ nghĩa trên website thật.
> - Thứ hai, **Bộ dữ liệu 9.007 mẫu SFT sạch** (từ 1.760 trajectory hợp lệ) trên 4 website WebArena mà hoàn toàn không cần nhãn người.
> - Thứ ba, **Mô hình HSGE-9B chạy cục bộ đạt 24,6%** (vượt GPT-4o-mini và đạt SOTA phân khúc dưới 10B) cùng kiểm chứng độc lập trên mô hình nền Qwen-2.5-7B.
> - Thứ tư, **Pipeline đánh giá trên benchmark WebArena**: dùng chung cấu hình prompt và bộ chấm chính thức của benchmark.
> - Thứ năm, **Báo cáo các bài học kinh nghiệm**: đúc kết 14 thực hành kỹ thuật thực tiễn trải trên 5 mảng triển khai.
>
> Về **tính khả thi kinh tế**: chi phí gọi API khám phá chỉ **0,0308 USD mỗi trajectory thành công**, **rẻ hơn 3,3 lần so với Go-Browse** (hệ thống SOTA cùng phân khúc).
>
> Khung dưới bên phải định vị rõ phạm vi đề tài: đầu vào là một website đang vận hành (chưa có nhãn); đầu ra là một agent chuyên biệt chạy cục bộ cho website đó. Nói cách khác, **thứ tổng quát hóa ở đây là pipeline, không phải model**. Pipeline có thể áp dụng cho website bất kỳ để sinh ra agent tương ứng.

**Câu chốt:** đóng góp nằm ở **tầng trừu tượng thứ hai** — kỹ năng đã kiểm chứng, ghép chuỗi được — chứ không phải ở việc thu nhiều dữ liệu hơn.

**Câu chốt phụ (bắt buộc nói, đừng đợi bị hỏi):** Phạm vi của nghiên cứu là **chuyên biệt hóa theo website**, không phải agent vạn năng. Thứ tổng quát hóa ở đây là **pipeline khám phá tự động**, không phải là một mô hình duy nhất.

**Tránh:** **không nói "khóa luận làm công cụ kiểm thử tự động"**. Bắt buộc có chữ _"tiềm năng, chưa thực nghiệm"_ trong cùng một câu — quyển báo cáo không có phần kiểm thử.

`[lược nếu trễ]` Bỏ đoạn ba nhóm ứng dụng, chỉ giữ câu "tổng quát hóa là pipeline, không phải model".

---

## Slide 6 - Tổng quan pipeline HSGE (3:45, trang 9)

> Đây là toàn bộ phương pháp HSGE trên một hình, vận hành như một vòng lặp khép kín, tự động hoàn toàn.
>
> Bắt đầu từ **Frontier** — hàng đợi lưu các trang web cần khám phá. Chọn một trang, một agent đề xuất các tác vụ làm được ngay trên trang đó, rồi solver thử thao tác trên trình duyệt thật. Những trajectory giải thành công được đưa vào khâu phát hiện kỹ năng: cắt thành đoạn nhỏ, gom cụm các thao tác tương đồng, trừu tượng hóa thành thẻ kỹ năng, rồi quy nạp thành **Operator** có tiền điều kiện (Precondition) và kết quả (Effect).
>
> Các operator này được ghép chuỗi với nhau để sinh ra các **Tác vụ có ngữ nghĩa (Semantic Task)** — tức tác vụ nhiều bước có ý nghĩa nghiệp vụ thực tế. Toàn bộ dữ liệu thu được đi qua hai cổng lọc chất lượng trực tuyến trước khi trở thành tập huấn luyện SFT. Và mỗi trang mới phát hiện lại quay về frontier để tiếp tục mở rộng.

**Câu chốt:** không phải thu thập rời rạc, mà **tích lũy tri thức có cấu trúc rồi mới khai thác lại**.

---

## Slide 7 - Đồ thị hai tầng (4:55, trang 10)

> Tri thức khám phá được lưu trữ trong một đồ thị hai tầng.
>
> - **Tầng thấp (State Graph):** Lưu vết duyệt web thực tế gồm các trang đã ghé thăm và hành động chuyển giữa chúng.
> - **Tầng cao (Operator Graph):** Mỗi operator là một kỹ năng chuẩn hóa với điều kiện đầu vào (Precondition) và kết quả đầu ra (Effect). Hai operator được nối với nhau khi **kết quả của bước trước thỏa mãn điều kiện đầu vào của bước sau**.
>
> _Ví dụ trực quan:_ Kỹ năng "Tìm kiếm sản phẩm" sinh ra kết quả "Đang ở trang chi tiết". Kết quả này khớp đúng điều kiện cần của kỹ năng "Thêm vào giỏ hàng" $\rightarrow$ Hệ thống tự động ghép nối thành tác vụ mua hàng hoàn chỉnh.
>
> Nhờ cấu trúc này, tri thức thu được có tính **tái sử dụng và tái tổ hợp**, giúp sinh ra vô số tác vụ dài hạn có ngữ nghĩa mà không cần người viết kịch bản.

**Câu chốt:** tầng cao là thứ phân biệt HSGE với Go-Browse — bên đó chỉ có tầng thấp.

---

## Slide 8 - Phát hiện skill và quy nạp operator (5:55, trang 11)

> Khâu phát hiện kỹ năng chỉ chạy trên trajectory của các tác vụ **đã giải thành công**, qua bốn bước:
>
> 1. **Phân cắt:** Cắt chuỗi thao tác dựa trên thay đổi URL và sự biến động của **cây trợ năng (AXTree)** — tức bản rút gọn văn bản của giao diện web chỉ chứa các nút bấm, ô nhập liệu có thể tương tác.
> 2. **Gom cụm:** Gom các đoạn thao tác có chức năng tương tự nhau.
> 3. **Trừu tượng hóa:** Rút trích thành thẻ kỹ năng có tham số hóa (như từ khóa tìm kiếm).
> 4. **Kiểm chứng:** Cho chạy thử lại trong ngữ cảnh mới để xác nhận tính dùng lại được.
>
> Để nâng kỹ năng lên thành Operator, hệ thống áp dụng hai cổng chặn: **cổng chống trùng lặp** loại bỏ các mệnh đề vô nghĩa, và **cổng kiểm chứng thực tế (grounding)** gỡ bỏ các kết quả không đúng trên phần lớn các lần chạy.
>
> `[lược nếu trễ]` Nhờ sự khắt khe này, từ 146 kỹ năng phát hiện được, hệ thống chắt lọc ra 57 operator thực sự chuẩn xác.

**Câu chốt:** "đã kiểm chứng" ở đây là **có cổng chặn đo được**, không phải nhãn tự phong.

---

## Slide 9 - Sinh tác vụ có ngữ nghĩa (7:05, trang 12)

> **Tác vụ có ngữ nghĩa (Semantic Task)** — tức tác vụ nhiều bước có ngữ nghĩa nghiệp vụ hoàn chỉnh — được sinh từ hai nguồn:
>
> - **Từ dưới lên (Bottom-up):** Ghép chuỗi operator bằng duyệt đồ thị, mỗi chuỗi từ hai operator trở lên sẽ tạo thành một nhiệm vụ dài kèm câu lệnh ngôn ngữ tự nhiên.
> - **Từ trên xuống (Top-down):** Gợi ý từ năng lực tổng quan của website (như chức năng quản trị, đăng bài, mua sắm) khi đồ thị còn thưa.
>
> Về số liệu thực tế: trong **142 tác vụ có ngữ nghĩa** đã thực thi, **130 tác vụ đến từ seed và 12 tác vụ đến từ ghép chuỗi operator**, đạt 71 tác vụ giải thành công (tỷ lệ 50,0%, xấp xỉ mức 47,6% của nhóm tác vụ LOCAL đơn trang). Kết quả này chứng minh cơ chế ghép chuỗi hoạt động đúng thiết kế, dù ở giai đoạn đầu tần suất ghép còn thưa.

**Câu chốt:** cơ chế ghép chuỗi được chứng minh là **khả thi**, chưa chứng minh được là **đủ dày** để làm nguồn dữ liệu chính.

**Tránh:** đừng nói "tác vụ có ngữ nghĩa chủ yếu sinh từ đồ thị operator" — số liệu ngược lại, và Hội đồng có thể đã đọc Chương 5.

---

## Slide 10 - Kiểm định trực tuyến & Đóng gói SFT (8:05, trang 13) — _điểm chuyển người trình bày_

> Nguyên tắc chất lượng cốt lõi: **không bao giờ tin vào lời tự khai hoàn thành của agent.**
>
> Điểm khác biệt quan trọng là toàn bộ việc kiểm soát chất lượng được thực hiện **trực tuyến ngay trong vòng lặp khám phá**, không cần chờ đến khâu hậu kiểm ngoại tuyến:
>
> 1. **Inline LLM Judge:** Mỗi khi agent tự tuyên bố xong, LLM Judge độc lập lập tức chấm lại trên trạng thái trang đích, loại bỏ ngay **801 episode (chiếm $\approx 27\%$)** dương tính giả khi tự đánh giá (false positive) từ nguồn.
> 2. **Cổng hành động hữu hiệu (Effective Action):** Viết bằng mã để chặn các trường hợp agent báo xong nhưng trang web không hề thay đổi trạng thái — loại bỏ thêm 104 trajectory không tạo ra thay đổi trạng thái (tương ứng 279 mẫu) mà Judge không thấy được.
>
> Nhờ dữ liệu trong kho `episodes/` đã hoàn toàn sạch từ quá trình khám phá, hệ thống tiến hành **đóng gói trực tiếp (Direct Build)** thành 1.760 trajectory sạch, tương ứng **8.554 mẫu train và 453 mẫu val** (tổng cộng 9.007 mẫu SFT) mà không cần thêm bất kỳ khâu lọc hậu kỳ nào.
>
> Dữ liệu được đóng gói theo nguyên tắc **Prompt Parity**: mẫu câu lệnh lúc huấn luyện trùng khớp từng byte với câu lệnh solver nhìn thấy lúc chạy thật, chia train/val theo cấp task đảm bảo **0 mục tiêu trùng lặp**.

**Câu chốt:** kiểm định trực tuyến ngay từ nguồn giúp dữ liệu sạch tuyệt đối, cho phép đóng gói trực tiếp tập SFT để huấn luyện mô hình.

---

## Slide 11 - Thiết lập thực nghiệm (9:05, trang 15)

> Thực nghiệm được tiến hành trên bốn website thuộc benchmark chuẩn quốc tế **WebArena**
> do nhóm tự triển khai (self-hosted): Shopping, Shopping Admin, GitLab và Reddit.

## Slide 11 - Thiết lập & Câu hỏi nghiên cứu (9:05, trang 15)

> _(Bấm Click 1 — hiện Cột trái: 3 Câu hỏi nghiên cứu)_
> Đi vào phần thực nghiệm, nghiên cứu tập trung giải đáp **3 câu hỏi cốt lõi (RQ)**:
>
> - **CH1:** Hệ thống có tự động sinh ra các tác vụ có ý nghĩa và quy mô dữ liệu chất lượng hay không?
> - **CH2:** Năng lực của SLM sau khi fine-tune được cải thiện thế nào so với mô hình nền và các công trình SOTA?
> - **CH3:** Chu trình tự động sinh dữ liệu đạt hiệu quả chi phí kinh tế ra sao?
>
> _(Bấm Click 2 — hiện Cột phải: Thiết lập thực nghiệm)_
> Để trả lời 3 câu hỏi này, thiết lập thực nghiệm được chuẩn hóa như sau:
>
> - **Môi trường**: Đánh giá trên benchmark **WebArena** với **655 tác vụ chính thức** thuộc 4 website (Shopping, Admin, Reddit, GitLab).
> - **Lý do loại trừ miền Map**: Benchmark WebArena gốc có 812 task trên 5 website. Nhóm quyết định **bỏ miền Map (OpenStreetMap, 157 task)** vì Map là giao diện bản đồ tương tác dạng Canvas / tọa độ pixel, không có cấu trúc cây DOM / Accessibility Tree tiêu chuẩn và không có các thao tác form / nhập liệu truyền thống. 4 website còn lại đại diện cho 4 miền dịch vụ web tiêu chuẩn sống động và phức tạp nhất.
> - **Hạ tầng & Vận hành**: 4 website được self-host bằng Docker container trên máy chủ nội bộ và mở tunnel qua Cloudflare quick tunnel. Do môi trường có *trạng thái dùng chung và bị biến đổi*, mọi lượt khám phá/đánh giá đều chạy đơn luồng và CSDL được khôi phục nguyên bản trước mỗi lượt đo.
> - **Mô hình & Huấn luyện**: Tinh chỉnh mô hình nền **Qwen3.5-9B** bằng LoRA / QLoRA qua 3 epoch (1.119 bước huấn luyện trên GPU A100/H100 thuê từ vast.ai), tạo thành **HSGE-9B**.
> - **Tiêu chí đánh giá**: Sử dụng **bộ chấm tự động chính thức của WebArena** (kiểm tra trạng thái CSDL hoặc chuỗi trả về) với ngân sách 15 bước để đo **Task Success Rate (Task SR)** hoàn toàn khách quan.

**Câu chốt:** Phép đo sử dụng bộ đề xuất và **bộ chấm chính thức của WebArena** trên 4 website tiêu chuẩn để đảm bảo tính khách quan hoàn toàn.

---

## Slide 12 - CH1: Tự động tạo tác vụ & Quy mô dữ liệu (10:00, trang 16)

> Trả lời **CH1**, phễu khám phá tự động của HSGE mang lại các kết quả quy mô ấn tượng:
>
> - **Quy mô khám phá & Tri thức**: Hệ thống tự động duyệt **4 website, 455 URL**, thực hiện **3.981 lượt tương tác thử** (khoảng 21 giờ / website), thu hoạch **146 skills** và quy nạp **57 operators**.
> - **Sinh tác vụ**: Tự động tạo và kiểm chứng **142 semantic task** đa bước bằng cách ghép chuỗi operator.
> - **Cổng lọc chất lượng (Bài học thực nghiệm cốt lõi)**: Khi chạy thực nghiệm thực tế, nhóm phát hiện LLM có xu hướng "nói dối" hoặc tưởng mình đã làm xong (dương tính giả). HSGE thiết lập 2 chốt chặn nghiêm ngặt:
>   1. **LLM-as-Judge**: Kiểm tra điều kiện tiền/hậu đề xuất, loại bỏ **801 lượt (27,4%)** dương tính giả.
>   2. **Effective Action Gate**: Loại bỏ **104 trajectory** thực thi lệnh nhưng không làm biến đổi trang DOM.
> - **Kết quả thu hoạch**: Thu được **1.760 trajectory sạch** (đạt tỷ lệ hợp lệ 53,2%), đóng gói thành **9.007 mẫu SFT** (8.554 train / 453 validation) hoàn toàn tự động mà **không cần 1 giờ gán nhãn thủ công nào từ con người**.

**Câu chốt:** HSGE tự động sinh tác vụ có ý nghĩa và thu hoạch 9.007 mẫu SFT sạch hoàn toàn không cần nhãn người.

---

## Slide 13 - CH2: So sánh hiệu năng với các hệ thống SOTA (11:10, trang 17)

> Trả lời **CH2 (phần 1)**, Bảng 2 đối chiếu kết quả của HSGE với các mô hình SOTA trên 655 tác vụ chính thức của WebArena:
>
> - **Mô hình thương mại đóng (để tham chiếu)**: GPT-4o-mini đạt **20,0%**, GPT-4o đạt **37,5%**.
> - **Các mô hình mở cùng phân khúc (<10B)**: Mô hình nền Qwen-2.5-7B chỉ đạt **8,3%**; hai hệ thống SOTA công bố gần đây là NNetNav-7B đạt **19,1%** và Go-Browse-7B đạt **22,6%**.
> - **Phân tích bản chất khác biệt về Mô hình nền (Base Model)**:
>   1. *Tính chất không kiểm soát của phép so sánh*: So sánh 24,6% của HSGE-9B với 22,6% của Go-Browse-7B **không phải là phép so sánh có kiểm soát tuyệt đối**, vì hai hệ thống dùng mô hình nền gốc khác nhau. Qwen3.5-9B có Base SR là **13,3%** (cao hơn 5 đpt so với Qwen-2.5-7B Base 8,3%). Một phần khoảng cách chắc chắn thuộc về năng lực sẵn có của mô hình nền 9B thế hệ mới hơn.
>   2. *Thực nghiệm chứng minh giá trị tập dữ liệu (HSGE-7B)*: Để tách biệt đóng góp của dữ liệu, nhóm đem đúng 8.554 mẫu HSGE fine-tune trên **Qwen-2.5-7B** (được dòng dưới cùng Bảng 2). Kết quả nâng Qwen-2.5-7B từ 8,3% lên **16,5%** (+8,2 đpt, tăng gần gấp đôi).
>   3. *Trích xuất nguyên nhân từ Trace thực nghiệm*: Trace cho thấy 58–60% phiên trượt của bản 7B chứa phản hồi `report_infeasible` viết trần (thiếu JSON wrapper) bị bộ phân giải loại bỏ. Do đó con số 16,5% là một **cận dưới bị hạ thấp bởi parser**.
> - **Kết luận về hiệu năng**: Tập dữ liệu HSGE chứng minh hiệu quả cải thiện trên **cả hai mô hình nền** (7B và 9B). Mô hình HSGE-9B đạt **24,6%**, tăng **+11,3 đpt** so với nền 9B gốc, đạt hiệu năng **ngang hàng SOTA phân khúc mở <10B** (dẫn đầu ở Shopping 28,3% và Reddit 34,0%) dù quy mô dữ liệu nhỏ hơn 5 lần so với Go-Browse (8,5k mẫu vs 40k mẫu).

**Câu chốt:** Tập dữ liệu HSGE nâng cao năng lực cho cả hai mô hình nền, giúp HSGE-9B đạt **24,6%** (ngang hàng SOTA phân khúc <10B) với dung lượng dữ liệu tinh gọn hơn 5 lần.

**Tránh phát biểu:** Không dùng từ "vượt trội tuyệt đối" so với Go-Browse — quyển báo cáo nêu rõ hai mô hình gốc khác nhau (Qwen3.5-9B vs Qwen-2.5-7B) và quy mô dữ liệu chênh lệch, phát biểu chuẩn xác là *ngang hàng / tương đương SOTA*.

---

## Slide 14 - CH2: So sánh mô hình nền (Base) và fine-tuning theo Website (12:20, trang 18)

> Trả lời **CH2 (phần 2)**, slide này bóc tách bản chất cải thiện năng lực của mô hình sau fine-tune:
>
> - **Hiệu quả theo từng Website & Kiểm định McNemar**: Cả 4/4 website đều ghi nhận mức tăng trưởng vượt trội có ý nghĩa thống kê ($p \le 0{,}011$), đặc biệt Reddit tăng từ 6,6% lên **34,0%** ($p < 0{,}001$). Có **100 task độc quyền** chỉ HSGE-9B mới giải được (so với 26 task Base giải được).
> - **Bóc tách 2 nguồn cải thiện năng lực (Câu chuyện thực nghiệm cốt lõi)**:
>   *Khi nhìn số liệu tăng từ 13,3% lên 24,6%, câu hỏi đặt ra là: Mô hình giỏi hơn thật hay chỉ vì nó bớt vô kỷ luật cú pháp?*
>   1. **Kỷ luật cú pháp**: Mô hình nền Base bị lỗi định dạng đầu ra (sinh câu vần vè lan man hoặc sai lệnh Python) ở **170/655 phiên (26,0%)**. Fine-tune giúp triệt tiêu lỗi này xuống còn **4 phiên (0,6%)**.
>   2. **Năng lực ra quyết định (Bằng chứng thuyết phục)**: Để loại trừ yếu tố cú pháp, nhóm bóc tách riêng **485 task mà mô hình nền vốn đã xuất đúng cú pháp**. Trên tập này, Task SR của HSGE-9B vẫn tăng từ **17,9% lên 23,5% ($p = 0{,}003$)**.
>
> Điều này chứng minh fine-tuning bằng dữ liệu tự sinh không chỉ dạy mô hình học thuộc cú pháp lệnh, mà thực sự nâng cao **khả năng suy luận và lựa chọn đúng hành động**.

**Câu chốt:** Fine-tuning làm chủ cả kỷ luật cú pháp lẫn năng lực lựa chọn hành động ($p = 0{,}003$).

---

## Slide 14b - CH3: Hiệu quả chi phí trong tự động tạo dữ liệu (13:10, trang 19)

> Trả lời **CH3**, slide này phân tích hiệu quả kinh tế trong quá trình tự động sinh dữ liệu:
>
> - **Câu chuyện tối ưu chi phí thực tế**: Ban đầu nếu dùng hoàn toàn GPT-4o cho mọi vai trò, chi phí sẽ hàng trăm USD. Nhóm đã phân tách vai trò thông minh: Solver (gợi ý bước hành động — chiếm **85,5%** trong tổng 20.808 lời gọi LLM) được dồn sang mô hình chi phí thấp **GPT-5.6-luna** (0,20 USD/triệu token vào, rẻ hơn 12 lần so với GPT-4o).
> - **Chi phí API toàn chu trình**: Tổng chi phí gọi API LLM đóng cho cả 4 website chỉ tốn **54,21 USD** (chưa tới **14 USD / website**).
> - **Đơn giá / Trajectory**: Trung bình mỗi trajectory thành công sạch chỉ tốn **0,0308 USD** (khoảng 3,1 cent, tương đương ~750 VNĐ).
> - **Chi phí GPU fine-tune**: Tốn **8,3 USD** (5 giờ 09 phút trên vast.ai H100/A100).
> - **So sánh kinh tế với Go-Browse**: Đơn giá **0,0308 USD/trajectory** của HSGE **rẻ hơn 3,3 lần** so với Go-Browse-7B ($0,1026 USD/trajectory), chứng minh tính khả thi cho các phòng thí nghiệm và tổ chức nhỏ.

**Câu chốt:** Tự động sinh dữ liệu với đơn giá 0,0308 USD/trajectory chứng minh tính khả thi kinh tế vượt trội cho các nhóm nghiên cứu và tổ chức nhỏ.

---

## Slide 15 - Kết luận: Đóng góp chính & Hướng phát triển (13:50, trang 20)

> _(Bấm Click 1 — hiện Cột trái: Đóng góp chính)_
> Tổng kết lại, khóa luận đóng góp 3 giá trị cốt lõi:
>
> - **Về Khoa học**: Đề xuất biểu diễn đồ thị 2 tầng (State Graph $\leftrightarrow$ Operator Graph) và thuật toán phát hiện skill, quy nạp operator và ghép chuỗi đa bước.
> - **Về Thực tiễn**: Cung cấp pipeline tự động hóa hoàn chỉnh, sinh **9.007 mẫu SFT**, huấn luyện **HSGE-9B đạt 24,6% Task SR** với chi phí rẻ hơn **3,3 lần** so với Go-Browse.
> - **Tài nguyên mở**: Bàn giao toàn bộ mã nguồn, bộ dataset và trọng số mô hình HSGE-9B.
>
> _(Bấm Click 2 — hiện Cột phải: Hướng phát triển tương lai)_
> Hướng phát triển tương lai tập trung vào 4 điểm rút ra từ thực nghiệm:
>
> 1. **Khôi phục lỗi tự động**: Thực nghiệm chỉ ra 58-60% lỗi xuất phát từ việc trang web bị DOM timeout hoặc kẹt giao diện; hệ thống cần cơ chế tự sửa lỗi và retry khi gặp sự cố DOM.
> 2. **Tối ưu khám phá với RL**: Kết hợp Học tăng cường (RL) giúp Explorer tự học chiến lược duyệt web tối ưu thay vì chỉ tìm kiếm theo phỏng đoán.
> 3. **Học từ thất bại**: Khai thác các trajectory thất bại bị loại bỏ thông qua DPO / Preference Learning.
> 4. **Tổng quát hóa**: Mở rộng pipeline khám phá cho các ứng dụng ngoài miền (cross-domain).
>
> Em xin chân thành cảm ơn Thầy Cô trong Hội đồng đã chú ý lắng nghe và xin nhận câu hỏi góp ý!

**Câu chốt:** Khóa luận chứng minh tính khả thi của việc tự sinh dữ liệu và fine-tune SLM chạy cục bộ với chi phí tối ưu.

---

## Phụ lục PL1–PL8: câu hỏi nào bật trang nào

| Slide | Trang | Nội dung                                            | Bật khi được hỏi về                                                    |
| ----- | ----- | --------------------------------------------------- | ---------------------------------------------------------------------- |
| PL1   | 24    | Tính hợp lệ của phép đánh giá                       | "Explore rồi test trên cùng app thì có hợp lệ không?"                  |
| PL2   | 25    | Hướng đến ai; pipeline mới là thứ tổng quát         | "Có phải muốn model generalize cho mọi trang không?"                   |
| PL3   | 26    | Task khả thi, ngân sách bước, tiêu chuẩn hoàn thành | "Task LLM đề xuất có thật không?", "Sao 25 bước?", "Sao biết đã xong?" |
| PL4   | 27    | Bốn CH: số liệu và mức độ trả lời                   | "Thực nghiệm trả lời được mục tiêu chưa?"                              |
| PL5   | 28    | Chi phí chi tiết                                    | "Chi phí đã tính đủ chưa?"                                             |
| PL6   | 29    | Frontier hai tầng                                   | "Khám phá không bị lạc bằng cách nào?"                                 |
| PL7   | 30    | Nguyên nhân thất bại; đặc tính hai mô hình          | "Điểm nghẽn còn lại ở đâu?"                                            |
| PL8   | 31    | Thêm dữ liệu; đổi mô hình nền                       | "Thêm dữ liệu nữa có tốt hơn không?", "Sao không dùng mô hình khác?"   |

---

## Câu hỏi dự kiến và hướng trả lời

### A. Sáu câu thầy phản biện đã hỏi

| Câu hỏi                                                                                                                       | Bật                            | Hướng trả lời                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Explore trên app của họ rồi test bằng bộ test của họ trên chính app đó có hợp lệ không? Phải test app khác cùng lĩnh vực chứ? | **PL1**                        | Pipeline **chưa từng nhìn thấy** 655 task benchmark — task huấn luyện do agent tự đề xuất từ giao diện; CSDL khôi phục nguyên bản trước mỗi đợt đo; không trajectory nào được dùng lại lúc chấm. Cùng-website là **giao thức chuẩn** của cả dòng nghiên cứu: Go-Browse cũng khám phá 20 URL mỗi domain của WebArena rồi chấm trên chính 812 task WebArena. Còn test "app khác" là bài toán **ngoài miền** — chưa ai giải được: trên Online-Mind2Web, Go-Browse-7B chỉ 5,33% và NNetNav-7B 4,00%, đều thua GPT-4o-mini 9,33%. |
| Động lực hướng đến ai? Có phải muốn một model generalize cho mọi trang cùng lĩnh vực?                                         | **Slide 5** trước, **PL2** sau | **Không.** Đích nhắm là chuyên biệt hóa cho _một_ website cụ thể. Câu chốt: **thứ tổng quát hóa là pipeline, không phải model**. Người dùng đích là nhóm vận hành vài website cố định, cần agent chạy tại chỗ. Khả thi vì **dưới 20 đô la mỗi website** và không cần người gán nhãn.                                                                                                                                                                                                                                         |
| Làm sao biết task do LLM đề xuất là hợp lý và làm được thật trên giao diện đó?                                                | **PL3** khối 1                 | Bộ đề xuất là một _agent_ đọc trực tiếp cây trợ năng của trang thật, không đề xuất từ trí nhớ. Quan trọng hơn: **khả thi được chứng minh bằng thực thi, không bằng lời** — chỉ task có ít nhất một lượt giải thành công _và qua kiểm chứng_ mới vào dataset. 637 task bị chính agent báo bất khả thi; 3981 lượt thử còn 2117 hợp lệ.                                                                                                                                                                                         |
| Vì sao ngân sách bước là 25?                                                                                                  | **PL3** khối 2                 | Chính xác là **15 bước cho task cục bộ, 25 cho semantic task nhiều bước**. Solver chiếm 85,5% trong 20.808 lượt gọi nên ngân sách bước _chính là_ ngân sách kinh phí — đây trước hết là quyết định chi phí. Nhưng dữ liệu cho thấy nó **không bóp méo phép đo**: episode thành công có trung vị 6 bước, và **không episode nào** đạt mục tiêu rồi mới bị cắt vì hết bước.                                                                                                                                                    |
| Dựa vào đâu để biết task đã hoàn thành?                                                                                       | **PL3** khối 3                 | **Ba lớp**, không phải hai: (i) solver tự khai hoặc vị từ tất định; (ii) LLM-as-Judge soi trạng thái trang đích → loại **801 lượt** dương tính giả khi tự đánh giá; (iii) cổng "hành động hữu hiệu" bằng mã → loại **104 trajectory**, nhóm lỗi mà judge _về nguyên tắc_ không thấy được. Và 24,6% được chấm bằng **bộ chấm chính thức của WebArena**.                                                                                                                                                                       |

| Thực nghiệm nhắm mục tiêu nào, đã trả lời được chưa? | **PL4** | CH1–CH4 đều có số liệu trả lời. Phần phải nói thật: **O2 và O4 mới hoàn thành một phần** — chỉ 12/142 semantic task từ ghép chuỗi, và **ablation đồ thị so với khám phá phẳng chưa chạy**. |

### B. Các câu khác

| Câu hỏi                                                                                                    | Bật                            | Hướng trả lời                                                                                                                                                                                                                                                                                                                |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Đóng góp mới so với Go-Browse / NNetNav là gì?                                                             | Slide 4–5                      | Kỹ năng được **kiểm chứng**, nâng thành operator có tiền điều kiện/kết quả, rồi **ghép chuỗi** thành task dài — hai cột mà cả hai công trình kia đều trống. Cộng thêm hai cổng chất lượng và prompt parity.                                                                                                                  |
| Sao không chứng minh được đồ thị tốt hơn khám phá phẳng?                                                   | Slide 15, PL4                  | Đúng, đó là ablation quan trọng nhất và chưa chạy. Thiết kế đã có sẵn: cùng ngân sách episode và lượt gọi, chỉ đổi chiến lược khám phá.                                                                                                                                                                                      |
| Vì sao ghép chuỗi chỉ sinh 12/142 task?                                                                    | Slide 9                        | Cạnh operator cần kết quả khớp tiền điều kiện; sau hai cổng chống trùng lặp và kiểm chứng thực tế, đồ thị còn thưa. Hạn chế đã ghi trong Chương 5.                                                                                                                                                                           |
| 24,6% có thấp quá không?                                                                                   | Slide 13                       | So với chính mô hình nền cùng điều kiện là **+11,3 điểm, p<0,001, có ý nghĩa trên cả 4/4 website**. Benchmark này GPT-4 chỉ đạt ~14% khi công bố, người đạt 78%. 24,6% ngang nhóm mô hình mở tốt nhất dưới 10B.                                                                                                              |
| Vì sao tin số liệu khi agent tự chấm?                                                                      | PL3                            | Không tin — ba lớp kiểm chứng; và phần đánh giá cuối dùng bộ chấm tự động của WebArena, không phải agent.                                                                                                                                                                                                                    |
| Chi phí đã tính đủ chưa?                                                                                   | PL5                            | **54,21 API + 24,40 GPU = 78,61 đô la** cho cả bốn website; chưa tính hạ tầng WebArena tự host và công vận hành. Mỗi trajectory 0,0308 đô — rẻ hơn Go-Browse 3,3 lần.                                                                                                                                                        |
| Vì sao chọn Qwen3.5-9B mà không nhỏ hơn?                                                                   | Slide 15, PL8                  | Ngưỡng "chạy được trên máy phổ thông" là dưới 10B; chưng cất xuống 1–3B là hướng phát triển. PL8 có sẵn phép đo đổi mô hình nền sang Qwen-2.5-7B trên **cùng** tập dữ liệu.                                                                                                                                                  |
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
> đúng nguyên tắc **prompt parity** mà nhóm em vừa trình bày ở slide 10.

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

- [ ] Mở sẵn `main.pdf` ở chế độ toàn màn hình, kiểm tra nhảy được tới trang 24–31.
- [ ] Video demo mở sẵn ở tab riêng, **âm lượng 0**, đã thử phát một lần.
- [ ] Nhớ ba con số không được nói sai: **24,6% / 13,3% / +11,3 điểm**.
- [ ] Slide 5 phải nói ra chữ **"một tập website cố định"** và chữ **"tiềm năng"** khi
      nhắc kiểm thử E2E.
- [ ] Nhớ hai chỗ **không được nói quá**: "ngang Go-Browse" (không phải _vượt_), và
      "ghép chuỗi mới khả thi" (không phải _đã đủ dày_).
- [ ] Người 2 nắm chắc mốc 8:30 — nếu người 1 trễ quá 1 phút thì lược
      `[lược nếu trễ]` ở slide 12 và 13.

---

## Nếu được 20 phút

Thêm bốn slide, theo thứ tự ưu tiên:

1. **Kéo PL7 (nguyên nhân thất bại) và PL6 (frontier hai tầng) vào phần nội dung** —
   cả hai đã dựng sẵn trong phụ lục, chỉ cần đổi chỗ.
2. **Ví dụ một semantic task** sinh từ chuỗi operator, kèm chuỗi tiền điều kiện/kết quả.
3. **Lộ trình nghiên cứu** (`fig_roadmap.pdf`, đã có trong `images/`), đặt ngay sau
   slide 5 (giải pháp & mục tiêu).
4. **Bài học vận hành** (Phụ lục E của quyển): chat template, prompt parity, chạy song
   song hai máy trên site sống.
