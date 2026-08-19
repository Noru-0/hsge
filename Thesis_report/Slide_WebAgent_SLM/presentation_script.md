# Script Thuyết Trình — WebAgent: From Raw Trajectories to a Trained SLM

> **Ký hiệu:**
> - `[chuyển slide]` — bấm sang slide tiếp theo
> - *(nghiêng)* — gợi ý giọng điệu hoặc ngôn ngữ cơ thể
> - `⏱ ~Xs` — thời gian tham khảo cho từng phần

---

## SLIDE 1 — Trang bìa

*(Đứng thẳng, nhìn vào khán giả, nói chậm và rõ)*

"Xin chào thầy/cô và các bạn. Hôm nay em sẽ trình bày về đề tài:
**'WebAgent — From Raw Trajectories to a Trained Small Language Model'**,
tức là: từ dữ liệu thô thu thập từ trình duyệt, qua một pipeline xử lý và huấn luyện,
để tạo ra một mô hình ngôn ngữ nhỏ có khả năng tự điều hướng giao diện web."

`[chuyển slide]` ⏱ ~20s

---

## SLIDE 2 — Outline

"Bài trình bày của em được chia làm bốn phần chính.
Phần một là toàn bộ pipeline xử lý dữ liệu.
Phần hai là quá trình huấn luyện mô hình với SFT và LoRA.
Phần ba là đóng gói môi trường bằng Docker và triển khai lên cloud.
Và cuối cùng là tổng kết."

`[chuyển slide]` ⏱ ~15s

---

## PHẦN 1 — PROJECT OVERVIEW

---

## SLIDE 3 — Objective & Three-Phase Pipeline

*(Nói với giọng dẫn dắt, như đang kể một câu chuyện)*

"Mục tiêu của đề tài là huấn luyện một **mô hình ngôn ngữ nhỏ** —
gọi tắt là SLM — để nó có thể tự thao tác trên giao diện web
mà không cần gọi đến các mô hình AI lớn như GPT-4 hay Claude ở mỗi bước.

Để đạt được điều đó, em thiết kế một pipeline gồm **ba giai đoạn**:

Giai đoạn một là **xử lý dữ liệu** — làm sạch và chuẩn hóa các log trình duyệt thô.

Giai đoạn hai là **huấn luyện mô hình** — dùng kỹ thuật SFT kết hợp LoRA adapter
để fine-tune một SLM có sẵn.

Giai đoạn ba là **đóng gói và triển khai** — đóng gói toàn bộ môi trường vào Docker
để có thể chạy trên bất kỳ máy GPU nào trên cloud."

`[chuyển slide]` ⏱ ~40s

---

## PHẦN 2 — DATA PROCESSING

---

## SLIDE 4 — Purpose of the Data Processing Pipeline

*(Giọng giải thích, từ tốn)*

"Đầu vào của pipeline là các **log phiên trình duyệt thô** —
tức là các file JSON ghi lại từng hành động mà một AI agent thực hiện
khi nó duyệt một trang web thương mại điện tử.

Vấn đề là dữ liệu thô này rất **lộn xộn**:
có session không có HTML, có session bị lặp hành động,
có session quá ngắn để học được gì.
Nếu đưa trực tiếp vào huấn luyện, mô hình sẽ bị 'nhiễm' bởi dữ liệu xấu.

Mục tiêu của pipeline là biến các log thô này thành các cặp **câu hỏi — câu trả lời**
có cấu trúc, sạch, và sẵn sàng cho việc huấn luyện.

Nhìn vào dòng pipeline ở dưới, ta thấy bảy bước tuần tự từ trái qua phải."

`[chuyển slide]` ⏱ ~45s

---

## SLIDE 5 — Preprocessing Pipeline: All 7 Modules *(ảnh tổng quan)*

*(Chỉ tay vào từng nhóm trên ảnh)*

"Đây là sơ đồ tổng quan của toàn bộ pipeline.

Ba nhóm chính được tô màu khác nhau:

Nhóm **Parse & Validate** màu xanh lá — gồm Module 1 và 2 —
thuộc Phase 2, chịu trách nhiệm format và làm sạch dữ liệu thô.

Nhóm **Transform & Flatten** màu vàng — Module 3, 4, 5 —
thuộc Phase 3, chuyển đổi trajectory thành các sample độc lập
và nén HTML thành cây DOM compact.

Nhóm **Sample & Export** màu tím — Module 6 và 7 —
định dạng và ghi ra file JSONL cuối cùng."

`[chuyển slide]` ⏱ ~35s

---

## SLIDE 6 — Phase 2: Collecting & Cleaning Trajectories

"Trong Phase 2, chúng ta xử lý hai việc chính.

**Module 1 — Format:** chuẩn hóa cấu trúc của file JSON thô,
đưa tất cả về một schema thống nhất với tên field và kiểu dữ liệu nhất quán.

**Module 2 — Clean:** lọc dữ liệu qua bốn bước tuần tự.
*Ghost drop* loại bỏ các session không có HTML —
tức là agent chạy nhưng không ghi lại được gì.
*Loop drop* loại bỏ session bị lặp hành động từ ba lần trở lên liên tiếp.
*Tail trim* cắt các bước cuối session không có HTML đi kèm.
*Min length* loại bỏ session quá ngắn.

*(nhấn mạnh)* Nếu chỉ một session bị lặp lọt vào dữ liệu huấn luyện,
mô hình sẽ học cách... đứng im và lặp lại hành động đó.
Đó là lý do bước này rất quan trọng."

`[chuyển slide]` ⏱ ~50s

---

## SLIDE 7 — Phase 2 Diagrams: Module 1 & 2 *(ảnh)*

*(Chỉ vào ảnh Module 1)*

"Ở đây ta thấy Module 1 nhận vào file `browser_use_raw.jsonl`,
đi qua sáu bước xử lý nội bộ —
từ parse JSON, xây dựng history, actions, HTML và candidates —
rồi xuất ra file `browser_use_steps.jsonl` chứa từng bước theo cấu trúc đã chuẩn hóa.

*(Chỉ vào ảnh Module 2)*

Module 2 nhận trajectory thô, chạy tuần tự qua sáu bộ lọc,
và xuất ra tập trajectory sạch kèm CleaningStats để theo dõi chất lượng."

`[chuyển slide]` ⏱ ~30s

---

## SLIDE 8 — Phase 3: Converting Trajectories into Training Samples

"Bước tiếp theo là chuyển đổi các trajectory sạch thành dữ liệu huấn luyện cụ thể.

**Module 3 — Validate:** đọc file JSONL và validate từng dòng theo schema Pydantic chặt chẽ.
Record nào lỗi thì bỏ qua, không dừng cả batch.

**Module 4 — Flatten:** đây là bước quan trọng nhất —
một trajectory N bước được tách thành N sample độc lập.
Mỗi sample chứa: nhiệm vụ, lịch sử hành động trước đó, và hành động đúng tiếp theo.
*(dừng một chút)* Nghĩa là một session 13 bước cho ta 13 cặp dữ liệu huấn luyện riêng biệt.

**Module 5 — DOM Representation:** HTML đầy đủ thường dài đến 50 nghìn ký tự —
quá lớn để đưa vào mô hình. Module này nén HTML thành một cây cú pháp compact,
chỉ giữ lại những element có ý nghĩa ngữ nghĩa.

**Module 6 — Format:** từ mỗi sample, tạo ra hai dạng:
dạng multiple-choice để mô hình học nhận biết,
và dạng generation để mô hình học tự sản sinh hành động."

`[chuyển slide]` ⏱ ~60s

---

## SLIDE 9 — Phase 3 Diagrams: Module 3 & 4 *(ảnh)*

*(Chỉ vào ảnh Module 3)*

"Module 3 nhận đường dẫn JSONL, mở file, đọc từng dòng, validate bằng Pydantic,
lọc theo giới hạn số action, rồi yield ra stream các TrajectoryRecord sạch.

*(Chỉ vào ảnh Module 4)*

Module 4 walk qua mảng actions của mỗi trajectory,
tạo một ActionSample cho mỗi bước, đính kèm metadata của task và session.
Output là mảng ActionSample — dữ liệu đã phẳng, sẵn sàng cho các bước sau."

`[chuyển slide]` ⏱ ~30s

---

## SLIDE 10 — Phase 3 Diagrams: Module 5 & 6 *(ảnh)*

*(Chỉ vào ảnh Module 5)*

"Module 5 nhận ActionSample cùng HTML thô,
parse bằng BeautifulSoup, áp dụng các rule lọc từ DomReprConfig,
rồi xây dựng và xuất ra chuỗi tree compact.

*(Chỉ vào ảnh Module 6)*

Module 6 nhận action, cây DOM, và config định dạng,
xây dựng cả sample multiple-choice lẫn sample generation,
đính kèm prompt và answer, serialize ra dict.
Đây là bước cuối cùng trước khi ghi file."

`[chuyển slide]` ⏱ ~30s

---

## SLIDE 11 — Phase 3 Diagrams: Module 7 & 8 *(ảnh)*

*(Chỉ vào ảnh Module 7)*

"Module 7 là Writer — nhận các dict đã format,
ghi vào hai file JSONL riêng biệt: một cho multichoice, một cho generation,
rồi flush và trả về WriterStats.

*(Chỉ vào ảnh Module 8)*

Module 8 là **Pipeline orchestrator** — nó kết nối toàn bộ Phase 3 lại với nhau:
load config, iter trajectories, flatten, build tree repr, format, write.
Đây là entry point của Phase 3, trả về PipelineStats tổng hợp."

`[chuyển slide]` ⏱ ~30s

---

## PHẦN 3 — TRAINING THE SMALL LANGUAGE MODEL

---

## SLIDE 12 — Training Data: Format and Split

*(Giọng chuyển sang nhịp điệu mới, bắt đầu phần huấn luyện)*

"Bây giờ chúng ta đã có dữ liệu sạch.
Mô hình nền em chọn là **Qwen2.5-1.5B-Instruct** —
một mô hình causal language model với 1.5 tỷ tham số,
đã được pre-train trên văn bản tổng quát.

Dữ liệu huấn luyện lấy từ file `generation_samples.jsonl` của Phase 3.
Mỗi sample có ba trường:
`seq_context` là cây DOM của trang hiện tại,
`seq_in` là câu hỏi gồm nhiệm vụ và lịch sử hành động trước,
`seq_out` là câu trả lời — element cần tương tác và loại hành động.

Tổng cộng khoảng **1.174 sample**, được shuffle ngẫu nhiên rồi chia
85% cho tập train và 15% cho tập validation."

`[chuyển slide]` ⏱ ~50s

---

## SLIDE 13 — Tokenization

"Trước khi đưa vào mô hình, văn bản cần được **tokenize** —
tức là chuyển thành chuỗi số nguyên.

Output gồm ba tensor:
`input_ids` là mã số của từng token,
`attention_mask` đánh dấu đâu là token thật, đâu là padding,
và `labels` — giống `input_ids` nhưng các token thuộc phần *prompt*
được mask bằng giá trị -100.

*(nhấn mạnh)* Việc mask phần prompt là rất quan trọng:
mô hình chỉ bị phạt khi dự đoán sai *câu trả lời*,
không bị phạt vì 'đọc lại' ngữ cảnh trang web.
Điều này giúp mô hình học đúng nhiệm vụ.

Độ dài tối đa là 2.048 token; ngữ cảnh dài hơn 6.000 ký tự được cắt trước khi tokenize."

`[chuyển slide]` ⏱ ~45s

---

## SLIDE 14 — Model Configuration: SFT + LoRA

"Để fine-tune mô hình, em dùng kỹ thuật **LoRA** —
thuộc nhóm PEFT, Parameter-Efficient Fine-Tuning.

Thay vì cập nhật toàn bộ 1.5 tỷ tham số — vốn rất tốn bộ nhớ GPU và thời gian —
LoRA chèn thêm các **adapter matrix hạng thấp** vào các layer được chọn.
Chỉ khoảng **1.3% tổng số tham số** được train.

Các siêu tham số LoRA:
Rank `r` = 32 điều chỉnh dung lượng của adapter.
Alpha = 64 cho hệ số scale bằng 2.
Dropout 0.05 giúp tránh overfitting.
Và adapter được gắn vào 7 layer —
cả attention lẫn feed-forward của mô hình.

Ngoài ra em dùng **QLoRA** — nén mô hình nền từ FP16 xuống 4-bit,
giảm VRAM cần thiết từ 3 GB xuống chỉ còn khoảng 1 GB,
trong khi vẫn tính toán ở độ chính xác BF16."

`[chuyển slide]` ⏱ ~55s

---

## SLIDE 15 — Training Configuration: Hyperparameters

"Về cấu hình huấn luyện —

Em train trong **5 epoch** với batch size 4 mỗi GPU.
Kết hợp gradient accumulation 2 bước,
effective batch size thực tế là 8.

Learning rate là 2×10⁻⁴, khá cao so với full fine-tuning
nhưng phù hợp với LoRA vì chỉ một phần nhỏ tham số được cập nhật.
Schedule là cosine decay với 10% warmup để khởi động êm.

Optimizer là **Paged AdamW 8-bit** — tiết kiệm khoảng 50% bộ nhớ optimizer
so với AdamW thông thường."

`[chuyển slide]` ⏱ ~40s

---

## SLIDE 16 — Training Configuration: Efficiency Techniques

"Ngoài LoRA và QLoRA, em còn áp dụng thêm bốn kỹ thuật tối ưu hiệu suất.

**Sample packing** nhồi nhiều sample ngắn vào một chuỗi 2.048 token —
tránh lãng phí GPU khi batch có nhiều sample ngắn.

**Liger Kernel** thay thế các CUDA kernel mặc định bằng phiên bản fused —
tăng tốc ~20% và giảm ~60% bộ nhớ activation.

**Flash Attention 2** tối ưu hóa tính toán attention —
nhanh gấp đôi và dùng ít hơn ba lần bộ nhớ so với attention chuẩn.

**Gradient checkpointing** không lưu toàn bộ activation,
mà tái tính toán khi cần trong backprop —
đổi tốc độ lấy bộ nhớ."

`[chuyển slide]` ⏱ ~45s

---

## SLIDE 17 — Training Pipeline & Checkpointing

*(Chỉ vào pseudocode)*

"Vòng lặp huấn luyện khá trực quan:
với mỗi epoch, với mỗi batch đã pack —
forward pass, tính loss chỉ trên completion tokens,
backprop, rồi cập nhật **chỉ** LoRA adapter — mô hình nền đứng yên.

Sau mỗi epoch, đánh giá trên tập validation và lưu checkpoint.
Chỉ giữ lại **2 checkpoint gần nhất** để tiết kiệm dung lượng.
Khi kết thúc, tự động khôi phục checkpoint có `eval_loss` thấp nhất."

`[chuyển slide]` ⏱ ~35s

---

## SLIDE 18 — Output Artifact

"Kết quả cuối cùng của quá trình huấn luyện là một **LoRA adapter**
nằm trong thư mục `final_adapter/`.

Adapter này chỉ nặng khoảng **80 MB** —
trong khi mô hình nền Qwen2.5-1.5B nặng đến ~3 GB.

Điều này có ý nghĩa thực tiễn quan trọng:
mô hình nền không thay đổi và có thể dùng lại cho nhiều thí nghiệm khác nhau.
Chỉ cần giữ adapter ~80 MB là đủ để tái tạo lại mô hình đã fine-tune."

`[chuyển slide]` ⏱ ~35s

---

## PHẦN 4 — DOCKERIZATION & CLOUD DEPLOYMENT

---

## SLIDE 19 — Why Docker and How It Works

*(Giọng thực tế, giải thích vấn đề trước khi đưa ra giải pháp)*

"Huấn luyện mô hình hiệu quả đòi hỏi một stack phần mềm rất cụ thể:
đúng phiên bản PyTorch, đúng phiên bản CUDA, Flash Attention phải được compile từ source.
Cài đặt thủ công trên từng máy cloud tốn nhiều giờ và dễ bị lỗi.

Giải pháp là đóng gói toàn bộ môi trường vào một **Docker image**.

Image được xây dựng theo từng layer:
Layer nền là PyTorch 2.3.1 với CUDA 12.1.
Tiếp theo là các build tool cần thiết để compile Flash Attention.
Sau đó là Flash Attention được compile sẵn cho kiến trúc Ampere và Ada.
Rồi đến các thư viện ML: transformers, peft, trl, bitsandbytes.
Cuối cùng là script huấn luyện.

*(nhấn mạnh)* Dữ liệu và checkpoint **không** bị nhúng vào image —
chúng được mount vào khi chạy. Điều này giữ image nhẹ và có thể tái sử dụng."

`[chuyển slide]` ⏱ ~55s

---

## SLIDE 20 — Cloud Deployment Workflow

*(Chỉ vào từng bước trong code block)*

"Quy trình triển khai lên cloud gồm bảy bước:

Build image trên máy local.
Smoke test với 20 sample trong 1 epoch để kiểm tra môi trường — chỉ mất vài phút.
Push lên Docker Hub.
Thuê GPU trên Vast.ai — em khuyến nghị RTX 4090 24GB để tiết kiệm chi phí.
Upload dữ liệu huấn luyện qua scp.
Khởi động training.
Và tải checkpoint adapter về khi xong.

*(Chỉ vào bảng)*

RTX 4090 mất khoảng 25 phút với chi phí chưa đến 50 xu.
A100 nhanh hơn nhưng đắt hơn ba lần.

Yêu cầu tối thiểu là kiến trúc Ampere trở lên — cần cho BF16 và Flash Attention 2."

`[chuyển slide]` ⏱ ~50s

---

## PHẦN 5 — SUMMARY

---

## SLIDE 21 — End-to-End Pipeline

*(Giọng chậm lại, như đang recap lại toàn bộ hành trình)*

"Nhìn lại toàn bộ hành trình từ đầu đến cuối:

Bắt đầu từ **log phiên trình duyệt** thô —
qua Format, Clean, Validate để có trajectory sạch —
qua Flatten, DOM Representation, Format Q&A để có file `generation_samples.jsonl`
với khoảng 1.174 cặp dữ liệu huấn luyện.

Từ đó, tokenize, pack, và train bằng SFT + LoRA —
ra được một **LoRA adapter 80 MB** trên nền Qwen2.5-1.5B.

Toàn bộ môi trường được đóng gói vào Docker image —
sẵn sàng triển khai trên bất kỳ máy GPU cloud nào."

`[chuyển slide]` ⏱ ~40s

---

## SLIDE 22 — Key Design Decisions

*(Chỉ vào từng dòng trong bảng, giọng tự tin)*

"Mỗi quyết định thiết kế trong đề tài đều có lý do cụ thể.

**LoRA thay vì full fine-tuning** — chỉ train 1.3% tham số,
vừa với một GPU consumer duy nhất.

**QLoRA 4-bit** — giảm bộ nhớ VRAM bốn lần mà không mất nhiều độ chính xác.

**Completion-only loss** — mô hình chỉ học dự đoán hành động,
không học 'đọc lại' nội dung trang web.

**DFT loss term** — bảo toàn khả năng ngôn ngữ tổng quát của mô hình,
tránh catastrophic forgetting.

**Docker packaging** — một lệnh, một môi trường nhất quán trên mọi máy.

**Adapter-only artifact** — deliverable chỉ 80 MB,
mô hình nền không thay đổi và có thể dùng lại cho nhiều thí nghiệm."

⏱ ~50s

---

## KẾT THÚC

*(Nhìn vào khán giả, nói tự nhiên)*

"Đó là toàn bộ nội dung em muốn trình bày hôm nay.

Tóm lại, đề tài đã xây dựng được một pipeline end-to-end:
từ dữ liệu thô, qua xử lý và huấn luyện, đến một SLM có thể tự điều hướng web
với chi phí vận hành thấp và môi trường hoàn toàn có thể tái tạo.

Em xin mời thầy/cô và các bạn có câu hỏi hoặc góp ý. Xin cảm ơn!"

⏱ ~25s

---

## TỔNG THỜI GIAN ƯỚC TÍNH

| Phần | Số slide | Thời gian |
|---|---|---|
| Giới thiệu & Overview | 2 | ~1.5 phút |
| Part 1: Data Processing | 8 | ~6 phút |
| Part 2: Training SLM | 7 | ~5.5 phút |
| Part 3: Docker & Deployment | 2 | ~2 phút |
| Summary & Q&A | 3 | ~2 phút |
| **Tổng** | **22** | **~17 phút** |

---

## GỢI Ý KHI TRÌNH BÀY

- **Phần ảnh module diagram**: đừng đọc từng bước trong ảnh —
  chỉ cần chỉ vào input/output và giải thích ý nghĩa tổng quát.
- **Khi có câu hỏi về chi tiết kỹ thuật**: trả lời trực tiếp, nếu không chắc
  thì thành thật nói "em sẽ kiểm tra lại" thay vì đoán.
- **Tốc độ**: nói chậm hơn bình thường khoảng 20% —
  người nghe cần thời gian xử lý thuật ngữ kỹ thuật.
- **Chuyển phần**: luôn có một câu chuyển tiếp trước khi bấm slide
  ("Bây giờ chúng ta đến phần...", "Với dữ liệu đã sẵn sàng, bước tiếp theo là...").
