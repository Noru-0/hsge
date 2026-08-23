# Kịch bản trình bày — Bảo vệ KLTN HSGE

**Ngân sách:** 15 phút trình bày + 15 phút hỏi đáp (thông báo bảo vệ đợt 04/2026).
Deck có **24 trang phần nội dung** (18 slide phải nói + 1 trang cảm ơn/Q&A + 1 trang mục
lục đầu bài + 4 trang mục lục chương lướt qua) và **8 trang phụ lục PL1–PL8** đặt sau
trang cảm ơn, chỉ bật khi được hỏi.

**Bố cục sáu mục** (theo góp ý của Hội đồng): _Giới thiệu (động lực) → Phát biểu bài toán
→ Nghiên cứu liên quan → Phương pháp → Thực nghiệm → Kết luận & Hỏi đáp_. Mạch kể là
**bài toán trước, thách thức, tình trạng hiện tại, rồi mới tới lời giải** — không nói
chi tiết phương pháp nào trước mục 4.

**Chia hai người:** Người 1 slide 1–12 (đặt vấn đề + phương pháp), Người 2 slide 13–18
(thực nghiệm + kết luận). Điểm cắt sau slide 12, khi chuyển từ _"làm thế nào"_
sang _"đo được gì"_.

**Cách đọc kịch bản:**

- **Nói** = lời thoại, viết theo văn nói, đọc thẳng được.
- **Câu chốt** = câu duy nhất bắt buộc phải lọt tai Hội đồng ở slide đó.
- **Tránh** = chỗ dễ nói quá; nói sai một chữ ở đây là mất điểm tin cậy.
- `[lược nếu trễ]` = cắt được mà không gãy mạch.
- Cột "Trang" là **số slide hiện ở footer** (`n / 24`), không phải số trang PDF: deck
  dùng overlay nên `main.pdf` hiện có 52 trang. Nhảy nhanh thì dùng số footer.
  Riêng phụ lục không có số footer — dùng **số trang PDF 45–52**.

---

## Bảng thời lượng

| Slide | Trang | Nội dung                                       | Mốc   | Thời lượng |
| ----- | ----- | ---------------------------------------------- | ----- | ---------- |
| 1     | 1     | Bìa                                            | 0:00  | 0:30       |
| 2     | 3     | _M1_ Động lực — khoảng cách hiệu năng trên web | 0:30  | 0:45       |
| 3     | 5     | _M2_ Phát biểu bài toán và phạm vi             | 1:15  | 0:45       |
| 4     | 6     | _M2_ Bốn thách thức cốt lõi                    | 2:00  | 0:45       |
| 5     | 8     | _M3_ Ba hướng tiếp cận hiện nay                | 2:45  | 0:45       |
| 6     | 9     | _M3_ Hạn chế và khoảng trống nghiên cứu        | 3:30  | 0:40       |
| 7     | 11    | _M4_ Giải pháp HSGE & các đóng góp chính       | 4:10  | 0:50       |
| 8     | 12    | _M4_ Tổng quan pipeline HSGE                   | 5:00  | 1:00       |
| 9     | 13    | _M4_ Đồ thị hai tầng                           | 6:00  | 0:55       |
| 10    | 14    | _M4_ Phát hiện skill → quy nạp operator        | 6:55  | 1:00       |
| 11    | 15    | _M4_ Sinh semantic task                        | 7:55  | 0:55       |
| 12    | 16    | _M4_ Tinh lọc dữ liệu _(chuyển người)_         | 8:50  | 0:55       |
| 13    | 18    | _M5_ Thiết lập & Câu hỏi nghiên cứu            | 9:45  | 0:45       |
| 14    | 19    | _M5_ CH1 — Tự động tạo tác vụ & Quy mô dữ liệu | 10:30 | 1:00       |
| 15    | 20    | _M5_ CH2 — So sánh hiệu năng SOTA              | 11:30 | 1:00       |
| 16    | 21    | _M5_ CH2 — So sánh Base và Fine-tuning         | 12:30 | 0:50       |
| 17    | 22    | _M5_ CH3 — Hiệu quả chi phí tự sinh dữ liệu    | 13:20 | 0:40       |
| 18    | 23    | _M6_ Kết luận & Hướng phát triển               | 14:00 | 1:00       |

Phần đặt vấn đề trải trên **năm** slide (2–6), mỗi slide đúng một nhịp: động lực → bài
toán → thách thức → công trình liên quan → khoảng trống. Tổng phần này ~3:40; nếu trễ thì
lược nhóm (A) ở slide 5 và cột trái slide 6 xuống còn hai gạch đầu dòng.

Trang 2 là mục lục đầu bài; trang 4, 7, 10, 17 là mục lục đầu mục — bấm lướt, không dừng
nói. Trang 24 là trang cảm ơn / Hỏi & Đáp; dừng ở đó và mời Hội đồng đặt câu hỏi.

---

## Slide 1 - Bìa (0:00, trang 1)

> Kính thưa Hội đồng. Em là Trương Bảo Kiệt, cùng bạn Hồ Tiến Phát, trình bày khóa
> luận _"Khám phá theo đồ thị kỹ năng phân cấp để tự động sinh dữ liệu huấn luyện cho
> tác nhân trí tuệ nhân tạo trên web"_, dưới sự hướng dẫn của PGS.TS. Nguyễn Văn Vũ.
>
> Bài trình bày gồm sáu phần: giới thiệu và động lực, phát biểu bài toán, các nghiên cứu
> liên quan, phương pháp HSGE, kết quả thực nghiệm, và cuối cùng là kết luận cùng phần
> hỏi đáp.

---

## Slide 2 - Động lực: khoảng cách hiệu năng trên tác vụ web (0:30, trang 3)

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
>
> Nếu nút thắt là dữ liệu, thì bài toán cần giải chính là: **lấy dữ liệu huấn luyện ở đâu
> cho một website cụ thể?**

**Câu chốt:** Nút thắt của Web Agent không nằm ở kiến trúc mô hình, mà nằm ở **dữ liệu tương tác thực tế cho từng website cụ thể**.

**Tránh:** không nói "LLM không làm được web" — con số đúng là _14,41% so với 78,24% của
con người trên WebArena_, tức là làm được nhưng còn xa mức dùng được.

---

## Slide 3 - Phát biểu bài toán và phạm vi (1:15, trang 5)

> Em xin phát biểu bài toán một cách chính xác trước khi nói tới bất kỳ giải pháp nào.
>
> _(Click 1 — Bài toán)_ **Đầu vào** là một **website mục tiêu đang vận hành**: nhóm chỉ có
> URL gốc và quyền truy cập, **không có một nhãn người nào**, và cũng không có sẵn bộ tác
> vụ mẫu để học theo. **Đầu ra** cần đạt là hai thứ: một bộ dữ liệu trajectory dùng để
> huấn luyện, và một **mô hình nhỏ dưới 10 tỷ tham số** đã fine-tune thành agent chuyên
> biệt cho đúng website đó.
>
> _(Click 2 — Ràng buộc)_ Bài toán bị ràng buộc bởi hai điều kiện thực tế: ngân sách gọi
> API ở mức một **nhóm nghiên cứu nhỏ**, và mô hình phải chạy được **tại chỗ (on-premise)**
> để dữ liệu không rời khỏi tổ chức.
>
> _(Click 3 — Tiêu chí đánh giá)_ Về đo lường, nhóm dùng **WebArena** với **655 tác vụ
> chính thức trên 4 website thực**, chấm bằng **bộ chấm của chính benchmark**, chỉ số chính
> là **tỷ lệ hoàn thành tác vụ — Task Success Rate**. Chỉ số phụ là **chi phí API trên mỗi
> trajectory**, vì ràng buộc kinh tế là một phần của bài toán chứ không phải chuyện phụ.
>
> _(Click 4 — Phạm vi)_ Và đây là chỗ em xin nói rõ ngay từ đầu để tránh hiểu nhầm: phạm vi
> là **một website cho ra một agent chuyên biệt**, không phải một agent vạn năng. Thứ tổng
> quát hóa ở đây là **quy trình (pipeline)**, không phải **mô hình**.

**Câu chốt:** Bài toán là _sinh dữ liệu và huấn luyện agent cho **một** website cụ thể, với **0 nhãn người**_ — và thứ tổng quát hóa là **pipeline, không phải model**.

**Câu chốt phụ (bắt buộc nói, đừng đợi bị hỏi):** người dùng đích là nhóm vận hành một tập
website cố định, cần agent chạy tại chỗ — không phải người cần một model dùng cho mọi trang.

**Tránh:** đừng hứa "agent tổng quát cho mọi website cùng lĩnh vực" — đó là bài toán ngoài
miền, khóa luận **không** giải và **không** đo.

---

## Slide 4 - Bốn thách thức cốt lõi (2:00, trang 6)

> Bài toán vừa nêu vướng bốn thách thức, và bốn thách thức này sẽ được nhắc lại xuyên suốt
> phần sau nên em xin đánh số **T1 đến T4**.
>
> _(Click 1 — T1)_ **T1 — chi phí gán nhãn.** Cách cổ điển là thuê người gán nhãn, và nó rất
> đắt: AutoWebGLM cần **20 người làm việc suốt một tháng** cho khoảng mười nghìn trajectory.
> Sinh mẫu ngoại tuyến thì rẻ hơn hẳn — Synatra chỉ tốn khoảng **3%** chi phí mỗi mẫu —
> nhưng rẻ mà không bám môi trường thật thì cũng không dùng được: chỉ đạt **6%** trên
> WebArena, so với **16%** của phương pháp học trực tiếp từ chính website đích.
>
> _(Click 2 — T2)_ **T2 — tri thức bị phân mảnh.** Trajectory thô chỉ là chuỗi thao tác rời
> rạc, không có **đơn vị kỹ năng** nào để tái sử dụng. Cùng một thao tác lặp lại ở mười
> trang khác nhau vẫn bị coi là mười mẩu dữ liệu mới, không được đúc kết thành gì cả.
>
> _(Click 3 — T3)_ **T3 — dương tính giả.** Vì không có nhãn người, agent phải **tự khai báo
> đã hoàn thành**. Lời tự khai thường sai, và dữ liệu bẩn lọt vào tập huấn luyện thì hậu quả
> nặng hơn thiếu dữ liệu: nó **dạy mô hình khai gian**.
>
> _(Click 4 — T4)_ **T4 — khó ghép thành tác vụ dài.** Tác vụ tự sinh thường bó hẹp trong
> một trang — tra cứu, điều hướng. Thiếu cơ chế biết được _làm xong A thì mới làm được B_
> thì không thể sinh ra tác vụ nhiều bước có ý nghĩa nghiệp vụ.
>
> Bốn thách thức này đã được cộng đồng tấn công tới đâu — đó là nội dung phần tiếp theo.

**Câu chốt:** bốn thách thức T1–T4 là **khung để chấm điểm mọi phương pháp**, kể cả HSGE — phần sau sẽ đối chiếu lại đúng bốn mục này.

`[lược nếu trễ]` Gộp T1 và T2 vào một câu, giữ nguyên T3 và T4 (đây là hai chỗ HSGE khác biệt nhất).

---

## Slide 5 - Ba hướng tiếp cận hiện nay (2:45, trang 8)

> Cộng đồng đã giải quyết bài toán dữ liệu cho web agent theo ba hướng.
>
> _(Click 1)_ **Nhóm (A) — tri thức gián tiếp:** Synatra và AgentTrek chuyển các bài hướng
> dẫn, tài liệu trên Internet thành mẫu huấn luyện; AgentTrek còn replay lại trên trình
> duyệt thật để lấy trajectory.
>
> _(Click 2)_ **Nhóm (B) — bộ nhớ và kỹ năng phục vụ lúc suy luận:** AWM trích các workflow
> lặp lại từ lịch sử rồi nhét vào prompt, nâng tỷ lệ hoàn thành trên WebArena từ **23,5%
> lên 35,5%**; SkillWeaver để agent tự khám phá và đóng gói kỹ năng thành các API tái sử
> dụng được.
>
> _(Click 3)_ **Nhóm (C) — tự khám phá để sinh dữ liệu huấn luyện cho mô hình nhỏ**, gần
> khóa luận nhất: NNetNav khám phá website rồi gán nhãn hồi tố, mô hình 8B đạt **16,3%**;
> Go-Browse mô hình hóa việc khám phá thành **bài toán tìm kiếm trên đồ thị** website, mô
> hình 7B đạt **21,7%** — mức tốt nhất của phân khúc dưới 10 tỷ tham số tại thời điểm công
> bố.
>
> Kết quả của Go-Browse củng cố đúng tiền đề của khóa luận: **khám phá có cấu trúc cho dữ
> liệu tốt hơn các chuỗi rollout rời rạc**. Đây cũng là mốc so sánh chính của nhóm.

**Câu chốt:** Ba hướng trước đã chứng minh **tự động sinh dữ liệu là khả thi**, và hướng
khám phá có cấu trúc là hướng cho kết quả tốt nhất.

`[lược nếu trễ]` Bỏ nhóm (A), vào thẳng (B) và (C).

---

## Slide 6 - Hạn chế và khoảng trống nghiên cứu (3:30, trang 9)

> Nhưng đối chiếu lại với bốn thách thức T1–T4 thì mỗi hướng đều còn một khoảng trống.
>
> **Nhóm (A)** bị chặn bởi đúng một thứ: lượng tài liệu hướng dẫn sẵn có. Quy trình nội bộ
> chưa ai viết ra, hay website vừa triển khai, thì nằm ngoài tầm với — nên **T1 chưa được
> giải**.
>
> **Nhóm (B)** — kỹ năng chỉ sống trong prompt của một mô hình lớn, **không hề cập nhật
> tham số**, nên không giúp gì cho bài toán mô hình nhỏ chạy cục bộ. Thêm nữa, workflow của
> AWM là chuỗi bước tuyến tính, **không có tiền điều kiện và kết quả tường minh**, nên không
> thể ghép chuỗi bằng thuật toán lập kế hoạch — tức còn **T2 và T4**.
>
> **Nhóm (C)** — NNetNav **không tích lũy** tri thức giữa các episode. Go-Browse có đồ thị,
> nhưng **chỉ một tầng**: node là URL, cạnh là trajectory, phía trên không có tầng trừu
> tượng nào. Hệ quả là bộ đề xuất task của Go-Browse được yêu cầu tường minh chỉ tìm những
> việc **làm được ngay trên trang hiện tại** — task sinh ra bị bó trong một trang, tức vẫn
> là **T4**.
>
> Và cả **(B) lẫn (C)** đều ghi nhận thành công phần lớn dựa trên **lời tự khai của agent**,
> không chạy lại để kiểm chứng — tức **T3 còn nguyên**.
>
> _(Click 2)_ Khung đỏ bên phải là khoảng trống nghiên cứu: chưa công trình nào nối trọn ba
> khâu **kiểm chứng kỹ năng → ghép thành tác vụ dài → dùng chính dữ liệu đó huấn luyện mô
> hình nhỏ**.
>
> _(Click 3)_ Từ đó, câu hỏi khóa luận đặt ra là: **Làm sao tận dụng LLM để tự động sinh dữ
> liệu huấn luyện trên website mục tiêu, hoàn toàn không cần nhãn con người, nhằm giúp mô
> hình nhỏ chạy cục bộ đạt hiệu năng tiệm cận hoặc vượt LLM lớn trên chính các trang đó?**

**Câu chốt:** Khoảng trống không phải là "thu được nhiều dữ liệu hơn", mà là **thiếu một
tầng kỹ năng đã kiểm chứng, ghép chuỗi được**.

**Tránh:** không nói các công trình trước "sai" hay "kém" — cách nói đúng là mỗi hướng
giải quyết _một phần_ của bài toán, và ba khâu đó chưa được nối liền.

---

## Slide 7 - Giải pháp HSGE và các đóng góp chính (4:10, trang 11)

> Để lấp khoảng trống đó, khóa luận đề xuất **HSGE (Hierarchical Skill-Graph Exploration)**,
> tự động hóa toàn chu trình từ website đến mô hình SLM cục bộ.
>
> _(Click 1)_ Về **đóng góp khoa học (kiến trúc & thuật toán)**:
>
> - Thứ nhất, **mô hình biểu diễn đồ thị hai tầng**: kết hợp State Graph ghi vết duyệt web ở tầng thấp với Operator Graph biểu diễn kỹ năng ở tầng cao — nhắm **T2**.
> - Thứ hai, **thuật toán quy nạp operator và ghép chuỗi đa bước**: tự động trích xuất các kỹ năng lặp lại, kiểm chứng và ghép chuỗi thành tác vụ có ngữ nghĩa — nhắm **T4**.
> - Thứ ba, **kiểm định trực tuyến ngay trong vòng lặp khám phá**, loại dương tính giả trước khi dữ liệu vào dataset — nhắm **T3**.
>
> _(Click 2)_ Về **đóng góp thực tiễn (sản phẩm & dữ liệu)**, đề tài bàn giao **năm sản phẩm chính**:
>
> - Thứ nhất, **Pipeline HSGE**: hệ thống tự động khám phá, quy nạp operator và sinh tác vụ có ngữ nghĩa trên website thật.
> - Thứ hai, **Bộ dữ liệu 9.007 mẫu SFT sạch** (từ 1.760 trajectory hợp lệ) trên 4 website WebArena mà hoàn toàn không cần nhãn người — nhắm **T1**.
> - Thứ ba, **Mô hình HSGE-9B chạy cục bộ đạt 24,6%** (vượt GPT-4o-mini và đạt SOTA phân khúc dưới 10B) cùng kiểm chứng độc lập trên mô hình nền Qwen-2.5-7B.
> - Thứ tư, **Pipeline đánh giá trên benchmark WebArena**: dùng chung cấu hình prompt và bộ chấm chính thức của benchmark.
> - Thứ năm, **Báo cáo các bài học kinh nghiệm**: đúc kết 14 thực hành kỹ thuật thực tiễn trải trên 5 mảng triển khai.
>
> Về **tính khả thi kinh tế**: chi phí gọi API khám phá chỉ **0,0308 USD mỗi trajectory
> thành công**, **rẻ hơn 3,3 lần so với Go-Browse**.
>
> Phần còn lại của mục này sẽ trình bày cách bốn thách thức T1–T4 được giải quyết trong một
> quy trình khép kín.

**Câu chốt:** đóng góp nằm ở **tầng trừu tượng thứ hai** — kỹ năng đã kiểm chứng, ghép chuỗi được — chứ không phải ở việc thu nhiều dữ liệu hơn.

**Tránh:** **không nói "khóa luận làm công cụ kiểm thử tự động"**. Bắt buộc có chữ _"tiềm năng, chưa thực nghiệm"_ trong cùng một câu — quyển báo cáo không có phần kiểm thử.

`[lược nếu trễ]` Bỏ sản phẩm thứ tư và thứ năm, chỉ giữ pipeline / dataset / mô hình.

---

## Slide 8 - Tổng quan pipeline HSGE (5:00, trang 12)

> Đây là toàn bộ phương pháp HSGE trên một hình, vận hành như một vòng lặp khép kín, tự động hoàn toàn.
>
> Bắt đầu từ **Frontier** — hàng đợi lưu các trang web cần khám phá. Chọn một trang, một agent đề xuất các tác vụ làm được ngay trên trang đó, rồi solver thử thao tác trên trình duyệt thật. Những trajectory giải thành công được đưa vào khâu phát hiện kỹ năng: cắt thành đoạn nhỏ, gom cụm các thao tác tương đồng, trừu tượng hóa thành thẻ kỹ năng, rồi quy nạp thành **Operator** có tiền điều kiện (Precondition) và kết quả (Effect).
>
> Các operator này được ghép chuỗi với nhau để sinh ra các **Tác vụ có ngữ nghĩa (Semantic Task)** — tức tác vụ nhiều bước có ý nghĩa nghiệp vụ thực tế. Toàn bộ dữ liệu thu được đi qua hai cổng lọc chất lượng trực tuyến trước khi trở thành tập huấn luyện SFT. Và mỗi trang mới phát hiện lại quay về frontier để tiếp tục mở rộng.

**Câu chốt:** không phải thu thập rời rạc, mà **tích lũy tri thức có cấu trúc rồi mới khai thác lại**.

---

## Slide 9 - Đồ thị hai tầng (6:00, trang 13)

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

## Slide 10 - Phát hiện skill và quy nạp operator (6:55, trang 14)

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

## Slide 11 - Sinh tác vụ có ngữ nghĩa (7:55, trang 15)

> **Tác vụ có ngữ nghĩa (Semantic Task)** — tức tác vụ nhiều bước có ngữ nghĩa nghiệp vụ hoàn chỉnh — được sinh từ hai nguồn:
>
> - **Từ dưới lên (Bottom-up):** Ghép chuỗi operator bằng duyệt đồ thị, mỗi chuỗi từ hai operator trở lên sẽ tạo thành một nhiệm vụ dài kèm câu lệnh ngôn ngữ tự nhiên.
> - **Từ trên xuống (Top-down):** Gợi ý từ năng lực tổng quan của website (như chức năng quản trị, đăng bài, mua sắm) khi đồ thị còn thưa.
>
> Về số liệu thực tế: trong **142 tác vụ có ngữ nghĩa** đã thực thi, **130 tác vụ đến từ seed và 12 tác vụ đến từ ghép chuỗi operator**, đạt 71 tác vụ giải thành công (tỷ lệ 50,0%, xấp xỉ mức 47,6% của nhóm tác vụ LOCAL đơn trang). Kết quả này chứng minh cơ chế ghép chuỗi hoạt động đúng thiết kế, dù ở giai đoạn đầu tần suất ghép còn thưa.

**Câu chốt:** cơ chế ghép chuỗi được chứng minh là **khả thi**, chưa chứng minh được là **đủ dày** để làm nguồn dữ liệu chính.

**Tránh:** đừng nói "tác vụ có ngữ nghĩa chủ yếu sinh từ đồ thị operator" — số liệu ngược lại, và Hội đồng có thể đã đọc Chương 5.

---

## Slide 12 - Kiểm định trực tuyến & Đóng gói SFT (8:50, trang 16) — _điểm chuyển người trình bày_

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

## Slide 13 - Thiết lập & Câu hỏi nghiên cứu (9:45, trang 18)

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
> - **Mô hình**: Tinh chỉnh từ mô hình nền **Qwen3.5-9B** tạo thành **HSGE-9B**.
> - **Fine-tuning**: Kỹ thuật LoRA / QLoRA qua 3 epoch (1.119 bước huấn luyện).
> - **Đánh giá**: 655 tác vụ chính thức của **WebArena** trên 4 website do nhóm **tự triển khai (self-hosted)** — Shopping, Shopping Admin, GitLab, Reddit — chấm bằng Task SR của benchmark.
> - **Đối chứng**: cùng prompt, cùng ngân sách bước với mô hình nền.
>
> _(Phạm vi và tiêu chí đã nêu ở slide 3 — ở đây chỉ nhắc lại phần cấu hình huấn luyện.)_

**Câu chốt:** Phép đo sử dụng bộ đề xuất và **bộ chấm chính thức của WebArena** để đảm bảo tính khách quan hoàn toàn.

---

## Slide 14 - CH1: Tự động tạo tác vụ & Quy mô dữ liệu (10:30, trang 19)

> Trả lời **CH1**, phễu khám phá tự động của HSGE mang lại các kết quả quy mô ấn tượng:
>
> - **Quy mô khám phá & Tri thức**: Khám phá **4 website, 455 URL**, thực hiện **3.981 lượt tương tác thử**, thu hoạch **146 skills** và quy nạp **57 operators**.
> - **Sinh tác vụ**: Tự động tạo và kiểm chứng **142 semantic task** đa bước.
> - **Cổng lọc chất lượng**:
>   1. **LLM-as-Judge** loại bỏ **801 lượt (27,4%)** dương tính giả (agent tự báo hoàn thành nhưng chưa làm đúng).
>   2. **Effective Action Gate** loại **104 trajectory** không làm biến đổi trang DOM.
> - **Kết quả thu hoạch**: Thu được **1.760 trajectory sạch** (đạt tỷ lệ hợp lệ 53,2%), đóng gói thành **9.007 mẫu SFT** (8.554 train / 453 validation) hoàn toàn tự động mà **không cần 1 giờ gán nhãn thủ công nào**.

**Câu chốt:** HSGE tự động sinh tác vụ có ý nghĩa và thu hoạch 9.007 mẫu SFT sạch hoàn toàn không cần nhãn người.

---

## Slide 15 - CH2: So sánh hiệu năng với các hệ thống SOTA (11:30, trang 20)

> Trả lời **CH2 (phần 1)**, Bảng 2 so sánh hiệu năng của HSGE-9B và HSGE-7B với các mô hình đóng và mở:
>
> - **Vị thế tổng thể**: HSGE-9B đạt tỷ lệ hoàn thành **24,6%** trên toàn bộ 655 task của WebArena, tăng **+11,3 điểm phần trăm** so với mức **13,3%** của mô hình nền Qwen3.5-9B.
> - **Chuyển giao tập dữ liệu sang mô hình 7B (Bảng 4.14)**: Cùng tập dữ liệu 8.554 mẫu HSGE nâng **Qwen-2.5-7B từ 8,3% lên 16,5%** (+8,2 đpt, tăng gần gấp đôi), chứng minh tri thức không phụ thuộc kiến trúc đơn lẻ.
> - **Vượt mô hình thương mại đóng**: Kết quả 24,6% của HSGE-9B vượt qua **GPT-4o-mini (20,0%)**.
> - **Vượt các SLM cùng phân khúc (<10B)**: HSGE-9B vượt xa **Qwen-2.5-7B-Instruct (8,3%)** và **NNetNav-7B (19,1%)**, đồng thời đạt mức **tương đương SOTA Go-Browse-7B (22,6%)**.
> - **Ưu thế trên từng website**: HSGE-9B dẫn đầu ở phân khúc <10B trên website Shopping (**28,3%**) và Reddit (**34,0%**).

**Câu chốt:** Fine-tuning giúp SLM 9B vượt GPT-4o-mini và đạt SOTA phân khúc mở dưới 10 tỷ tham số.

**Tránh:** Không nói "vượt Go-Browse" — con số 24,6% so với 22,6% nằm trong khoảng biến động thống kê, phát biểu chuẩn xác là _tương đương SOTA Go-Browse-7B_.

---

## Slide 16 - CH2: So sánh mô hình nền (Base) và fine-tuning theo Website (12:30, trang 21)

> Trả lời **CH2 (phần 2)**, slide này bóc tách bản chất cải thiện năng lực của mô hình sau fine-tune:
>
> - **Độ tăng theo từng Website**: Cả 4/4 website đều ghi nhận mức tăng trưởng vượt trội có ý nghĩa thống kê theo **kiểm định McNemar** ($p \le 0{,}011$), đặc biệt Reddit tăng từ 6,6% lên **34,0%** ($p < 0{,}001$).
> - **Ý nghĩa thống kê McNemar**: Có **100 task độc quyền** chỉ HSGE-9B mới giải được (so với 26 task Base giải được), đạt ý nghĩa thống kê cao trên toàn bộ 4 website ($p < 0{,}001$).
> - **Bóc tách 2 nguồn cải thiện năng lực**:
>   1. **Kỷ luật cú pháp**: Lỗi định dạng đầu ra giảm triệt để từ **26,0% down còn 0,6%**.
>   2. **Năng lực ra quyết định**: Trên tập 485 task mà mô hình nền đã xuất đúng cú pháp, Task SR của HSGE-9B vẫn tăng từ **17,9% lên 23,5% ($p = 0{,}003$)**.
>
> Điều này chứng minh fine-tuning không chỉ giúp mô hình học đúng cú pháp lệnh, mà thực sự nâng cao **năng lực ra quyết định hành động**.

**Câu chốt:** Fine-tuning làm chủ cả kỷ luật cú pháp lẫn năng lực lựa chọn hành động ($p = 0{,}003$).

---

## Slide 17 - CH3: Hiệu quả chi phí trong tự động tạo dữ liệu (13:20, trang 22)

> Trả lời **CH3**, slide này phân tích hiệu quả kinh tế trong quá trình tự động sinh dữ liệu:
>
> - **Chi phí API toàn chu trình**: Tổng chi phí API gọi LLM đóng (OpenAI + DeepSeek) cho cả 4 website chỉ tốn **54,21 USD** (chưa tới **14 USD / website**).
> - **Đơn giá / Trajectory**: Trung bình mỗi trajectory thành công sạch chỉ tốn **0,0308 USD** (khoảng 3,1 cent).
> - **Phân bổ lời gọi API**: Tổng cộng 20.808 lượt gọi LLM, trong đó Solver chiếm **85,5%**. Việc dồn Solver sang mô hình chi phí thấp (GPT-5.6-luna) giúp giảm đơn giá token đầu vào **~12 lần** so với GPT-4o.
> - **So sánh kinh tế với Go-Browse**: Đơn giá **0,0308 USD/trajectory** của HSGE **rẻ hơn 3,3 lần** so với Go-Browse-7B ($0,1026 USD/trajectory).

**Câu chốt:** Tự động sinh dữ liệu với đơn giá 0,0308 USD/trajectory chứng minh tính khả thi kinh tế vượt trội cho các nhóm nghiên cứu và tổ chức nhỏ.

---

## Slide 18 - Kết luận: Đóng góp chính & Hướng phát triển (14:00, trang 23)

> _(Bấm Click 1 — hiện Cột trái: Đóng góp chính)_
> Tổng kết lại, khóa luận đóng góp 3 giá trị cốt lõi:
>
> - **Về Khoa học**: Đề xuất biểu diễn đồ thị 2 tầng (State Graph $\leftrightarrow$ Operator Graph) và thuật toán phát hiện skill, quy nạp operator và ghép chuỗi đa bước.
> - **Về Thực tiễn**: Cung cấp pipeline tự động hóa hoàn chỉnh, sinh **9.007 mẫu SFT**, huấn luyện **HSGE-9B đạt 24,6% Task SR** với chi phí rẻ hơn **3,3 lần** so với Go-Browse.
> - **Tài nguyên mở**: Bàn giao toàn bộ mã nguồn, bộ dataset và trọng số mô hình HSGE-9B.
>
> _(Bấm Click 2 — hiện Cột phải: Hướng phát triển tương lai)_
> Hướng phát triển tương lai tập trung vào 4 điểm:
>
> 1. **Khôi phục lỗi tự động**: Tự sửa lỗi và thử lại khi gặp sự cố giao diện (timeout, kẹt trang DOM).
> 2. **Tối ưu khám phá với RL**: Kết hợp Học tăng cường (RL) giúp Explorer tự học chiến lược duyệt web tối ưu.
> 3. **Học từ thất bại**: Khai thác các trajectory thất bại thông qua DPO / Preference Learning.
> 4. **Tổng quát hóa**: Mở rộng pipeline khám phá cho các ứng dụng ngoài miền (cross-domain).
>
> Em xin chân thành cảm ơn Thầy Cô trong Hội đồng đã chú ý lắng nghe và xin nhận câu hỏi góp ý!

**Câu chốt:** Khóa luận chứng minh tính khả thi của việc tự sinh dữ liệu và fine-tune SLM chạy cục bộ với chi phí tối ưu.

---

## Phụ lục PL1–PL8: câu hỏi nào bật trang nào

Phụ lục không có số footer — cột "Trang" dưới đây là **số trang PDF** trong `main.pdf`.

| Slide | Trang | Nội dung                                            | Bật khi được hỏi về                                                    |
| ----- | ----- | --------------------------------------------------- | ---------------------------------------------------------------------- |
| PL1   | 45    | Tính hợp lệ của phép đánh giá                       | "Explore rồi test trên cùng app thì có hợp lệ không?"                  |
| PL2   | 46    | Hướng đến ai; pipeline mới là thứ tổng quát         | "Có phải muốn model generalize cho mọi trang không?"                   |
| PL3   | 47    | Task khả thi, ngân sách bước, tiêu chuẩn hoàn thành | "Task LLM đề xuất có thật không?", "Sao 25 bước?", "Sao biết đã xong?" |
| PL4   | 48    | Ba CH: số liệu và mức độ trả lời                    | "Thực nghiệm trả lời được mục tiêu chưa?"                              |
| PL5   | 49    | Chi phí chi tiết                                    | "Chi phí đã tính đủ chưa?"                                             |
| PL6   | 50    | Frontier hai tầng                                   | "Khám phá không bị lạc bằng cách nào?"                                 |
| PL7   | 51    | Nguyên nhân thất bại; đặc tính hai mô hình          | "Điểm nghẽn còn lại ở đâu?"                                            |
| PL8   | 52    | Thêm dữ liệu; đổi mô hình nền                       | "Thêm dữ liệu nữa có tốt hơn không?", "Sao không dùng mô hình khác?"   |

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

### B. Các câu khác

| Câu hỏi                                                                                                    | Bật                            | Hướng trả lời                                                                                                                                                                                                                                                                                                                |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Đóng góp mới so với Go-Browse / NNetNav là gì?                                                             | Slide 6–7                      | Kỹ năng được **kiểm chứng**, nâng thành operator có tiền điều kiện/kết quả, rồi **ghép chuỗi** thành task dài — hai cột mà cả hai công trình kia đều trống. Cộng thêm hai cổng chất lượng và prompt parity.                                                                                                                  |
| Sao không chứng minh được đồ thị tốt hơn khám phá phẳng?                                                   | Slide 18, PL4                  | Đúng, đó là ablation quan trọng nhất và chưa chạy. Thiết kế đã có sẵn: cùng ngân sách episode và lượt gọi, chỉ đổi chiến lược khám phá.                                                                                                                                                                                      |
| Vì sao ghép chuỗi chỉ sinh 12/142 task?                                                                    | Slide 11                       | Cạnh operator cần kết quả khớp tiền điều kiện; sau hai cổng chống trùng lặp và kiểm chứng thực tế, đồ thị còn thưa. Hạn chế đã ghi trong Chương 5.                                                                                                                                                                           |
| 24,6% có thấp quá không?                                                                                   | Slide 15                       | So với chính mô hình nền cùng điều kiện là **+11,3 điểm, p<0,001, có ý nghĩa trên cả 4/4 website**. Benchmark này GPT-4 chỉ đạt ~14% khi công bố, người đạt 78%. 24,6% ngang nhóm mô hình mở tốt nhất dưới 10B.                                                                                                              |
| Vì sao tin số liệu khi agent tự chấm?                                                                      | PL3                            | Không tin — ba lớp kiểm chứng; và phần đánh giá cuối dùng bộ chấm tự động của WebArena, không phải agent.                                                                                                                                                                                                                    |
| Chi phí đã tính đủ chưa?                                                                                   | PL5                            | **54,21 API + 24,40 GPU = 78,61 đô la** cho cả bốn website; chưa tính hạ tầng WebArena tự host và công vận hành. Mỗi trajectory 0,0308 đô — rẻ hơn Go-Browse 3,3 lần.                                                                                                                                                        |
| Vì sao chọn Qwen3.5-9B mà không nhỏ hơn?                                                                   | Slide 18, PL8                  | Ngưỡng "chạy được trên máy phổ thông" là dưới 10B; chưng cất xuống 1–3B là hướng phát triển. PL8 có sẵn phép đo đổi mô hình nền sang Qwen-2.5-7B trên **cùng** tập dữ liệu.                                                                                                                                                  |
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

- [ ] Mở sẵn `main.pdf` ở chế độ toàn màn hình, kiểm tra nhảy được tới **trang PDF 45–52** (phụ lục PL1–PL8).
- [ ] Video demo mở sẵn ở tab riêng, **âm lượng 0**, đã thử phát một lần.
- [ ] Nhớ ba con số không được nói sai: **24,6% / 13,3% / +11,3 điểm**.
- [ ] Slide 3 phải nói ra chữ **"một tập website cố định"**; slide 7 phải có chữ
      **"tiềm năng"** khi nhắc kiểm thử E2E.
- [ ] Nhớ hai chỗ **không được nói quá**: "ngang Go-Browse" (không phải _vượt_), và
      "ghép chuỗi mới khả thi" (không phải _đã đủ dày_).
- [ ] Người 2 nắm chắc mốc 8:50 — nếu người 1 trễ quá 1 phút thì lược
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
   song hai máy trên site sống.
