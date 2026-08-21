# Kịch bản trình bày — Bảo vệ KLTN HSGE

**Ngân sách: 15 phút trình bày + 15 phút hỏi đáp, 14 slide nội dung** — theo thông báo bảo vệ
đợt 04/2026 của CTĐA. (Hướng dẫn chung 2023 của thầy Vũ ghi 20 phút / 20–35 slide;
nếu Hội đồng đợt này theo bản đó, xem mục "Nếu được 20 phút" ở cuối file.)

Cấu trúc bám đúng khung thầy Vũ yêu cầu: *giới thiệu → động lực → mục tiêu →
công trình liên quan → phương pháp → kết quả → demo → kết luận*.

Cột "Mốc" là thời điểm *bắt đầu* slide. Trễ quá 1 phút so với mốc thì cắt phần
đánh dấu `[có thể lược]`.

Gợi ý chia hai người: **Người 1** slide 1–8 (đặt vấn đề + phương pháp),
**Người 2** slide 9–14 (thực nghiệm + demo + kết luận). Điểm cắt tự nhiên là sau
slide 8, khi chuyển từ "làm thế nào" sang "đo được gì".

Deck còn **8 slide phụ lục (PL1–PL8)** đặt sau slide cảm ơn, không tính vào 14 slide
nội dung và không hiện trong mục lục. Chúng dành riêng cho phần hỏi đáp — xem bảng
"Câu hỏi dự kiến" ở cuối file để biết câu nào bật slide nào.

| Slide | Nội dung | Mốc | Thời lượng |
|---|---|---|---|
| 1 | Bìa | 0:00 | 0:30 |
| 2 | Bối cảnh, bài toán, thách thức | 0:30 | 1:15 |
| 3 | Mục tiêu và định vị | 1:45 | 1:15 |
| 4 | Tổng quan pipeline HSGE | 3:00 | 1:15 |
| 5 | Đồ thị hai tầng | 4:15 | 1:00 |
| 6 | Phát hiện skill → operator | 5:15 | 1:15 |
| 7 | Sinh semantic task | 6:30 | 1:00 |
| 8 | Tinh lọc dữ liệu | 7:30 | 1:00 |
| 9 | Thiết lập thực nghiệm | 8:30 | 0:45 |
| 10 | CH1 — thu được gì | 9:15 | 1:00 |
| 11 | CH2 — kết quả chính | 10:15 | 1:15 |
| 12 | CH2–CH3 — phân tích | 11:30 | 1:15 |
| 13 | **Demo** | 12:45 | 1:15 |
| 14 | Kết luận | 14:00 | 1:00 |

*Slide "Frontier hai tầng" đã chuyển sang phụ lục (**PL6**) để giữ phần nội dung
trong 14 slide; nếu Hội đồng hỏi về cơ chế khám phá thì bật PL6.*

## Slide 1 — Bìa (0:00)

> Kính thưa Hội đồng. Chúng em là Trương Bảo Kiệt và Hồ Tiến Phát, thực hiện khóa
> luận "Xây dựng dữ liệu và tinh chỉnh mô hình ngôn ngữ nhỏ cho tác nhân trí tuệ
> nhân tạo trên web", dưới sự hướng dẫn của PGS.TS. Nguyễn Văn Vũ. Phương pháp
> chúng em đề xuất có tên HSGE — khám phá web theo đồ thị kỹ năng phân cấp.

## Slide 2 — Bối cảnh, bài toán, thách thức (0:30)

> Web agent hiện nay chạy được là nhờ các mô hình ngôn ngữ lớn độc quyền. Điều đó
> kéo theo ba rào cản khi triển khai thật: chi phí, độ trễ, và việc toàn bộ nội
> dung trang phải gửi ra máy chủ bên thứ ba.
>
> Mô hình ngôn ngữ nhỏ, dưới 10 tỷ tham số, giải quyết được cả ba — nhưng chỉ khi
> nó được chuyên biệt hóa cho website đó. Muốn chuyên biệt hóa thì phải fine-tune,
> và fine-tune lại đụng ngay nút thắt dữ liệu. AutoWebGLM cần 20 người gán nhãn
> làm việc trong một tháng; mỗi website mới lại phải làm gần như lại từ đầu.
>
> Vì vậy bài toán của khóa luận là: cho một website đang chạy và một SLM đã
> pretrain, tạo ra phiên bản fine-tune làm được task trên website đó — mà **không
> dùng bất kỳ nhãn nào do con người tạo**.
>
> `[có thể lược]` Trong năm thách thức bên phải, em xin nhấn ba cái nặng nhất:
> website thật rất dễ làm agent sa vào hàng nghìn trang trùng cấu trúc; task sinh
> ngẫu nhiên gần như vô giá trị khi làm dữ liệu huấn luyện; và agent ở đây vừa ra
> đề vừa tự chấm, nên kiểm chứng là bắt buộc.

## Slide 3 — Mục tiêu và định vị (1:45)

> Khóa luận đặt năm mục tiêu, từ khám phá tự động, sinh semantic task đã kiểm
> chứng, tinh lọc dataset, fine-tune và đánh giá, cho tới đúc kết kinh nghiệm.
>
> Bảng bên phải là phần định vị. Các công trình khám phá kỹ năng như AWM hay
> SkillWeaver có tích lũy tri thức có cấu trúc, nhưng chỉ dùng nó ở **thời điểm suy
> luận** cho mô hình lớn, không sinh dữ liệu huấn luyện. Ngược lại, nhóm sinh dữ
> liệu cho mô hình nhỏ như NNetNav hay Go-Browse thì khám phá ít cấu trúc và dừng
> ở mức trang đơn lẻ.
>
> Theo khảo sát của chúng em, chưa có công trình nào đi trọn cả ba bước: kiểm
> chứng skill, ghép chúng thành task dài hạn, rồi dùng chính task đó huấn luyện
> một mô hình nhỏ. Đó là khoảng trống khóa luận nhắm vào.

## Slide 4 — Tổng quan pipeline HSGE (3:00)

> Đây là toàn bộ phương pháp trên một slide. Hàng trên: frontier chọn một trang,
> Explorer đề xuất các task gắn với trang đó, Solver thực thi trên trình duyệt
> thật, và mỗi task giải được để lại một trajectory.
>
> Hàng giữa là phần cốt lõi: trajectory thành công được cắt, gom cụm, trừu tượng
> hóa thành **skill**, và chỉ vào thư viện nếu qua kiểm chứng. Skill được nâng
> thành **operator** có precondition và effect, rồi ghép chuỗi thành **semantic
> task** dài hạn.
>
> Mũi tên đứt nét quay ngược lại chính là điểm mấu chốt: tri thức khám phá được
> nuôi vòng khám phá kế tiếp. Hàng dưới: mọi episode đều phải qua các cổng chất
> lượng trước khi thành dữ liệu SFT. Năm slide sau em đi vào từng khối.

## Slide 5 — Đồ thị hai tầng (4:15)

> Tầng thấp là các trạng thái trang đã thăm, nối bằng cạnh hành động. Tầng cao là
> các skill, biểu diễn dưới dạng *option* — một bộ ba gồm tập khởi đầu, chính sách
> và điều kiện dừng.
>
> Skill được nâng thành operator khi có precondition và effect. Hai operator nối
> được với nhau khi effect của cái trước thỏa precondition của cái sau. Chính cạnh
> này sinh ra task dài hạn.
>
> Điểm cần nhấn: nhờ biểu diễn này, cái pipeline tích lũy được không phải một đống
> trajectory rời rạc, mà là tri thức **tái sử dụng và tái tổ hợp được**.

## Slide 6 — Phát hiện skill và quy nạp operator (5:15)

> Pipeline phát hiện skill chỉ chạy trên trajectory của task **đã giải thành
> công**, qua bốn giai đoạn: phân cắt, gom cụm, trừu tượng hóa thành thẻ kỹ năng,
> và kiểm chứng. Không qua kiểm chứng thì bị loại.
>
> Khi nâng skill lên operator có hai cổng chặn, cả hai đều rút ra từ chạy thật.
> Cổng chống tautology loại những effect chỉ lặp lại precondition. Cổng grounding
> gỡ bỏ effect không đúng trên ít nhất một nửa số thành viên của skill — đã từng
> có operator được nạp với độ chính xác effect bằng 0.

## Slide 7 — Sinh semantic task (6:30)

> Có hai nguồn. Nguồn từ dưới lên là ghép chuỗi operator: mỗi chuỗi từ hai
> operator trở lên thành một task nhiều bước. Nguồn từ trên xuống là seed năng lực
> website, dùng khi đồ thị còn quá thưa.
>
> Số liệu thực tế em xin nói thẳng: trong 142 semantic task đã thực thi, 130 đến
> từ seed và chỉ 12 đến từ ghép chuỗi operator. Cơ chế từ dưới lên chạy đúng thiết
> kế nhưng kích hoạt rất thưa — đây cũng là một hạn chế chúng em nêu ở cuối bài.

## Slide 8 — Tinh lọc dữ liệu (7:30) — *điểm chuyển người trình bày*

> Nguyên tắc xuyên suốt: không episode nào được tính là thành công bằng lời khai
> của chính agent.
>
> Cổng thứ nhất — mọi lần agent tự tuyên bố hoàn thành đều được một LLM độc lập
> chấm lại trên chính trang cuối. Cổng này đã hạ cấp 801 episode, khoảng 27%.
>
> Cổng thứ hai bắt đúng nhóm mà cổng thứ nhất bỏ sót: task gắn nhãn sửa đổi nhưng
> không có hành động nào thay đổi trang. Judge không thấy được, vì trang cuối
> không hề đổi. Cổng này loại thêm 104 trajectory.
>
> Cuối cùng là prompt parity: prompt huấn luyện trùng từng byte với prompt solver
> dùng lúc chạy thật. Train/val chia ở cấp task, nên không mục tiêu nào xuất hiện
> ở cả hai tập.

## Slide 9 — Thiết lập thực nghiệm (8:30)

> Thực nghiệm chạy trên bốn website WebArena tự triển khai, đánh giá trên 655 task
> chính thức với bộ chấm tự động của benchmark, ngân sách 15 bước mỗi task.
> Khám phá gồm bốn đợt, mỗi đợt khoảng 21 giờ. Mô hình đích là Qwen3.5-9B
> fine-tune bằng LoRA.
>
> Bốn câu hỏi nghiên cứu ở cột phải. Chúng em xin nói rõ ngay: câu hỏi 4 chỉ được
> trả lời một phần, vì các ablation có kiểm soát đã thiết kế nhưng chưa chạy kịp.

## Slide 10 — CH1: thu được gì (9:15)

> Phễu khám phá: 455 node, 3981 episode, trong đó 2117 hợp lệ sau kiểm chứng —
> tức 53%. Từ đó thu được 146 skill, quy nạp 57 operator, thực thi 142 semantic
> task. Sau hai cổng lọc còn 1760 trajectory, xuất ra 9007 mẫu — không mẫu nào do
> con người gán nhãn.
>
> Chi phí toàn chu trình là 78,6 đô la: 54,2 tiền gọi API và 24,4 tiền thuê GPU.
> Quy về mỗi trajectory thành công là 3,1 cent — rẻ hơn Go-Browse khoảng 3,3 lần.

## Slide 11 — CH2: kết quả chính (10:15)

> Trên 655 task chính thức, mô hình sau fine-tune đạt 24,6%, so với 13,3% của
> chính mô hình đó khi chưa fine-tune — chênh 11,3 điểm phần trăm.
>
> Vì hai mô hình được đo trên cùng một tập task, phép kiểm định phù hợp là McNemar
> theo cặp: 100 task chỉ mô hình fine-tune giải được, so với 26 task chỉ mô hình
> nền giải được, cho p nhỏ hơn 0,001. Lần này mức tăng đạt ý nghĩa thống kê trên
> **cả bốn** website, p không quá 0,011 ở website yếu nhất.
>
> `[có thể lược]` Một chi tiết về quy trình đo: cơ sở dữ liệu cả bốn website được
> khôi phục nguyên trạng trước khi đo mô hình nền, vì một đợt đo trước đó cho thấy
> thay đổi của lượt trước bị bộ chấm ghi nhận cho lượt sau.

## Slide 12 — Phần tăng thuộc về năng lực nào (11:30)

> Slide này là giới hạn diễn giải quan trọng nhất, và chúng em muốn nêu chủ động
> thay vì để Hội đồng phải hỏi.
>
> Mô hình nền hỏng định dạng đầu ra ở 170 trên 655 episode — hơn một phần tư số
> phiên kết thúc vì phản hồi không phân giải được thành hành động hợp lệ. Ở mô
> hình sau fine-tune con số đó chỉ còn 4.
>
> Tách theo tiêu chí này: trên đúng 170 task đó, mô hình nền được 0, mô hình
> fine-tune được 47. Trên 485 task còn lại — nơi mô hình nền vẫn chạy trọn vẹn —
> hai bên là 17,9% và 23,5%, và p bằng 0,003, tức **đạt** ý nghĩa. Nghĩa là tập dữ
> liệu dạy được cả hai thứ: vừa tính kỷ luật của giao diện hành động, vừa năng lực
> *chọn* đúng hành động — 27 trong 74 task tăng thêm nằm ở nhóm thứ hai.
>
> Đặt cạnh nhóm dưới 10B: cao hơn NNetNav-7B (19,1%) và GPT-4o-mini (20,0%), và
> ngang Go-Browse-7B (22,6%) — chênh 2,0 điểm, nhỏ hơn khoảng tin cậy ±3,3 nên
> phát biểu đúng là *ngang*, không phải *vượt*. Đạt được với dữ liệu nhỏ hơn
> khoảng năm lần.

## Slide 13 — Demo (12:45)

> Sau đây là một episode thật của mô hình sau fine-tune, trên một task lấy nguyên
> văn từ bộ chính thức. Xin Hội đồng lưu ý ba điểm: mỗi bước mô hình chỉ nhận URL
> và accessibility tree chứ không nhận ảnh; nó phát ra cặp thought–action đúng
> định dạng, đây chính là năng lực mô hình nền không có; và kết quả do bộ chấm của
> benchmark xác nhận, không phải agent tự khai.

**Cue kỹ thuật**

- Video đã quay sẵn, **không** thao tác trực tiếp trên website sống lúc bảo vệ.
- Mở sẵn video ở một cửa sổ riêng trước khi vào phòng; chuyển cửa sổ tại slide này
  rồi quay lại slide 14. Kiểm tra âm lượng = 0 (video không cần tiếng).
- Độ dài mục tiêu 60–90 giây. Nếu quá 90 giây, cắt phần cuộn trang.
- Bản backup: để cùng video trong USB, và chèn ảnh poster vào slide (đã có sẵn
  chỗ, xem chú thích trong `sections/03_thucnghiem.tex`) để vẫn nói được nếu
  video không chạy.

## Slide 14 — Kết luận (14:00)

> Tóm lại, khóa luận đã cài đặt trọn vẹn một pipeline đi từ một website không nhãn
> đến một mô hình được đánh giá chính thức, không dùng nhãn người, với chi phí
> khoảng 59 đô la.
>
> Hạn chế chúng em nêu nguyên trạng: phần lớn mức tăng thuộc về tuân thủ định
> dạng; mỗi số liệu là một lần chạy nên chưa có lặp thống kê; ablation đồ thị so
> với khám phá phẳng chưa chạy; và ghép chuỗi operator mới kích hoạt thưa. Đó cũng
> chính là các hướng tiếp theo.
>
> Em xin hết phần trình bày, kính mời Hội đồng đặt câu hỏi.

---

## Câu hỏi dự kiến và hướng trả lời

### A. Sáu câu thầy phản biện đã hỏi — mỗi câu có một slide phụ lục

| Câu hỏi | Bật slide | Hướng trả lời |
|---|---|---|
| Explore trên app của họ rồi test bằng bộ test của họ trên chính app đó thì có hợp lệ không? Phải test trên app khác cùng lĩnh vực chứ? | **PL1** | Pipeline **chưa từng nhìn thấy** 655 task benchmark — task huấn luyện do agent tự đề xuất từ giao diện; CSDL khôi phục nguyên bản trước mỗi đợt đo. Cùng-website là **giao thức chuẩn** của cả dòng nghiên cứu: Go-Browse cũng khám phá 20 URL/domain của WebArena rồi chấm trên chính 812 task WebArena. Test "app khác" là bài toán khác — ngoài miền — mà **chưa ai giải được**: trên Online-Mind2Web, Go-Browse-7B chỉ 5,33% và NNetNav-7B 4,00%, đều thua GPT-4o-mini 9,33%. |
| Động lực hướng đến ai? Có phải muốn một model generalize cho mọi trang cùng lĩnh vực không? | **PL2** | **Không.** Đích nhắm là chuyên biệt hóa cho *một* website cụ thể. Câu chốt: **thứ tổng quát hóa là pipeline, không phải model**. Người dùng đích là nhóm/doanh nghiệp vận hành vài website cố định, cần agent chạy tại chỗ. Khả thi vì dưới **\$20/website** và không cần người gán nhãn (đối chiếu AutoWebGLM: 20 người × 1 tháng). |
| Làm sao biết task do LLM đề xuất là hợp lý và làm được thật trên giao diện đó? | **PL3** (khối 1) | Bộ đề xuất là một *agent* đọc trực tiếp cây trợ năng của trang thật, không đề xuất từ trí nhớ. Quan trọng hơn: **khả thi được chứng minh bằng thực thi, không bằng lời** — chỉ task có ít nhất một lượt giải thành công *và qua kiểm chứng* mới vào dataset. 637 task bị chính agent báo bất khả thi; 3981 lượt thử còn 2117 hợp lệ (53,2%). |
| Vì sao ngân sách bước là 25? | **PL3** (khối 2) | Chính xác là **15 bước cho task cục bộ, 25 cho semantic task nhiều bước**. Solver chiếm 85,5% trong 20.808 lượt gọi LLM nên ngân sách bước *chính là* ngân sách tiền — đây trước hết là quyết định chi phí. Nhưng dữ liệu cho thấy nó **không bóp méo phép đo**: episode thành công có trung vị 6 bước, và **không episode nào** đạt được mục tiêu rồi mới bị cắt vì hết bước. |
| Dựa vào đâu để biết task đã hoàn thành? | **PL3** (khối 3) | **Ba lớp**, không phải hai: (i) solver tự khai hoặc vị từ tất định; (ii) LLM-as-Judge soi trạng thái trang cuối → hạ cấp **801 lượt** (27%); (iii) cổng "hành động hữu hiệu" bằng mã → loại **104 trajectory** tuyên bố xong mà không đổi gì trên trang, nhóm lỗi mà judge *về nguyên tắc* không thấy được. Và con số 24,6% được chấm bằng **bộ chấm chính thức của WebArena**, không phải judge của nhóm. |
| Thực nghiệm nhắm mục tiêu nào, kết quả đã trả lời được chưa? | **PL4** | CH1–CH4 đều có số liệu trả lời (bảng ở PL4). Phần phải nói thật: **O2 và O4 mới hoàn thành một phần** — chỉ 12/142 semantic task đến từ ghép chuỗi operator, và **ablation đồ thị so với khám phá phẳng vẫn chưa chạy**. |

### B. Các câu khác

| Câu hỏi | Bật slide | Hướng trả lời |
|---|---|---|
| Đóng góp mới so với Go-Browse / NNetNav là gì? | Slide 3 | Skill được **kiểm chứng**, nâng thành operator có precondition/effect, rồi **ghép chuỗi** thành task dài hạn — hai cột mà cả hai công trình kia đều trống. Cộng thêm hai cổng chất lượng và prompt parity. |
| Sao không chứng minh được đồ thị tốt hơn khám phá phẳng? | Slide 14, PL4 | Đúng, đó là ablation quan trọng nhất và chưa chạy. Thiết kế đã có: cùng ngân sách episode và lời gọi LLM, chỉ đổi chiến lược khám phá. |
| Vì sao ghép chuỗi chỉ sinh 12/142 task? | Slide 7 | Cạnh operator cần effect khớp precondition; sau hai cổng chống tautology và grounding, đồ thị còn thưa. Hạn chế đã ghi trong Chương 5. |
| 24,6% có thấp quá không? | Slide 11 | So với chính mô hình nền cùng điều kiện là **+11,3 điểm, p<0,001 trên cả 4/4 website**. Benchmark này GPT-4 chỉ đạt ~14% khi công bố, người đạt 78%. 24,6% ngang nhóm mô hình mở tốt nhất dưới 10B (Go-Browse-7B 22,6%, NNetNav-7B 19,1%). |
| Vì sao tin số liệu khi agent tự chấm? | PL3 | Không tin — ba lớp kiểm chứng (xem trên); phần đánh giá cuối dùng bộ chấm tự động của WebArena, không phải agent. |
| Chi phí đã tính đủ chưa? | PL5 | **54,21 USD API + 24,40 USD GPU = 78,61 USD** cho cả bốn website; chưa tính hạ tầng WebArena tự host và công vận hành. Quy về mỗi trajectory là 0,0308 USD — rẻ hơn Go-Browse 3,3 lần. |
| Vì sao chọn Qwen3.5-9B mà không phải mô hình nhỏ hơn? | Slide 14, PL8 | Ngưỡng "chạy được trên máy phổ thông" là dưới 10B; chưng cất xuống 1–3B là hướng phát triển. PL8 có sẵn phép đo đổi mô hình nền sang Qwen-2.5-7B trên cùng tập dữ liệu. |
| Điểm nghẽn còn lại nằm ở đâu? | PL7 | Tầng thực thi: 85–96% episode thất bại có ≥1 hành động bị trình duyệt từ chối. Fine-tune làm mô hình **bền bỉ** hơn chứ không **chính xác** hơn — tỷ lệ lỗi trên mỗi bước gần như không đổi (0,358 → 0,344). |
| Thêm dữ liệu nữa thì có tốt hơn không? | PL8 | Có, nhưng hiệu suất giảm nhanh: gần **gấp ba** dữ liệu của hai website chỉ đổi lấy **+2,1 điểm**. Nên hướng tiếp theo là sửa tầng thực thi, không phải nhân đôi dữ liệu. |

## Nếu được 20 phút (theo hướng dẫn chung 2023)

Thêm bốn slide, theo thứ tự ưu tiên:

1. **Kéo PL7 (nguyên nhân thất bại) và PL6 (frontier hai tầng) vào phần nội dung** —
   cả hai đã dựng sẵn trong phụ lục, chỉ cần đổi chỗ.
2. **Ví dụ một semantic task** sinh từ chuỗi operator, kèm chuỗi precondition/effect.
3. **Lộ trình nghiên cứu** (`fig_roadmap.pdf`, đã có trong `images/`) đặt ngay sau
   slide mục tiêu.
4. **Bài học vận hành** (Chương 5): chat template, prompt-fidelity, hai máy chạy
   song song trên site sống.
