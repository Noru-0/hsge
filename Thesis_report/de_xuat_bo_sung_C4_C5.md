# ĐỀ XUẤT CHỈNH SỬA & BỔ SUNG CHƯƠNG 4–5

> **Nguồn đối chiếu:** `docs/tong_hop_ket_qua_eval.md`, `docs/phan_tich_ket_qua_eval.md`,
> và dữ liệu thô `outputs/eval/**/{results.jsonl,traces/}`.
> **Đối tượng:** `Thesis_report/thesis_hsge_vi/Chapter4/chapter4.tex` (885 dòng),
> `Chapter5/chapter5.tex` (284 dòng).
> **Ngày lập:** 2026-08-21. Đây là **đề xuất**, chưa sửa file .tex nào.

---

## 0. Tóm tắt điều hành

Bảy khoản, xếp theo mức bắt buộc. Hai khoản đầu là **lỗi/lỗ hổng phòng thủ cần
sửa bất kể có bổ sung gì hay không**; năm khoản sau là bổ sung tùy chọn.

| # | Khoản | Loại | Vị trí | Chi phí |
| :--- | :--- | :--- | :--- | :--- |
| **P0-1** | Phát biểu "thứ tự mức cải thiện trùng thứ tự lượng dữ liệu" **sai** và tự mâu thuẫn với §4.6 | 🔴 Sửa lỗi | C4:559–561, C5:35 | 2 câu |
| **P0-2** | Phát hiện 2 chưa chống được câu phản biện "`max_tokens` đặt thấp" | 🔴 Phòng thủ | C4:563 hoặc caption `tab:profile` | 2 câu |
| **P1** | Bổ sung thí nghiệm **Qwen2.5-7B** trên cùng tập dữ liệu — lấp đúng chỗ §4.6 đang trống | 🟠 Bổ sung lớn | §4.6 + §5.5 | ~1 trang |
| **P2** | Quan sát **lợi ích cận biên của dữ liệu** (Đợt 1→Đợt 2) | 🟡 Xung đột quyết định cũ | §4.6 hoặc phụ lục | 0,5–1 trang |
| **P3** | Taxonomy **lỗi của bộ chấm** cho §5.5 "Hợp lệ cấu trúc" | 🟢 Làm giàu | C5:279 | 4–5 câu |
| **P4** | Sắc hóa lý do **thua Shopping Admin** bằng chính số liệu Go-Browse | 🟢 Làm giàu | C5:149–157 | 3 câu |
| **P5** | `tab:crosssite` thêm cột "Δ so với mô hình nền" | 🟢 Nhỏ | C4:701–717 | 1 cột |

---

## P0-1 🔴 Sửa: "thứ tự mức cải thiện trùng thứ tự lượng dữ liệu" là phát biểu sai

### Hiện trạng

**C4 dòng 559–561:**
> "Đáng chú ý, thứ tự mức cải thiện trùng với thứ tự lượng dữ liệu thu được cho
> từng website: hai website có nhiều dữ liệu nhất cũng là hai website cải thiện
> nhiều nhất."

**C5 dòng 35** (phát biểu trần, không có mệnh đề giảm nhẹ đi kèm):
> "Thứ tự này trùng với thứ tự lượng dữ liệu thu được cho từng website."

### Vì sao sai

Hai thứ hạng **đảo nhau ở đúng hai vị trí đầu**:

| Hạng | Theo lượng dữ liệu (`tab:crosssite`) | Theo mức cải thiện (`tab:baseline`) |
| :---: | :--- | :--- |
| 1 | Shopping Admin — 41,9% | **Reddit — +27,4 đpt** |
| 2 | Reddit — 36,6% | **Shopping Admin — +8,8 đpt** |
| 3 | Shopping — 11,4% | Shopping — +8,6 đpt |
| 4 | GitLab — 10,0% | GitLab — +7,2 đpt |

Website **nhiều dữ liệu nhất** cải thiện **kém hơn ba lần** website đứng thứ hai.
Mệnh đề sau dấu hai chấm ở C4 ("hai website có nhiều dữ liệu nhất cũng là hai
website cải thiện nhiều nhất") thì **đúng** — nhưng nó nói về *tập hai phần tử*,
không phải về *thứ tự*, nên nó không chứng minh mệnh đề đứng trước nó.

Dữ liệu bổ sung củng cố thêm: trong đợt thu bổ sung, shopping\_admin nhận
**+2.410 mẫu** còn reddit chỉ **+1.856 mẫu** — website nhận nhiều hơn lại cải
thiện ít hơn (`docs/phan_tich_ket_qua_eval.md` §3.1).

### Vì sao đây là lỗi đáng sửa chứ không phải diễn đạt vụng

Câu này **chọi trực tiếp với chính lập luận của quyển** cách đó chưa tới hai
trang. §4.6 (C4:719–723) và CH4 (C5:55) dùng đúng `tab:crosssite` để **bác bỏ**
cách nghĩ "đổ thêm dữ liệu vào website nào thì website đó khá lên". Một người
phản biện đọc liền mạch sẽ thấy quyển tự nói ngược mình.

### Đề xuất câu thay thế

**C4:559–561 →**
> Đáng chú ý, hai website được cấp ngân sách khám phá lớn nhất cũng là hai
> website cải thiện nhiều nhất — nhưng thứ tự bên trong cặp đó thì ngược lại:
> Shopping Admin chiếm phần dữ liệu huấn luyện lớn hơn Reddit (41,9\% so với
> 36,6\%) mà chỉ cải thiện $+8{,}8$ điểm so với $+27{,}4$ điểm của Reddit. Lượng
> dữ liệu vì vậy giải thích được việc một website có nằm trong nhóm cải thiện
> mạnh hay không, nhưng không giải thích được mức cải thiện bên trong nhóm;
> Mục~\ref{sec:exp-ablation} bàn tiếp điểm này.

**C5:35 →**
> Hai website đứng đầu về mức cải thiện cũng là hai website thu được nhiều dữ
> liệu nhất, song thứ tự bên trong cặp thì ngược: Shopping Admin nhiều dữ liệu
> hơn Reddit mà cải thiện kém hơn ba lần. Quan hệ giữa lượng dữ liệu và mức cải
> thiện vì vậy chỉ đứng vững ở mức nhóm, không ở mức thứ hạng — nhất quán với
> câu trả lời cho CH4 ở Mục~\ref{sec:disc-results}.

---

## P0-2 🔴 Phòng thủ: Phát hiện 2 chưa trả lời được câu hỏi "`max_tokens` đặt thấp"

### Rủi ro

Phát hiện 2 là một trong ba phát hiện tiêu đề của quyển, dựa trên con số **170
trên 655 phiên (26,0%) của mô hình nền hỏng định dạng** (`tab:profile`, C4:840).
Một người phản biện sẽ hỏi ngay: *"170 phiên đó có phải do các anh đặt giới hạn
token đầu ra quá thấp, cắt ngang phản hồi của mô hình nền không?"* Nếu đúng thì
Phát hiện 2 không còn là một tính chất của mô hình mà là một tham số cấu hình —
và quyển hiện **không có câu trả lời nào**.

### Câu trả lời đã đo được

| | Số phiên | Bản chất |
| :--- | :---: | :--- |
| `finish_reason = length` | **91** | Phản hồi bị cắt vì chạm trần ngữ cảnh |
| `finish_reason = stop` | **79** | Mô hình tự kết thúc nhưng chuỗi không phân giải được |

Với 91 phiên bị cắt:
- **Không hề đặt `max_tokens`** trong lời gọi (`training/eval_webarena.py`), nên
  trần thực tế là phần còn lại của cửa sổ ngữ cảnh 8192 token
  (`training/serve_vllm.sh`).
- Prompt trung vị **8.169 ký tự** (~2.000 token), tức còn dư khoảng 6.000 token.
- Phản hồi bị cắt dài **trung vị 21.060 ký tự** (~5.300 token; ngắn nhất 11.655,
  dài nhất 30.687).

Nghĩa là mô hình nền sinh liên tục hơn năm nghìn token mà **vẫn chưa đóng được
một đối tượng JSON**. Đây là hiện tượng sinh tràn, không phải bị cắt oan.

### Đề xuất

Thêm vào cuối đoạn C4:563 (hoặc vào caption `tab:profile`) hai câu:

> Trong 170 phiên đó, 91 phiên bị cắt vì chạm trần cửa sổ ngữ cảnh và 79 phiên
> kết thúc bình thường nhưng cho ra chuỗi không phân giải được. Cần nói rõ rằng
> 91 phiên đầu \emph{không} phải hệ quả của một giới hạn token do khóa luận áp
> đặt: lời gọi không đặt \texttt{max\_tokens}, prompt trung vị chỉ chiếm khoảng
> 2000 token trong cửa sổ 8192 token, trong khi phản hồi bị cắt dài trung vị
> khoảng 5300 token mà vẫn chưa đóng được đối tượng JSON - tức mô hình nền sinh
> tràn chứ không bị cắt ngang.

**Lợi ích:** biến một lỗ hổng phản biện thành một bằng chứng bổ sung cho chính
Phát hiện 2, tốn hai câu.

---

## P1 🟠 Bổ sung: thí nghiệm Qwen2.5-7B — lấp đúng chỗ §4.6 đang bỏ trống

### Vì sao đáng đưa vào

Quyển hiện **không có ablation nào đã chạy** (§4.6, C4:688: *"Các ablation có
kiểm soát chưa được thực hiện"*). Trong khi đó `tong_hop_ket_qua_eval.md` Bảng 1
là một thí nghiệm **đã chạy xong, đủ 655 task**, và nó cô lập được đúng biến số
mà quyển đang phải ước lượng gián tiếp ở ba chỗ (§4.5.3 mục 1, §5.3.1, §5.5):
**đóng góp của mô hình nền so với đóng góp của tập dữ liệu**.

Thiết kế của nó gần như một ablation sạch: **cùng tập dữ liệu 8.554 mẫu**, cùng
bộ chấm `gpt-4-turbo`, cùng ngân sách 15 bước, cùng 655 task — chỉ đổi mô hình
nền sang **Qwen2.5-7B-Instruct**, tức đúng backbone Go-Browse và NNetNav dùng.

| | Qwen2.5-7B | Qwen3.5-9B |
| :--- | :---: | :---: |
| Mô hình nền (4 site) | 8,3% | 13,3% |
| Sau fine-tune trên **cùng 8.554 mẫu** | 16,5% | 24,6% |
| Mức tăng | +8,2 đpt | +11,3 đpt |

### ⚠️ Nhưng KHÔNG được dùng nó làm phép so sánh cùng-backbone với Go-Browse

Đây là điểm quan trọng nhất của khoản này. Nhìn qua thì bảng trên cho phép nói
*"cùng backbone Qwen2.5-7B, HSGE đạt 16,5% còn Go-Browse 22,6%"*. **Phát biểu đó
sai về mặt đo lường**, vì kết quả 7B bị nhiễu bởi một quyết định ở tầng harness
chứ không phải bởi chất lượng dữ liệu. Bằng chứng, đọc trực tiếp từ trace:

- **275/275** phản hồi "hỏng định dạng" của bản 7B có `finish_reason = stop`,
  tức phản hồi hoàn chỉnh, không bị cắt.
- **92–98% trong số đó là một lệnh `report_infeasible(...)` viết trần**, kèm lý
  do mạch lạc, chỉ thiếu lớp vỏ JSON. Ví dụ nguyên văn:
  `report_infeasible("The Period control is set to Day, while Quarter is
  explicitly unavailable as an option...")`. Phần còn lại gần như toàn bộ là
  `send_msg_to_user(...)` — cũng là lệnh kết thúc.
- Hệ quả đo được: bản 7B chỉ ghi nhận **10/182** lần báo bất khả thi trên
  shopping\_admin, so với **41/182** của bản 9B — không phải vì nó ít báo, mà vì
  bộ phân giải **vứt bỏ** phần lớn các lần báo đó và episode bị ghi thành
  `budget`/`stuck`.

Vì WebArena **cho điểm** khi agent báo bất khả thi đúng trên task có nhãn `N/A`,
một bộ phân giải khoan dung hơn gần như chắc chắn sẽ **nâng** điểm của bản 7B,
theo mức chưa xác định. Nói cách khác **16,5% là một cận dưới bị hạ thấp bởi độ
nghiêm của bộ phân giải**, không phải một phép đo chất lượng dữ liệu.

Đối chiếu để thấy hai hiện tượng khác hẳn nhau: 170 phiên hỏng của mô hình nền
9B là **sinh tràn / JSON dở dang** (P0-2), còn 275 phiên của bản 7B là **lệnh
kết thúc hợp lệ viết sai vỏ**. Gộp hai thứ này dưới một nhãn "hỏng định dạng" sẽ
làm hỏng cả hai lập luận.

### Đề xuất trình bày

Thêm một tiểu mục vào **§4.6** (nơi đang trống), tên đề nghị *"Thay mô hình nền,
giữ nguyên tập dữ liệu"*, gồm:

1. Bảng ba dòng như trên (nền / sau fine-tune / mức tăng) cho hai backbone.
2. Một đoạn nêu **điều rút ra được**: cùng một tập dữ liệu nâng được cả hai
   backbone, và mức nâng tuyệt đối của backbone yếu hơn thấp hơn — tức tập dữ
   liệu không phụ thuộc vào một backbone cụ thể, nhưng trần mà nó chạm tới thì
   có.
3. Một đoạn nêu **điều KHÔNG rút ra được**, với đúng bằng chứng ở trên: không
   dùng con số 16,5% để so với Go-Browse-7B, vì phép đo bị nhiễu bởi bộ phân
   giải; muốn so được thì phải chạy lại với bộ phân giải chấp nhận lệnh viết
   trần.

Và thêm một mục vào **§5.5 "Hợp lệ nội tại"**: bộ phân giải đầu ra là một thành
phần của phép đo, và với backbone nhỏ hơn thì độ nghiêm của nó ảnh hưởng tới
điểm số ở mức không bỏ qua được.

### Rủi ro nếu bỏ qua khoản này

Kết quả 7B đã tồn tại trong repo và trong `tong_hop_ket_qua_eval.md`. Nếu hội
đồng biết tới nó mà quyển không nhắc, tình huống xấu hơn hẳn so với việc quyển
tự trình bày kèm caveat.

---

## P2 🟡 Lợi ích cận biên của dữ liệu — **khoản này đi ngược một quyết định đã chốt**

### Nêu rõ xung đột trước

Ngày 20-08, hai quyết định đã được chốt theo yêu cầu trực tiếp:
- **19:44** — trình bày dữ liệu như **một đợt thu duy nhất**, gỡ mọi tương phản
  Đợt 1 / Đợt 2, xóa `tab:rawadj` và mọi số liệu thô đối chứng.
- **20:41** — trình bày huấn luyện như **một lượt chạy** với lịch learning rate
  hai pha ($10^{-4} \rightarrow 3\times10^{-5}$), thay vì hai chặng.

Khoản đề xuất dưới đây **mâu thuẫn với cả hai**. Nêu ra vì nó là bằng chứng
mạnh nhất còn lại cho CH4, không phải để lật quyết định cũ.

### Nó mua được gì

CH4 hiện được trả lời bằng hai căn cứ: (i) thứ hạng chéo giữa 4 website — mà
chính quyển thừa nhận *"với bốn điểm dữ liệu thì đây không phải một kết luận
thống kê"*; và (ii) bảng phân loại lỗi. Cả hai đều là bằng chứng **gián tiếp**.

Dữ liệu Đợt 1 → Đợt 2 là phép đo **trực tiếp, trong cùng một website, có trước
và sau**:

| Website | Mẫu bổ sung | SR trước | SR sau | Δ (thô) | Δ (đã rà soát) | đpt / 1.000 mẫu |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Reddit | +1.856 (×2,45) | 20,8% | 23,6% | +2,8 | +13,2 | +1,5 → +7,1 |
| Shopping Admin | +2.410 (×3,05) | 15,4% | 17,0% | +1,6 | +6,0 | +0,7 → +2,5 |

Hai điều đọc được, không suy diễn:
1. Website nhận **nhiều mẫu hơn** lại có hiệu suất trên mỗi mẫu **thấp hơn ~2,8
   lần**. Đây là bằng chứng within-site cho luận điểm "lượng dữ liệu không phải
   nút thắt", mạnh hơn hẳn thứ hạng chéo n=4.
2. Gần **gấp ba** lượng dữ liệu của hai website đó (2.454 → 6.720 mẫu) chỉ đổi
   được mức tăng trên — tức **lợi ích cận biên đang giảm rõ**, đúng điều Phát
   hiện 3 khẳng định nhưng hiện chưa có số nào chống lưng.

### Ba phương án

| | Phương án | Giữ được khung "một đợt thu"? | Sức nặng cho CH4 |
| :--- | :--- | :---: | :---: |
| **A** | Không làm gì | ✅ | không đổi |
| **B** | Đưa vào **phụ lục** dưới dạng "quan sát về lợi ích cận biên", diễn đạt theo *quy mô tập dữ liệu* chứ không theo *đợt thu* | ✅ (gần như) | +đáng kể |
| **C** | Khôi phục đầy đủ tương phản hai đợt vào §4.6 | ❌ | +mạnh nhất |

**Khuyến nghị: B.** Có thể viết mà không dùng chữ "đợt" lần nào, ví dụ:
*"Một phép đo phụ trên hai website cho thấy khi tăng phần dữ liệu của chúng từ
2.454 lên 6.720 mẫu, tỷ lệ hoàn thành trên 288 task tương ứng đi từ 17,4% lên
26,0% — tức khoảng 2,0 điểm phần trăm cho mỗi 1.000 mẫu thêm vào, và hiệu suất
này không đồng đều giữa hai website."*

Cần đi kèm caveat bắt buộc: số "đã rà soát" của mốc sau được soi false-negative
còn mốc trước thì không, nên phải nêu cả cột thô làm cận dưới.

**Quyết định thuộc về người viết**, vì nó đánh đổi tính nhất quán của cách kể
lấy sức nặng của bằng chứng.

---

## P3 🟢 Làm giàu §5.5 "Hợp lệ cấu trúc": taxonomy lỗi của bộ chấm

### Hiện trạng (C5:279)

Quyển nói bộ chấm nhị phân *"chưa ghi nhận được mức độ tiến bộ từng phần"* và
dẫn Xue và cộng sự. Đó là một nhận định **mượn từ tài liệu khác**, trong khi
khóa luận có **bằng chứng của chính mình** đang không được dùng: 19 phiên bị
chấm trượt nhầm đã được khôi phục (`tab:baseline` caption đã nhắc con số 19
nhưng không nói chúng sai theo kiểu gì).

### Đề xuất

Thêm 4–5 câu liệt kê **khuôn lỗi** rút từ hai báo cáo rà soát
(`outputs/eval/eval_anomaly_report_reddit_rerun.md`,
`..._shopping_admin_2.md`):

| Khuôn lỗi của bộ chấm | Ví dụ đo được |
| :--- | :--- |
| `url_match` xét URL ở khoảnh khắc cuối, mà `send_msg_to_user` lại giữ agent ở trang vừa tạo | 6 task reddit (đăng bài, downvote) |
| Locator đọc `.value` của phần tử form **sau khi form đã submit** — thẻ input không còn tồn tại | tạo forum Karaoke; cập nhật tồn kho |
| `exact_match` trên chuỗi ngày gõ thô: `01/01/2022` bị coi là khác `1/1/2022` dù Magento tự chuẩn hóa | 4 task báo cáo doanh thu |
| Đáp án hardcode một danh sách tên forum, bỏ sót lựa chọn hợp lý khác | 2 task, agent chọn `/f/cmu_lti` |
| Bắt buộc tiền tố URL tuyệt đối trong câu trả lời dạng danh sách | 1 task |

Kèm một câu kết luận đúng phạm vi: những khuôn này đều là **lỗi tiêu chí chấm**
chứ không phải đánh giá lại theo cảm tính, và chúng phạt **hành vi kết thúc
episode đúng cách** (báo cho người dùng) — tức bộ chấm không trung lập với phong
cách hành vi mà nó đo.

**Vì sao đáng làm:** biến một nhận định vay mượn thành một quan sát tự đo, đúng
tinh thần "đóng góp O5". Không cần thêm số liệu mới nào.

---

## P4 🟢 Sắc hóa §5.3.1: vì sao thua Shopping Admin

### Hiện trạng (C5:149–157)

> "Chiều lệch này không quy về lượng dữ liệu được: Shopping Admin chính là
> website chiếm phần lớn nhất trong tập huấn luyện (41,9%) mà lại là website duy
> nhất khóa luận thua... yếu tố chi phối không phải khối lượng dữ liệu mà là
> kiểu lỗi chiếm ưu thế trên từng website."

Đúng, nhưng dừng ở mức "kiểu lỗi khác nhau" — chưa nói được **vì sao Go-Browse
lại mạnh riêng ở đó**.

### Bổ sung đề xuất

Lấy chính Bảng 3 của Go-Browse, tính biên độ của họ so với NNetNav-7B theo từng
website:

| Website | Go-Browse-7B | NNetNav-7B | Biên độ |
| :--- | :---: | :---: | :---: |
| Shopping Admin | 25,3% | 14,3% | **+11,0 đpt** |
| Reddit | 30,7% | 23,7% | +7,0 đpt |
| Shopping | 22,4% | 20,3% | **+2,1 đpt** |
| GitLab | 15,3% | 19,9% | −4,6 đpt |

Kết hợp với phần phân tích của chính họ (Go-Browse §6: lợi thế đến từ việc chạm
tới các URL sâu như `catalog/product/edit/id/{id}`, `sales/order/view/...` — đều
thuộc Shopping Admin), rút ra được một cách đọc **tự phê hơn và nhiều thông tin
hơn**:

> Shopping Admin đúng là website mà cơ chế khám phá sâu — thứ HSGE và Go-Browse
> cùng chia sẻ — phát huy mạnh nhất: đó là nơi Go-Browse bỏ xa NNetNav nhiều
> nhất (+11,0 điểm), trong khi ở Shopping biên độ của họ chỉ còn +2,1 điểm. Việc
> khóa luận thua đúng ở website đó, chứ không phải ở một website ngẫu nhiên, gợi
> ý rằng phần khám phá theo chiều sâu của HSGE chưa khai thác hết những trang
> nằm sâu trong giao diện quản trị — nhất quán với việc tỷ lệ task hết ngân sách
> hoặc kẹt vòng lặp ở website này là cao nhất trong bốn website.

**Vì sao đáng làm:** hiện §5.3.1 giải thích khoảng thua bằng "kiểu lỗi", mà
không nói kiểu lỗi đó gắn với cơ chế nào. Bổ sung này nối được khoảng thua với
đúng cơ chế mà chương 3 mô tả, và nó **bất lợi cho khóa luận** — loại lập luận
làm tăng độ tin cậy của cả chương.

Đồng thời nó trả lời được câu hỏi tiềm ẩn ở §5.3.1 về Shopping: khóa luận hơn
Go-Browse 5,9 điểm ở Shopping, nhưng Shopping lại là website mà **mọi phương
pháp khám phá đều hội tụ về cùng một chỗ** (biên độ Go-Browse chỉ +2,1) — nên
khoảng hơn đó nên quy cho mô hình nền chứ không cho pipeline.

---

## P5 🟢 `tab:crosssite` thêm một cột

Bảng hiện có: *Tỷ lệ dữ liệu | Hạng dữ liệu | SR*. Lập luận "trần khác nhau, dữ
liệu quyết định tiến gần trần tới đâu" (C4:725–733) cần **cột Δ so với mô hình
nền**, hiện phải lật sang `tab:baseline` mới thấy:

| Website | Tỷ lệ dữ liệu | SR | **Δ so với nền** |
| :--- | :---: | :---: | :---: |
| Shopping Admin | 41,9% | 21,4% | **+8,8** |
| Reddit | 36,6% | 34,0% | **+27,4** |
| Shopping | 11,4% | 28,3% | **+8,6** |
| GitLab | 10,0% | 18,3% | **+7,2** |

Đặt cạnh nhau, bảng tự nói ra cả hai vế của lập luận, và P0-1 trở nên hiển nhiên
với người đọc.

---

## 6. Những gì trong hai tài liệu **không nên** đưa vào quyển

| Nội dung | Lý do loại |
| :--- | :--- |
| Chỉ số "SR trên nhóm đầu ra sạch" của bản 7B (21,9% / 23,7% / 34,1%) | Nhóm này không phải mẫu ngẫu nhiên — task ngắn ít cơ hội hỏng định dạng hơn — nên là ước lượng thiên lệch lên. Dùng để chẩn đoán nội bộ thì được, đưa vào quyển thì thành một tuyên bố không đứng vững |
| Bảng Δ "đã rà soát" đặt cạnh Δ "thô" trong bảng kết quả chính | Quyết định 21-08 đã thu gọn công bố rà soát còn một câu trong caption; dựng lại lối trình bày song song sẽ lật quyết định đó |
| Tổng SR 4 miền của đợt bổ sung (24,58% so với 20,76%) | Shopping/GitLab không nhận mẫu mới và không được đo lại, nên con số tổng vừa pha loãng hiệu ứng vừa mang một giả định chưa kiểm chứng |
| Suy luận "HSGE hiệu quả dữ liệu hơn Go-Browse ~8 lần trên Shopping" | Hai thí nghiệm không đồng nhất (khác explorer, khác reward model, khác siêu tham số). §4.1.3 đã có phép so chi phí ở mức thận trọng vừa đủ; đẩy thêm sẽ vượt quá dữ liệu |

---

## 7. Thứ tự thực hiện đề nghị

1. **P0-1 + P0-2** — làm ngay, độc lập với mọi lựa chọn khác, tổng cộng 4 câu.
2. **P5 + P3 + P4** — rẻ, không đụng tới cấu trúc chương, làm chắc thêm ba chỗ
   lập luận đang mỏng.
3. **P1** — cần quyết định: có đưa thí nghiệm 7B vào không. Nếu có, phải viết
   kèm caveat bộ phân giải, nếu không thì đừng đưa nửa vời.
4. **P2** — cần quyết định của người viết vì đụng vào quyết định đã chốt.

Mọi số liệu trong tài liệu này đều tái lập được từ `outputs/eval/`; các lệnh
kiểm chứng nằm ở `docs/phan_tich_ket_qua_eval.md` §5.
