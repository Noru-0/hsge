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
- Cột "Trang" là số trang PDF thật, để nhảy nhanh khi hỏi đáp.

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

Trang 3, 6, 12, 18 là mục lục đầu mỗi chương — bấm lướt, không dừng nói.
Trang 20 là trang cảm ơn; dừng ở đó và mời Hội đồng đặt câu hỏi.

---

## Slide 1 — Bìa (0:00, trang 1)

> Kính thưa Hội đồng. Em là Trương Bảo Kiệt, cùng bạn Hồ Tiến Phát, trình bày khóa
> luận *"Khám phá theo đồ thị kỹ năng phân cấp để tự động sinh dữ liệu huấn luyện cho
> tác nhân trí tuệ nhân tạo trên web"*, dưới sự hướng dẫn của PGS.TS. Nguyễn Văn Vũ.
>
> Bài trình bày gồm bốn phần: bài toán và định vị, phương pháp HSGE, kết quả thực
> nghiệm, và kết luận.

---

## Slide 2 — Bối cảnh, bài toán, thách thức (0:30, trang 4)

> Web agent là tác nhân nhận yêu cầu bằng ngôn ngữ tự nhiên rồi tự thao tác trên trình
> duyệt để hoàn thành. Muốn dùng nó trong thực tế thì hiện phải gọi API của các mô hình
> lớn — tốn tiền theo từng bước, độ trễ cao, và dữ liệu nội bộ phải gửi ra ngoài.
>
> Hướng thay thế là dùng mô hình ngôn ngữ nhỏ, dưới 10 tỷ tham số, chạy ngay tại chỗ.
> Nhưng mô hình nhỏ không tự biết thao tác trên một website cụ thể; phải fine-tune nó,
> mà fine-tune thì cần dữ liệu trajectory của chính website đó — thứ gần như không có
> sẵn. Gán nhãn tay thì rất đắt: AutoWebGLM cần **20 người làm liên tục một tháng**.
>
> Vì vậy bài toán của khóa luận là: **tự động khám phá một website đang hoạt động và
> sinh ra dữ liệu huấn luyện cho website đó, không dùng bất kỳ nhãn nào do con người
> tạo.**
>
> `[lược nếu trễ]` Năm thách thức kỹ thuật ở cột phải: khám phá không bị lạc, sinh task
> có ý nghĩa, tự kiểm chứng, ghép được task dài, và giữ prompt đồng nhất giữa huấn
> luyện với suy luận.

**Câu chốt:** nút thắt không phải mô hình, mà là **dữ liệu cho từng website cụ thể**.

**Tránh:** đừng nói "làm agent tổng quát cho mọi website" — đó chính là hiểu nhầm mà
slide 3 và PL2 phải chặn.

---

## Slide 3 — Mục tiêu và định vị (1:45, trang 5)

> Khóa luận đặt năm mục tiêu: khám phá tự động, sinh semantic task đã kiểm chứng, tinh
> lọc thành dataset, fine-tune và đánh giá trên WebArena, và đúc kết kinh nghiệm vận
> hành.
>
> Bảng bên phải là định vị so với bốn công trình gần nhất. AWM và SkillWeaver có khai
> thác kỹ năng, nhưng chỉ dùng ở thời điểm suy luận — không huấn luyện lại mô hình.
> NNetNav và Go-Browse có huấn luyện mô hình nhỏ, nhưng dữ liệu dừng ở mức từng trang
> đơn, không có tầng kỹ năng được kiểm chứng.
>
> Khoảng trống là ở chỗ chưa công trình nào nối trọn ba khâu: **kiểm chứng kỹ năng →
> ghép thành task dài → huấn luyện mô hình nhỏ**. Đó là phần khóa luận làm.

**Câu chốt:** đóng góp nằm ở **tầng trừu tượng thứ hai** — kỹ năng đã kiểm chứng — chứ
không phải ở việc thu nhiều dữ liệu hơn.

---

## Slide 4 — Tổng quan pipeline HSGE (3:00, trang 7)

> Đây là toàn bộ phương pháp trên một hình. Vòng lặp khép kín, chạy hoàn toàn tự động.
>
> Bắt đầu từ frontier — hàng đợi các trang cần khám phá. Chọn một trang, một agent đề
> xuất các task làm được ngay trên trang đó, rồi solver thử giải từng task trên trình
> duyệt thật. Những trajectory giải thành công được đưa vào khâu phát hiện kỹ năng: cắt
> thành đoạn, gom cụm, trừu tượng hóa thành thẻ kỹ năng, rồi quy nạp thành operator có
> tiền điều kiện và kết quả.
>
> Các operator này ghép chuỗi với nhau để sinh ra task nhiều bước. Toàn bộ trajectory
> thu được đi qua hai cổng lọc chất lượng trước khi trở thành dữ liệu huấn luyện. Và
> mỗi trang mới phát hiện lại quay về frontier — vòng lặp đóng lại ở đó.

**Câu chốt:** không phải thu trajectory rời rạc, mà **tích lũy tri thức có cấu trúc rồi
mới khai thác lại**.

---

## Slide 5 — Đồ thị hai tầng (4:15, trang 8)

> Tri thức được lưu trong một đồ thị hai tầng.
>
> Tầng thấp là đồ thị trạng thái: các trang đã thăm và hành động chuyển giữa chúng —
> đây là vết duyệt web thô.
>
> Tầng cao là đồ thị operator. Mỗi operator là một kỹ năng đã được chuẩn hóa, mang tiền
> điều kiện và kết quả tường minh. Hai operator nối được với nhau khi **kết quả của cái
> trước thỏa tiền điều kiện của cái sau** — và chính quan hệ đó cho phép ghép thành
> chuỗi thao tác dài.
>
> Điểm cần nhấn: nhờ biểu diễn này, thứ pipeline tích lũy được không phải một đống
> trajectory rời rạc, mà là tri thức **tái sử dụng và tái tổ hợp được**.

**Câu chốt:** tầng cao là thứ phân biệt HSGE với Go-Browse — bên đó chỉ có tầng thấp.

---

## Slide 6 — Phát hiện skill và quy nạp operator (5:15, trang 9)

> Khâu phát hiện kỹ năng chỉ chạy trên trajectory của task **đã giải thành công**, qua
> bốn bước: phân cắt trajectory theo đổi URL và tụt tương đồng cây trợ năng; gom cụm
> các đoạn giống nhau; trừu tượng hóa mỗi cụm thành một thẻ kỹ năng có tham số; và kiểm
> chứng bằng cách thực thi lại trong ngữ cảnh mới.
>
> Từ kỹ năng lên operator còn hai cổng chặn nữa. Cổng chống trùng lặp loại các operator
> mà kết quả chỉ chép lại tiền điều kiện — tức không phát biểu được điều gì mới. Cổng
> kiểm chứng thực tế gỡ bỏ những kết quả không đúng trên quá nửa số thành viên trong
> cụm.
>
> `[lược nếu trễ]` Hai cổng này khắt khe có chủ đích: trong 146 kỹ năng thu được, chỉ
> 57 vượt qua để thành operator.

**Câu chốt:** "đã kiểm chứng" ở đây là **có cổng chặn đo được**, không phải nhãn tự
phong.

---

## Slide 7 — Sinh semantic task (6:30, trang 10)

> Semantic task — task nhiều bước, có ngữ nghĩa hoàn chỉnh — được sinh từ hai nguồn.
>
> Nguồn từ dưới lên là ghép chuỗi operator: duyệt trên đồ thị operator, mỗi chuỗi từ hai
> operator trở lên thành một task dài kèm chỉ dẫn ngôn ngữ tự nhiên. Nguồn từ trên
> xuống là seed năng lực website, dùng khi đồ thị còn quá thưa để ghép.
>
> Số liệu thực tế em xin nói thẳng: trong **142 semantic task** đã thực thi, **130 đến
> từ seed và chỉ 12 đến từ ghép chuỗi operator**, đạt 71 task thành công. Cơ chế từ dưới
> lên chạy đúng thiết kế nhưng kích hoạt còn thưa — đây là hạn chế chúng em nêu lại ở
> slide kết luận.

**Câu chốt:** cơ chế ghép chuỗi được chứng minh là **khả thi**, chưa chứng minh được là
**đủ dày** để làm nguồn dữ liệu chính.

**Tránh:** đừng nói "semantic task chủ yếu sinh từ đồ thị operator" — số liệu ngược lại,
và Hội đồng có thể đã đọc Chương 5.

---

## Slide 8 — Tinh lọc dữ liệu (7:30, trang 11) — *điểm chuyển người trình bày*

> Nguyên tắc xuyên suốt: **không episode nào được tính là thành công bằng lời khai của
> chính agent.**
>
> Cổng thứ nhất — mọi lần agent tự tuyên bố hoàn thành đều được một mô hình độc lập chấm
> lại trên chính trạng thái trang cuối. Cổng này đã hạ cấp **801 episode, khoảng 27%**
> số lần tự tuyên bố.
>
> Cổng thứ hai bắt đúng nhóm mà cổng thứ nhất **về nguyên tắc** không thấy được: task
> gắn nhãn sửa đổi nhưng không có hành động nào thực sự thay đổi trang. Judge chỉ nhìn
> trang cuối, mà trang cuối thì không đổi. Cổng này viết bằng mã, loại thêm **104
> trajectory**.
>
> Cuối cùng là prompt parity: prompt lúc huấn luyện trùng từng byte với prompt solver
> dùng lúc chạy thật, kể cả ngưỡng cắt cây trợ năng ở 6000 ký tự. Train và validation
> chia ở cấp task, nên **không mục tiêu nào xuất hiện ở cả hai tập**.

**Câu chốt:** ba lớp kiểm soát, và lớp thứ ba tồn tại vì lớp thứ hai có điểm mù cấu
trúc.

---

## Slide 9 — Thiết lập thực nghiệm (8:30, trang 13)

> Môi trường là bốn website WebArena nhóm tự triển khai: Shopping, Shopping Admin,
> GitLab và Reddit. Đánh giá trên **655 task chính thức** của benchmark, chấm hoàn toàn
> tự động bằng bộ chấm của WebArena, giới hạn 15 bước mỗi task, nhiệt độ bằng 0.
>
> Khám phá chạy bốn đợt, khoảng 21 giờ mỗi website, tổng cộng hơn 20 nghìn lượt gọi mô
> hình. Huấn luyện dùng Qwen3.5-9B với LoRA, 1119 bước trong 5 giờ 09 phút.
>
> Bốn câu hỏi nghiên cứu ở cột phải sẽ được trả lời lần lượt trong ba slide tiếp theo.

**Câu chốt:** đánh giá dùng **bộ chấm chính thức của benchmark**, không phải cơ chế kiểm
chứng nội bộ của nhóm.

---

## Slide 10 — CH1: thu được gì, chi phí bao nhiêu (9:15, trang 14)

> Phễu khám phá: duyệt **455 trang**, ghi nhận **3981 lượt thử**, trong đó **2117 hợp lệ
> sau kiểm chứng** — tức 53%. Từ đó thu được **146 kỹ năng**, quy nạp **57 operator**,
> thực thi **142 semantic task**. Sau hai cổng lọc còn **1760 trajectory**, xuất ra
> **9007 mẫu** huấn luyện — không mẫu nào do con người gán nhãn.
>
> Về chi phí: **54,21 đô la** tiền gọi API cho toàn bộ giai đoạn khám phá, cộng **24,40
> đô la** tiền thuê GPU cho fine-tune và đánh giá. Quy về mỗi trajectory thành công là
> **3,1 cent** — rẻ hơn Go-Browse khoảng **3,3 lần**.
>
> `[lược nếu trễ]` Con số đáng chú ý không phải tổng chi phí mà là vị trí của nó: rào
> cản không nằm ở khâu huấn luyện hay đánh giá, mà ở khâu thu thập dữ liệu.

**Câu chốt:** cả chu trình cho bốn website tốn **dưới 80 đô la** và **không cần người gán
nhãn**.

---

## Slide 11 — CH2: kết quả chính (10:15, trang 15)

> Trên 655 task chính thức, mô hình sau fine-tune đạt **24,6%**, so với **13,3%** của
> chính mô hình đó khi chưa fine-tune — chênh **11,3 điểm phần trăm**.
>
> Vì hai mô hình được đo trên cùng một tập task, cùng prompt, cùng ngân sách bước và
> cùng bộ chấm, phép kiểm định phù hợp là McNemar theo cặp: **100 task chỉ mô hình
> fine-tune giải được**, so với 26 task chỉ mô hình nền giải được, cho p nhỏ hơn 0,001.
>
> Mức tăng đạt ý nghĩa thống kê trên **cả bốn website**, p không quá 0,011 ở website
> yếu nhất. Reddit tăng mạnh nhất, từ 6,6% lên 34%.
>
> `[lược nếu trễ]` Một chi tiết về quy trình đo: cơ sở dữ liệu cả bốn website được khôi
> phục nguyên trạng trước mỗi lượt đo, vì một đợt đo trước đó cho thấy thay đổi của lượt
> trước bị bộ chấm ghi nhận cho lượt sau.

**Câu chốt:** so sánh với **chính mô hình nền trong cùng điều kiện** — đây là phép đo
sạch nhất khóa luận có.

---

## Slide 12 — CH2–CH3: phần tăng thuộc về năng lực nào (11:30, trang 16)

> Slide này là giới hạn diễn giải quan trọng nhất, và chúng em muốn nêu chủ động thay vì
> để Hội đồng phải hỏi.
>
> Mô hình nền hỏng định dạng đầu ra ở **170 trên 655** phiên — hơn một phần tư số phiên
> kết thúc vì phản hồi không phân giải được thành hành động hợp lệ. Ở mô hình sau
> fine-tune con số đó chỉ còn **4**.
>
> Tách 655 task theo đúng ranh giới đó. Trên 170 task mà mô hình nền hỏng định dạng, nó
> được 0, mô hình fine-tune được 47. Trên **485 task còn lại** — nơi mô hình nền vẫn
> chạy trọn vẹn — hai bên là **17,9% và 23,5%, với p bằng 0,003**, tức **vẫn đạt** ý
> nghĩa thống kê.
>
> Nghĩa là tập dữ liệu dạy được **cả hai thứ**: vừa kỷ luật của giao diện hành động,
> vừa năng lực *chọn* đúng hành động.
>
> Đặt cạnh nhóm dưới 10B: kết quả cao hơn NNetNav-7B và GPT-4o-mini, và **ngang**
> Go-Browse-7B — chênh 2,0 điểm, nhỏ hơn khoảng tin cậy ±3,3 điểm.

**Câu chốt:** phần tăng **không chỉ** là học đúng cú pháp; nhóm 485 task đã chứng minh
điều đó với p = 0,003.

**Tránh:** **không nói "vượt Go-Browse" hay "dẫn đầu"**. Quyển ghi rõ phát biểu đúng là
*ngang*; nói quá ở đây là tự tạo mâu thuẫn với chính báo cáo.

---

## Slide 13 — Demo (12:45, trang 17)

> Đây là mô hình sau fine-tune giải một task WebArena thật.
>
> Đầu vào chỉ gồm URL và cây trợ năng của trang — **không dùng ảnh chụp màn hình**. Mỗi
> bước mô hình sinh ra một cặp suy nghĩ và hành động, hành động được thực thi thẳng
> trên trình duyệt.
>
> *(Chạy video. Vừa chạy vừa chỉ: đây là bước đọc trang, đây là hành động, đây là trạng
> thái trang sau hành động, và đây là bước kết thúc khi mô hình tự tuyên bố hoàn thành.)*
>
> Toàn bộ chuỗi này chạy cục bộ trên một GPU, không gọi ra dịch vụ bên ngoài.

**Cue kỹ thuật:** mở video trước ở tab riêng, **âm lượng = 0**. Chạy xong quay lại
trang 19 (slide 14). Nếu video lỗi: mô tả bằng lời trong 20 giây rồi đi tiếp — đừng sửa
trên bục.

---

## Slide 14 — Kết luận (14:00, trang 19)

> Tóm lại, khóa luận đã dựng được một pipeline khép kín chạy trên bốn website thật, thu
> 146 kỹ năng và 57 operator, tạo ra tập dữ liệu 1760 trajectory và 8554 mẫu huấn luyện
> hoàn toàn tự động; fine-tune một mô hình 9B lên **24,6%** trên 655 task chính thức của
> WebArena, so với 13,3% của chính nó khi chưa fine-tune.
>
> Hai hạn chế chúng em nêu rõ. Thứ nhất, cơ chế ghép chuỗi operator mới chứng minh được
> là khả thi chứ chưa đủ dày — chỉ 12 trên 142 semantic task đến từ nó. Thứ hai, và
> quan trọng hơn: **ablation so sánh khám phá theo đồ thị với khám phá phẳng vẫn chưa
> chạy** — đó là phép đo duy nhất chứng minh trực tiếp giá trị của cấu trúc đồ thị.
>
> Hướng phát triển gồm bổ sung trajectory phục hồi sau lỗi, khai thác tín hiệu thất bại
> bằng học tăng cường, và chưng cất xuống mô hình 1–3B.
>
> Em xin hết phần trình bày. Kính mong nhận được góp ý của Hội đồng.

**Câu chốt:** chủ động nêu hạn chế trước khi bị hỏi — đặc biệt là ablation chưa chạy.

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
| Động lực hướng đến ai? Có phải muốn một model generalize cho mọi trang cùng lĩnh vực? | **PL2** | **Không.** Đích nhắm là chuyên biệt hóa cho *một* website cụ thể. Câu chốt: **thứ tổng quát hóa là pipeline, không phải model**. Người dùng đích là nhóm vận hành vài website cố định, cần agent chạy tại chỗ. Khả thi vì **dưới 20 đô la mỗi website** và không cần người gán nhãn. |
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
| Điểm nghẽn còn lại ở đâu? | PL7 | Tầng thực thi: 85–96% episode thất bại có ít nhất một hành động bị trình duyệt từ chối. Fine-tune làm mô hình **bền bỉ** hơn chứ không **chính xác** hơn — tỷ lệ lỗi trên mỗi bước gần như không đổi. |
| Thêm dữ liệu nữa có tốt hơn không? | PL8 | Có, nhưng hiệu suất giảm nhanh: gần **gấp ba** dữ liệu của hai website chỉ đổi lấy **+2,1 điểm**. Nên hướng tiếp theo là sửa tầng thực thi, không phải nhân đôi dữ liệu. |

---

## Checklist trước khi lên

- [ ] Mở sẵn `main.pdf` ở chế độ toàn màn hình, kiểm tra nhảy được tới trang 22–29.
- [ ] Video demo mở sẵn ở tab riêng, **âm lượng 0**, đã thử phát một lần.
- [ ] Nhớ ba con số không được nói sai: **24,6% / 13,3% / +11,3 điểm**.
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
