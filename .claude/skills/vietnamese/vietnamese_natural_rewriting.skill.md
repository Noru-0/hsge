# Skill: Chuyển bản dịch tiếng Việt word-by-word thành tiếng Việt tự nhiên

## Mục đích

Skill này dùng để **biên tập lại một văn bản tiếng Việt đã được dịch từ tiếng Anh theo kiểu word-by-word** thành một văn bản tiếng Việt tự nhiên, mạch lạc và giống cách người Việt thực sự viết.

### Input

Một văn bản **tiếng Việt đã dịch nhưng còn mang dấu vết của cấu trúc tiếng Anh**, ví dụ:

- Dịch sát từng từ.
- Giữ nguyên cấu trúc câu tiếng Anh.
- Lạm dụng đại từ.
- Dùng từ nối cứng nhắc.
- Câu dài và nặng nề.
- Dùng collocation không tự nhiên trong tiếng Việt.
- Danh từ hóa quá mức.
- Mang phong cách "văn dịch".

### Output

Một phiên bản tiếng Việt:

- Tự nhiên hơn.
- Mạch lạc hơn.
- Dễ đọc hơn.
- Đúng ngữ pháp và cách dùng từ tiếng Việt.
- Giữ nguyên ý nghĩa của bản gốc đã được dịch.
- Giữ nguyên thông tin, số liệu, thuật ngữ và quan hệ logic.
- Không còn cảm giác được dịch trực tiếp từ tiếng Anh.

**Không yêu cầu người dùng cung cấp lại văn bản tiếng Anh.** Skill phải làm việc chủ yếu dựa trên văn bản tiếng Việt đầu vào.

---

## Nguyên tắc cốt lõi

### 1. Không chỉ sửa từng từ

Mục tiêu không phải là thay một vài từ "không tự nhiên" bằng từ khác.

Hãy xem toàn bộ câu và đoạn văn như một văn bản tiếng Việt cần được viết lại.

Ví dụ:

> Công nghệ đã thay đổi cách thức mà mọi người giao tiếp với nhau.

Có thể viết tự nhiên hơn:

> Công nghệ đã làm thay đổi cách con người giao tiếp với nhau.

Nếu cần, có thể thay đổi mạnh hơn:

> Công nghệ đã làm thay đổi hoàn toàn cách chúng ta giao tiếp.

Chỉ chọn cách cuối nếu mức độ ý nghĩa phù hợp với văn bản đầu vào.

### 2. Ưu tiên cách người Việt thực sự diễn đạt

Khi có nhiều cách viết đúng, ưu tiên cách:

1. Tự nhiên.
2. Rõ nghĩa.
3. Gọn.
4. Phù hợp với ngữ cảnh.
5. Giống văn bản do người Việt viết trực tiếp.

Không cố giữ lại cách diễn đạt chỉ vì nó gần với cấu trúc của bản dịch đầu vào.

### 3. Phá bỏ cấu trúc tiếng Anh còn sót lại

Tìm và viết lại những cấu trúc có dấu hiệu dịch word-by-word:

- "có thể được nhìn thấy rằng..."
- "điều này dẫn đến việc..."
- "thực hiện một quyết định"
- "có một ảnh hưởng đến..."
- "đóng một vai trò quan trọng trong việc..."
- "theo một cách mà..."
- "là lý do tại sao..."
- "mặc dù thực tế rằng..."
- "với mục đích để..."
- "trong trường hợp mà..."
- "những người mà..."
- "nó được cho rằng..."
- "được sử dụng để..."

Không tự động thay tất cả các cấu trúc trên. Hãy xét toàn bộ câu và viết lại theo cách tự nhiên nhất.

### 4. Có thể thay đổi cấu trúc câu

Được phép:

- Đảo trật tự thành phần câu.
- Tách câu dài thành nhiều câu.
- Gộp các câu ngắn nếu cần.
- Chuyển câu bị động thành chủ động.
- Chuyển câu chủ động thành bị động nếu phù hợp.
- Chuyển danh từ thành động từ.
- Chuyển động từ thành danh từ khi văn phong yêu cầu.
- Lược bỏ chủ ngữ/đại từ khi ngữ cảnh đã rõ.
- Thay đổi từ nối.
- Viết lại toàn bộ câu.

Không được thay đổi nội dung chỉ để câu nghe "hay" hơn.

---

## Các dấu hiệu cần phát hiện

### 1. Đại từ dư thừa

Tiếng Việt không phải lúc nào cũng cần dịch đầy đủ:

- he
- she
- it
- they
- their
- this
- that

Ví dụ:

**Word-by-word:**
> Khi sinh viên hoàn thành khóa học, họ có thể áp dụng những gì họ đã học vào công việc của họ.

**Tự nhiên hơn:**
> Sau khi hoàn thành khóa học, sinh viên có thể áp dụng những kiến thức đã học vào công việc.

---

### 2. Collocation không tự nhiên

Phát hiện các cụm từ có vẻ đúng nghĩa từng từ nhưng người Việt ít sử dụng.

Ví dụ:

> thực hiện một quyết định

→ **đưa ra quyết định**

> tạo ra một ảnh hưởng

→ **gây ảnh hưởng / tạo ảnh hưởng**

> có một cuộc thảo luận về

→ **thảo luận về**

> làm một nghiên cứu

→ **tiến hành nghiên cứu / thực hiện nghiên cứu**

> nhận được lợi ích từ

→ **được hưởng lợi từ / hưởng lợi từ**

Không thay đổi máy móc. Chọn cách phù hợp với ngữ cảnh.

---

### 3. Danh từ hóa quá mức

Bản dịch từ tiếng Anh thường chứa quá nhiều danh từ.

Ví dụ:

> Việc thực hiện việc triển khai hệ thống đã dẫn đến sự cải thiện về hiệu năng.

Tự nhiên hơn:

> Việc triển khai hệ thống đã giúp cải thiện hiệu năng.

Hoặc:

> Triển khai hệ thống giúp cải thiện hiệu năng.

Tùy văn phong mà chọn cách phù hợp.

---

### 4. Từ nối cứng nhắc

Không giữ nguyên một cách máy móc:

- however → tuy nhiên
- therefore → do đó
- moreover → hơn nữa
- in addition → ngoài ra
- nevertheless → tuy vậy

Có thể thay bằng:

- nhưng
- thế nhưng
- dù vậy
- vì thế
- do đó
- ngoài ra
- thêm vào đó
- mặt khác

Thậm chí có thể **bỏ từ nối** nếu quan hệ giữa các câu đã rõ.

---

### 5. Câu quá dài

Nếu một câu tiếng Việt chứa quá nhiều mệnh đề lồng nhau và đọc giống cấu trúc tiếng Anh, hãy cân nhắc tách thành hai hoặc nhiều câu.

Ví dụ:

**Word-by-word:**
> Những sinh viên đã tham gia khóa học, mặc dù họ ban đầu gặp nhiều khó khăn trong việc hiểu các khái niệm được giảng dạy, cuối cùng đã có thể áp dụng những kiến thức mà họ đã học vào công việc của họ.

**Tự nhiên hơn:**
> Những sinh viên tham gia khóa học ban đầu gặp khá nhiều khó khăn trong việc tiếp thu các khái niệm được giảng dạy. Tuy nhiên, cuối cùng họ vẫn có thể áp dụng những kiến thức đã học vào công việc.

---

### 6. Cấu trúc "có + danh từ" không cần thiết

Ví dụ:

> Có nhiều nghiên cứu cho thấy rằng...

Có thể viết:

> Nhiều nghiên cứu cho thấy...

> Có một sự khác biệt đáng kể giữa hai nhóm.

→

> Hai nhóm có sự khác biệt đáng kể.

Hoặc:

> Hai nhóm khác nhau đáng kể.

Tùy ngữ cảnh.

---

## Bảo toàn ý nghĩa

Đây là nguyên tắc bắt buộc.

Khi viết lại:

### Không được tự ý:

- Thêm thông tin mới.
- Bỏ thông tin quan trọng.
- Thay đổi số liệu.
- Thay đổi tên riêng.
- Thay đổi thuật ngữ.
- Thay đổi mức độ chắc chắn.
- Thay đổi nguyên nhân/kết quả.
- Thay đổi quan hệ so sánh.
- Thay đổi điều kiện.
- Thay đổi thời gian.

Ví dụ:

> Có thể góp phần cải thiện hiệu quả.

Không được viết thành:

> Chắc chắn sẽ cải thiện hiệu quả.

Vì mức độ chắc chắn đã thay đổi.

---

## Xử lý thuật ngữ chuyên ngành

Nếu input chứa thuật ngữ chuyên ngành:

- Giữ nguyên thuật ngữ đã đúng.
- Chỉ sửa nếu cách dùng hiện tại không chính xác hoặc không tự nhiên.
- Không Việt hóa tùy tiện.
- Với thuật ngữ phổ biến, ưu tiên cách dùng chuẩn trong tiếng Việt chuyên ngành.

Ví dụ:

> kiến trúc hướng sự kiện (event-driven architecture)

Có thể giữ nguyên nếu đây là văn bản kỹ thuật.

Không biến thành một cách diễn đạt quá đời thường làm mất tính chính xác.

---

## Quy trình xử lý

### Bước 1 — Đọc toàn bộ đoạn

Không sửa từng câu ngay lập tức.

Đọc toàn bộ văn bản để hiểu:

- Chủ đề.
- Đối tượng.
- Văn phong.
- Mối quan hệ giữa các câu.
- Thuật ngữ quan trọng.

### Bước 2 — Xác định các dấu hiệu "văn dịch"

Đánh dấu trong đầu:

- Cấu trúc tiếng Anh.
- Collocation bất thường.
- Đại từ dư thừa.
- Câu dài.
- Danh từ hóa.
- Từ nối cứng.
- Cách dùng từ không giống tiếng Việt tự nhiên.

### Bước 3 — Xác định ý nghĩa của từng câu

Trước khi sửa, xác định:

> "Câu này thực sự muốn nói điều gì?"

Không bắt đầu bằng:

> "Từ này nên thay bằng từ nào?"

### Bước 4 — Viết lại câu

Viết một câu tiếng Việt mới dựa trên **ý nghĩa**, không dựa trên cấu trúc câu cũ.

### Bước 5 — Kiểm tra tính liên kết

Sau khi sửa từng câu, đọc lại cả đoạn.

Đảm bảo:

- Đại từ vẫn tham chiếu đúng.
- Từ nối hợp lý.
- Không bị lặp từ.
- Các câu liên kết tự nhiên.
- Mạch lập luận không bị thay đổi.

### Bước 6 — Kiểm tra lần cuối

Đọc bản cuối cùng như một người Việt không biết văn bản gốc.

Tự hỏi:

> "Nếu tôi không biết đây là bản dịch, tôi có nghĩ đây là văn bản do một người Việt viết trực tiếp không?"

Nếu câu trả lời là "chưa", tiếp tục viết lại.

---

## Mức độ can thiệp

Không phải câu nào cũng cần viết lại mạnh.

### Mức 1 — Chỉnh từ

Khi cấu trúc câu đã tự nhiên nhưng một số từ/cụm từ không phù hợp.

### Mức 2 — Chỉnh cấu trúc

Khi câu có dấu vết tiếng Anh nhưng vẫn có thể giữ phần lớn cấu trúc.

### Mức 3 — Viết lại toàn câu

Khi cấu trúc word-by-word khiến câu rất thiếu tự nhiên.

### Mức 4 — Tách/gộp câu

Khi cấu trúc của cả đoạn cần thay đổi để tiếng Việt mạch lạc hơn.

Luôn chọn **mức can thiệp thấp nhất nhưng đủ để đạt độ tự nhiên cần thiết**, trừ khi câu/đoạn thực sự cần viết lại.

---

## Văn phong mặc định

Nếu người dùng không chỉ định, sử dụng:

**Tiếng Việt tự nhiên, rõ ràng, trung tính.**

Không:

- Quá khẩu ngữ.
- Quá văn hoa.
- Quá hàn lâm.
- Quá trang trọng.

Nếu văn bản có ngữ cảnh rõ ràng, phải điều chỉnh theo ngữ cảnh đó.

Ví dụ:

- Bài IELTS → tự nhiên nhưng phù hợp văn viết học thuật.
- Báo cáo kỹ thuật → chính xác, súc tích, chuyên ngành.
- Email → lịch sự, tự nhiên.
- Nội dung đời thường → gần với cách nói thực tế.
- Bài nghiên cứu → trang trọng và nhất quán.

---

## Format output mặc định

Chỉ trả về **văn bản tiếng Việt đã được viết lại**, không cần giải thích quá trình chỉnh sửa.

Nếu người dùng yêu cầu giải thích, có thể trả:

### Bản tự nhiên
[Phiên bản đã viết lại]

### Những điểm đã thay đổi
- ...
- ...
- ...

### Cách diễn đạt đáng chú ý
- Bản cũ: ...
- Bản tự nhiên: ...
- Lý do: ...

---

## Prompt vận hành

> Bạn là một biên tập viên tiếng Việt chuyên xử lý các bản dịch từ tiếng Anh.
>
> Văn bản đầu vào là **tiếng Việt đã được dịch theo kiểu word-by-word**, vì vậy có thể còn giữ cấu trúc, cách dùng từ, collocation, đại từ và cách diễn đạt của tiếng Anh.
>
> Nhiệm vụ của bạn là **viết lại văn bản này thành tiếng Việt tự nhiên hơn**, giống như văn bản được một người Việt viết trực tiếp từ đầu.
>
> ### Yêu cầu:
>
> 1. Không dịch lại từng từ.
> 2. Không cố giữ nguyên cấu trúc câu hiện tại nếu cấu trúc đó mang dấu vết của tiếng Anh.
> 3. Ưu tiên cách diễn đạt tự nhiên và phổ biến trong tiếng Việt.
> 4. Có thể thay đổi trật tự từ, cấu trúc câu, từ nối, đại từ và cách dùng từ.
> 5. Có thể tách hoặc gộp câu khi cần.
> 6. Sửa các collocation không tự nhiên.
> 7. Loại bỏ đại từ hoặc từ ngữ dư thừa khi tiếng Việt không cần dùng.
> 8. Chuyển các cấu trúc danh từ hóa nặng nề sang cách diễn đạt tự nhiên hơn khi phù hợp.
> 9. Không dịch thành ngữ theo nghĩa đen; hãy dùng cách diễn đạt tương đương trong tiếng Việt.
> 10. Giữ nguyên hoàn toàn ý nghĩa, thông tin, số liệu, thuật ngữ, mức độ chắc chắn và quan hệ logic của văn bản.
> 11. Không tự ý thêm hoặc bớt thông tin.
> 12. Giữ văn phong phù hợp với ngữ cảnh của văn bản.
>
> ### Tiêu chí quan trọng nhất:
>
> Sau khi viết lại, hãy đọc văn bản như thể bạn **không biết nó được dịch từ tiếng Anh**. Văn bản phải có cảm giác giống tiếng Việt nguyên bản, không phải "bản dịch đã được sửa".
>
> ### Văn bản cần xử lý:
>
> [DÁN VĂN BẢN TIẾNG VIỆT WORD-BY-WORD VÀO ĐÂY]

---

## Checklist nội bộ

Trước khi xuất kết quả, kiểm tra:

- [ ] Câu có đọc giống tiếng Việt tự nhiên không?
- [ ] Có còn cấu trúc tiếng Anh rõ ràng không?
- [ ] Có từ/cụm từ nào dịch sát nhưng người Việt ít dùng không?
- [ ] Có đại từ nào có thể lược bỏ không?
- [ ] Có câu nào quá dài không?
- [ ] Có danh từ hóa không cần thiết không?
- [ ] Từ nối có thực sự cần thiết không?
- [ ] Collocation có tự nhiên không?
- [ ] Thuật ngữ chuyên ngành có chính xác không?
- [ ] Ý nghĩa có được giữ nguyên không?
- [ ] Có vô tình thêm/bớt thông tin không?
- [ ] Văn phong có phù hợp với ngữ cảnh không?
- [ ] Nếu bỏ bản tiếng Anh đi, văn bản có giống văn tiếng Việt nguyên bản không?

## Nguyên tắc cuối cùng

**Không biến một bản dịch word-by-word thành một bản dịch word-by-word "đẹp hơn".**

Hãy biến nó thành **một văn bản tiếng Việt tự nhiên, trong đó người đọc không còn cảm nhận rõ cấu trúc của ngôn ngữ nguồn**.
