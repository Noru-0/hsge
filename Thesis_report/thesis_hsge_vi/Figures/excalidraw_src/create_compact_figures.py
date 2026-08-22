#!/usr/bin/env python3
"""
Generate clean, highly-legible Excalidraw diagrams for the HSGE thesis and slides.
Engineered to prevent text truncation, clipping, and border overflow.
Wide boxes, generous padding, clear hierarchy, and slide-optimized fonts.
"""

import json
import os
import subprocess
from PIL import Image

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
RENDER_SCRIPT = "/Users/Kiet/Documents/Code/WebAgent/Phat/Skill_Operator/.claude/skills/excalidraw-diagram/references/render_excalidraw.py"
SLIDE_IMG_DIR = "/Users/Kiet/Documents/Code/WebAgent/Phat/Skill_Operator/Thesis_report/Slide_KLTN_HSGE/images"


def base_elem(id_val, el_type, x, y, width, height, **kwargs):
    return {
        "id": id_val,
        "type": el_type,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0,
        "strokeColor": kwargs.get("stroke", "#1e1e1e"),
        "backgroundColor": kwargs.get("bg", "transparent"),
        "fillStyle": kwargs.get("fill_style", "solid"),
        "strokeWidth": kwargs.get("stroke_width", 2.5),
        "strokeStyle": kwargs.get("stroke_style", "solid"),
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": {"type": 3} if kwargs.get("radius") else None,
        "seed": kwargs.get("seed", 1000),
        "version": 1,
        "versionNonce": 1,
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
    }


def rect(id_val, x, y, w, h, **kwargs):
    return base_elem(id_val, "rectangle", x, y, w, h, **kwargs)


def ellipse(id_val, x, y, w, h, **kwargs):
    return base_elem(id_val, "ellipse", x, y, w, h, **kwargs)


def diamond(id_val, x, y, w, h, **kwargs):
    return base_elem(id_val, "diamond", x, y, w, h, **kwargs)


def text(id_val, x, y, w, h, text_val, **kwargs):
    color = kwargs.get("color", kwargs.get("stroke", "#0f172a"))
    kwargs["stroke"] = color
    el = base_elem(id_val, "text", x, y, w, h, **kwargs)
    el.update({
        "text": text_val,
        "fontSize": kwargs.get("size", 20),
        "fontFamily": kwargs.get("font_family", 2),  # 2: Helvetica / Clean sans
        "textAlign": kwargs.get("align", "left"),
        "verticalAlign": kwargs.get("valign", "top"),
        "containerId": None,
        "originalText": text_val,
        "lineHeight": kwargs.get("line_height", 1.25),
    })
    return el


def arrow(id_val, start_x, start_y, points, **kwargs):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    w = max(xs) - min(xs) if xs else 0
    h = max(ys) - min(ys) if ys else 0
    el = base_elem(id_val, "arrow", start_x, start_y, w, h, **kwargs)
    el.update({
        "points": points,
        "lastCommittedPoint": None,
        "startBinding": None,
        "endBinding": None,
        "startArrowhead": kwargs.get("start_head", None),
        "endArrowhead": kwargs.get("end_head", "arrow"),
    })
    return el


def save_excalidraw(filename, elements):
    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {
            "viewBackgroundColor": "#ffffff",
            "gridSize": None,
        },
        "files": {},
    }
    path = os.path.join(OUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"Wrote {filename}")
    return path


# ==============================================================================
# 1. FIG_ROADMAP: Lộ trình nghiên cứu & Định vị các chương
# ==============================================================================
def build_fig_roadmap():
    elems = []
    elems.append(text("title", 20, 15, 1160, 32, "Lộ trình nghiên cứu: Định vị phương pháp & đóng góp của luận văn", size=26, color="#1e40af", align="center"))

    # Top band: Chương 2
    elems.append(rect("ch2_box", 20, 55, 1160, 50, stroke="#475569", bg="#f8fafc", stroke_style="dashed", radius=3))
    elems.append(text("ch2_txt", 30, 67, 1140, 26, "Chương 2 — Kiến thức nền & Định vị HSGE trong bức tranh Web Agent tổng thể", size=20, color="#334155", align="center"))

    # Inputs (Left)
    elems.append(rect("in_web", 20, 140, 260, 125, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("in_web_t", 30, 155, 240, 95, "Website Thực tế\n• URL / Sitemap\n• Chưa có nhãn task", size=21, color="#9a3412", align="center"))

    elems.append(rect("in_slm", 20, 285, 260, 125, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("in_slm_t", 30, 300, 240, 95, "SLM Pre-train (<10B)\n• Qwen 7B/9B, LLaMA\n• Chưa biết dùng web", size=21, color="#5b21b6", align="center"))

    # Middle Section: HSGE PIPELINE
    elems.append(rect("pipe_outer", 310, 120, 530, 370, stroke="#1e3a5f", bg="#f0f9ff", stroke_style="dashed", radius=3))
    elems.append(text("pipe_title", 320, 130, 510, 28, "HSGE Pipeline (Chương 3 — Phương pháp)", size=22, color="#1e40af", align="center"))

    # 4 Steps
    elems.append(rect("p_s1", 330, 170, 230, 110, stroke="#1e3a5f", bg="#93c5fd", radius=3))
    elems.append(text("p_s1_t", 335, 185, 220, 80, "1. Khám phá\n(Explorer & Solver\nInline Judge)", size=20, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_p1_p2", 560, 225, [[0, 0], [40, 0]], stroke="#1e3a5f", stroke_width=2.5))

    elems.append(rect("p_s2", 600, 170, 220, 110, stroke="#1e3a5f", bg="#bfdbfe", radius=3))
    elems.append(text("p_s2_t", 605, 185, 210, 80, "2. Phát hiện Skill\n(Cụm & Trừu tượng\nKiểm chứng ≥ 2)", size=20, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_p2_p3", 710, 280, [[0, 0], [0, 30]], stroke="#1e3a5f", stroke_width=2.5))

    elems.append(rect("p_s3", 600, 310, 220, 110, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("p_s3_t", 605, 325, 210, 80, "3. Ghép Operator\n(Sinh Semantic Task\nĐa bước dài hạn)", size=20, color="#5b21b6", align="center"))

    elems.append(arrow("arr_p3_p4", 600, 365, [[0, 0], [-40, 0]], stroke="#1e3a5f", stroke_width=2.5))

    elems.append(rect("p_s4", 330, 310, 230, 110, stroke="#047857", bg="#a7f3d0", radius=3))
    elems.append(text("p_s4_t", 335, 325, 220, 80, "4. Đóng gói SFT\n(Build trực tiếp\nPrompt Parity)", size=20, color="#065f46", align="center"))

    elems.append(arrow("arr_in_pipe", 280, 260, [[0, 0], [30, 0]], stroke="#1e3a5f", stroke_width=3))
    elems.append(arrow("arr_pipe_eval", 840, 305, [[0, 0], [30, 0]], stroke="#1e3a5f", stroke_width=3))

    # Evaluation (Right)
    elems.append(rect("eval_outer", 870, 120, 310, 370, stroke="#6d28d9", bg="#faf5ff", stroke_style="dashed", radius=3))
    elems.append(text("eval_title", 880, 130, 290, 28, "Đánh giá (Chương 4)", size=22, color="#6d28d9", align="center"))

    elems.append(rect("box_lora", 885, 175, 280, 80, stroke="#1e3a5f", bg="#ede9fe", radius=3))
    elems.append(text("txt_lora", 890, 190, 270, 50, "Fine-tune LoRA\n(LLaMA-Factory)", size=20, color="#5b21b6", align="center"))

    elems.append(arrow("arr_l_b", 1025, 255, [[0, 0], [0, 25]], stroke="#1e3a5f", stroke_width=2.5))

    elems.append(rect("box_bench", 885, 280, 280, 95, stroke="#047857", bg="#d1fae5", radius=3))
    elems.append(text("txt_bench", 890, 292, 270, 70, "Benchmark WebArena\nShopping · Reddit · GitLab", size=20, color="#065f46", align="center"))

    elems.append(rect("box_res_mini", 885, 390, 280, 85, stroke="#047857", bg="#a7f3d0", radius=3))
    elems.append(text("txt_res_m", 890, 402, 270, 60, "Tỷ lệ Hoàn thành ↑\nVượt WebArena SFT", size=20, color="#065f46", align="center"))

    return save_excalidraw("fig_roadmap.excalidraw", elems)


# ==============================================================================
# 2. FIG_PIPELINE: Tổng quan Kiến trúc Pipeline Khép kín HSGE (Slide 7)
# ==============================================================================
def build_fig_pipeline():
    elems = []
    # Title
    elems.append(text("title", 20, 15, 1260, 32, "Pipeline HSGE: Vòng lặp Khép kín Tự Sinh Dữ liệu Huấn luyện", size=26, color="#1e40af", align="center"))

    # ROW 1: 4 Main Stages with generous widths (285px each)
    w_box = 285
    h_box = 160
    y_row1 = 65

    # 1. Khám phá
    elems.append(rect("p1_box", 20, y_row1, w_box, h_box, stroke="#0284c7", bg="#e0f2fe", radius=3))
    elems.append(text("p1_t", 25, y_row1 + 15, w_box - 10, 30, "1. KHÁM PHÁ TỰ HÀNH", size=20, color="#0369a1", align="center"))
    elems.append(text("p1_d", 35, y_row1 + 55, w_box - 30, 90, "• Explorer: Sinh task cục bộ\n• Solver: ReAct duyệt web\n• Inline Judge: Lọc đỗ ảo live", size=16, color="#075985"))

    elems.append(arrow("arr_1_2", 305, y_row1 + 80, [[0, 0], [30, 0]], stroke="#0284c7", stroke_width=3))

    # 2. Phát hiện Skill & Operator
    elems.append(rect("p2_box", 335, y_row1, w_box, h_box, stroke="#7c3aed", bg="#f5f3ff", radius=3))
    elems.append(text("p2_t", 340, y_row1 + 15, w_box - 10, 30, "2. PHÁT HIỆN SKILL & OP", size=20, color="#5b21b6", align="center"))
    elems.append(text("p2_d", 350, y_row1 + 55, w_box - 30, 90, "• Phân đoạn & Gom cụm\n• Trừu tượng hóa SkillCard\n• Quy nạp Operator (Pre/Eff)", size=16, color="#6d28d9"))

    elems.append(arrow("arr_2_3", 620, y_row1 + 80, [[0, 0], [30, 0]], stroke="#7c3aed", stroke_width=3))

    # 3. Ghép Semantic Task
    elems.append(rect("p3_box", 650, y_row1, w_box, h_box, stroke="#c026d3", bg="#fdf4ff", radius=3))
    elems.append(text("p3_t", 655, y_row1 + 15, w_box - 10, 30, "3. GHÉP SEMANTIC TASK", size=20, color="#86198f", align="center"))
    elems.append(text("p3_d", 665, y_row1 + 55, w_box - 30, 90, "• Nối chuỗi Op (len ≥ 2)\n• Sinh task mục tiêu dài hạn\n• Mở rộng độ phủ website", size=16, color="#701a75"))

    elems.append(arrow("arr_3_4", 935, y_row1 + 80, [[0, 0], [30, 0]], stroke="#059669", stroke_width=3))

    # 4. Đóng gói SFT Trực tiếp
    elems.append(rect("p4_box", 965, y_row1, w_box + 15, h_box, stroke="#059669", bg="#ecfdf5", radius=3))
    elems.append(text("p4_t", 970, y_row1 + 15, w_box + 5, 30, "4. ĐÓNG GÓI SFT", size=20, color="#065f46", align="center"))
    elems.append(text("p4_d", 980, y_row1 + 55, w_box - 15, 90, "• Trajectories sạch từ nguồn\n• Prompt Parity khớp từng byte\n• Không cần lọc ngoại tuyến", size=16, color="#047857"))

    # Feedback Loop (Bottom Channel)
    elems.append(arrow("arr_loop", 792, y_row1 + h_box, [[0, 0], [0, 45], [-630, 45], [-630, 0]], stroke="#c026d3", stroke_style="dashed", stroke_width=3))
    elems.append(rect("b_loop_lbl", 280, 245, 540, 45, stroke="#c026d3", bg="#fdf4ff", radius=3))
    elems.append(text("txt_loop_lbl", 290, 255, 520, 25, "Đồ thị Operator định hướng vòng khám phá tiếp theo ⟳", size=18, color="#86198f", align="center"))

    # Target: SLM Fine-tuning Output Banner
    elems.append(rect("b_sft_out", 20, 315, 1245, 85, stroke="#059669", bg="#a7f3d0", radius=3))
    elems.append(text("txt_sft_out", 30, 335, 1225, 45, "➔ ĐẦU RA: Tập dữ liệu SFT Chuẩn hóa đưa thẳng vào Huấn luyện LoRA cho SLMs (<10B)", size=22, color="#065f46", align="center"))

    return save_excalidraw("fig_pipeline.excalidraw", elems)


# ==============================================================================
# 3. FIG_TWOLEVEL: Đồ thị Hai Tầng (Slide 8)
# ==============================================================================
def build_fig_twolevel():
    elems = []
    elems.append(text("title", 20, 15, 1200, 32, "Biểu Diễn Tri Thức: Đồ Thị Hai Tầng (Two-Level Graph)", size=26, color="#1e40af", align="center"))

    # Upper container: Tầng cao (Operator Graph)
    elems.append(rect("top_outer", 20, 55, 1200, 175, stroke="#6d28d9", bg="#faf5ff", stroke_style="dashed", stroke_width=2.5, radius=3))
    elems.append(text("top_title", 35, 65, 900, 26, "TẦNG CAO: Operator Graph (Kỹ năng logic dạng Precondition / Effect)", size=22, color="#6d28d9"))

    # 3 Operators with wide boxes (330px each)
    elems.append(rect("op1", 40, 100, 330, 115, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("op1_t", 45, 108, 320, 28, "Op 1: Login", size=23, color="#5b21b6", align="center"))
    elems.append(text("op1_d", 45, 140, 320, 65, "pre: chưa đăng nhập\neff: đã đăng nhập", size=19, color="#4c1d95", align="center"))

    elems.append(arrow("arr_op12", 370, 155, [[0, 0], [70, 0]], stroke="#6d28d9", stroke_width=3))
    elems.append(text("lbl_op12", 370, 122, 70, 25, "ghép nối", size=18, color="#6d28d9", align="center"))

    elems.append(rect("op2", 440, 100, 360, 115, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("op2_t", 445, 108, 350, 28, "Op 2: Add to Cart", size=23, color="#5b21b6", align="center"))
    elems.append(text("op2_d", 445, 140, 350, 65, "pre: đã đăng nhập + xem SP\neff: giỏ có sản phẩm", size=19, color="#4c1d95", align="center"))

    elems.append(arrow("arr_op23", 800, 155, [[0, 0], [70, 0]], stroke="#6d28d9", stroke_width=3))
    elems.append(text("lbl_op23", 800, 122, 70, 25, "ghép nối", size=18, color="#6d28d9", align="center"))

    elems.append(rect("op3", 870, 100, 330, 115, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("op3_t", 875, 108, 320, 28, "Op 3: Checkout", size=23, color="#5b21b6", align="center"))
    elems.append(text("op3_d", 875, 140, 320, 65, "pre: giỏ có sản phẩm\neff: đơn hàng xác nhận", size=19, color="#4c1d95", align="center"))

    # Lower container: Tầng thấp (Page States)
    elems.append(rect("bot_outer", 20, 255, 1200, 165, stroke="#1e3a5f", bg="#f0f9ff", stroke_style="dashed", stroke_width=2.5, radius=3))
    elems.append(text("bot_title", 35, 265, 900, 26, "TẦNG THẤP: Page State Graph (Duyệt trang & Chuyển đổi thực tế)", size=22, color="#0369a1"))

    # Page state sequence
    states = [
        ("Trang chủ\n/home", 40, "#ffedd5", "#c2410c"),
        ("Sản phẩm\n/product", 335, "#93c5fd", "#1e3a5f"),
        ("Giỏ hàng\n/cart", 630, "#93c5fd", "#1e3a5f"),
        ("Xác nhận\n/success", 925, "#a7f3d0", "#047857"),
    ]
    for st_title, st_x, st_bg, st_stroke in states:
        elems.append(rect(f"st_{st_x}", st_x, 305, 245, 95, stroke=st_stroke, bg=st_bg, radius=3))
        elems.append(text(f"st_t_{st_x}", st_x + 5, 320, 235, 65, st_title, size=21, color=st_stroke, align="center"))

    elems.append(arrow("a_st_1", 285, 350, [[0, 0], [50, 0]], stroke="#1e3a5f", stroke_width=2.5))
    elems.append(arrow("a_st_2", 580, 350, [[0, 0], [50, 0]], stroke="#1e3a5f", stroke_width=2.5))
    elems.append(arrow("a_st_3", 875, 350, [[0, 0], [50, 0]], stroke="#1e3a5f", stroke_width=2.5))

    return save_excalidraw("fig_twolevel.excalidraw", elems)


# ==============================================================================
# 4. FIG_DISCOVERY: Pipeline 4 Bước Phát Hiện Kỹ Năng (Slide 9)
# ==============================================================================
def build_fig_discovery():
    elems = []
    w_disc = 420
    elems.append(text("title", 20, 15, w_disc, 28, "Phát Hiện Skill & Operator", size=22, color="#1e40af", align="center"))

    steps = [
        ("1. Phân cắt (Segmentation)", "Tách sub-trajectories theo ranh giới trang & AXTree", "#0284c7", "#e0f2fe", 55),
        ("2. Gom cụm (Clustering)", "Vector hóa ngữ nghĩa & gom cụm tương đồng", "#0284c7", "#e0f2fe", 175),
        ("3. Trừu tượng (SkillCard)", "Tổng hợp tên & tham số hóa thành SkillCard", "#7c3aed", "#f5f3ff", 295),
        ("4. Quy nạp Operator", "Rút trích Pre/Effect, lọc Tautology & Grounding (≥50%)", "#059669", "#ecfdf5", 415),
    ]

    for title_txt, desc_txt, st_color, bg_color, y_pos in steps:
        elems.append(rect(f"box_{y_pos}", 20, y_pos, w_disc, 105, stroke=st_color, bg=bg_color, radius=3))
        elems.append(text(f"t_{y_pos}", 25, y_pos + 12, w_disc - 10, 26, title_txt, size=20, color=st_color, align="center"))
        elems.append(text(f"d_{y_pos}", 30, y_pos + 48, w_disc - 20, 48, desc_txt, size=15, color="#1e293b", align="center"))
        if y_pos < 415:
            elems.append(arrow(f"arr_{y_pos}", 230, y_pos + 105, [[0, 0], [0, 15]], stroke=st_color, stroke_width=2.5))

    return save_excalidraw("fig_discovery.excalidraw", elems)


# ==============================================================================
# 5. FIG_SEMANTIC: Sinh Semantic Task Bằng Ghép Chuỗi (Slide 10)
# ==============================================================================
def build_fig_semantic():
    elems = []
    elems.append(text("title", 20, 15, 1200, 32, "Sinh Semantic Task: Ghép Chuỗi Operator Đa Bước", size=26, color="#1e40af", align="center"))

    # Operator Chain Sequence (Wide cards 360px each)
    ops = [
        ("Op 1: Login", "pre: ở trang đăng nhập\neff: đã đăng nhập", 30),
        ("Op 2: Search", "pre: đã đăng nhập\neff: đang xem danh sách SP", 430),
        ("Op 3: Add to Cart", "pre: đang xem danh sách SP\neff: giỏ hàng có sản phẩm", 830),
    ]

    for op_name, op_desc, op_x in ops:
        elems.append(rect(f"op_{op_x}", op_x, 65, 360, 130, stroke="#0284c7", bg="#e0f2fe", radius=3))
        elems.append(text(f"op_t_{op_x}", op_x + 10, 75, 340, 28, op_name, size=24, color="#0369a1", align="center"))
        elems.append(text(f"op_d_{op_x}", op_x + 10, 112, 340, 65, op_desc, size=18, color="#075985", align="center"))

    elems.append(arrow("arr_s1", 390, 130, [[0, 0], [40, 0]], stroke="#0284c7", stroke_width=3))
    elems.append(arrow("arr_s2", 790, 130, [[0, 0], [40, 0]], stroke="#0284c7", stroke_width=3))

    # Resulting Semantic Task Banner (Bottom)
    elems.append(arrow("arr_to_task", 610, 195, [[0, 0], [0, 30]], stroke="#059669", stroke_width=3))

    elems.append(rect("box_res", 30, 225, 1160, 155, stroke="#059669", bg="#ecfdf5", radius=3))
    elems.append(text("res_title", 45, 235, 1130, 28, "➔ NHIỆM VỤ TỔNG HỢP SINH RA (Semantic Task):", size=22, color="#065f46"))

    elems.append(rect("b_inst", 45, 270, 1130, 90, stroke="#059669", bg="#ffffff", radius=3))
    elems.append(text("inst_txt", 55, 285, 1110, 60, "\"Từ /login: Đăng nhập tài khoản, tìm kiếm sản phẩm và thêm vào giỏ hàng.\"\n(Tác vụ dài hạn vượt khỏi phạm vi trang đơn lẻ)", size=22, color="#047857", align="center"))

    return save_excalidraw("fig_semantic.excalidraw", elems)


# ==============================================================================
# 6. FIG_CURATION: Kiểm định Trực tuyến & Đóng gói SFT (Slide 11)
# ==============================================================================
def build_fig_curation():
    elems = []
    w_cur = 420
    elems.append(text("cur_title", 20, 15, w_cur, 28, "Kiểm Định & Đóng Gói SFT", size=22, color="#1e40af", align="center"))

    # Block 1: Inline Quality Gates
    elems.append(rect("b_in", 20, 55, w_cur, 135, stroke="#0284c7", bg="#f0f9ff", radius=3))
    elems.append(text("b_in_t", 25, 65, w_cur - 10, 28, "1. CỔNG CHẤT LƯỢNG RUNTIME", size=20, color="#0369a1", align="center"))
    elems.append(text("b_in_d", 30, 100, w_cur - 20, 80, "• Inline LLM Judge: Chấm live trang đích\n  loại bỏ 801 episode (27.4%) đỗ ảo\n• Effective Action: Chặn task không đổi web", size=16, color="#075985"))

    elems.append(arrow("a_1_2", 230, 190, [[0, 0], [0, 25]], stroke="#0284c7", stroke_width=3))

    # Block 2: Clean Trajectories Storage
    elems.append(rect("b_clean", 20, 215, w_cur, 120, stroke="#7c3aed", bg="#f5f3ff", radius=3))
    elems.append(text("b_cl_t", 25, 225, w_cur - 10, 28, "2. KHO TRAJECTORIES SẠCH", size=20, color="#5b21b6", align="center"))
    elems.append(text("b_cl_d", 30, 260, w_cur - 20, 65, "• 1760 trajectory sạch / 8554 mẫu SFT\n• Đã được thẩm định trực tiếp từ nguồn", size=17, color="#6d28d9", align="center"))

    elems.append(arrow("a_2_3", 230, 335, [[0, 0], [0, 25]], stroke="#059669", stroke_width=3))

    # Block 3: Direct SFT Packaging
    elems.append(rect("b_sft", 20, 360, w_cur, 145, stroke="#059669", bg="#ecfdf5", radius=3))
    elems.append(text("b_sft_t", 25, 370, w_cur - 10, 28, "3. ĐÓNG GÓI SFT TRỰC TIẾP", size=20, color="#065f46", align="center"))
    elems.append(text("b_sft_d", 30, 405, w_cur - 20, 90, "• Build trực tiếp bằng build_sft_dataset.py\n• KHÔNG CẦN khâu lọc ngoại tuyến\n• Prompt Parity khớp từng byte ➔ LoRA SLM", size=16, color="#047857"))

    return save_excalidraw("fig_curation.excalidraw", elems)


# ==============================================================================
# 7. FIG_FRONTIER: Quản lý Frontier (Slide 27 Phụ lục)
# ==============================================================================
def build_fig_frontier():
    elems = []
    elems.append(text("title", 20, 15, 1220, 32, "Quản Lý Frontier: Phân Tầng, Template Cap & Khử Trùng Lặp", size=26, color="#1e40af", align="center"))

    # 3 Big Columns (370px each, total 1220px)
    # Col 1: Sources
    elems.append(rect("b_s1", 20, 65, 370, 340, stroke="#0284c7", bg="#f0f9ff", radius=3))
    elems.append(text("s1_t", 25, 80, 360, 30, "1. Nguồn Ứng Viên", size=23, color="#0369a1", align="center"))
    
    elems.append(rect("b_t0", 35, 125, 340, 100, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("t0_t", 45, 135, 320, 80, "Tier 0 (Ưu tiên cao nhất)\n• URL solver đã điều hướng tới\n• Tab trình duyệt đang mở", size=17, color="#9a3412"))
    
    elems.append(rect("b_t1", 35, 245, 340, 135, stroke="#1e3a5f", bg="#ede9fe", radius=3))
    elems.append(text("t1_t", 45, 255, 320, 115, "Tier 1 (Khai thác tĩnh)\n• Thẻ <a> trên DOM trang web\n• Gated bởi Template Cap (c ≤ 3)\n  (tránh bão hòa cùng khuôn dạng)", size=16, color="#5b21b6"))

    elems.append(arrow("a_1_2", 390, 235, [[0, 0], [45, 0]], stroke="#0284c7", stroke_width=3))

    # Col 2: Priority Queue
    elems.append(rect("b_s2", 435, 65, 370, 340, stroke="#7c3aed", bg="#f5f3ff", radius=3))
    elems.append(text("s2_t", 440, 80, 360, 30, "2. Hàng Đợi Ưu Tiên", size=23, color="#5b21b6", align="center"))
    
    elems.append(rect("b_key", 450, 125, 340, 150, stroke="#334155", bg="#1e293b", radius=3))
    elems.append(text("k_t", 460, 135, 320, 25, "Khóa Sắp Xếp Heapq (Key):", size=17, color="#93c5fd"))
    elems.append(text("k_c", 460, 165, 320, 100, "key = (tier, novelty, depth, seq)\n  tier: 0 (đã tới) > 1 (khai thác)\n  novelty: ít ghé > nhiều ghé\n  depth: nông > sâu (BFS)", size=15, color="#4ade80", font_family=3))
    
    elems.append(text("pq_note", 450, 285, 340, 100, "▲ Tier 0 luôn đứng trước\n▲ Ưu tiên khuôn dạng (template) mới\n▲ Khám phá theo độ sâu tăng dần", size=16, color="#6d28d9"))

    elems.append(arrow("a_2_3", 805, 235, [[0, 0], [45, 0]], stroke="#7c3aed", stroke_width=3))

    # Col 3: Deduplication
    elems.append(rect("b_s3", 850, 65, 370, 340, stroke="#059669", bg="#ecfdf5", radius=3))
    elems.append(text("s3_t", 855, 80, 360, 30, "3. Khử Trùng Lặp", size=23, color="#065f46", align="center"))
    
    elems.append(rect("b_land", 865, 125, 340, 105, stroke="#059669", bg="#ffffff", radius=3))
    elems.append(text("land_t", 875, 135, 320, 85, "• Landed URL: URL sau redirect\n• seen_content: SHA-256(AXTree)\n➔ Bỏ qua nếu trang đã ghé", size=17, color="#047857"))
    
    elems.append(rect("b_exp_ok", 865, 250, 340, 130, stroke="#059669", bg="#a7f3d0", radius=3))
    elems.append(text("exp_t", 875, 275, 320, 80, "➔ Nạp Trình Duyệt &\nThực Thi Tác Vụ Khám Phá", size=19, color="#065f46", align="center"))

    return save_excalidraw("fig_frontier.excalidraw", elems)


def render_and_sync():
    figs = [
        "fig_roadmap",
        "fig_pipeline",
        "fig_twolevel",
        "fig_discovery",
        "fig_semantic",
        "fig_curation",
        "fig_frontier",
    ]

    for name in figs:
        src = os.path.join(OUT_DIR, f"{name}.excalidraw")
        png = os.path.join(OUT_DIR, f"{name}.png")
        pdf_thesis = os.path.join(os.path.dirname(OUT_DIR), f"{name}.pdf")
        pdf_slide = os.path.join(SLIDE_IMG_DIR, f"{name}.pdf")

        print(f"Rendering {name}.excalidraw...")
        cmd = [
            "python3", RENDER_SCRIPT,
            src,
            "--output", png,
            "--scale", "3",
            "--width", "4000"
        ]
        subprocess.run(cmd, check=True)

        img = Image.open(png)
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        img.save(pdf_thesis, "PDF", resolution=300.0)
        img.save(pdf_slide, "PDF", resolution=300.0)
        print(f"✓ Synced {name}.pdf to Thesis & Slide images\n")


if __name__ == "__main__":
    build_fig_roadmap()
    build_fig_pipeline()
    build_fig_twolevel()
    build_fig_discovery()
    build_fig_semantic()
    build_fig_curation()
    build_fig_frontier()
    render_and_sync()
