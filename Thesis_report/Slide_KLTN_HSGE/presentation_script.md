# Kịch bản trình bày — Bảo vệ KLTN HSGE

**Ngân sách: 15 phút trình bày + 15 phút hỏi đáp, 15 slide** — theo thông báo bảo vệ
đợt 04/2026 của CTĐA. (Hướng dẫn chung 2023 của thầy Vũ ghi 20 phút / 20–35 slide;
nếu Hội đồng đợt này theo bản đó, xem mục "Nếu được 20 phút" ở cuối file.)

Cấu trúc bám đúng khung thầy Vũ yêu cầu: *giới thiệu → động lực → mục tiêu →
công trình liên quan → phương pháp → kết quả → demo → kết luận*.

Cột "Mốc" là thời điểm *bắt đầu* slide. Trễ quá 1 phút so với mốc thì cắt phần
đánh dấu `[có thể lược]`.

Gợi ý chia hai người: **Người 1** slide 1–9 (đặt vấn đề + phương pháp),
**Người 2** slide 10–15 (thực nghiệm + demo + kết luận). Điểm cắt tự nhiên là sau
slide 9, khi chuyển từ "làm thế nào" sang "đo được gì".

| Slide | Nội dung | Mốc | Thời lượng |
|---|---|---|---|
| 1 | Bìa | 0:00 | 0:30 |
| 2 | Bối cảnh, bài toán, thách thức | 0:30 | 1:15 |
| 3 | Mục tiêu và định vị | 1:45 | 1:15 |
| 4 | Tổng quan pipeline HSGE | 3:00 | 1:15 |
| 5 | Đồ thị hai tầng | 4:15 | 1:00 |
| 6 | Frontier hai tầng | 5:15 | 0:45 |
| 7 | Phát hiện skill → operator | 6:00 | 1:00 |
| 8 | Sinh semantic task | 7:00 | 0:45 |
| 9 | Tinh lọc dữ liệu | 7:45 | 1:00 |
| 10 | Thiết lập thực nghiệm | 8:45 | 0:45 |
| 11 | CH1 — thu được gì | 9:30 | 1:00 |
| 12 | CH2 — kết quả chính | 10:30 | 1:15 |
| 13 | CH2–CH3 — phân tích | 11:45 | 1:15 |
| 14 | **Demo** | 13:00 | 1:15 |
| 15 | Kết luận | 14:15 | 0:45 |

---

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

## Slide 6 — Frontier hai tầng (5:15)

> Frontier là hàng đợi ưu tiên với hai tầng ứng viên. Tier 0 là URL solver đã thực
> sự đi tới — vào thẳng hàng đợi. Tier 1 là liên kết khai thác từ DOM, phải qua
> giới hạn theo khuôn dạng URL: tối đa 3 trang mỗi khuôn dạng.
>
> Chính giới hạn này khiến hàng nghìn trang sản phẩm hay bài đăng không làm ngập
> frontier, trong khi các loại trang khác nhau vẫn được thăm đủ. Node trùng nội
> dung với trang đã thăm thì bị bỏ qua — thực tế loại được 31 trên 258 node.
>
> `[có thể lược]` Ở phía Solver, bài học lớn nhất là nhắc bằng prompt không đủ:
> một lần chạy thật cho thấy mô hình bấm mãi một liên kết chết suốt cả ngân sách
> bước dù cảnh báo đã hiện. Nên chúng em thay bằng chốt chặn cấu trúc.

## Slide 7 — Phát hiện skill và quy nạp operator (6:00)

> Pipeline phát hiện skill chỉ chạy trên trajectory của task **đã giải thành
> công**, qua bốn giai đoạn: phân cắt, gom cụm, trừu tượng hóa thành thẻ kỹ năng,
> và kiểm chứng. Không qua kiểm chứng thì bị loại.
>
> Khi nâng skill lên operator có hai cổng chặn, cả hai đều rút ra từ chạy thật.
> Cổng chống tautology loại những effect chỉ lặp lại precondition. Cổng grounding
> gỡ bỏ effect không đúng trên ít nhất một nửa số thành viên của skill — đã từng
> có operator được nạp với độ chính xác effect bằng 0.

## Slide 8 — Sinh semantic task (7:00)

> Có hai nguồn. Nguồn từ dưới lên là ghép chuỗi operator: mỗi chuỗi từ hai
> operator trở lên thành một task nhiều bước. Nguồn từ trên xuống là seed năng lực
> website, dùng khi đồ thị còn quá thưa.
>
> Số liệu thực tế em xin nói thẳng: trong 66 semantic task đã thực thi, 59 đến từ
> seed và chỉ 7 đến từ ghép chuỗi. Cơ chế từ dưới lên chạy đúng thiết kế nhưng
> kích hoạt rất thưa — đây cũng là một hạn chế chúng em nêu ở cuối bài.

## Slide 9 — Tinh lọc dữ liệu (7:45) — *điểm chuyển người trình bày*

> Nguyên tắc xuyên suốt: không episode nào được tính là thành công bằng lời khai
> của chính agent.
>
> Cổng thứ nhất — mọi lần agent tự tuyên bố hoàn thành đều được một LLM độc lập
> chấm lại trên chính trang cuối. Cổng này đã hạ cấp 497 episode, khoảng 32%.
>
> Cổng thứ hai bắt đúng nhóm mà cổng thứ nhất bỏ sót: task gắn nhãn sửa đổi nhưng
> không có hành động nào thay đổi trang. Judge không thấy được, vì trang cuối
> không hề đổi. Cổng này loại thêm 104 trajectory.
>
> Cuối cùng là prompt parity: prompt huấn luyện trùng từng byte với prompt solver
> dùng lúc chạy thật. Train/val chia ở cấp task, nên không mục tiêu nào xuất hiện
> ở cả hai tập.

## Slide 10 — Thiết lập thực nghiệm (8:45)

> Thực nghiệm chạy trên bốn website WebArena tự triển khai, đánh giá trên 655 task
> chính thức với bộ chấm tự động của benchmark, ngân sách 15 bước mỗi task.
> Khám phá gồm bốn đợt, mỗi đợt khoảng 21 giờ. Mô hình đích là Qwen3.5-9B
> fine-tune bằng LoRA.
>
> Bốn câu hỏi nghiên cứu ở cột phải. Chúng em xin nói rõ ngay: câu hỏi 4 chỉ được
> trả lời một phần, vì các ablation có kiểm soát đã thiết kế nhưng chưa chạy kịp.

## Slide 11 — CH1: thu được gì (9:30)

> Phễu khám phá: 258 node, 2178 episode, trong đó 1067 hợp lệ sau kiểm chứng. Từ
> đó thu được 59 skill, quy nạp 25 operator, thực thi 66 semantic task. Sau hai
> cổng lọc còn 1029 trajectory, xuất ra 4554 mẫu — không mẫu nào do con người gán
> nhãn.
>
> Chi phí toàn chu trình khoảng 59 đô la, tức 3,5 cent mỗi trajectory — bằng
> khoảng một phần ba chi phí mỗi trajectory mà Go-Browse báo cáo.

## Slide 12 — CH2: kết quả chính (10:30)

> Trên 655 task chính thức, mô hình sau fine-tune đạt 20,8%, so với 13,3% của
> chính mô hình đó khi chưa fine-tune — chênh 7,5 điểm phần trăm.
>
> Vì hai mô hình được đo trên cùng một tập task, phép kiểm định phù hợp là McNemar
> theo cặp: 77 task chỉ mô hình fine-tune giải được, so với 28 task chỉ mô hình
> nền giải được, cho p nhỏ hơn 0,001. Đạt ý nghĩa thống kê trên ba trong bốn
> website; riêng Shopping Admin chỉ tăng 2,7 điểm và chưa tách được khỏi nhiễu.
>
> `[có thể lược]` Một chi tiết về quy trình đo: cơ sở dữ liệu cả bốn website được
> khôi phục nguyên trạng trước khi đo mô hình nền, vì một đợt đo trước đó cho thấy
> thay đổi của lượt trước bị bộ chấm ghi nhận cho lượt sau.

## Slide 13 — Phần tăng thuộc về năng lực nào (11:45)

> Slide này là giới hạn diễn giải quan trọng nhất, và chúng em muốn nêu chủ động
> thay vì để Hội đồng phải hỏi.
>
> Mô hình nền hỏng định dạng đầu ra ở 170 trên 655 episode — hơn một phần tư số
> phiên kết thúc vì phản hồi không phân giải được thành hành động hợp lệ. Ở mô
> hình sau fine-tune con số đó là 2.
>
> Tách theo tiêu chí này: trên đúng 170 task đó, mô hình nền được 0, mô hình
> fine-tune được 35. Trên 485 task còn lại, hai bên là 87 và 101, và p bằng 0,120
> — chưa đạt ý nghĩa. Nghĩa là 35 trong 49 task tăng thêm thuộc về việc học tính
> kỷ luật của giao diện hành động. Chúng em kết luận đúng mức đó: pipeline sinh
> được dữ liệu đủ chất lượng để chuyên biệt hóa một mô hình nhỏ.
>
> Đặt cạnh nhóm dưới 10B, kết quả cao hơn NNetNav-7B, tiệm cận GPT-4o-mini, thấp
> hơn Go-Browse-7B 1,8 điểm — với dữ liệu nhỏ hơn một bậc độ lớn.

## Slide 14 — Demo (13:00)

> Sau đây là một episode thật của mô hình sau fine-tune, trên một task lấy nguyên
> văn từ bộ chính thức. Xin Hội đồng lưu ý ba điểm: mỗi bước mô hình chỉ nhận URL
> và accessibility tree chứ không nhận ảnh; nó phát ra cặp thought–action đúng
> định dạng, đây chính là năng lực mô hình nền không có; và kết quả do bộ chấm của
> benchmark xác nhận, không phải agent tự khai.

**Cue kỹ thuật**

- Video đã quay sẵn, **không** thao tác trực tiếp trên website sống lúc bảo vệ.
- Mở sẵn video ở một cửa sổ riêng trước khi vào phòng; chuyển cửa sổ tại slide này
  rồi quay lại slide 15. Kiểm tra âm lượng = 0 (video không cần tiếng).
- Độ dài mục tiêu 60–90 giây. Nếu quá 90 giây, cắt phần cuộn trang.
- Bản backup: để cùng video trong USB, và chèn ảnh poster vào slide (đã có sẵn
  chỗ, xem chú thích trong `sections/03_thucnghiem.tex`) để vẫn nói được nếu
  video không chạy.

## Slide 15 — Kết luận (14:15)

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

| Câu hỏi | Hướng trả lời |
|---|---|
| Đóng góp mới so với Go-Browse / NNetNav là gì? | Slide 3: skill được **kiểm chứng**, nâng thành operator có precondition/effect, rồi **ghép chuỗi** thành task dài hạn — hai cột mà cả hai công trình kia đều trống. Cộng thêm hai cổng chất lượng và prompt parity. |
| Sao không chứng minh được đồ thị tốt hơn khám phá phẳng? | Đúng, đó là ablation quan trọng nhất và chưa chạy; đã nêu ở slide 15. Thiết kế đã có: cùng ngân sách episode và lời gọi LLM, chỉ đổi chiến lược khám phá. |
| Vì sao ghép chuỗi chỉ sinh 7/66 task? | Cạnh operator cần effect khớp precondition; sau hai cổng chống tautology và grounding, đồ thị còn thưa. Hạn chế đã ghi trong Chương 5. |
| 20,8% có thấp quá không? | So với chính mô hình nền cùng điều kiện là +7,5 điểm, p<0,001. Benchmark này GPT-4 chỉ đạt ~14% khi công bố, người đạt 78%. 20,8% nằm giữa nhóm mô hình mở tốt nhất dưới 10B. |
| Vì sao tin số liệu khi agent tự chấm? | Không tin — có cổng judge độc lập (hạ cấp 497 episode) và cổng hành động hữu hiệu (loại 104 trajectory); phần đánh giá cuối dùng bộ chấm tự động của WebArena, không phải agent. |
| Chi phí đã tính đủ chưa? | 36,48 USD API + 22,70 USD GPU; chưa tính hạ tầng WebArena tự host và công vận hành. |
| Vì sao chọn Qwen3.5-9B mà không phải mô hình nhỏ hơn? | Ngưỡng "chạy được trên máy phổ thông" là dưới 10B; chưng cất xuống 1–3B là hướng phát triển đã nêu ở slide 15. |

## Nếu được 20 phút (theo hướng dẫn chung 2023)

Thêm bốn slide, theo thứ tự ưu tiên:

1. **Phân loại nguyên nhân thất bại** (Bảng 4.x): lỗi hành động 25–45%, kẹt vòng
   lặp 31–56% — trả lời trực tiếp "điểm nghẽn còn lại ở đâu".
2. **Ví dụ một semantic task** sinh từ chuỗi operator, kèm chuỗi precondition/effect.
3. **Lộ trình nghiên cứu** (`fig_roadmap.pdf`, đã có trong `images/`) đặt ngay sau
   slide mục tiêu.
4. **Bài học vận hành** (Chương 5): chat template, prompt-fidelity, hai máy chạy
   song song trên site sống.
