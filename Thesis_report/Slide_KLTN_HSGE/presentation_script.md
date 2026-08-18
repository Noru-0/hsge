# Kịch bản trình bày — Bảo vệ KLTN HSGE

**Ngân sách: 15 phút trình bày + 15 phút hỏi đáp.** 15 slide, trung bình 1 phút/slide.
Cột "Mốc" là thời điểm *bắt đầu* slide đó — nếu trễ quá 1 phút so với mốc, cắt bớt
phần chi tiết được đánh dấu `[có thể lược]`.

Gợi ý chia hai người: **Người 1** slide 1–10 (đặt vấn đề + phương pháp),
**Người 2** slide 11–15 (thực nghiệm + kết luận). Điểm cắt tự nhiên là ngay sau
slide 10, khi chuyển từ "làm thế nào" sang "đo được gì".

---

## Slide 1 — Bìa (0:00, 30 giây)

> Kính thưa Hội đồng. Chúng em là Trương Bảo Kiệt và Hồ Tiến Phát, thực hiện khóa
> luận "Xây dựng dữ liệu và tinh chỉnh mô hình ngôn ngữ nhỏ cho tác nhân trí tuệ
> nhân tạo trên web", dưới sự hướng dẫn của PGS.TS. Nguyễn Văn Vũ. Phương pháp
> chúng em đề xuất có tên HSGE — khám phá web theo đồ thị kỹ năng phân cấp.

## Slide 2 — Nội dung (0:30, 30 giây)

> Bài trình bày gồm bốn phần: đặt vấn đề, phương pháp HSGE, thực nghiệm và kết quả,
> và cuối cùng là kết luận.

## Slide 3 — Bối cảnh, bài toán, thách thức (1:00, 1 phút 30)

> Web agent hiện nay chạy được là nhờ các mô hình ngôn ngữ lớn độc quyền. Điều đó
> kéo theo ba rào cản khi triển khai thật: chi phí, độ trễ, và việc toàn bộ nội
> dung trang phải gửi ra máy chủ bên thứ ba.
>
> Mô hình ngôn ngữ nhỏ, dưới 10 tỷ tham số, giải quyết được cả ba — nhưng chỉ khi
> nó được chuyên biệt hóa cho website đó. Mà muốn chuyên biệt hóa thì phải
> fine-tune, và fine-tune lại đụng ngay nút thắt dữ liệu.
>
> Con số minh họa: AutoWebGLM cần 20 người gán nhãn làm việc trong một tháng.
> Mỗi website mới lại phải làm gần như lại từ đầu.
>
> Vì vậy bài toán của khóa luận là: cho một website đang chạy và một SLM đã
> pretrain, tạo ra phiên bản fine-tune làm được task trên website đó — mà **không
> dùng bất kỳ nhãn nào do con người tạo**.
>
> `[có thể lược]` Năm thách thức ở cột phải, em xin nhấn ba cái nặng nhất: khám phá
> website thật rất dễ sa vào hàng nghìn trang trùng cấu trúc; task sinh ngẫu nhiên
> gần như vô giá trị khi làm dữ liệu huấn luyện; và agent trong hệ thống này vừa
> ra đề vừa tự chấm — nên kiểm chứng là bắt buộc.

## Slide 4 — Mục tiêu và lộ trình (2:30, 1 phút)

> Khóa luận đặt năm mục tiêu, tương ứng đúng năm giai đoạn trong sơ đồ bên phải:
> khám phá tự động, sinh semantic task đã kiểm chứng, tinh lọc thành dataset,
> fine-tune và đánh giá, và cuối cùng là đúc kết kinh nghiệm vận hành.
>
> Đầu vào chỉ gồm hai thứ: một website đang chạy chưa có nhãn nào, và một SLM
> pretrain. Đầu ra là một mô hình được đo trên benchmark chính thức.

## Slide 5 — Tổng quan pipeline HSGE (3:30, 1 phút 30)

> Đây là toàn bộ phương pháp trên một slide. Vòng lặp đi từ trái sang phải, hàng trên:
> frontier chọn một trang, Explorer đề xuất các task gắn với trang đó, Solver thực thi
> trên trình duyệt thật, và mỗi task giải được để lại một trajectory.
>
> Hàng giữa là phần cốt lõi: trajectory thành công được cắt, gom cụm, trừu tượng hóa
> thành **skill**, và chỉ vào thư viện nếu qua kiểm chứng. Skill được nâng thành
> **operator** có precondition và effect, rồi ghép chuỗi thành **semantic task** dài
> hạn — loại task vượt khỏi phạm vi một trang đơn lẻ.
>
> Mũi tên đứt nét quay ngược lại chính là điểm mấu chốt: tri thức khám phá được nuôi
> vòng khám phá kế tiếp.
>
> Hàng dưới: mọi episode đều phải qua ba cổng chất lượng trước khi thành dữ liệu SFT.
>
> Bốn slide sau em xin đi vào từng khối.

## Slide 6 — Đồ thị hai tầng (5:00, 1 phút)

> Cấu trúc lưu tri thức là một đồ thị hai tầng. Tầng thấp là các trạng thái trang đã
> thăm, nối bằng cạnh hành động. Tầng cao là các skill, biểu diễn dưới dạng *option*
> — một bộ ba gồm tập khởi đầu, chính sách và điều kiện dừng.
>
> Skill được nâng lên thành operator khi có precondition và effect. Hai operator nối
> được với nhau khi effect của cái trước thỏa precondition của cái sau. Chính cạnh
> này sinh ra task dài hạn.
>
> Điểm cần nhấn: nhờ biểu diễn này, cái pipeline tích lũy được không phải một đống
> trajectory rời rạc, mà là tri thức **tái sử dụng và tái tổ hợp được**.

## Slide 7 — Frontier hai tầng (6:00, 1 phút)

> Về khám phá. Frontier là hàng đợi ưu tiên với hai tầng ứng viên. Tier 0 là URL mà
> solver đã thực sự đi tới — vào thẳng hàng đợi. Tier 1 là liên kết khai thác từ DOM,
> phải qua giới hạn theo khuôn dạng URL: tối đa 3 trang mỗi khuôn dạng.
>
> Chính giới hạn này khiến hàng nghìn trang sản phẩm hay bài đăng không thể làm ngập
> frontier, trong khi các loại trang khác nhau vẫn được thăm đủ. Ngoài ra, node nào
> có nội dung trùng mã băm với trang đã thăm thì bị bỏ qua — thực tế loại được
> 31 trên 258 node.
>
> `[có thể lược]` Ở phía Solver, bài học lớn nhất là nhắc bằng prompt không đủ. Một
> lần chạy thật cho thấy mô hình bấm mãi một liên kết chết suốt cả ngân sách bước dù
> cảnh báo đã hiện. Nên chúng em thay bằng chốt chặn cấu trúc: dừng cứng khi lặp cùng
> một đích mà trang không đổi.

## Slide 8 — Phát hiện skill và quy nạp operator (7:00, 1 phút)

> Pipeline phát hiện skill chỉ chạy trên trajectory của task **đã giải thành công**,
> qua bốn giai đoạn: phân cắt, gom cụm, trừu tượng hóa thành thẻ kỹ năng, và kiểm
> chứng. Không qua kiểm chứng thì bị loại.
>
> Khi nâng skill lên thành operator, có hai cổng chặn — cả hai đều rút ra từ chạy
> thật. Cổng chống tautology loại những effect chỉ lặp lại precondition. Cổng
> grounding gỡ bỏ effect không đúng trên ít nhất một nửa số thành viên của skill —
> đã từng có operator được nạp với độ chính xác effect bằng 0.

## Slide 9 — Sinh semantic task (8:00, 1 phút)

> Có hai nguồn sinh semantic task. Nguồn từ dưới lên là ghép chuỗi operator: duyệt
> DFS có chặn, mỗi chuỗi từ hai operator trở lên thành một task nhiều bước. Nguồn từ
> trên xuống là seed năng lực website, dùng khi đồ thị còn quá thưa.
>
> Số liệu thực tế em xin nói thẳng: trong 66 semantic task đã thực thi, 59 đến từ
> seed và chỉ 7 đến từ ghép chuỗi. Cơ chế từ dưới lên chạy đúng thiết kế nhưng kích
> hoạt rất thưa — nguyên nhân được phân tích ở Chương 5 và cũng là một hạn chế chúng
> em nêu ở cuối bài.

## Slide 10 — Tinh lọc dữ liệu (9:00, 1 phút) — *điểm chuyển người trình bày*

> Nguyên tắc xuyên suốt: không episode nào được tính là thành công bằng lời khai của
> chính agent.
>
> Cổng thứ nhất — mọi lần agent tự tuyên bố hoàn thành đều được một LLM độc lập chấm
> lại trên chính trang cuối. Cổng này đã hạ cấp 497 episode, khoảng 32%.
>
> Cổng thứ hai bắt đúng nhóm mà cổng thứ nhất bỏ sót: task gắn nhãn sửa đổi nhưng
> không có hành động nào thay đổi trang. Judge không thấy được, vì trang cuối không
> hề đổi. Cổng này loại thêm 104 trajectory.
>
> Cuối cùng là prompt parity: prompt huấn luyện trùng từng byte với prompt solver
> dùng lúc chạy thật, kể cả ngưỡng cắt accessibility tree. Và train/val được chia ở
> cấp task, nên không mục tiêu nào xuất hiện ở cả hai tập.

## Slide 11 — Thiết lập thực nghiệm (10:00, 1 phút)

> Thực nghiệm chạy trên bốn website WebArena tự triển khai, đánh giá trên 655 task
> chính thức với bộ chấm tự động của benchmark, ngân sách 15 bước mỗi task.
>
> Giai đoạn khám phá gồm bốn đợt, mỗi đợt khoảng 21 giờ, tổng hơn 20 nghìn lời gọi
> LLM. Mô hình đích là Qwen3.5-9B fine-tune bằng LoRA.
>
> Bốn câu hỏi nghiên cứu ở cột phải. Chúng em xin nói rõ ngay: câu hỏi 4 chỉ được
> trả lời một phần, vì các ablation có kiểm soát đã thiết kế nhưng chưa chạy kịp.

## Slide 12 — CH1: thu được gì (11:00, 1 phút)

> Phễu khám phá: 258 node, 2178 episode, trong đó 1067 episode hợp lệ sau kiểm chứng.
> Từ đó thu được 59 skill, quy nạp 25 operator, và thực thi 66 semantic task.
> Sau hai cổng lọc còn 1029 trajectory, xuất ra 4554 mẫu huấn luyện — không mẫu nào
> do con người gán nhãn.
>
> Chi phí toàn chu trình khoảng 59 đô la, tức 3,5 cent cho mỗi trajectory — bằng
> khoảng một phần ba chi phí mỗi trajectory mà Go-Browse báo cáo.

## Slide 13 — CH2: kết quả chính (12:00, 1 phút 30)

> Đây là kết quả chính. Trên 655 task chính thức, mô hình sau fine-tune đạt 20,8%,
> so với 13,3% của chính mô hình đó khi chưa fine-tune — chênh 7,5 điểm phần trăm.
>
> Vì hai mô hình được đo trên cùng một tập task, phép kiểm định phù hợp là McNemar
> theo cặp: 77 task chỉ mô hình fine-tune giải được, so với 28 task chỉ mô hình nền
> giải được, cho p nhỏ hơn 0,001.
>
> Mức cải thiện đạt ý nghĩa thống kê trên ba trong bốn website. Riêng Shopping Admin
> chỉ tăng 2,7 điểm và chưa tách được khỏi nhiễu.
>
> Một chi tiết về quy trình đo: cơ sở dữ liệu của cả bốn website được khôi phục
> nguyên trạng trước khi đo mô hình nền, vì một đợt đo trước đó cho thấy thay đổi
> của lượt trước bị bộ chấm ghi nhận cho lượt sau.

## Slide 14 — Phần tăng thuộc về năng lực nào (13:30, 1 phút 30)

> Slide này là giới hạn diễn giải quan trọng nhất của khóa luận, và chúng em muốn
> nêu chủ động thay vì để Hội đồng phải hỏi.
>
> Mô hình nền hỏng định dạng đầu ra ở 170 trên 655 episode — tức hơn một phần tư số
> phiên kết thúc vì phản hồi không phân giải được thành hành động hợp lệ. Ở mô hình
> sau fine-tune con số đó là 2.
>
> Tách theo tiêu chí này: trên đúng 170 task đó, mô hình nền được 0, mô hình
> fine-tune được 35. Trên 485 task còn lại, nơi mô hình nền chạy trọn vẹn, hai bên
> là 87 và 101, và p bằng 0,120 — chưa đạt ý nghĩa.
>
> Nghĩa là 35 trong 49 task tăng thêm thuộc về việc mô hình học được tính kỷ luật của
> giao diện hành động. Phần cải thiện về năng lực thao tác web tuy cùng chiều nhưng
> chưa tách khỏi nhiễu ở quy mô mẫu hiện tại. Chúng em kết luận đúng mức đó: pipeline
> sinh được dữ liệu đủ chất lượng để chuyên biệt hóa một mô hình nhỏ.
>
> Đặt cạnh các hệ thống cùng phân khúc dưới 10B, kết quả cao hơn NNetNav-7B, tiệm cận
> GPT-4o-mini, và thấp hơn Go-Browse-7B 1,8 điểm — với tập dữ liệu nhỏ hơn khoảng một
> bậc độ lớn. Nhưng đây không phải so sánh có kiểm soát: khác mô hình gốc, khác quy mô
> dữ liệu, khác ngân sách bước.

## Slide 15 — Kết luận (15:00, 1 phút)

> Tóm lại, khóa luận đã cài đặt trọn vẹn một pipeline đi từ một website không nhãn đến
> một mô hình được đánh giá chính thức, không dùng nhãn người, với chi phí khoảng 59
> đô la.
>
> Hạn chế chúng em nêu nguyên trạng: phần lớn mức tăng thuộc về tuân thủ định dạng;
> mỗi số liệu là một lần chạy nên chưa có lặp thống kê; ablation đồ thị so với khám
> phá phẳng — phép đo duy nhất chứng minh trực tiếp giá trị của cấu trúc đồ thị —
> chưa chạy; và ghép chuỗi operator mới kích hoạt thưa.
>
> Đó cũng chính là các hướng tiếp theo. Em xin hết phần trình bày, kính mời Hội đồng
> đặt câu hỏi.

---

## Câu hỏi dự kiến và hướng trả lời

| Câu hỏi | Hướng trả lời |
|---|---|
| Đóng góp mới so với Go-Browse / NNetNav là gì? | Skill graph làm bộ nhớ trung gian: skill được kiểm chứng, nâng thành operator có precondition/effect, rồi *ghép chuỗi* thành task dài hạn — thay vì chỉ sinh task theo trang. Cộng thêm hai cổng chất lượng và prompt parity. |
| Sao không chứng minh được đồ thị tốt hơn khám phá phẳng? | Đúng, đó là ablation quan trọng nhất và chưa chạy; nêu rõ ở slide 15. Thiết kế đã có: cùng ngân sách episode và lời gọi LLM, chỉ đổi chiến lược khám phá. |
| Vì sao ghép chuỗi chỉ sinh 7/66 task? | Cạnh operator cần effect khớp precondition; sau hai cổng chống tautology và grounding, đồ thị còn thưa. Đây là hạn chế đã ghi trong Chương 5. |
| 20,8% có thấp quá không? | So với chính mô hình nền cùng điều kiện là +7,5 điểm, p<0,001; benchmark này GPT-4 chỉ đạt ~14% khi công bố, người đạt 78%. Mức 20,8% nằm giữa nhóm mô hình mở tốt nhất dưới 10B. |
| Vì sao tin số liệu khi agent tự chấm? | Không tin — có cổng judge độc lập (hạ cấp 497 episode) và cổng hành động hữu hiệu (loại 104 trajectory); riêng phần đánh giá cuối dùng bộ chấm tự động của WebArena, không phải agent. |
| Chi phí đã tính đủ chưa? | 36,48 USD API + 22,70 USD GPU; chưa tính chi phí hạ tầng WebArena tự host và công sức vận hành. |
