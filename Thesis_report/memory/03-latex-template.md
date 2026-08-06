# Template LaTeX thesis_v3 — cấu trúc & cách dùng

Nguồn: `Thesis_report/thesis_v3/` — template KLTN của trường ĐH KHTN
(gốc: nqminh@fit.hcmus.edu.vn, 2016; Overleaf chính thức của Khoa:
https://www.overleaf.com/read/ttmrfskbmcxm), đã được nhóm thesis mẫu tùy biến.
Cách tái sử dụng cho HSGE: copy thư mục, xóa nội dung chương, giữ preamble.

## Cấu trúc thư mục

```
main.tex                 # preamble + include mọi thứ
Title/title.tex          # trang bìa (TikZ)
Chapter1..Chapter6/      # mỗi chương 1 folder, 1 file chapterN.tex
Appendix/                # thanks, decuong (tóm lược các chương), glossary,
                         # tomtat (tóm tắt), appendix1..2, publish (công trình)
References/references.bib
images/, Figures/        # graphicspath trỏ cả hai
Tables/                  # bảng tách file (nhóm mẫu dùng)
scripts/                 # script Python tái tính bảng số liệu chương 4
check_acronyms.py, extract_acronyms.py, sort_glossary.py  # tiện ích glossary
```

## Preamble chính (main.tex)

- `\documentclass[oneside,a4paper,14pt]{extreport}` — font 14pt đúng quy định Khoa.
- Tiếng Việt: `[T5]{fontenc}` + `[utf8]{inputenc}` (không dùng babel/vntex ở đây).
- **Font Times New Roman**: `\usepackage{mathptmx}` (URW Nimbus Roman qua
  vntex, tương thích T5) — đã kiểm chứng hiển thị đủ dấu tiếng Việt, không
  missing glyph. Đây là cách đúng quy định Khoa (template gốc để mặc định
  Computer Modern là lệch). Áp cho cả `thesis_hsge` và `thesis_hsge_vi`
  (2026-07-18).
- **hyperref** dùng `[unicode,hidelinks]` — tắt ô màu/khung quanh trích dẫn
  và cross-ref cho bản in (không dùng `[unicode]` trơn nữa).
- Tham khảo: `biblatex` backend **bibtex**, `sorting=nty`, `defernumbers=true`;
  `\addbibresource{References/references.bib}`; in bằng
  `\printbibliography[title={Tài liệu tham khảo}]`.
- Có sẵn: listings (mã nguồn), algorithm/algpseudocode (mã giả), multirow/
  longtable + cột L/C/R tùy biến, setspace `\onehalfspacing` (dãn 1.5),
  indentfirst, `secnumdepth=3`, hyperref unicode, TikZ cho bìa.
- Đổi tên mặc định sang tiếng Việt: Chương/Hình/Bảng/Mục lục/Danh sách hình/
  Danh sách bảng/Phụ lục.
- Lề hiện tại: `top=30mm, bottom=25mm, left=30mm, right=20mm` — ⚠️ lệch quy
  định Khoa (trên 3 / dưới 3.5 / trái 3.5 / phải 2 cm), xem 01-quy-dinh-khoa.md.
- **Thông tin chung điền một chỗ** trong main.tex, tự lan ra các trang khác:
  `\tenSV`, `\mssv`, `\tenKL`, `\tenGVHD`, `\tenBM` (dùng `~` nối từ để khỏi vỡ dòng).

## Thứ tự nội dung trong main.tex

`Title` → (chỗ chèn nhận xét GVHD/GVPB sau bảo vệ) → `\pagenumbering{roman}` →
Lời cảm ơn → Tóm lược nội dung các chương (decuong) → glossary → Mục lục +
danh sách hình/bảng → Tóm tắt → `\pagenumbering{arabic}` → Chương 1–6 →
(Danh mục công trình, comment nếu không có) → Tài liệu tham khảo →
`\appendix` → phụ lục. Các phần ngoài chương đều `\addcontentsline` thủ công.

## Build

```bash
# xóa file tạm trước, rồi build BIB > PDF > PDF:
rm -f *.aux *.bbl *.blg *.log *.out *.toc *.lof *.lot *.run.xml *-blx.bib
rm -f Chapter*/*.aux Appendix/*.aux
pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

Kiểm tra sau build: 0 error, không còn "Hình ??"/cross-ref chưa resolve
(review thesis mẫu từng bắt lỗi này), số trang hợp lý (mẫu: 76 trang).
Cần TeX Live có gói tiếng Việt (vntex/T5).

### Cạm bẫy build (gặp thật 2026-08-07, thesis_hsge_vi)

- **Bước xóa file tạm là BẮT BUỘC, không phải tùy chọn.** Bỏ qua nó thì mỗi
  lần build lại cross-ref hỏng thêm (đo được: 0 → 96 → 181 reference chưa
  resolve qua 3 lần build liên tiếp trên cùng source đúng). Luôn chạy trọn
  gói clean → pdflatex → bibtex → pdflatex → pdflatex.
- **Đừng dùng `latexmk`** cho thesis_hsge_vi: nó gọi bibtex sai thời điểm
  (khi `main.aux` chưa có `\citation`) rồi ghi `main.bbl` rỗng, và kết thúc
  bằng "pdflatex needed too many passes".
- Bibliography dùng **biblatex `style=ieee` với `backend=bibtex`**
  (`main.tex` dòng 18–25) — nên chạy `bibtex main`, KHÔNG phải `biber`.
  `biber` sẽ báo "Cannot find main.bcf".
- **Trường `note` trong `.bib` được IN RA** trong mục tài liệu tham khảo ở
  style IEEE. Ghi chú nội bộ (kiểu "VERIFY: cần kiểm venue") phải để dưới
  dạng comment `%` phía trên entry, không để trong `note` — đã bị lọt ra
  PDF một lần.
- Máy này đọc file rời rạc giữa các lệnh shell hay dính **bản cache cũ**
  (`main.bbl` báo 0 byte dù vừa ghi 55 KB). Chạy build + kiểm tra trong
  **một script duy nhất**, và xác minh trên `pdftotext main.pdf` thay vì
  tin vào `.log`/`.blg` đọc ở lần gọi sau.

## Việc cần làm khi fork template cho HSGE

- Sửa `\tenSV`/`\mssv`/`\tenKL`/`\tenGVHD`/`\tenBM` trong main.tex.
- Viết lại Title nếu khác chương trình (mẫu đang là CLC — kiểm tra loại
  chương trình trên bìa theo mẫu Khoa).
- Làm rỗng Chapter1–6, Appendix/{thanks,decuong,glossary,tomtat,appendix1},
  References/references.bib; xóa images/Figures/Tables/scripts cũ.
- Cân nhắc chỉnh geometry theo đúng quy định Khoa (hỏi GVHD trước).
- Giữ lại các script glossary (check_acronyms.py, sort_glossary.py) — hữu ích
  cho bảng viết tắt.
