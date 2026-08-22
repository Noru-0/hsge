#!/bin/bash
# Tự động theo dõi các thay đổi trong file .tex, .bib và tự động build PDF
cd "$(dirname "$0")"
echo "Đang khởi chạy latexmk ở chế độ theo dõi (continuous preview mode)..."
echo "Mỗi khi bạn lưu file .tex (như chapter3.tex), file main.pdf sẽ được tự động rebuild."
echo "Nhấn Ctrl+C để dừng."
echo ""
latexmk -pvc -pdf main.tex
