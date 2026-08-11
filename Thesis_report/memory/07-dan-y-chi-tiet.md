# Dàn ý chi tiết báo cáo (v1 — 2026-07-17, chưa gửi GVHD duyệt)

## ⚠️ RỦI RO LỚN NHẤT CHƯA XỬ LÝ (phát hiện 2026-07-20)

**Semantic task chưa từng chạy thật lần nào.** Kiểm chứng trực tiếp trên
`outputs/`:
- **0 / 1745** episode có tag `GOAL` (toàn bộ 12 run).
- `summary.json` mọi run: `GOAL: {success: 0, fail: 0}`; không có sự kiện
  goal-task nào trong `run_log.jsonl`.
- 370 example trong `training/train_12.jsonl` **100% từ low-level task**.

Nguyên nhân (không phải bug): operator graph gần như không có cạnh. Ở run
lớn nhất `wa_run_07` (128 node, 13 operator) chỉ có **đúng 1 cạnh**
effect→precondition (`clickandexaminelink → navigate_to_post`), và cạnh đó
chỉ hình thành khi operator thứ 13 — operator cuối — được induce, lúc run
đã bị ngắt (`status: "running"`). Nên `all_chains(min_len=2)` rỗng suốt run
và `_goal_tasks()` không sinh được gì. Đây là hệ quả trực tiếp của điểm yếu
predicate canonicalization đã biết (synonym thật 0,570 < ngưỡng 0,6 < cặp
sai 0,606): mỗi operator nhận một predicate id riêng nên không nối được.

Cơ chế **có** cài đặt đầy đủ và có test trên mock (`test_operators.py`,
`test_goal_task.py` assert đúng các chain) — chỉ là chưa kích hoạt được
trên site thật.

**Chỗ khóa luận đang nói quá:** `Chapter6/chapter6.tex` bảng O1–O5, dòng O2
ghi "Achieved: ... chain-based goal generation"; `Chapter1/chapter1.tex` O2
hứa "verified, long-horizon semantic tasks". Đúng loại lỗi P0-1 mà review
thesis mẫu bắt nặng nhất.

**Chỗ thứ BA, phát hiện 2026-07-20 khi rà soát phản biện** (chưa xử lý, cần
user quyết): `Chapter5/chapter5.tex` §5.1, câu "Equally important is what the
end-to-end run \emph{demonstrated}: every stage --- exploration, discovery,
**operator chaining**, curation, training, serving, and official evaluation
--- executed against a real website without manual intervention". Câu này
mạnh hơn O2: nó khẳng định khâu ghép chuỗi operator **đã chạy đầu–cuối trên
site thật**, trong khi `all_chains` trả về rỗng suốt cả 12 run nên không có
chuỗi nào được ghép. Khâu induction operator thì có chạy thật; khâu *chaining*
thì không sinh ra gì. Nếu run mới vẫn 0 goal task, phải sửa câu này cùng lúc
với O2 (bản VI: câu "mọi công đoạn --- khám phá, phát hiện, ghép chuỗi
operator, ... --- đều chạy..." ở cùng mục). Cố ý CHƯA sửa để giữ đúng quyết
định "chờ kết quả run mới" của user.

**Quyết định của user (2026-07-20):** tạm gác, **sẽ chạy lại thực nghiệm
sau**. Giữ nguyên câu chữ hiện tại chờ kết quả run mới. ⚠️ **Nếu run mới
vẫn không sinh được semantic task thì BẮT BUỘC sửa O2 ở C1/C6** thành
"cài đặt + kiểm chứng trên mock, chưa kích hoạt được trên run thật", báo
cáo 0 GOAL episode ở C4, và viết mục C5 phân tích operator graph rỗng cạnh
như một kết quả âm có giá trị. Không được để "Achieved" nếu số liệu không
đỡ được.

## Trạng thái viết (cập nhật 2026-07-17)

Bản LaTeX sống ở **`Thesis_report/thesis_hsge/`** (fork từ template, tiếng
Anh, lề đúng quy định Khoa, biblatex style=ieee, build sạch 43 trang):
- ✅ **Chapter 3 (Method)**: đã viết trọn bản nháp đầu (8 mục, hình pipeline
  TikZ, bảng action space, Algorithm frontier loop, bảng module).
- ✅ **Chapter 5 (Discussion)**: đã viết trọn bản nháp đầu (7 mục, format
  problem→diagnosis→fix→lesson; 5.1 interpret kết quả có TODO refresh khi có
  thêm site; bảng best practices 10 dòng; threats to validity 3 loại).
- ✅ **Chapter 1 (Introduction)**: đã viết trọn (hook developer/issue-tracker,
  problem statement dạng Given/Produce/Without, 5 challenges ↔ 5 objectives
  O1–O5, bảng contributions "existing vs ours", scope 4 site, hình roadmap
  Big Picture gắn số chương). Số liệu WebArena 14%/78% có TODO(verify).
- ✅ **Chapter 6 (Conclusion)**: đã viết trọn (5 artifacts, bảng O1–O5 vs
  outcomes — O4 ghi "in progress" cho 3 site còn lại, 5 hướng future work,
  closing message). Có TODO cập nhật khi có kết quả 4 site.
- ✅ Front matter: title (bìa tạm — chờ chốt tên tiếng Anh), acknowledgments,
  chapter summaries, glossary, **abstract đã có bản nháp đầy đủ**.
- ✅ References/references.bib: 13 entry nền (một số đánh dấu VERIFY).
- ✅ **Chapter 2 (Related Work)**: đã viết trọn (6 mục; mỗi công trình có câu
  critique "However"; bảng positioning 11 hệ thống × 5 trục với ký hiệu
  wasysym \CIRCLE/\LEFTcircle). ~20 paper mới được verify qua web search
  (WebArena số liệu 14.41%/78.24% xác nhận đúng; đối thủ gần nhất:
  **Go-Browse** — Gandhi & Neubig ICLR 2026, graph-of-pages, 21.7% WebArena
  7B — phân biệt bằng two-level graph + semantic task; SkillWeaver/ASI cho
  mảng skill; NNetNav/OS-Genesis/PAE/InSTA/Synatra/AgentTrek cho data-gen;
  WebRL/WebAgent-R1/WebEvolver cho RL/world-model; AutoWebGLM + NVIDIA
  position paper cho SLM). Một số entry trong references.bib còn note
  `VERIFY` (author list đầy đủ / venue cuối) — agent verify đang chạy,
  vá xong thì xóa note.
- ✅ **Chapter 4 (Thực nghiệm) — đã viết trọn bản VI (2026-08-11)**, dựa trên
  đợt đánh giá 4 domain hoàn tất: **136/655 = 20,8%** (shopping 53/187 = 28,3%,
  reddit 22/106 = 20,8%, gitlab 33/180 = 18,3%, shopping_admin 28/182 = 15,4%;
  0 task lỗi, mẫu số đầy đủ). 7 mục theo đúng dàn ý bên dưới; 4.5 (lặp thống kê)
  và 4.6 (ablation) **giữ nguyên trạng thái chưa làm**, viết rõ thiếu gì thay vì
  bỏ trống. Bảng so sánh 4.8 **tính lại** số của Go-Browse/NNetNav theo trọng số
  đúng 4 website (Go-Browse-7B 22,6%, NNetNav-7B 19,1%, GPT-4o-mini 20,0%,
  Qwen-2.5-7B nền 8,3%) — KHÔNG so trực tiếp với con số 812-task của họ.
  Build sạch 142 trang.
  ✅ **Chương 5 và 6 đã cập nhật đồng bộ (2026-08-11)**: §5.1 viết lại thành 3
  tiểu mục (con số chứng minh gì / cái gì đang chặn — bảng liên-website bác bỏ
  "thêm dữ liệu cho site nào thì site đó khá lên", và bảng lỗi chỉ vào lớp thực
  thi / rút lại câu "operator chaining đã chạy đầu–cuối"); thêm §5.4.3 (hai cổng
  operator là cần nhưng chưa đủ) và một tiểu mục §5.5 về lỗi mà judge về mặt cấu
  trúc không thể thấy; §5.5 mục đánh giá song song viết lại theo cách chia 4 máy
  thật; §5.7 thêm 3 sai lệch + biến gây nhiễu mô hình dạy; bảng best practice
  +3 dòng. C6: số liệu, O1/O2/O4, bảng mục tiêu chuyển thành `longtable`,
  hướng phát triển xếp lại ưu tiên.
  ➕ **Phát sinh: đã bổ sung §3.5 tiểu mục "Seed năng lực website"** — cơ chế này
  TRƯỚC ĐÓ KHÔNG ĐƯỢC MÔ TẢ Ở ĐÂU trong quyển, dù C4/C5 quy 57/63 lượt goal task
  cho nó; đồng thời sửa 2 chỗ nói judge chấm "ngoại tuyến" thành chấm inline.
  ⚠️ **Còn lại chưa sửa**: `Appendix/decuongchitiet.tex` mục 2.3.3 (370 mẫu,
  10/180 vs 12/180, "0 semantic task") — đề cương có HAI bản phải sửa đồng bộ,
  và nó là **bản đã nộp Khoa**, nên cần user quyết có sửa hay không.
  ⚠️ **Bản EN `thesis_hsge/Chapter4` chưa được viết lại** — vẫn là skeleton.
  ⚠️ **Về O2**: run mới ĐÃ sinh được task GOAL thật (66 task, 25 thành công) —
  nhưng 57/63 lượt là từ **seed năng lực website**, chỉ 6 lượt từ **chuỗi
  operator**, và 2/4 website không hình thành được chuỗi nào.
- ✅ **Đề cương chi tiết (2026-07-20)**: checklist nộp cuốn của Khoa
  (`KLTN/Quy trình nộp đề tài tốt nghiệp từ năm 2025.docx`) bắt buộc có mục
  này **giữa Lời cảm ơn và Mục lục** — báo cáo trước đó thiếu hẳn. Nay ở
  `thesis_hsge_vi/Appendix/decuongchitiet.tex` (**chỉ bản VI**; đề cương là
  biểu mẫu hành chính nên luôn tiếng Việt). File cũ tên `decuong.tex` thực ra
  là "Tóm lược nội dung các chương" → đã đổi tên thành `tomluoc.tex`.
  `glossary` chuyển từ trước Mục lục sang **sau** Mục lục cho đúng checklist.
  - **Có HAI bản đề cương phải giữ đồng bộ** (2026-07-20):
    1. `thesis_hsge_vi/Appendix/decuongchitiet.tex` — bản nằm trong quyển.
    2. `DeCuongKhoaLuan/decuong_webagent.tex` — bản độc lập để **in nộp thầy ký**.
    Cùng nội dung, khác quy ước trình bày: bản trong quyển dùng `\section*`
    đánh số tay (vì `\chapter*` làm section tự động thành "0.1"); bản độc lập
    là `article` + `titlesec` nên dùng `\section` tự đánh số. Bản độc lập có
    `thebibliography` viết tay 15 mục; bản trong quyển `\cite` thẳng vào
    bibliography chung của quyển, không in danh sách riêng.
    **Sửa nội dung một bản thì phải sửa bản kia.**
  - ⚠️ `[T826_KL_CNPM04]_DeCuong_06042026.pdf` ở gốc `Thesis_report/` là
    **bản đã nộp Khoa 06/04/2026** — trước 2026-07-20 nó MD5 trùng
    `DeCuongKhoaLuan/decuong_webagent.pdf`, giờ thì không còn trùng nữa vì
    bản `DeCuongKhoaLuan/` đã được cập nhật. File PDF ở gốc là ảnh chụp
    nguyên trạng bản đã nộp, **đừng ghi đè**. Nội dung cũ của nó mô tả một
    đề tài **khác hẳn** (pipeline 5 phase trên browser-use, benchmark
    Mind2Web, schema (s,o,a,v), xác thực L1/L2/L3 + đồng thuận 2 tác nhân,
    QLoRA + DPO trên Qwen2.5-1.5B/3B) — đừng lấy làm nguồn sự thật.
  - ⚠️ **Tên đề tài đã thống nhất lại** thành tên đầy đủ của đề cương:
    *"Xây dựng dữ liệu và tinh chỉnh mô hình ngôn ngữ nhỏ cho tác nhân trí tuệ
    nhân tạo trên web"* / *"Data Construction and Fine-tuning of Small Language
    Models for Web AI Agents"*, sửa ở **4 chỗ** (`\tenKL` của cả hai bản +
    `Title/title.tex` của cả hai bản). Trước đó bìa tự rút gọn mất vế "Xây dựng
    dữ liệu và tinh chỉnh" → lệch hồ sơ Khoa. Giữ tên này thì **không cần Đơn
    xác nhận đổi tên**; đổi sang tên khác thì bắt buộc phải có, GVHD ký.
  - Mục 2.3.3 của đề cương **đã nói thẳng 0 semantic task chạy được** và ghi rõ
    cặp GitLab 10/180→12/180 là n=1. Nếu run mới đổi kết quả thì đây là **chỗ
    thứ tư** phải sửa đồng bộ cùng O2 ở C1/C6 và câu §5.1 (xem cảnh báo đầu file).
  - ⚠️ **Sau bảo vệ** checklist đòi đề cương **có chữ ký GVHD** = bản scan.
    `main.tex` gọi `decuongchitiet.tex` bằng đúng 1 dòng → lúc đó chỉ cần thay
    ruột file này bằng `\includepdf` bản scan.
  - Bẫy LaTeX gặp phải: `\caption*` **không dùng được** trong float `table` vì
    package `float` phá nó (vẫn để lại mục rỗng `*` trong Danh sách bảng) → bỏ
    float, dùng `minipage` (cũng cần để tiêu đề không rời khỏi bảng qua ranh
    giới trang). `\multicolumn{2}{c}{...}` **không xuống dòng được** → phải
    dùng `C{...}`. VI 94→108 trang.

- ✅ **Phụ lục A–D (2026-07-20)**: đã viết trọn cả hai bản, thay 4
  placeholder. A = bản đồ 26 module (longtable, tự ngắt trang) + lược đồ dữ
  liệu + lớp tách backend + cấu hình model theo vai trò + tham số chạy;
  B = 7 prompt nguyên văn lấy thẳng từ source (giữ tiếng Anh ở cả bản VI vì
  đó là văn bản chạy thật), mỗi prompt kèm một câu nói rõ nó sửa lỗi hành vi
  nào; C = thống kê 12 run (301 node, 1174 episode, 827/330/48 task, 37
  skill, 35 operator) + bảng theo loại task run 4–6 (INFO 86% / NAV 72% /
  MOD 73%) + **mục C.3 báo cáo trung thực 0 goal task** (xem cảnh báo đầu
  file); D = hướng dẫn tái lập. EN 74→89 trang, VI 78→93 trang, build sạch.
  ⚠️ Mục C.4 (kết quả 180 task/site) vẫn là `[Sẽ bổ sung]` — chờ thực nghiệm.

**Bản tiếng Việt song song** (user yêu cầu 2026-07-18): sống ở
`Thesis_report/thesis_hsge_vi/` — dịch trọn C1/C2/C3/C5/C6 + front matter,
C4 khung; giữ nguyên thuật ngữ chuyên ngành tiếng Anh; có **Bảng chú thích
thuật ngữ** (28 thuật ngữ Anh → giải nghĩa Việt) + bảng viết tắt trong
`Appendix/glossary.tex`; caption Việt hóa lại (Chương/Hình/Bảng); build
sạch 77 trang. ⚠️ Khi sửa nội dung một bản, nhớ sửa bản kia tương ứng
(hai bản chia sẻ cùng references.bib nội dung nhưng là 2 file riêng).
Lưu ý build: log chứa ký tự Việt → grep cần cờ `-a`; chuỗi tt dài dùng
`\slash` để bẻ dòng.

**Sơ đồ (2026-07-19, bản cuối = Excalidraw)**: 5 sơ đồ Chương 3 đã được vẽ
lại bằng **Excalidraw** (theme màu, roughness 0, đẹp hơn draw.io) sau khi
user thấy draw.io còn đơn giản. Nguồn: `Thesis_report/.excalidraw-tmp/`
(git-ignored) — `build.py` (builder Python: tự lo bindings/seeds/tọa độ,
tính height label theo số dòng để không chồng chữ) + `diagrams.py` (định
nghĩa 5 hình + bảng text EN/VI, chạy `python3 diagrams.py en|vi`). Export:
Kroki API (`curl POST kroki.io/excalidraw/svg`) → SVG → `rsvg-convert -f pdf`
→ PDF vector ở `<edition>/Figures/*.pdf`. Màu semantic: process xanh dương,
operator/thành công xanh lá, decision vàng, loại-bỏ đỏ, semantic-task vàng
nổi bật, start cam. Width trong LaTeX: twolevel 0.95, semantic 0.78, solver
1.0, discovery 0.48, curation 0.50 \\textwidth (đã chỉnh theo tỉ lệ
excalidraw). Excalidraw KHÔNG xuất PDF trực tiếp — phải qua SVG. Font là
Helvetica (không phải Times như body) — chấp nhận đánh đổi để đẹp hơn.
(Lịch sử trước đó: từng vẽ bằng draw.io theme academic rồi tô màu tech-blue;
đã thay hết bằng Excalidraw.)
- **`fig_frontier` (§3.3 quản lý frontier) — hình thứ 8, thêm 2026-07-20.**
  Mẫu convergence với **cổng bất đối xứng**: tier 0 (URL solver đã đi tới) vào
  thẳng hàng đợi, tier 1 (href khai thác) phải qua trần theo template — cổng
  chỉ nằm trên MỘT trong hai cạnh vào, đó chính là lập luận. Hàng đợi vẽ dạng
  các ô có thứ tự, tier 0 nằm trên tier 1. Đã chèn §3.3 cả hai bản kèm
  `\ref{fig:frontier}`. EN 90tr / VI 94tr.
  **Kết luận về "có thêm hình nữa không": KHÔNG.** C2 đã có bảng positioning;
  C5 là văn xuôi vấn đề→chẩn đoán→sửa + bảng best practices; C6 là kết luận.
  Biểu đồ kết quả C4 thì muốn nhưng **bị chặn bởi dữ liệu** — vẽ cột cho một
  cặp n=1 (10/180 vs 12/180) là thổi phồng bằng đồ họa, đúng lỗi P0-1; đợi đủ
  4 site + lặp thống kê rồi vẽ kèm thanh sai số.
- `fig_twolevel` (§3.2 graph hai tầng), `fig_solver` (§3.3 vòng lặp solver),
  `fig_discovery` (§3.4 phát hiện skill), `fig_semantic` (§3.5 sinh semantic
  task — hình "đắt" nhất), `fig_curation` (§3.6 tinh lọc dữ liệu).
- Nguồn YAML ở `Thesis_report/.drawio-tmp/*.yaml` (git-ignored); PDF ở
  `<edition>/Figures/`. Bản EN và VI có YAML/PDF riêng (label dịch).
- **Màu (2026-07-20, BẢN CUỐI)**: đã đổi sang **palette của skill
  `excalidraw-diagram`** (`references/color-palette.md`) trong `build.py::PAL`,
  giữ nguyên ngữ nghĩa cũ: `process` #93c5fd (bước thường), `primary` #60a5fa
  (bước nhấn), **`llm`/`external` #ddd6fe viền #6d28d9 (vai trò LLM/AI)**,
  `success` #a7f3d0, `decision` #fef3c7, `error` #fecaca, `trigger` #fed7aa,
  `neutral` #dbeafe. Chữ trong hộp #374151, chữ chú thích #64748b. Đậm hơn bản
  cũ. Hộp LLM trong fig_solver đã chuyển từ `primary` sang `llm` cho đúng nghĩa.
- (lịch sử) **Màu (2026-07-19)**: đổi theme `academic` (đen trắng) → `tech-blue` (có
  màu) + style override theo nghĩa: xanh lá = output/thành công (Skill
  library, SFT dataset, Episode end, operator); đỏ = loại bỏ (Discarded,
  Dropped); vàng = decision (auto) + semantic-task output nổi bật; xanh dương
  = process/skill. Sửa 5 file EN rồi chạy lại script dịch để lan sang VI.
- **Hình 3.1 (pipeline overview)**: đã vẽ lại bằng Excalidraw (hàm
  `pipeline()` trong diagrams.py) và thay khối TikZ trong cả hai bản
  (2026-07-20). Giờ CẢ 6 hình Chương 3 đều là Excalidraw.
- **Hình 1.1 (roadmap Chương 1)**: đã vẽ lại bằng Excalidraw (hàm
  `roadmap()`, 2026-07-20). **Không còn TikZ picture nào trong cả hai bản.**
- **⚠️ BẪY LỚN NHẤT của Excalidraw (phát hiện 2026-07-20)**: **không bao giờ
  gắn nhãn vào mũi tên** bằng `containerId` (bound label). Excalidraw chừa một
  khoảng trống dọc mũi tên bằng đúng bounding box của nhãn; nhãn ở đây rộng
  ~100–140px trong khi mũi tên chỉ dài 50–98px, nên khoảng trống nuốt trọn
  thân mũi tên và bản xuất ra **chỉ còn trơ đầu mũi tên**. Cả 7 hình trong
  quyển đã dính lỗi này mà không ai phát hiện (hình càng nhiều nhãn càng hỏng
  nặng: fig_semantic mất cả 3/3 mũi tên). `build.py::Scene.arrow()` giờ đẩy
  nhãn thành text trôi cạnh mũi tên (`Scene.alabel()`). Quy tắc rút ra: **luôn
  render PNG và soi bằng mắt sau mỗi lần sinh hình** — lỗi này vô hình trong
  JSON, chỉ hiện ra khi nhìn ảnh.
- **`Scene.line(pts, head=False)`** (thêm 2026-07-20): polyline không bind, để
  vẽ đường cấu trúc (trục gom, nhánh cây, timeline) — `arrow()` bắt buộc bind
  hai đầu vào shape nên không dùng được cho các đường này.
- **Cả 7 hình đã qua vòng render-soi-sửa (2026-07-20)**, theo phương pháp luận
  skill `excalidraw-diagram`. Giữ bảng màu semantic của dự án (skill nói palette
  là phần để tùy biến theo brand; 7 hình phải đồng bộ nhau).
  `fig_solver` vẽ lại thành **cycle** (cũ là một hàng 1670×380, tỉ lệ 4,4:1 →
  chữ chỉ ~4pt ở `\textwidth`, và đường thẳng nói sai cơ chế: solver là vòng
  lặp có hai cửa thoát); `fig_pipeline` thêm 2 zone + nắn đường `episodes`;
  `fig_curation` thêm chú thích nội dung §3.6 vào chỗ trống bên phải.
  **`fig_roadmap` cố ý giữ nguyên** — 5 chặng trái→phải đúng chức năng roadmap
  C1, cỡ chữ đã chỉnh, không có lỗi; đổi sang timeline chỉ là restyling.
- **fig_semantic đã vẽ lại (2026-07-20)** theo mẫu *convergence*. Bản cũ vẽ mũi
  tên "chain" đi ra từ RIÊNG operator B → đọc thành "B sinh ra semantic task",
  **sai cơ chế** (task sinh từ cả chuỗi A→B→C). Bản mới: 3 operator đổ vào một
  trục gom, trục gom hội tụ vào hộp task (hero). Chưa soi bằng mắt:
  `fig_solver`, `fig_pipeline`, `fig_curation`, `fig_roadmap`.
- **Export qua Kroki — bẫy quan trọng**: phải gửi `Content-Type: text/plain`.
  Nếu gửi `application/json`, Kroki hiểu body là envelope JSON của nó và báo
  lỗi 400 "Field diagram_source must not be empty".
  Lệnh: `curl -s -X POST -H "Content-Type: text/plain" --data-binary
  @fig_x_en.excalidraw https://kroki.io/excalidraw/svg -o fig_x_en.svg`
  rồi `rsvg-convert -f pdf -o <edition>/Figures/fig_x.pdf fig_x_en.svg`.
- **Cỡ chữ trong hình**: canvas Excalidraw bị scale xuống `\textwidth`
  (~411pt), nên `fontSize` px hiển thị ra pt rất nhỏ. Quy tắc:
  `pt ≈ fontSize_px × 411 / (chiều rộng canvas px)`. Nhắm ~7,5–9pt (nhỏ hơn
  body 13pt nhưng còn đọc được); hình roadmap phải để fontsize 22px mới đạt
  ~7,5pt. Luôn render thử trang PDF ra PNG để kiểm tra trước khi chốt.
- **Cảnh báo build có sẵn từ trước**: cả hai bản in "LaTeX Warning: There were
  undefined references" nhưng **mọi `\ref` và `\cite` đều resolve** (đã đối
  chiếu key trong .tex với `\newlabel` trong .aux và với references.bib —
  không thiếu cái nào). Nguyên nhân là bookkeeping của biblatex
  `defernumbers=true`, vô hại. Đừng mất thời gian truy lại.
- **Cách chạy skill drawio** (nếu cần vẽ thêm): cần cài `js-yaml@4.1.0` vào
  `~/.agents/skills/drawio/node_modules` (v5 lỗi default export); font phải
  khai đủ `primary/cjk/formula`; nhãn nhiều dòng dùng `\n` (KHÔNG dùng `<br>`
  — bị nhầm là math HTML); nhãn ngắn, chi tiết đưa vào `\caption`; decision
  (hình thoi) giữ nhãn cực ngắn kẻo tràn. Render: `node
  ~/.claude/skills/drawio/scripts/cli.js in.yaml out.pdf --validate
  --use-desktop`.
- Build: `pdflatex → bibtex → pdflatex ×2` từ trong thesis_hsge/ (main.tex).
  ⚠️ Sau khi THÊM citation mới phải chạy đủ chu trình sạch (rm aux/bbl →
  4 lệnh trên), nếu không sẽ dính đúng lỗi "reference [0]" mà review mẫu
  từng bắt (P0-6) — đã gặp và fix khi viết C1.
- TikZ: không đặt tên style là `step` (key có sẵn của TikZ, gây lỗi
  pgfkeys) — dùng `stage`.
- Lưu ý khi viết C5 đã đổi 3 tiêu đề mục cho khỏi tràn dòng: 5.2 "Lessons
  from Exploring Live Websites", 5.3 "Structural Guardrails over Prompt
  Nudges", 5.4 "Lessons from Operator Induction".

Đề tài: **Small Language Models for Web AI Agents** (tên tiếng Anh đề xuất,
chờ chốt) — "Mô hình ngôn ngữ nhỏ cho tác nhân trí tuệ nhân tạo trên web".
Báo cáo viết **tiếng Anh**. Cấu trúc **6 chương** (Intro / Related Work /
Method / Experiments / Discussion / Conclusion) — chọn 6 thay vì 5 vì user
muốn nhấn mạnh Discussion thành chương riêng; ⚠️ cần xác nhận với thầy Vũ.

Trọng tâm theo yêu cầu user: **Chương 3 (Method), Chương 5 (Discussion),
Chương 6 (Conclusion)** viết đậm; Chương 4 dựng khung trước, các mục đánh dấu
`[TO ADD]` sẽ bổ sung khi có thực nghiệm mới (~25 ngày tới).

Narrative xuyên suốt (nhắc lại ở Abstract, C1, C6): *LLM lớn làm web agent tốt
nhưng đắt; SLM rẻ nhưng yếu vì thiếu dữ liệu huấn luyện chất lượng; chúng tôi
xây pipeline khám phá website dựa trên GRAPH — từ các LOW-LEVEL TASK theo trang
tích lũy thành skill/operator graph, rồi compose graph đó thành các SEMANTIC
TASK dài hạn đã kiểm chứng — tạo dataset SFT, và cho thấy SLM 9B được
fine-tune cải thiện trên benchmark WebArena chính thức.*

**Thuật ngữ chốt (user, 2026-07-17)** — dùng nhất quán toàn báo cáo:
- **Low-level task**: task theo trang do PageExplorer (LLM) đề xuất khi khám
  phá (INFO/NAV/MOD) — nguyên liệu để thu trajectory và phát hiện skill,
  KHÔNG gọi đây là semantic task.
- **Semantic task**: task được **sinh từ Operator Graph** — chain ≥2 operator
  (effect→precondition) compose thành goal task dài hạn, có ngữ nghĩa, có
  instruction sinh tự động và có cơ chế verify. Đây là đóng góp trung tâm.

---

## Front matter

- Title page / phụ bìa theo mẫu Khoa (hỏi giáo vụ về bìa tiếng Anh/song ngữ).
- Acknowledgments; Glossary & abbreviations (SLM, LLM, SFT, LoRA, HSGE, axtree,
  MDP, option, operator, WebArena, BrowserGym... — dùng script glossary có sẵn).
- Chapter summaries (decuong); ToC; List of Figures/Tables.
- **Abstract** (100–300 từ, 5 phần theo slide thầy Vũ): context/problem 1–2 câu
  → objective 1 câu → method 1–2 câu → results 1–2 câu (hedge đúng mức, xem 05)
  → conclusion 1–2 câu.

## Chapter 1 — Introduction (~8–10 trang)

Roadmap đánh số đầu chương; transition cuối chương (áp dụng cho MỌI chương).

- **1.1 Context and motivation** — hook thực tế (một tác vụ web lặp lại: tạo
  issue GitLab, quản lý repo...); web agent là gì; hiện trạng: agent chạy trên
  LLM proprietary lớn → chi phí API, độ trễ, privacy, không tự chủ; SLM
  (≤~10B, chạy local) là hướng thay thế nhưng success rate thấp. Dẫn chứng
  bằng số liệu có kiểm chứng (WebArena: human ~78% vs GPT-4 ~14% — verify số
  từ paper gốc; giá API vs self-host). KHÔNG nêu số kết quả của đề tài ở đây.
- **1.2 Problem statement** — Input: một website không có annotation + một SLM
  pretrained. Output: SLM đã fine-tune hoàn thành task ngôn ngữ tự nhiên trên
  site đó. Formal hóa: web env như (PO)MDP (observation = accessibility tree,
  action space click/fill/goto...); bài toán con trọng tâm: **tự động sinh
  cặp (goal, trajectory) chất lượng cao không cần người gán nhãn**. Tiêu chí
  đánh giá: task success rate trên benchmark WebArena (evaluator chính thức).
- **1.3 Challenges** — (i) exploration trên site thật: bùng nổ trạng thái,
  trang trùng lặp, side effects; (ii) sinh task **có ngữ nghĩa** thay vì click
  ngẫu nhiên; (iii) kiểm chứng chất lượng trajectory (agent tự chấm bài mình);
  (iv) task dài hạn cần compose nhiều kỹ năng; (v) giới hạn của SLM.
- **1.4 Objectives and contributions** — liệt kê khớp chuỗi thách thức:
  (1) pipeline khám phá dựa trên **two-level graph** (skill → operator →
  chained goal task); (2) cơ chế sinh task hai tầng — **low-level task** (LLM
  đề xuất theo trang) nuôi exploration, **semantic task** (compose từ operator
  graph) tạo dữ liệu dài hạn — kèm kiểm chứng (judge, thought reannotation);
  (3) dataset SFT + SLM Qwen3.5-9B
  fine-tuned; (4) đánh giá trên WebArena GitLab chính thức; (5) báo cáo kinh
  nghiệm & best practices vận hành agent trên site thật. Contribution box:
  phân tách rõ cái có sẵn (WebArena, BrowserGym, LLaMA-Factory, Qwen) vs. cái
  đề tài tạo ra.
- **1.5 Scope** — môi trường WebArena self-host; **đánh giá trên 4 site:
  Shopping, Shopping Admin, GitLab, Reddit** (GitLab đã có kết quả, 3 site còn
  lại bổ sung sau); SFT/LoRA (không RL); SLM cỡ 9B; tiếng Anh; không xử lý
  CAPTCHA/login ngoài phạm vi benchmark (login dùng cached session chuẩn).
- **1.6 Thesis organization** — kèm **hình Big Picture** (pipeline tổng quan
  từ website → graph exploration → semantic tasks → dataset → SLM → eval).

## Chapter 2 — Background and Related Work (~10 trang)

Mỗi mục: gom theo chủ đề, cũ → mới, mỗi công trình 2–4 câu, **kết bằng câu
critique** ("However, ...") — tránh lỗi "giống khảo sát tài liệu".

- **2.1 Background** — web agent formulation (obs/action space, axtree);
  benchmark & môi trường: WebArena, BrowserGym; agent loop kiểu
  ReAct/CoT; SFT & LoRA (ngắn gọn, đủ để C3.7 đứng được).
- **2.2 LLM-based web agents** — các agent trên WebArena và tương tự (baseline
  gốc, các phương pháp prompting/planning). *However*: phụ thuộc LLM lớn
  proprietary, chi phí cao, không cải thiện được model.
- **2.3 Skill/workflow discovery and memory for agents** — options framework
  ⟨I, π, β⟩; Agent Workflow Memory (AWM) và các hướng induce workflow/skill.
  *However*: memory phẳng, skill không được verify, không compose có cấu trúc.
- **2.4 Automatic data generation for agent training** — các pipeline sinh
  instruction/trajectory cho web agent (khảo sát & verify citation: NNetNav,
  OS-Genesis, Synatra... — PHẢI verify từng paper theo quy trình 04). *However*:
  exploration phẳng/ngẫu nhiên → task nông, ít kiểm chứng chất lượng.
- **2.5 Small language models as agents / distillation** — xu hướng SLM agent,
  distill từ model lớn. *However*: nghẽn ở chất lượng dữ liệu, không phải
  thuật toán train.
- **2.6 Positioning** — bảng so sánh các trục: exploration có cấu trúc graph?
  task có verify? có compose dài hạn? train SLM? → khoảng trống mà HSGE lấp.
- Nguồn: paper WebArena, BrowserGym, AWM; SOTA 2024–2026 qua web search.
  (Đã kiểm tra 2026-07-17: 2 PDF trong thesis_v3 — 2507.17128v2,
  2510.02585v1 — đều là paper autoscaling của đề tài mẫu, KHÔNG liên quan.)

## Chapter 3 — Proposed Method (~18–22 trang) ★ TRỌNG TÂM

Nguồn chính: `.claude/rules/architecture.md`, `docs/superpowers/specs/*`,
`hsge/` source. Quy tắc: sơ đồ + diễn giải từng thành phần; thuật toán = mã
giả; hạn chế code thật; link repo để footnote.

- **3.1 Overview** — nhắc lại problem setup; **kiến trúc tổng quan** (hình):
  Exploration loop → Skill discovery → Operator graph → Goal-task generation →
  Data curation → SFT. Ba design principles: (P1) *verify trước khi tái sử
  dụng* (skill/task/trajectory đều qua cổng kiểm chứng); (P2) *graph thay vì
  flat* (hai tầng: trang–trạng thái & kỹ năng–operator); (P3) *task hai tầng*:
  low-level task (LLM đề xuất theo trang) để khám phá và thu skill; semantic
  task (compose từ operator graph) để tạo dữ liệu dài hạn có ngữ nghĩa.
- **3.2 Two-level graph formalism** — định nghĩa & ký hiệu: low-level graph
  (page states + trajectory edges); high-level graph (skill = option ⟨I, π, β⟩,
  initiation/effect edges, skill→skill composition edges); operator =
  ⟨preconditions, effects⟩ trên NL predicates được chuẩn hóa embedding;
  terminal predicate. Đây là phần "GRAPH" của câu chuyện — viết kỹ.
- **3.3 Graph-guided exploration** —
  - Frontier: priority queue 2 tier (tier 0 = URL agent thực sự đi tới;
    tier 1 = href mining) + **URL templating** với per-template cap (chống
    flood trang trùng dạng) + content dedup bằng axtree hash. Mã giả frontier
    loop. Lý do thiết kế: frontier starvation từ run thật (kể ở C5).
  - **Low-level task proposal** (PageExplorer): LLM đề xuất task cụ thể theo
    trang, phân loại cấu trúc INFO/NAV/MOD, negative context + dedup sitewide,
    read-only mode, thứ tự cắt (INFO bị cắt trước). Nêu rõ vì sao task
    LLM-proposed ≠ random walk, nhưng cũng nói rõ giới hạn: đây mới là task
    theo trang, ngắn hạn — nguyên liệu cho skill discovery, chưa phải
    semantic task (được sinh ở 3.5).
  - **Solver**: action space 10 hành động, history có outcome, phát hiện kẹt
    (same-target + no-progress → warn → hard stop), wrap-up call, infeasible
    là kết cục hạng nhất. Mã giả solve loop.
- **3.4 Skill discovery pipeline** — segmentation (cut = URL change + axtree
  similarity drop, LLM arbitration, merge nav 1-step); streaming clustering
  (cosine-threshold/DP-means, không cần biết trước số cluster); abstraction
  (cluster → parameterized SkillCard); verification (admit khi ≥k lần thành
  công ở ngữ cảnh held-out). Mỗi bước 1 hình nhỏ hoặc 1 ví dụ chạy thật.
- **3.5 From skills to operators and composed goal tasks** — operator
  induction bằng LLM (vocabulary-aware để tái dùng predicate, anti-tautology
  gate `eff − pre`); predicate registry (canonical id, threshold, vì sao
  embedding-only thất bại — số liệu 0.570/0.606 từ wa_run_09); BFS planning;
  **operator chaining** (`all_chains` DFS bounded) → mỗi chain ≥2 operator
  thành 1 composed GOAL task với instruction sinh tự động — **đây chính là
  SEMANTIC TASK** theo định nghĩa của đề tài (mục trọng tâm nhất của C3, đặt
  tiêu đề mục nêu bật điều đó, vd "Semantic task generation via operator
  chaining"). Verify: deterministic khi có terminal predicate, self-graded +
  offline judge khi không.
- **3.6 Data curation for SFT** — 3 pass offline: judge (LLM re-verify các
  episode tự nhận thành công); thought reannotation (state/reflection/subgoal/
  completion-check, replay segmentation offline; subgoal chỉ ở target, không ở
  prompt — tránh train/serve mismatch); dataset builder (**prompt parity** với
  Solver thật: cùng SYSTEM, cùng axtree cap, cùng outcome-annotated history;
  loại step lỗi; giữ infeasible; curriculum ordering; metadata trajectory).
  Nhấn mạnh nguyên tắc: *dữ liệu train nhìn thấy đúng cái model sẽ thấy lúc
  inference*.
- **3.7 SLM fine-tuning and serving** — LoRA trên Qwen3.5-9B (LLaMA-Factory,
  template nothink — lý do: data không có <think>), split theo trajectory
  (chống leak), merge + vLLM serving, tắt thinking khi inference.
- **3.8 Implementation** — bảng module ↔ vai trò; seam mock/real backend
  (giá trị: test deterministic không cần API); per-role LLM routing. Ngắn gọn,
  chi tiết đẩy xuống Appendix A.

## Chapter 4 — Experiments (~8 trang khung, sẽ nở ra) — bổ sung sau

- **4.1 Experimental setup** — môi trường: WebArena self-host (GitLab qua
  tunnel), vast.ai A100-80GB; model theo role (bảng từ config.yaml); tham số
  run (max_nodes/steps/tasks, maturity...); công cụ đánh giá: BrowserGym
  scored envs + evaluator chính thức, replay terminal action.
- **4.2 Data collection results** — số liệu các run (wa_run_02/07/09/12):
  nodes, tasks proposed/solved/infeasible, skills admitted, operators, chains;
  dataset cuối: 370 examples (352 train / 18 val). Bảng + 1–2 ví dụ semantic
  task/skill tiêu biểu.
- **4.3 Fine-tuning results** — loss (0.32 train / 0.24 eval), thời gian/chi
  phí (bảng từ docs/14).
- **4.4 Main evaluation: official WebArena, 4 sites** — đánh giá trên
  **Shopping, Shopping Admin, GitLab, Reddit** (bảng kết quả per-site + tổng).
  Protocol chung (kể cả two-machine read/write split + reset giữa sweep).
  Hiện có: **GitLab** baseline 10/180 (5.56%) vs finetuned 12/180 (6.67%),
  +1.1pp (~20% relative); **[TO ADD]** kết quả Shopping / Shopping Admin /
  Reddit. **Trình bày là tín hiệu định hướng** — hedge theo 05/P0-1, ghi rõ
  n=1 (chừng nào chưa có 4.5).
- **4.5 [TO ADD] Statistical repeats** — chạy lặp ≥3–5 lần (hoặc nhiều seed)
  cho baseline & finetuned → mean ± SD, 95% CI, test phi tham số. Ưu tiên #1.
- **4.6 [TO ADD] Ablations** — (a) **graph-explore data vs. flat-explore
  data** (cùng budget LLM/episode — thực nghiệm "đinh" chứng minh giá trị
  pipeline); (b) có/không judge pass; (c) có/không thought reannotation;
  (d) phân tích cross-site từ kết quả 4 site (train data từ site nào giúp
  site nào — thay cho ablation "site thứ hai" cũ).
- **4.7 Analysis** — breakdown theo loại task, ví dụ thành công/thất bại định
  tính, failure taxonomy (nối sang C5).

## Chapter 5 — Discussion (~10–12 trang) ★ TRỌNG TÂM

Dạng "báo cáo kinh nghiệm + best practice" — mỏ tư liệu: docs/10–14,
`.claude/memory/bugs.md`, changelog. Mỗi mục: vấn đề gặp thật → chẩn đoán →
giải pháp → bài học khái quát. Chi tiết dài đẩy xuống Appendix, chương giữ ý chính.

- **5.1 Interpreting the results** — vì sao cải thiện khiêm tốn (352 examples,
  9B model, 1 site); cái pipeline thực sự đóng góp (dữ liệu có cấu trúc, có
  kiểm chứng) vs. cái chưa chứng minh được; trả lời từng RQ nếu C3 đặt RQ.
- **5.2 Exploring live websites is an engineering problem** — frontier
  starvation (run reddit dừng 57/500 nodes) → href mining + template caps;
  46% task trùng lặp → dedup + negative context; trang lỗi/timeout → node
  error resilience, fail-soft; site chia sẻ trạng thái → read-only mode,
  reset kỷ luật, cấm task xóa account.
- **5.3 LLM agents need structural guardrails, not prompt nudges** — [TAG]
  convention thất bại (89% không có bracket) → structured output; warning
  chống kẹt không đủ (model click link chết hết 15 bước) → hard stop theo
  same-target + no-progress; INFO task tự lộ đáp án; vision call rỗng → retry
  text-only. Bài học: *đo hành vi thật rồi mới thiết kế cơ chế*.
- **5.4 Verified structure beats raw scale in operator induction** — operator
  tautological (3/4 ở wa_run_09) → anti-tautology gate; embedding-only không
  gộp được synonym (0.570 < 0.6 < 0.606 false pair) → vocabulary-aware
  induction; grounding check chất lượng operator.
- **5.5 Training and serving SLMs: pitfalls** — chat template & thinking mode
  (nothink); "prompt-fidelity bug" (test prompt xấp xỉ → tưởng train hỏng);
  venv isolation (transformers@main vs vLLM pin); judge pass bắt "tự chấm bài
  mình"; prompt parity train ↔ inference.
- **5.6 Best practices (distilled)** — bảng ngắn: verify-then-admit; prompt
  parity; fail-soft mọi browser op; persist artifact mỗi node (interrupt-safe);
  two-machine eval với phân loại read/write; log mọi event ra jsonl.
- **5.7 Threats to validity & limitations** — internal (n nhỏ, n=1/task,
  LLM-judge bias), external (1 site, 1 model size), construct (success-rate
  evaluator). Trung thực nhưng ngắn — phần "hạn chế" chính thức không nằm ở
  Kết luận (theo hướng dẫn).

## Chapter 6 — Conclusion (~4–5 trang) ★ TRỌNG TÂM

- **6.1 Summary of contributions and products** — liệt kê sản phẩm cụ thể:
  (1) HSGE pipeline (mã nguồn, mock + real backend); (2) bộ semantic task +
  trajectory dataset SFT; (3) SLM Qwen3.5-9B fine-tuned; (4) kết quả benchmark
  chính thức; (5) bộ kinh nghiệm/best practices + tutorial tái lập
  (docs/14, training/README). Nhắc lại thông điệp chính.
- **6.2 Objectives vs. achievements** — bảng đối chiếu từng mục tiêu ở 1.4
  với kết quả đạt được (tập trung ưu điểm, không biện minh).
- **6.3 Future directions** — data scaling (nhiều site, transfer.py đã có
  khung); RL/DPO trên trajectory đã verify; model nhỏ hơn (≤3B); online
  skill retrieval lúc inference (hiện subgoal chỉ dùng lúc train); benchmark
  rộng hơn (WebArena full, các site ngoài benchmark).

## Appendices

- **A** — Detailed design: module map, data schema (Step/SubTrajectory/
  SkillCard/Task), per-role LLM config.
- **B** — Prompts: EXPLORER_SYS, SOLVER_SYS + ACTIONS_DOC, judge, reannotator,
  operator inducer (nguyên văn — minh bạch, khỏi chép vào thân bài).
- **C** — Run statistics chi tiết (bảng per-run, per-node), số liệu đánh giá
  đầy đủ 180 task.
- **D** — Reproducibility guide: lệnh từng bước (thu data → judge → reannotate
  → build → train → serve → eval), repo URL (footnote trong thân bài), checksum
  /release tag nếu công bố.
- **E** — (nếu cần) Nhật ký kinh nghiệm chi tiết cho C5.

---

## Việc viết theo thứ tự đề xuất

1. C3 (Method) — tư liệu sẵn 100%, viết được ngay.
2. C5 (Discussion) — tư liệu sẵn (docs 10–14, bugs.md), viết song song C3.
3. C1 + C6 (cùng narrative, viết sau khi C3/C5 định hình).
4. C2 (cần vòng đọc + verify citation).
5. C4 khung trước, điền số khi thực nghiệm bổ sung xong.
6. Front matter + Appendix cuối cùng.

Checklist mỗi chương khi viết: roadmap đầu chương, transition cuối chương,
không ký hiệu tự đặt chưa định nghĩa, mọi hình/bảng được tham chiếu, câu
<35 từ, mỗi công trình liên quan có câu critique, mọi citation đã verify.
