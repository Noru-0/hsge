# PHÂN TÍCH KẾT QUẢ ĐÁNH GIÁ — TRẢ LỜI 4 CÂU HỎI THẢO LUẬN

> Tài liệu này trả lời bốn câu hỏi ở cuối [`tong_hop_ket_qua_eval.md`](tong_hop_ket_qua_eval.md),
> dựa trên: (a) các bảng SR đã điều chỉnh trong tài liệu đó, (b) dữ liệu thô
> `outputs/eval/**/results.jsonl` + `summary.json` trong repo, (c) thành phần tập
> huấn luyện trong `training_data*/`, và (d) bài báo gốc
> [Go-Browse](go-browse.md) (Gandhi & Neubig).
>
> **Ngày lập:** 2026-08-21. Mọi con số đều truy ngược được về đường dẫn nêu ở §5.

---

## 0. Ba chỉ số nền cần thống nhất trước

Ba đại lượng dưới đây được dùng xuyên suốt phần trả lời; chúng lấy trực tiếp từ
`results.jsonl` chứ không phải từ bảng SR.

| Chỉ số | Ý nghĩa | Vì sao quan trọng |
| :--- | :--- | :--- |
| `n_unparsed_llm` | Số lần mô hình trả về chuỗi **không parse được** thành JSON `{thought, action}` | Một lần hỏng định dạng là một bước bị mất trắng; đây là lỗi **tuân thủ định dạng**, không phải lỗi suy luận |
| `terminal_delivery` | Episode có kết thúc bằng hành động cuối hợp lệ (`send_msg_to_user` / `report_infeasible`) hay không | Task INFO không "delivered" thì chắc chắn trượt dù mô hình đã tìm ra đáp án |
| `stop_reason` | `budget` (hết 16 bước) / `stuck` (lặp vô ích) / `""` (tự kết thúc) | Phân biệt "không biết làm" với "biết làm nhưng không đủ bước / bị kẹt" |

**Bảng nền — dữ liệu thô toàn bộ các đợt chạy** (đơn vị: task, trừ cột bước/task):

| Mô hình / miền | SR thô | Bước/task | % task có ≥1 lần hỏng định dạng | % task kết thúc hợp lệ | budget + stuck |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Qwen2.5-7B FT** shopping_admin | 16/182 (8,8%) | 10,6 | **60%** (109/182) | 30% (54/182) | 110/182 (60%) |
| **Qwen2.5-7B FT** gitlab | 18/180 (10,0%) | 10,2 | **58%** (104/180) | 30% (54/180) | 85/180 (47%) |
| **Qwen2.5-7B FT** reddit | 15/106 (14,2%) | 11,4 | **58%** (62/106) | 23% (24/106) | 58/106 (55%) |
| Qwen3.5-9B base shopping_admin | 23/182 (12,6%) | 8,5 | 25% | — | — |
| **Qwen3.5-9B FT** shopping | 53/187 (28,3%) | 9,0 | **0%** (0/187) | 63% (117/187) | 67/187 (36%) |
| **Qwen3.5-9B FT** shopping_admin | 39/182 (21,4%) | 11,0 | **0%** (0/182) | 49% (90/182) | 110/182 (60%) |
| **Qwen3.5-9B FT** gitlab | 33/180 (18,3%) | 11,1 | **0,6%** (1/180) | 62% (112/180) | 88/180 (49%) |
| **Qwen3.5-9B FT** reddit | 36/106 (34,0%) | 9,8 | **3%** (3/106) | 40% (42/106) | 46/106 (43%) |

> Lưu ý: SR thô của bản 7B ở bảng này là số **chưa qua rà soát false-negative**;
> Bảng 1 của tài liệu tổng hợp dùng số **đã rà soát** (shopping_admin 21, gitlab
> 22, reddit 25, shopping 40 task). Chênh lệch giữa hai cột là kết quả của đợt
> audit, không phải hai lần chạy khác nhau.

---

## 1. Câu hỏi 1 — Vì sao Shopping Admin của HSGE-7B (11,5%) và HSGE-9B (21,4%) chênh nhau lớn?

**Khoảng cách cần giải thích: 9,9 điểm phần trăm** (11,54% vs 21,43%; nếu so số
thô chưa audit thì 8,79% vs 21,43%).

Điều đáng chú ý đầu tiên: **không thể đổ cho dữ liệu**. Bản 7B được huấn luyện
trên `training_data_merged_v1` (8.554 mẫu, trong đó shopping_admin có **3.585
mẫu / 529 quỹ đạo**), tức là *nhiều hơn* lượng dữ liệu shopping_admin mà bản 9B
Đợt 1 từng thấy (1.175 mẫu / 202 quỹ đạo). Vậy nguyên nhân nằm ở chỗ khác.

### 1.1 Khoảng 5,5/9,9 điểm đã tồn tại từ trước khi finetune

| | Qwen2.5-7B | Qwen3.5-9B | Chênh |
| :--- | :---: | :---: | :---: |
| Base, shopping_admin | 7,1% | 12,6% | **+5,5 pp** |
| Finetuned, shopping_admin | 11,5% | 21,4% | +9,9 pp |
| Mức tăng do finetune | +4,4 pp | +8,8 pp | |

Hơn một nửa khoảng cách (5,5/9,9 ≈ **56%**) là chênh lệch năng lực nền của hai
mô hình xương sống, đã có mặt trước khi HSGE can thiệp. Phần còn lại (4,4 pp) là
chênh lệch ở **khả năng hấp thụ dữ liệu SFT** — cùng một tập dữ liệu, mô hình 9B
biến thành +8,8 pp còn 7B chỉ +4,4 pp.

### 1.2 Nguyên nhân chi phối phần còn lại: bản 7B hỏng định dạng đầu ra

Đây là phát hiện mạnh nhất trong dữ liệu thô:

| | 7B FT (admin) | 9B FT (admin) |
| :--- | :---: | :---: |
| Task có ≥1 phản hồi không parse được | **109/182 (60%)** | **0/182 (0%)** |
| SR trên nhóm task bị hỏng định dạng | **0/109 (0,0%)** | — |
| SR trên nhóm task đầu ra sạch | **16/73 (21,9%)** | 39/182 (21,4%) |

Đọc dòng cuối: **khi bản 7B giữ được định dạng suốt episode, tỷ lệ thành công
của nó trên shopping_admin là 21,9% — ngang bằng bản 9B (21,4%).** Toàn bộ 109
task còn lại thành công 0 task.

Cùng khuôn mẫu ở hai miền kia:

| Miền | SR 7B trên nhóm đầu ra sạch | SR 9B (toàn bộ) |
| :--- | :---: | :---: |
| shopping_admin | 21,9% (16/73) | 21,4% |
| gitlab | 23,7% (18/76) | 18,3% |
| reddit | 34,1% (15/44) | 34,0% |

Ba miền, ba lần trùng khớp. Kết luận: **năng lực giải task của bản 7B sau
finetune không hề thua bản 9B; cái nó thua là khả năng phát ra đúng một JSON
`{thought, action}` ở mọi bước.** Chuỗi hỏng định dạng còn kéo theo hệ quả dây
chuyền: chỉ 30% episode của 7B kết thúc bằng hành động hợp lệ (`delivered`), so
với 49% của 9B — nghĩa là ngay cả khi tìm ra đáp án, nó thường không kịp giao.

⚠️ **Giới hạn của lập luận này:** nhóm "đầu ra sạch" không phải mẫu ngẫu nhiên.
Task ngắn/dễ có ít cơ hội hỏng định dạng hơn task dài, nên 21,9% là ước lượng
**thiên lệch lên**. Nó chứng minh được "phần lớn khoảng cách đến từ tuân thủ
định dạng", nhưng không chứng minh được "7B mạnh ngang 9B".

### 1.2b Hỏng định dạng ở đây nghĩa là gì — đọc thẳng từ trace

Soi nội dung thô của 275 lời gọi hỏng trên ba miền của bản 7B cho thấy đây
**không** phải chuỗi rác:

| | 7B FT (3 miền) | 9B base (4 miền) |
| :--- | :---: | :---: |
| Tổng lời gọi hỏng | 275 | 170 |
| `finish_reason = stop` (phản hồi hoàn chỉnh) | **275 (100%)** | 79 (46%) |
| `finish_reason = length` (bị cắt vì chạm trần ngữ cảnh) | 0 | **91 (54%)** |
| Là một lệnh `report_infeasible(...)` viết trần | **92–98%** | ~0 |
| Là JSON dở dang / văn xuôi | ~1% | ~100% |

Bản 7B **giữ đúng định dạng ở các hành động thường** và chỉ đánh rơi lớp vỏ JSON
đúng lúc phát **lệnh kết thúc**, kèm lý do mạch lạc, ví dụ nguyên văn:
`report_infeasible("The Period control is set to Day, while Quarter is
explicitly unavailable as an option...")`.

Hệ quả đo được: bản 7B chỉ ghi nhận **10/182** lần báo bất khả thi trên
shopping_admin, so với **41/182** của bản 9B — không phải vì nó ít báo, mà vì bộ
phân giải **vứt bỏ** phần lớn các lần báo đó và episode bị ghi thành
`budget`/`stuck`. Vì WebArena **cho điểm** khi agent báo bất khả thi đúng trên
task có nhãn `N/A`, một bộ phân giải khoan dung hơn gần như chắc chắn sẽ **nâng**
điểm của bản 7B theo mức chưa xác định.

**Do đó, con số của bản 7B là một cận dưới bị hạ thấp bởi độ nghiêm của bộ phân
giải, không phải một phép đo chất lượng dữ liệu** — không được dùng nó để so
cùng-backbone với Go-Browse-7B. Ngược lại, 170 phiên của mô hình nền 9B là hiện
tượng **sinh tràn** thật (trung vị ~21.000 ký tự, ~5.300 token, trong khi lời gọi
không đặt `max_tokens` và cửa sổ ngữ cảnh là 8192 token), nên không chịu cùng
cách phản bác.

### 1.3 Vì sao riêng shopping_admin lộ rõ nhất

Shopping_admin là miền dài hơi nhất trong bốn miền: 11,0 bước/task (9B) và
**60% task hết ngân sách hoặc bị kẹt**. Xác suất một episode sống sót qua N bước
mà không hỏng định dạng lần nào giảm theo N; miền càng nhiều bước thì lỗi tuân
thủ định dạng càng "ăn" nhiều task. Đó là lý do khoảng cách 7B–9B ở admin
(9,9 pp) lớn hơn ở gitlab (6,1 pp) dù tỷ lệ hỏng định dạng của 7B ở hai miền
gần như nhau (60% vs 58%).

### 1.4 Trả lời gọn

> Khoảng cách 11,5% → 21,4% gồm hai phần: **5,5 pp là chênh lệch năng lực nền**
> của Qwen2.5-7B so với Qwen3.5-9B (đã đo được trước khi finetune), và **phần
> còn lại chủ yếu là lỗi tuân thủ định dạng đầu ra** — 60% task của bản 7B chứa
> ít nhất một phản hồi không parse được và **không một task nào trong số đó
> thành công**; loại trừ nhóm này, SR của 7B là 21,9%, ngang bản 9B. Không phải
> vấn đề thiếu dữ liệu: bản 7B đã được huấn luyện trên tập shopping_admin lớn
> gấp 3 lần tập mà bản 9B Đợt 1 dùng. Lưu ý ở §1.2b: 92–98% các phản hồi hỏng đó
> là lệnh `report_infeasible(...)` viết trần chứ không phải chuỗi rác, nên con số
> của bản 7B là **cận dưới bị bộ phân giải hạ thấp**, không dùng để so
> cùng-backbone với Go-Browse-7B được.

---

## 2. Câu hỏi 2 — Vì sao Shopping của HSGE-7B (21,4%) và Go-Browse-7B (22,4%) không khác biệt?

**Chênh lệch 1,0 pp trên 187 task ≈ 2 task.** Với SR quanh 22% và n = 187, sai
số chuẩn của một tay đo là √(0,22 × 0,78 / 187) ≈ 3,0 pp, tức khoảng tin cậy 95%
rộng khoảng ±5,9 pp. **Chênh lệch 1,0 pp nằm sâu trong nhiễu thống kê** — đây
không phải "HSGE thua", mà là "hai phương pháp không phân biệt được ở cỡ mẫu
này". (Chính bài Go-Browse cũng chỉ đạt p = 0,094–0,108 khi so với NNetNav và
GPT-4o-mini trên toàn bộ 812 task.)

Bốn lý do khiến sự trùng khớp này là **kết quả đáng chờ đợi**, không phải trùng
hợp:

### 2.1 Cùng một mô hình xương sống ⇒ cùng một trần

Cả hai đều finetune `Qwen2.5-7B-Instruct` (base shopping = 9,4%). Go-Browse đưa
lên 22,4% (+13,0 pp), HSGE đưa lên 21,4% (+12,0 pp). Khi hai phương pháp thu
dữ liệu khác nhau cùng đẩy một mô hình 7B tới ~21–22% trên cùng một miền, khả
năng cao là cả hai đều **chạm trần của mô hình nền**, chứ không phải đang đo
chất lượng dữ liệu.

### 2.2 Shopping là miền mà "khám phá có cấu trúc" mang lại ít lợi ích nhất

Đọc chính bảng 3 của Go-Browse (§5), lấy khoảng cách của Go-Browse-7B so với
NNetNav-7B theo từng miền:

| Miền | Go-Browse-7B | NNetNav-7B | Chênh |
| :--- | :---: | :---: | :---: |
| Shopping Admin | 25,3% | 14,3% | **+11,0 pp** |
| Reddit | 30,7% | 23,7% | **+7,0 pp** |
| **Shopping** | **22,4%** | **20,3%** | **+2,1 pp** |
| GitLab | 15,3% | 19,9% | −4,6 pp |

Shopping là miền có biên độ nhỏ nhất trong ba miền Go-Browse thắng. Lý do nằm
trong chính phần phân tích của bài báo (§6): lợi thế của Go-Browse đến từ việc
**đi sâu** vào các URL khó tìm (`catalog/product/edit/id/{id}`,
`sales/order/view/order_id/{id}`) — mà những URL đó thuộc *shopping_admin*.
Storefront shopping thì nông: phần lớn task là tìm kiếm và đọc thông tin sản
phẩm, đạt được từ trang chủ trong vài bước. Khi cấu trúc miền không thưởng cho
việc đi sâu, mọi phương pháp khám phá đều hội tụ về cùng một chỗ.

### 2.3 HSGE đạt kết quả đó với dữ liệu ít hơn khoảng một bậc

| | Go-Browse-WA (shopping) | HSGE (shopping) |
| :--- | :---: | :---: |
| Bước huấn luyện thành công | ≈ 7.900 (39.339 / 5 miền) | **979** |
| Quỹ đạo | ≈ 1.900 (9.504 / 5) | **250** |
| URL khám phá | 20 | 79 node |
| Mô hình dùng để thu dữ liệu | Claude-3.7-Sonnet + GPT-4o + GPT-4o-mini | GPT-4o / GPT-4o-mini |
| Chi phí thu dữ liệu (toàn bộ 5 miền) | **975,57 USD** | — |

Với **≈ 1/8 số bước huấn luyện**, HSGE đạt SR chênh 1 pp. Nếu diễn giải theo
hiệu suất trên mỗi mẫu dữ liệu thì đây là điểm mạnh chứ không phải điểm yếu —
nhưng cần nói rõ đây là suy luận từ hai thí nghiệm không đồng nhất (khác
explorer, khác reward model, khác siêu tham số), **không phải một ablation có
kiểm soát**.

Cũng cần thẳng thắn: shopping là miền HSGE **dừng thu sớm nhất**. Chỉ có
`wa_run_20_shopping` (79 node, 565 episode); không có `wa_run_21`/`22` cho
shopping như reddit và shopping_admin. Nghĩa là chưa có bằng chứng nào cho thấy
HSGE *đã cạn* khả năng cải thiện trên miền này — chỉ là chưa thử.

### 2.4 Phần thất bại còn lại thuộc tầng thực thi, giống nhau ở cả hai bên

Dữ liệu 9B FT shopping: 0,46 lỗi hành động/bước, 50 task hết ngân sách + 17 task
kẹt trên 187. Đây là lỗi **định vị phần tử và bám mục tiêu qua nhiều bước** —
loại lỗi mà thêm dữ liệu bắt chước không sửa được, vì bản thân dữ liệu cũng do
một agent mắc cùng loại lỗi sinh ra.

### 2.5 Trả lời gọn

> Vì cả hai cùng finetune một mô hình `Qwen2.5-7B-Instruct` và **cùng chạm trần
> của mô hình đó trên một miền nông**. Shopping là miền mà lợi thế "khám phá
> sâu" của Go-Browse phát huy yếu nhất (chính bài báo cho thấy Go-Browse chỉ hơn
> NNetNav 2,1 pp ở shopping, so với 11,0 pp ở shopping_admin). Chênh lệch 1,0 pp
> tương đương 2 task và nằm trong nhiễu ±5,9 pp. Điểm đáng ghi nhận là HSGE đạt
> mức đó với **979 bước huấn luyện so với ≈7.900 của Go-Browse**, và là miền duy
> nhất HSGE chưa hề chạy đợt thu bổ sung.

---

## 3. Câu hỏi 3 — Vì sao giữa Đợt 1 và Đợt 2, Admin cải thiện ít trong khi Reddit tăng mạnh?

### 3.1 Nghịch lý: Admin được thêm **nhiều** dữ liệu hơn Reddit

| | Đợt 1 (`checkpoint-536`) | Bổ sung | Đợt 2 | Hệ số |
| :--- | :---: | :---: | :---: | :---: |
| reddit — mẫu (bước) | 1.279 | **+1.856** | 3.135 | ×2,45 |
| reddit — quỹ đạo | 308 | +370 | 678 | ×2,20 |
| shopping_admin — mẫu | 1.175 | **+2.410** | 3.585 | ×3,05 |
| shopping_admin — quỹ đạo | 202 | +327 | 529 | ×2,62 |

Shopping_admin nhận **nhiều hơn reddit 554 mẫu** nhưng cải thiện ít hơn. Câu hỏi
vì thế không phải "reddit được ưu ái hơn" mà "vì sao cùng lượng dữ liệu lại cho
hiệu quả khác nhau".

### 3.2 Con số thật: tính theo số task, hai miền tăng **bằng nhau**

| | Đợt 1 | Đợt 2 (thô) | Δ thô | Đợt 2 (đã audit) | Δ đã audit |
| :--- | :---: | :---: | :---: | :---: | :---: |
| reddit (n=106) | 22 (20,75%) | 25 (23,58%) | **+3 task / +2,8 pp** | 36 (33,96%) | +14 task / +13,2 pp |
| shopping_admin (n=182) | 28 (15,38%) | 31 (17,03%) | **+3 task / +1,6 pp** | 39 (21,43%) | +11 task / +6,0 pp |

Trên **số liệu thô so số liệu thô** — phép so sánh duy nhất công bằng, vì Đợt 1
chưa từng được rà soát false-negative còn Đợt 2 thì có — **cả hai miền đều tăng
đúng 3 task.** Toàn bộ ấn tượng "reddit bùng nổ còn admin giậm chân" đến từ ba
nguồn, xếp theo mức đóng góp:

**(a) Mẫu số khác nhau — thuần số học.** Reddit chỉ có 106 task, admin có 182.
Cùng +3 task thành +2,8 pp ở reddit nhưng chỉ +1,6 pp ở admin. Riêng yếu tố này
đã tạo ra hệ số **1,7 lần** mà không cần bất kỳ lý do kỹ thuật nào.

**(b) Đợt audit false-negative bất đối xứng.** Đợt 1 chưa bao giờ được soi
false-negative; Đợt 2 thì được soi cả hai miền. Reddit phục hồi 11 task, admin
phục hồi 8 task. Nếu Đợt 1 cũng được soi bằng cùng tiêu chuẩn, cả hai Δ sẽ nhỏ
lại đáng kể. **Đây là caveat bắt buộc phải nêu khi trích Bảng 3.**

**(c) Bản chất miền.** Phần này mới là nội dung kỹ thuật thực sự:

| | reddit | shopping_admin |
| :--- | :---: | :---: |
| SR mô hình nền (dư địa) | **6,6%** (thấp nhất 4 miền) | 12,6% |
| Bước/task (9B FT) | 9,8 | **11,0** |
| Task hết ngân sách hoặc kẹt | 46/106 (**43%**) | 110/182 (**60%**) |
| Không gian hành động | Nhỏ, lặp lại: đăng bài, bình luận, vote, tạo forum, tìm kiếm | Rộng: bộ lọc grid, khoảng ngày, báo cáo, duyệt review, sửa sản phẩm |
| Loại false-negative gặp phải | `url_match` sau `send_msg_to_user`, locator `.value` sau submit | `exact_match` chuỗi ngày (`01/01/2022` vs `1/1/2022`), locator sau khi rời trang |

Ba hệ quả:

1. **Dư địa.** Reddit xuất phát từ 6,6% — gần như bằng không. Bất kỳ hành vi
   bắt chước hợp lý nào cũng cho lợi ích lớn ngay. Admin đã ở 12,6%, phần "dễ
   ăn" đã bị Đợt 1 lấy hết.
2. **Độ đồng nhất của kỹ năng.** Reddit có repertoire nhỏ và lặp: 370 quỹ đạo
   mới hầu hết là biến thể của cùng vài kỹ năng ⇒ tín hiệu học **dày và trùng
   lặp có ích**. Admin có repertoire rộng: 327 quỹ đạo mới trải mỏng trên nhiều
   loại thao tác khác nhau ⇒ mỗi kỹ năng chỉ được vài ví dụ.
3. **Nút thắt không nằm ở kiến thức mà ở chân trời thực thi.** 60% task
   shopping_admin *không bao giờ kết thúc* (hết 16 bước hoặc kẹt). Thêm bản
   trình diễn cho một mô hình đang thất bại vì *độ dài và độ chính xác chuỗi
   thao tác* thì lợi ích cận biên rất nhỏ. Đây là chẩn đoán quan trọng nhất của
   mục này: **admin cần ngân sách bước lớn hơn và cơ chế chống lang thang, không
   phải thêm dữ liệu.**

**(d) Chất lượng dữ liệu thu được cũng khác.** Tỷ lệ episode LOCAL thành công
trong chính hai đợt thu bổ sung:

| Đợt thu | LOCAL success / total | Kỹ năng phát hiện |
| :--- | :---: | :---: |
| `wa_run_21_reddit` | 236/402 (**58,7%**) | 29 |
| `wa_run_22_reddit` | 179/289 (**61,9%**) | 11 |
| `wa_run_21_shopping_admin` | 131/231 (**56,7%**) | 28 |
| `wa_run_22_shopping_admin` | 122/287 (**42,5%**) | 19 |

Đợt thu admin thứ hai có tỷ lệ thành công tụt xuống 42,5% và tỷ lệ
`infeasible` cao (83/287) — tức là 1.077 mẫu admin cuối cùng được lọc ra từ một
đợt khám phá kém hiệu quả hơn hẳn.

### 3.3 Trả lời gọn

> Trên số liệu thô, **hai miền tăng bằng nhau: đúng +3 task mỗi bên.** Chênh lệch
> phần trăm đến từ (1) mẫu số 106 vs 182 — riêng yếu tố này đã nhân 1,7 lần, và
> (2) đợt rà soát false-negative chỉ áp cho Đợt 2 chứ không áp cho Đợt 1. Phần
> nguyên nhân kỹ thuật thật sự là: reddit xuất phát từ dư địa lớn nhất (base
> 6,6%) với không gian hành động nhỏ và lặp lại nên dữ liệu bổ sung chuyển hóa
> gần như 1:1; còn shopping_admin thất bại vì **chân trời thực thi** — 60% task
> hết ngân sách bước hoặc bị kẹt — nên thêm 2.410 mẫu bắt chước không chạm được
> vào nút thắt. Nói cách khác, admin không thiếu dữ liệu, admin thiếu số bước và
> khả năng bám mục tiêu dài hơi.

---

## 4. Câu hỏi 4 — Bổ sung bao nhiêu dữ liệu thì SR tăng bao nhiêu?

**Phạm vi mục này:** chỉ hai miền thực sự được bổ sung dữ liệu —
**reddit (106 task)** và **shopping_admin (182 task)**, tổng 288 task. Shopping
và gitlab không nhận mẫu mới nào và cũng không được đánh giá lại ở Đợt 2, nên
không có mặt ở đây; gộp chúng vào chỉ làm loãng con số cần đo.

### 4.1 Bảng đối chiếu trực tiếp

Mô hình Đợt 2 là bản **continue-finetune** (`qwen35-9b-lora-continue-v1`), khởi
động ấm từ `checkpoint-536`, huấn luyện 1 epoch, LR 3e-5, trên
`training_data_continue_v1` = **4.266 mẫu mới + 760 mẫu replay** (15%
shopping/gitlab, chỉ để chống quên thảm họa, không nhằm cải thiện gì) = 5.026 mẫu.

| Miền | Mẫu thêm | Quỹ đạo thêm | SR Đợt 1 | SR Đợt 2 (thô) | SR Đợt 2 (đã audit) | Δ thô | Δ đã audit |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 💬 **reddit** (n=106) | +1.856 (×2,45) | +370 | 22 (20,8%) | 25 (23,6%) | 36 (34,0%) | **+2,8 pp** | **+13,2 pp** |
| ⚙️ **shopping_admin** (n=182) | +2.410 (×3,05) | +327 | 28 (15,4%) | 31 (17,0%) | 39 (21,4%) | **+1,6 pp** | **+6,0 pp** |
| **Cộng hai miền** (n=288) | **+4.266** | **+697** | 50 (17,4%) | 56 (19,4%) | 75 (26,0%) | **+2,1 pp** | **+8,7 pp** |

**Hiệu suất trên mỗi 1.000 mẫu bổ sung:**

| Miền | pp / 1.000 mẫu (thô) | pp / 1.000 mẫu (đã audit) |
| :--- | :---: | :---: |
| 💬 reddit | +1,5 | **+7,1** |
| ⚙️ shopping_admin | +0,7 | **+2,5** |
| **Cộng hai miền** | +0,5 | **+2,0** |

Đọc ngang hai dòng đầu: reddit cho hiệu suất trên mỗi mẫu **cao gấp khoảng 2,8
lần** shopping_admin, dù nhận ít hơn 554 mẫu. Lý do đã phân tích ở §3.2.

### 4.2 Cách đọc hai cột Δ

- **Cột "thô"** so số chấm tự động với số chấm tự động. Đây là **cận dưới đáng
  tin cậy**: +2,8 pp reddit, +1,6 pp admin.
- **Cột "đã audit"** là số dùng trong Bảng 3 của tài liệu tổng hợp. Nó **so một
  bên đã được soi false-negative với một bên chưa được soi**, nên là **cận
  trên**. Giá trị thật nằm giữa hai cột.

Khi trích dẫn ra ngoài (báo cáo, slide), nên nêu cả hai cùng lúc, ví dụ:
*"reddit tăng từ 20,8% lên 34,0% sau khi rà soát lỗi chấm; nếu chỉ so số chấm
tự động chưa rà soát ở cả hai đợt thì mức tăng là 20,8% → 23,6%."*

### 4.3 Ba cảnh báo bắt buộc kèm theo các con số này

1. **Bất đối xứng audit** — như §3.2(b) và §4.2: Đợt 1 chưa từng được soi
   false-negative, Đợt 2 thì có. Đây là lý do hai cột Δ chênh nhau nhiều.
2. **Mô hình chấm bị thay.** `gpt-4-1106-preview` của WebArena gốc đã bị khai
   tử; toàn bộ các đợt chạy dùng `gpt-4-turbo` thay thế
   (`training/patch_webarena_judge.py`). Ghi nhận trong mọi `summary.json`.
3. **Chưa kiểm chứng tác dụng phụ lên hai miền không bổ sung.** Lát replay 15%
   shopping/gitlab tồn tại để chống quên thảm họa, nhưng chưa ai chạy lại hai
   miền đó sau continue-finetune (`training_data_continue_v1/README.md` ghi rõ:
   *"After training, evaluate all four domains"*). Không ảnh hưởng đến các con
   số reddit/shopping_admin ở trên, nhưng có nghĩa là **chi phí thật của đợt bổ
   sung này chưa được biết đủ**.

### 4.4 Lợi ích cận biên đang giảm rõ rệt

Đặt cạnh nhau hai vòng cho hai miền được bổ sung:

| Vòng | Mẫu tích lũy (reddit + admin) | SR trên 288 task |
| :--- | :---: | :---: |
| Đợt 1 | 2.454 | 50/288 (17,4%) |
| Đợt 2 | 6.720 (**×2,74**) | 75/288 (**26,0%**) — hoặc 56/288 (19,4%) theo số thô |

Gần **gấp ba lượng dữ liệu** đổi lấy +8,7 pp (cận trên) hoặc +2,1 pp (cận dưới).
Đối chiếu §3.2, hướng đi tiếp theo có triển vọng hơn việc thu thêm dữ liệu là:

- **Sửa nút thắt thực thi** (ưu tiên 1): nâng ngân sách bước cho task nhiều
  bước, chống lang thang dựa trên tiến độ — nhắm vào 60% task admin chết vì
  `budget`/`stuck`. Đúng với chẩn đoán trong `docs/17_phaseC_solver_competence_plan.md`.
- **Sửa lỗi tuân thủ định dạng** (ưu tiên 1 cho nhánh 7B): xem §1.2 — đây là
  đòn bẩy lớn nhất và rẻ nhất còn lại của bản 7B, ước lượng theo dữ liệu là
  từ 8,8% lên vùng 20%+ mà **không cần một mẫu dữ liệu mới nào**.
- **Sửa độ giòn của bộ chấm** (không nâng năng lực nhưng nâng số đo đúng): 19
  task đã bị chấm sai âm chỉ trong hai đợt rà soát.

### 4.5 Trả lời gọn

> Bổ sung **4.266 mẫu (697 quỹ đạo)** cho hai miền:
> - **reddit** +1.856 mẫu (×2,45): 20,8% → **23,6%** (thô) hoặc **34,0%** (đã
>   rà soát lỗi chấm) — tức **+2,8 đến +13,2 pp**, ứng với **+1,5 đến +7,1 pp
>   trên mỗi 1.000 mẫu**.
> - **shopping_admin** +2.410 mẫu (×3,05): 15,4% → **17,0%** (thô) hoặc
>   **21,4%** (đã rà soát) — tức **+1,6 đến +6,0 pp**, ứng với **+0,7 đến
>   +2,5 pp trên mỗi 1.000 mẫu**.
>
> Cộng riêng 288 task của hai miền này: 17,4% → 19,4% (thô) hoặc 26,0% (đã rà
> soát). Reddit hiệu quả trên mỗi mẫu **gấp ~2,8 lần** shopping_admin dù nhận ít
> mẫu hơn. Và lợi ích cận biên đang giảm rõ: **gần gấp ba lượng dữ liệu** của
> hai miền (2.454 → 6.720 mẫu) chỉ đổi được mức tăng nêu trên.

---

## 5. Nguồn số liệu

| Nội dung | Đường dẫn |
| :--- | :--- |
| Kết quả từng task, mọi đợt chạy | `outputs/eval/{eval_base,eval_finetuned}/<site>/<variant>/results.jsonl` |
| Kết quả 7B (Qwen2.5) | `outputs/eval/{reddit,gitlab,shopping_admin}/finetuned/` |
| Báo cáo rà soát bất thường | `outputs/eval/eval_anomaly_report*.md` (4 file) |
| Thành phần tập huấn luyện Đợt 1 | `training_data/train.jsonl` (4.288 mẫu) |
| Tập bổ sung Đợt 2 | `training_data_continue_v1/README.md` (5.026 mẫu) |
| Tập hợp nhất dùng cho bản 7B | `training_data_merged_v1/README.md` (8.554 mẫu) |
| Thống kê các đợt khám phá | `outputs/wa_run_2{0,1,2}_*/summary.json` |
| Cấu hình huấn luyện Đợt 2 | `training/qwen35_9b_lora_continue_v1.yaml` |
| Số liệu Go-Browse | [`docs/go-browse.md`](go-browse.md) — Bảng 1, 3, 9 |
| Nhật ký các đợt chạy | `.claude/memory/changelog.md` (mục 2026-08-19, 2026-08-20) |

### Lệnh tái lập bảng nền §0

```bash
python3 - <<'EOF'
import json, collections
for p in ['outputs/eval/shopping_admin/finetuned/results.jsonl',
          'outputs/eval/eval_finetuned/shopping_admin/finetuned/results.jsonl']:
    rows = [json.loads(l) for l in open(p)]
    u = [r for r in rows if r['n_unparsed_llm'] > 0]
    c = [r for r in rows if r['n_unparsed_llm'] == 0]
    print(p)
    print(f"  hong dinh dang: {len(u)}/{len(rows)}  SR={sum(r['success'] for r in u)}/{len(u) or 1}")
    print(f"  dau ra sach   : {len(c)}/{len(rows)}  SR={sum(r['success'] for r in c)}/{len(c) or 1}")
    print("  stop_reason:", dict(collections.Counter(r['stop_reason'] for r in rows)))
EOF
```
