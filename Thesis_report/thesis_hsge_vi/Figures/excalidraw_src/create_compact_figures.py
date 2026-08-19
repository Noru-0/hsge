#!/usr/bin/env python3
"""
Generate clean, highly-legible Excalidraw diagrams for the HSGE thesis.
Optimized for zero overlaps, crisp 18-24px typography, high-contrast colors, and clean orthogonal arrow routing.
"""

import json
import os
import subprocess
from PIL import Image

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
RENDER_SCRIPT = "/Users/Kiet/Documents/Code/WebAgent/Phat/Skill_Operator/.claude/skills/excalidraw-diagram/references/render_excalidraw.py"


def base_elem(id_val, el_type, x, y, width, height, **kwargs):
    el = {
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
        "strokeWidth": kwargs.get("stroke_width", 2),
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
    return el


def rect(id_val, x, y, w, h, **kwargs):
    return base_elem(id_val, "rectangle", x, y, w, h, **kwargs)


def ellipse(id_val, x, y, w, h, **kwargs):
    return base_elem(id_val, "ellipse", x, y, w, h, **kwargs)


def diamond(id_val, x, y, w, h, **kwargs):
    return base_elem(id_val, "diamond", x, y, w, h, **kwargs)


def text(id_val, x, y, w, h, text_val, **kwargs):
    color = kwargs.get("color", kwargs.get("stroke", "#1e1e1e"))
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
        "lineHeight": 1.25,
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
            "gridSize": 20,
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
    # Title
    elems.append(text("title", 20, 15, 1040, 26, "Lộ trình nghiên cứu: Định vị phương pháp & đóng góp của luận văn", size=22, color="#1e40af", align="center"))

    # Top band: Chương 2
    elems.append(rect("ch2_box", 20, 50, 1040, 48, stroke="#475569", bg="#f8fafc", stroke_style="dashed", stroke_width=2, radius=3))
    elems.append(text("ch2_txt", 30, 62, 1020, 24, "Chương 2 — Kiến thức nền & Công trình liên quan: Định vị HSGE trong bức tranh Web Agent tổng thể", size=18, color="#334155", align="center"))

    # Left Section: INPUTS (x=20..240)
    elems.append(text("in_title", 20, 115, 220, 24, "INPUT ĐẦU VÀO", size=19, color="#1e40af"))

    elems.append(rect("in_web", 20, 150, 215, 95, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("in_web_t", 25, 162, 205, 70, "Website đang chạy\n(Seed URL / Sitemap\nchưa có nhãn/task)", size=17, color="#9a3412", align="center"))

    elems.append(rect("in_slm", 20, 265, 215, 95, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("in_slm_t", 25, 277, 205, 70, "SLM pre-train (<10B)\n(vd. Qwen2.5-7B /\nQwen3.5-9B)", size=17, color="#5b21b6", align="center"))

    # Connecting dot & arrow from Inputs to Pipeline
    elems.append(arrow("arr_in_web", 235, 197, [[0, 0], [40, 60]], stroke="#c2410c", stroke_width=2, end_head=None))
    elems.append(arrow("arr_in_slm", 235, 312, [[0, 0], [40, -55]], stroke="#6d28d9", stroke_width=2, end_head=None))
    elems.append(ellipse("dot_in", 272, 254, 8, 8, stroke="#1e3a5f", bg="#1e3a5f"))
    elems.append(arrow("arr_in_pipe", 280, 258, [[0, 0], [40, 0]], stroke="#1e3a5f", stroke_width=2.5))

    # Middle Section: HSGE PIPELINE (x=320..760)
    elems.append(rect("pipe_outer", 320, 110, 440, 390, stroke="#1e3a5f", bg="#f0f9ff", stroke_style="dashed", stroke_width=2, radius=3))
    elems.append(text("pipe_title", 330, 122, 420, 24, "HSGE Pipeline (Chương 3 — Phương pháp)", size=18, color="#1e40af", align="center"))

    # Step 1: Khám phá
    elems.append(rect("p_s1", 335, 155, 195, 95, stroke="#1e3a5f", bg="#93c5fd", radius=3))
    elems.append(text("p_s1_t", 340, 165, 185, 75, "1. Khám phá tự hành\n(Explorer · Solver\nTier 0/1 Frontier)", size=16, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_p1_p2", 530, 202, [[0, 0], [30, 0]], stroke="#1e3a5f", stroke_width=2))

    # Step 2: Phát hiện Skill
    elems.append(rect("p_s2", 560, 155, 185, 95, stroke="#1e3a5f", bg="#bfdbfe", radius=3))
    elems.append(text("p_s2_t", 565, 165, 175, 75, "2. Phát hiện Skill\n(cụm · trừu tượng\nkiểm chứng ≥ k lần)", size=16, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_p2_p3", 652, 250, [[0, 0], [0, 25]], stroke="#1e3a5f", stroke_width=2))

    # Step 3: Ghép Operator
    elems.append(rect("p_s3", 560, 275, 185, 95, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("p_s3_t", 565, 285, 175, 75, "3. Ghép Operator\n(sinh semantic task\nchuỗi nhiều bước)", size=16, color="#5b21b6", align="center"))

    elems.append(arrow("arr_p3_p4", 560, 322, [[0, 0], [-30, 0]], stroke="#1e3a5f", stroke_width=2))

    # Step 4: Tinh lọc Dataset
    elems.append(rect("p_s4", 335, 275, 195, 95, stroke="#047857", bg="#a7f3d0", radius=3))
    elems.append(text("p_s4_t", 340, 285, 185, 75, "4. Tinh lọc Dataset\n(3 cổng chất lượng\nJudge review)", size=16, color="#065f46", align="center"))

    # Pipeline Feedback Loop (runs in outer left margin at x=325, no crossing through p_s4)
    elems.append(arrow("arr_p_loop", 652, 370, [[0, 0], [0, 50], [-325, 50], [-325, -168], [-317, -168]], stroke="#6d28d9", stroke_style="dashed", stroke_width=2))
    elems.append(text("lbl_p_loop", 340, 435, 400, 22, "đồ thị skill định hướng vòng khám phá tiếp theo ⟳", size=15, color="#6d28d9", align="center"))

    # Arrow from Pipeline to Evaluation
    elems.append(arrow("arr_pipe_eval", 760, 305, [[0, 0], [30, 0]], stroke="#1e3a5f", stroke_width=2.5))

    # Right Section: EVALUATION (x=790..1060)
    elems.append(rect("eval_outer", 790, 110, 270, 390, stroke="#6d28d9", bg="#faf5ff", stroke_style="dashed", stroke_width=2, radius=3))
    elems.append(text("eval_title", 800, 122, 250, 24, "Đánh giá (Chương 4)", size=18, color="#6d28d9", align="center"))

    elems.append(rect("box_lora", 805, 155, 240, 65, stroke="#1e3a5f", bg="#ede9fe", radius=3))
    elems.append(text("txt_lora", 810, 165, 230, 45, "Fine-tune LoRA\n(LLaMA-Factory)", size=17, color="#5b21b6", align="center"))

    elems.append(arrow("arr_lora_bench", 925, 220, [[0, 0], [0, 20]], stroke="#1e3a5f", stroke_width=2))

    elems.append(rect("box_bench", 805, 240, 240, 80, stroke="#047857", bg="#d1fae5", radius=3))
    elems.append(text("txt_bench", 810, 250, 230, 60, "Benchmark WebArena\n(Shopping, Reddit,\nGitLab...)", size=17, color="#065f46", align="center"))

    elems.append(arrow("arr_bench_chart", 925, 320, [[0, 0], [0, 20]], stroke="#047857", stroke_width=2))

    # Mini Performance Chart
    elems.append(rect("box_chart", 805, 340, 240, 140, stroke="#047857", bg="#f0fdf4", radius=3))
    elems.append(text("txt_sr", 810, 348, 230, 22, "Tỷ lệ hoàn thành task ↑", size=16, color="#065f46", align="center"))
    elems.append(arrow("axis_h", 830, 445, [[0, 0], [190, 0]], stroke="#475569", stroke_width=2, end_head=None))
    elems.append(rect("bar_pre", 845, 415, 40, 30, stroke="#dc2626", bg="#fecaca", radius=2))
    elems.append(text("lbl_pre", 840, 450, 50, 18, "trước", size=13, color="#64748b", align="center"))
    elems.append(rect("bar_post", 935, 380, 45, 65, stroke="#047857", bg="#a7f3d0", radius=2))
    elems.append(text("lbl_post", 935, 450, 45, 18, "sau", size=13, color="#065f46", align="center"))

    # Bottom Band: Chapter Flow Navigation (y=520)
    chapters = [
        ("Chương 3 — Phương pháp", "#1e3a5f", "#dbeafe"),
        ("Chương 4 — Thực nghiệm", "#6d28d9", "#ede9fe"),
        ("Chương 5 — Bàn luận", "#c2410c", "#ffedd5"),
        ("Chương 6 — Kết luận", "#047857", "#d1fae5"),
    ]
    cur_x = 20
    box_w = 230
    gap = 40
    for idx, (ch_title, col_stroke, col_bg) in enumerate(chapters):
        elems.append(rect(f"nav_ch_{idx}", cur_x, 520, box_w, 55, stroke=col_stroke, bg=col_bg, radius=3))
        elems.append(text(f"nav_txt_{idx}", cur_x + 5, 535, box_w - 10, 24, ch_title, size=16, color=col_stroke, align="center"))
        if idx < len(chapters) - 1:
            elems.append(arrow(f"arr_nav_{idx}", cur_x + box_w, 547, [[0, 0], [gap, 0]], stroke=col_stroke, stroke_width=2.5))
        cur_x += box_w + gap

    return save_excalidraw("fig_roadmap.excalidraw", elems)


# ==============================================================================
# 2. FIG_PIPELINE: Tổng quan Kiến trúc Pipeline Khép kín HSGE
# ==============================================================================
def build_fig_pipeline():
    elems = []
    # Title
    elems.append(text("title", 20, 15, 1040, 26, "Pipeline HSGE: Vòng lặp khép kín Khám phá – Phát hiện Skill – Sinh dữ liệu", size=22, color="#1e40af", align="center"))

    # ----------------- ROW 1: Exploration Loop (y=55..160) -----------------
    elems.append(rect("b_front", 20, 55, 235, 105, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("b_front_t", 25, 65, 225, 85, "Frontier (Priority Queue)\n• Tier 0: URL solver đã tới\n• Tier 1: href DOM (c ≤ 3)", size=16, color="#9a3412"))

    elems.append(arrow("arr_f_exp", 255, 107, [[0, 0], [35, 0]], stroke="#c2410c", stroke_width=2))

    elems.append(rect("b_exp", 290, 55, 215, 105, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("b_exp_t", 295, 72, 205, 75, "Explorer (LLM)\nĐề xuất low-level task\ngắn với trang hiện tại", size=16, color="#5b21b6", align="center"))

    elems.append(arrow("arr_exp_sol", 505, 107, [[0, 0], [35, 0]], stroke="#1e3a5f", stroke_width=2))

    elems.append(rect("b_sol", 540, 55, 235, 105, stroke="#1e3a5f", bg="#3b82f6", radius=3))
    elems.append(text("b_sol_t", 545, 72, 225, 75, "Solver (ReAct Agent)\nThực thi task trên\ntrình duyệt thật", size=18, color="#ffffff", align="center"))

    elems.append(arrow("arr_sol_traj", 775, 107, [[0, 0], [35, 0]], stroke="#1e3a5f", stroke_width=2))

    # Trajectory box with clean high-contrast styling
    elems.append(rect("b_traj", 810, 55, 250, 105, stroke="#1e3a5f", bg="#1e293b", radius=3))
    elems.append(text("b_traj_t", 815, 72, 240, 75, "Trajectory\n(obs, act) sequence\ntask thành công", size=17, color="#4ade80", align="center"))

    # Arrow from Trajectory down-and-left to Skill Discovery (clean unobstructed routing in middle band)
    elems.append(arrow("arr_traj_disc", 935, 160, [[0, 0], [0, 35], [-635, 35], [-635, 70]], stroke="#1e3a5f", stroke_width=2))

    # ----------------- ROW 2: Skill Discovery & Chaining (y=230..390) -----------------
    elems.append(rect("b_disc_box", 20, 230, 580, 160, stroke="#1e3a5f", bg="#f0f9ff", stroke_style="dashed", stroke_width=2, radius=3))
    elems.append(text("b_disc_title", 35, 240, 550, 22, "Skill Discovery (4 giai đoạn phát hiện kỹ năng)", size=17, color="#1e40af"))

    # 4 Discovery stages
    st_w = 125
    st_h = 75
    st_y = 270
    stages = [
        ("1. Phân cắt\n(segmentation)", "#1e3a5f", "#93c5fd"),
        ("2. Gom cụm\n(clustering)", "#1e3a5f", "#bfdbfe"),
        ("3. Trừu tượng\n(SkillCard)", "#6d28d9", "#ede9fe"),
        ("4. Kiểm chứng\n(≥k lần test)", "#047857", "#a7f3d0"),
    ]
    sx = 35
    for sidx, (stitle, sstroke, sbg) in enumerate(stages):
        elems.append(rect(f"sd_s_{sidx}", sx, st_y, st_w, st_h, stroke=sstroke, bg=sbg, radius=3))
        elems.append(text(f"sd_t_{sidx}", sx + 2, st_y + 12, st_w - 4, 55, stitle, size=14, color=sstroke, align="center"))
        if sidx < 3:
            elems.append(arrow(f"sd_a_{sidx}", sx + st_w, st_y + st_h // 2, [[0, 0], [15, 0]], stroke=sstroke, stroke_width=1.5))
        sx += st_w + 15

    elems.append(text("disc_sub", 35, 355, 550, 20, "Trajectory hoàn tất ➔ Cắt ➔ Gom ➔ Trừu tượng ➔ Kiểm chứng môi trường", size=13, color="#64748b"))

    elems.append(arrow("arr_disc_chain", 600, 310, [[0, 0], [35, 0]], stroke="#047857", stroke_width=2.5))

    # Ghép Operator Box
    elems.append(rect("b_chain", 635, 230, 425, 160, stroke="#6d28d9", bg="#faf5ff", radius=3))
    elems.append(text("b_chain_t", 645, 242, 405, 24, "Ghép Operator ➔ Semantic Task", size=19, color="#5b21b6", align="center"))
    elems.append(text("b_chain_d", 645, 275, 405, 100, "Nối các operator có effect khớp precondition\nsinh ra semantic task dài hạn (GOAL task)\nvượt khỏi phạm vi trang đơn lẻ", size=16, color="#4c1d95", align="center"))

    # Feedback loop: Ghép Operator -> Frontier (clean lower-channel route across y=415, 0 crossings)
    elems.append(arrow("arr_chain_front", 850, 390, [[0, 0], [0, 25], [-840, 25], [-840, -283], [-830, -283]], stroke="#c2410c", stroke_style="dashed", stroke_width=2))
    elems.append(text("lbl_loop_exp", 380, 402, 300, 20, "nuôi vòng khám phá tiếp theo ⟳", size=14, color="#c2410c", align="center"))

    # ----------------- ROW 3: Quality Gates & SFT Dataset (y=420..560) -----------------
    elems.append(arrow("arr_chain_ep", 750, 390, [[0, 0], [0, 45], [-505, 45], [-505, 65]], stroke="#1e3a5f", stroke_width=2))

    elems.append(rect("b_ep", 20, 455, 235, 105, stroke="#1e3a5f", bg="#ede9fe", radius=3))
    elems.append(text("b_ep_t", 25, 470, 225, 75, "Episode ghi nhận\n(LOCAL / UNPREFIXED\n/ GOAL tasks)", size=17, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_ep_gates", 255, 507, [[0, 0], [35, 0]], stroke="#1e3a5f", stroke_width=2))

    # 3 Quality Gates container
    elems.append(rect("b_qg", 290, 430, 460, 140, stroke="#c2410c", bg="#fffbeb", stroke_style="dashed", stroke_width=2, radius=3))
    elems.append(text("b_qg_t", 305, 440, 430, 22, "3 Cổng chất lượng tự động (Quality Gates)", size=17, color="#9a3412"))

    elems.append(rect("qg_1", 305, 468, 135, 90, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("qg_1_t", 310, 478, 125, 70, "Judge Review\n(chấm lại task\ntự khai)", size=14, color="#9a3412", align="center"))

    elems.append(rect("qg_2", 450, 468, 140, 90, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("qg_2_t", 455, 478, 130, 70, "Effective Gate\n(loại hành động\nkhông đổi state)", size=14, color="#9a3412", align="center"))

    elems.append(rect("qg_3", 600, 468, 135, 90, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("qg_3_t", 605, 478, 125, 70, "Infeasible Gate\n(giữ report hợp lệ\nlàm nhãn)", size=14, color="#9a3412", align="center"))

    elems.append(arrow("arr_qg_sft", 750, 507, [[0, 0], [35, 0]], stroke="#047857", stroke_width=2.5))

    # SFT Dataset box
    elems.append(rect("b_sft", 785, 445, 275, 115, stroke="#047857", bg="#a7f3d0", radius=3))
    elems.append(text("b_sft_t", 790, 465, 265, 75, "Tập dữ liệu SFT\n(trajectory chuẩn hóa\nkèm goal) ➔ LoRA SLM", size=18, color="#065f46", align="center"))

    return save_excalidraw("fig_pipeline.excalidraw", elems)


# ==============================================================================
# 3. FIG_TWOLEVEL: Đồ thị Hai Tầng (Operator Graph & Page State Graph)
# ==============================================================================
def build_fig_twolevel():
    elems = []
    # Main Title
    elems.append(text("title", 20, 15, 1040, 26, "Đồ thị Hai Tầng: Tầng Cao (Operator) & Tầng Thấp (Page States)", size=22, color="#1e40af", align="center"))

    # Upper container: Tầng cao (y=55..215)
    elems.append(rect("top_outer", 20, 55, 1040, 160, stroke="#6d28d9", bg="#faf5ff", stroke_style="dashed", stroke_width=2, radius=3))
    elems.append(text("top_title", 35, 65, 700, 24, "Tầng cao — Skill đã nâng thành Operator (Trừu tượng hóa & Ghép nối)", size=18, color="#6d28d9"))

    # 3 Operators
    elems.append(rect("op1", 35, 95, 280, 105, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("op1_t", 40, 102, 270, 26, "Skill: login", size=20, color="#5b21b6", align="center"))
    elems.append(text("op1_d", 40, 130, 270, 65, "pre: chưa đăng nhập\neff: đã đăng nhập", size=16, color="#4c1d95", align="center"))

    elems.append(arrow("arr_op12", 315, 147, [[0, 0], [70, 0]], stroke="#6d28d9", stroke_width=2.5))
    elems.append(text("lbl_op12", 315, 112, 70, 32, "eff = pre\nđã login", size=14, color="#6d28d9", align="center"))

    elems.append(rect("op2", 385, 95, 305, 105, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("op2_t", 390, 102, 295, 26, "Skill: add_to_cart", size=20, color="#5b21b6", align="center"))
    elems.append(text("op2_d", 390, 130, 295, 65, "pre: đã login + xem sản phẩm\neff: giỏ hàng có sản phẩm", size=16, color="#4c1d95", align="center"))

    elems.append(arrow("arr_op23", 690, 147, [[0, 0], [70, 0]], stroke="#6d28d9", stroke_width=2.5))
    elems.append(text("lbl_op23", 690, 112, 70, 32, "eff = pre\ngiỏ có SP", size=14, color="#6d28d9", align="center"))

    elems.append(rect("op3", 760, 95, 285, 105, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("op3_t", 765, 102, 275, 26, "Skill: checkout", size=20, color="#5b21b6", align="center"))
    elems.append(text("op3_d", 765, 130, 275, 65, "pre: giỏ hàng có sản phẩm\neff: đơn hàng đã xác nhận", size=16, color="#4c1d95", align="center"))

    # Lower container: Tầng thấp (y=295..630)
    elems.append(rect("bot_outer", 20, 295, 1040, 340, stroke="#1e3a5f", bg="#f8fafc", stroke_style="dashed", stroke_width=2, radius=3))

    # Title placed in empty lower-left area (x=35..210, y=470..530) under Trang chủ
    elems.append(rect("bot_badge", 35, 470, 175, 65, stroke="#1e3a5f", bg="#f0f9ff", radius=3))
    elems.append(text("bot_title", 40, 478, 165, 50, "TẦNG THẤP:\nPage State Graph\n(Trajectory thực tế)", size=13, color="#0369a1", align="center"))

    # Row 1 of page states (y=360..435)
    elems.append(rect("st_home0", 35, 360, 175, 75, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("st_home0_t", 40, 372, 165, 50, "Trang chủ\n(chưa đăng nhập)", size=16, color="#9a3412", align="center"))

    elems.append(arrow("arr_st0_prod", 210, 397, [[0, 0], [60, 0]], stroke="#1e3a5f", stroke_width=2))
    elems.append(text("lbl_goto", 210, 370, 60, 22, "goto(url)", size=13, color="#1e3a5f", align="center"))

    elems.append(rect("st_prod", 270, 360, 195, 75, stroke="#1e3a5f", bg="#93c5fd", radius=3))
    elems.append(text("st_prod_t", 275, 372, 185, 50, "Trang sản phẩm\n(áo thun nam)", size=16, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_st_prod_cart", 465, 397, [[0, 0], [55, 0]], stroke="#1e3a5f", stroke_width=2))
    elems.append(text("lbl_add", 465, 370, 55, 22, "click(add)", size=13, color="#1e3a5f", align="center"))

    elems.append(rect("st_cart", 520, 360, 185, 75, stroke="#1e3a5f", bg="#93c5fd", radius=3))
    elems.append(text("st_cart_t", 525, 382, 175, 30, "Trang giỏ hàng", size=17, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_st_cart_chk", 705, 397, [[0, 0], [60, 0]], stroke="#1e3a5f", stroke_width=2))
    elems.append(text("lbl_chk", 705, 370, 60, 22, "checkout", size=13, color="#1e3a5f", align="center"))

    elems.append(rect("st_done", 765, 360, 280, 75, stroke="#047857", bg="#a7f3d0", radius=3))
    elems.append(text("st_done_t", 770, 372, 270, 50, "Trang xác nhận\nđơn hàng (hoàn tất)", size=16, color="#065f46", align="center"))

    # Row 2: Sub-loop for login flow (y=465..535)
    elems.append(rect("st_login", 270, 465, 195, 70, stroke="#1e3a5f", bg="#bfdbfe", radius=3))
    elems.append(text("st_login_t", 275, 477, 185, 45, "Trang đăng nhập\n(redirect)", size=16, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_prod_login", 335, 435, [[0, 0], [0, 30]], stroke="#1e3a5f", stroke_width=1.5))
    elems.append(text("lbl_req_login", 340, 440, 120, 22, "yêu cầu login", size=13, color="#64748b"))

    elems.append(arrow("arr_login_home1", 465, 500, [[0, 0], [55, 0]], stroke="#1e3a5f", stroke_width=1.5))
    elems.append(text("lbl_fill", 465, 477, 55, 22, "fill/login", size=13, color="#1e3a5f", align="center"))

    elems.append(rect("st_home1", 520, 465, 185, 70, stroke="#1e3a5f", bg="#bfdbfe", radius=3))
    elems.append(text("st_home1_t", 525, 477, 175, 45, "Trang chủ\n(đã login)", size=16, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_home1_prod", 550, 465, [[0, 0], [0, -15], [-130, -15], [-130, -30]], stroke="#1e3a5f", stroke_width=1.5))
    elems.append(text("lbl_back", 435, 440, 80, 20, "quay lại SP", size=13, color="#64748b"))

    # Vertical Projection / Anchoring Arrows (Orange Dashed, starting at y=200, entering cards cleanly at y=360)
    elems.append(arrow("anc_s1_start", 125, 200, [[0, 0], [0, 160]], stroke="#c2410c", stroke_style="dashed", stroke_width=2))
    elems.append(arrow("anc_s1_eff", 240, 200, [[0, 0], [0, 300], [30, 300]], stroke="#c2410c", stroke_style="dashed", stroke_width=2))
    elems.append(arrow("anc_s2_start", 480, 200, [[0, 0], [-110, 160]], stroke="#c2410c", stroke_style="dashed", stroke_width=2))
    elems.append(arrow("anc_s2_eff", 615, 200, [[0, 0], [0, 160]], stroke="#c2410c", stroke_style="dashed", stroke_width=2))
    elems.append(arrow("anc_s3_start", 830, 200, [[0, 0], [-20, 160]], stroke="#c2410c", stroke_style="dashed", stroke_width=2))
    elems.append(arrow("anc_s3_eff", 970, 200, [[0, 0], [-65, 160]], stroke="#c2410c", stroke_style="dashed", stroke_width=2))

    # Labels for vertical projection in the clear middle gap (y=245)
    elems.append(text("lbl_anc_s1", 85, 245, 80, 20, "khởi đầu", size=13, color="#c2410c", align="center"))
    elems.append(text("lbl_anc_e1", 200, 245, 80, 20, "effect", size=13, color="#c2410c", align="center"))
    elems.append(text("lbl_anc_s2", 400, 245, 80, 20, "khởi đầu", size=13, color="#c2410c", align="center"))
    elems.append(text("lbl_anc_e2", 625, 245, 80, 20, "effect", size=13, color="#c2410c", align="center"))
    elems.append(text("lbl_anc_s3", 755, 245, 80, 20, "khởi đầu", size=13, color="#c2410c", align="center"))
    elems.append(text("lbl_anc_e3", 940, 245, 80, 20, "effect", size=13, color="#c2410c", align="center"))

    # Legend box at bottom (y=555..615)
    elems.append(rect("leg_box", 35, 555, 1010, 60, stroke="#94a3b8", bg="#ffffff", radius=3))
    elems.append(text("leg_t", 45, 572, 130, 24, "Chú giải cạnh:", size=16, color="#1e3a5f"))

    elems.append(arrow("leg_a1", 185, 585, [[0, 0], [45, 0]], stroke="#1e3a5f", stroke_width=2))
    elems.append(text("leg_l1", 240, 572, 180, 24, "Hành động (trajectory)", size=15, color="#1e3a5f"))

    elems.append(arrow("leg_a2", 450, 585, [[0, 0], [45, 0]], stroke="#6d28d9", stroke_width=2.5))
    elems.append(text("leg_l2", 505, 572, 210, 24, "Ghép operator (composition)", size=15, color="#6d28d9"))

    elems.append(arrow("leg_a3", 740, 585, [[0, 0], [45, 0]], stroke="#c2410c", stroke_style="dashed", stroke_width=2))
    elems.append(text("leg_l3", 795, 572, 220, 24, "Neo xuống tầng thấp (anchoring)", size=15, color="#c2410c"))

    return save_excalidraw("fig_twolevel.excalidraw", elems)


# ==============================================================================
# 4. FIG_FRONTIER: Quản lý Frontier (Phân tầng, Template, Khử trùng lặp)
# ==============================================================================
def build_fig_frontier():
    elems = []
    # Title
    elems.append(text("title", 20, 15, 1040, 26, "Quản lý Frontier: Phân tầng ứng viên, Giới hạn khuôn dạng & Khử trùng lặp", size=22, color="#1e40af", align="center"))

    # Section 1: Candidate Sources (x=20..270)
    elems.append(text("s1_title", 20, 55, 250, 24, "1. Nguồn ứng viên", size=19, color="#1e40af"))

    elems.append(rect("b_t0", 20, 90, 250, 110, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("b_t0_t", 25, 98, 240, 95, "Tier 0 (Ưu tiên cao nhất)\n• URL solver đã đi tới\n• Tab trình duyệt đang mở", size=16, color="#9a3412"))

    elems.append(rect("b_t1", 20, 230, 250, 110, stroke="#1e3a5f", bg="#ede9fe", radius=3))
    elems.append(text("b_t1_t", 25, 238, 240, 95, "Tier 1 (Thu thập tự động)\n• Liên kết <a> khai thác DOM\n• Cần kiểm tra khuôn dạng", size=16, color="#5b21b6"))

    # Arrow from Tier 0 directly to Priority Queue (y=145)
    elems.append(arrow("arr_t0_pq", 270, 145, [[0, 0], [210, 0]], stroke="#c2410c", stroke_width=2.5))
    elems.append(text("lbl_t0_direct", 280, 120, 190, 22, "đưa thẳng vào hàng đợi", size=14, color="#c2410c", align="center"))

    # Diamond for Tier 1 Rate Limiting (x=300..430, y=235..335)
    elems.append(arrow("arr_t1_dia", 270, 285, [[0, 0], [30, 0]], stroke="#1e3a5f", stroke_width=2))

    elems.append(diamond("dia_c", 300, 235, 130, 100, stroke="#c2410c", bg="#fffbeb"))
    elems.append(text("dia_c_t", 310, 260, 110, 50, "≤ c / dạng?\n(c = 3)", size=16, color="#9a3412", align="center"))

    # Diamond branch: Discard (down)
    elems.append(arrow("arr_c_rej", 365, 335, [[0, 0], [0, 50]], stroke="#dc2626", stroke_width=2))
    elems.append(text("lbl_c_rej", 375, 350, 70, 20, "vượt c", size=14, color="#dc2626"))

    elems.append(rect("b_discard", 300, 385, 130, 50, stroke="#dc2626", bg="#fef2f2", radius=3))
    elems.append(text("b_discard_t", 305, 398, 120, 25, "Loại (discard)", size=15, color="#b91c1c", align="center"))

    # Diamond branch: Accept (to PQ)
    elems.append(arrow("arr_c_acc", 430, 285, [[0, 0], [50, 0]], stroke="#047857", stroke_width=2))
    elems.append(text("lbl_c_acc", 425, 260, 60, 20, "chưa đầy", size=13, color="#047857"))

    # Section 2: Priority Queue (x=480..700)
    elems.append(text("s2_title", 480, 55, 230, 24, "2. Hàng đợi ưu tiên", size=19, color="#1e40af"))

    elems.append(rect("b_pq", 480, 90, 220, 280, stroke="#1e3a5f", bg="#ffffff", stroke_width=2, radius=3))
    elems.append(text("pq_top", 485, 98, 210, 22, "▲ Ưu tiên cao nhất", size=14, color="#c2410c", align="center"))

    elems.append(rect("pq_1", 490, 125, 200, 42, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("pq_1_t", 495, 136, 190, 22, "Tier 0 · URL đã tới", size=15, color="#9a3412", align="center"))

    elems.append(rect("pq_2", 490, 175, 200, 42, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("pq_2_t", 495, 186, 190, 22, "Tier 0 · Tab đang mở", size=15, color="#9a3412", align="center"))

    elems.append(rect("pq_3", 490, 225, 200, 42, stroke="#1e3a5f", bg="#93c5fd", radius=3))
    elems.append(text("pq_3_t", 495, 236, 190, 22, "Tier 1 · Khuôn dạng mới", size=15, color="#1e3a5f", align="center"))

    elems.append(rect("pq_4", 490, 275, 200, 42, stroke="#1e3a5f", bg="#bfdbfe", radius=3))
    elems.append(text("pq_4_t", 495, 286, 190, 22, "Tier 1 · Khuôn dạng cũ", size=15, color="#1e3a5f", align="center"))

    elems.append(rect("pq_5", 490, 320, 200, 42, stroke="#1e3a5f", bg="#dbeafe", radius=3))
    elems.append(text("pq_5_t", 495, 331, 190, 22, "Tier 1 · Độ sâu lớn hơn", size=15, color="#1e3a5f", align="center"))

    # Sorting Key Box (x=480..700, y=385..535)
    elems.append(rect("b_key", 480, 385, 220, 150, stroke="#334155", bg="#1e293b", radius=3))
    elems.append(text("k_t", 490, 395, 200, 22, "Khóa sắp xếp:", size=15, color="#93c5fd"))
    elems.append(text("k_c", 490, 420, 200, 105, "key = (\n  tier,\n  novelty,\n  depth,\n  seq\n)", size=15, color="#4ade80", font_family=3))

    # Arrow from PQ to Pop
    elems.append(arrow("arr_pq_pop", 700, 230, [[0, 0], [40, 0]], stroke="#1e3a5f", stroke_width=2))

    # Section 3: Pop & Deduplication (x=740..1060)
    elems.append(text("s3_title", 740, 55, 300, 24, "3. Khử trùng khi pop", size=19, color="#1e40af"))

    elems.append(ellipse("pop_node", 740, 205, 80, 50, stroke="#1e3a5f", bg="#3b82f6"))
    elems.append(text("pop_txt", 745, 218, 70, 24, "Pop", size=17, color="#ffffff", align="center"))

    elems.append(arrow("arr_pop_hash", 820, 230, [[0, 0], [40, 0]], stroke="#1e3a5f", stroke_width=2))

    # Diamond for Axtree Hash
    elems.append(diamond("dia_hash", 860, 175, 130, 110, stroke="#c2410c", bg="#fffbeb"))
    elems.append(text("dia_h_t", 865, 208, 120, 45, "Trùng hash\naxtree?", size=15, color="#9a3412", align="center"))

    # Branch: Not Duplicate (explore)
    elems.append(arrow("arr_h_no", 925, 175, [[0, 0], [0, -40]], stroke="#047857", stroke_width=2))
    elems.append(text("lbl_h_no", 940, 145, 65, 20, "không", size=14, color="#047857"))

    elems.append(rect("b_explore", 850, 80, 150, 55, stroke="#047857", bg="#a7f3d0", radius=3))
    elems.append(text("b_explore_t", 855, 95, 140, 25, "Khám phá node", size=16, color="#065f46", align="center"))

    # Branch: Duplicate (skip)
    elems.append(arrow("arr_h_yes", 925, 285, [[0, 0], [0, 55]], stroke="#dc2626", stroke_width=2))
    elems.append(text("lbl_h_yes", 940, 305, 40, 20, "có", size=14, color="#dc2626"))

    elems.append(rect("b_skip", 850, 340, 150, 55, stroke="#dc2626", bg="#fef2f2", radius=3))
    elems.append(text("b_skip_t", 855, 355, 140, 25, "Bỏ qua (skip)", size=16, color="#b91c1c", align="center"))

    # Loop back from Skip to Pop (clean bottom channel)
    elems.append(arrow("arr_skip_pop", 925, 395, [[0, 0], [0, 55], [-145, 55], [-145, -145]], stroke="#dc2626", stroke_style="dashed", stroke_width=1.5))
    elems.append(text("lbl_pop_next", 790, 465, 120, 20, "pop kế tiếp ➔", size=13, color="#dc2626"))

    # Example URL Template Box (x=20..440, y=385..535)
    elems.append(rect("b_tmpl", 20, 385, 440, 150, stroke="#334155", bg="#1e293b", radius=3))
    elems.append(text("tmpl_t", 30, 395, 420, 22, "Ví dụ khuôn dạng URL (URL template):", size=15, color="#93c5fd"))
    elems.append(text("tmpl_c", 30, 425, 420, 95, "/f/AskReddit/comments/12345/title\n➔ /f/AskReddit/comments/*/*\n\n(Quy chuẩn ID/slug thành wildcard để tránh\nbùng nổ số lượng trang cùng một khuôn)", size=14, color="#4ade80", font_family=3))

    # Summary band at bottom
    elems.append(rect("sum_bar", 20, 555, 1040, 45, stroke="#1e3a5f", bg="#f0f9ff", radius=3))
    elems.append(text("sum_txt", 25, 567, 1030, 22, "Tóm tắt: Tier 0 ➔ đi thẳng | Tier 1 ➔ rate limit (c=3) | PQ sắp xếp theo (tier, novelty, depth, seq) | Pop ➔ hash check", size=15, color="#1e40af", align="center"))

    return save_excalidraw("fig_frontier.excalidraw", elems)


# ==============================================================================
# 5. FIG_SOLVER: Vòng lặp Solver ReAct với Hai Chốt Chặn
# ==============================================================================
def build_fig_solver():
    elems = []
    # Title
    elems.append(text("title", 20, 15, 1040, 26, "Vòng Lặp Solver: Quan sát – Suy nghĩ – Hành động với hai chốt chặn", size=22, color="#1e40af", align="center"))

    # Left Half: ReAct loop (x=20..495)
    elems.append(text("lh_title", 20, 55, 475, 24, "1. Vòng lặp tương tác (ReAct Architecture)", size=19, color="#1e40af"))

    # Observation Box
    elems.append(rect("box_obs", 20, 85, 215, 80, stroke="#1e3a5f", bg="#93c5fd", radius=3))
    elems.append(text("txt_obs", 25, 95, 205, 60, "Quan sát (Observation)\n• URL tương đối\n• Axtree cắt 6000 ký tự", size=15, color="#1e3a5f"))

    elems.append(arrow("arr_obs_th", 235, 125, [[0, 0], [45, 0]], stroke="#1e3a5f", stroke_width=2))

    # Thought Box
    elems.append(rect("box_th", 280, 85, 215, 80, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("txt_th", 285, 95, 205, 60, "Suy nghĩ (LLM)\nViết dòng suy luận\nchọn đúng 1 hành động", size=15, color="#5b21b6", align="center"))

    elems.append(arrow("arr_th_act", 387, 165, [[0, 0], [0, 40]], stroke="#6d28d9", stroke_width=2))

    # Action Box
    elems.append(rect("box_act", 280, 205, 215, 80, stroke="#1e3a5f", bg="#3b82f6", radius=3))
    elems.append(text("txt_act", 285, 220, 205, 50, "Hành động (Action)\nThực thi trên browser", size=17, color="#ffffff", align="center"))

    # Loop arrow from Action back to Observation (clean channel)
    elems.append(arrow("arr_act_obs", 280, 245, [[0, 0], [-150, 0], [-150, -80]], stroke="#1e3a5f", stroke_width=2))
    elems.append(text("lbl_loop_step", 140, 225, 130, 20, "lặp lại mỗi bước", size=13, color="#1e3a5f"))

    # Evidence boxes for inputs & actions
    elems.append(rect("box_obs_payload", 20, 305, 475, 175, stroke="#334155", bg="#1e293b", radius=3))
    elems.append(text("txt_obs_p_t", 30, 313, 455, 20, "Nội dung quan sát gửi cho LLM:", size=15, color="#93c5fd"))
    elems.append(text("txt_obs_p_c", 30, 335, 455, 135, "URL: /category/power-tools (dạng tương đối)\naxtree: ... [TRUNCATED: 3184 ký tự không hiển thị]\nLỗi hành động trước: (none)\n6 hành động gần nhất:\n  click(234) ➔ trang đã đổi\n  fill(112, \"drill\") ➔ không đổi", size=14, color="#4ade80", font_family=3))

    elems.append(rect("box_acts_space", 20, 490, 475, 100, stroke="#334155", bg="#1e293b", radius=3))
    elems.append(text("txt_acts_t", 30, 498, 455, 20, "Không gian hành động hợp lệ:", size=15, color="#93c5fd"))
    elems.append(text("txt_acts_c", 30, 520, 455, 60, "click(bid) · fill(bid, text) · select_option(bid, val)\npress(bid, key) · goto(url) · go_back() · scroll · hover\nsend_msg_to_user(text) · report_infeasible(reason)", size=14, color="#4ade80", font_family=3))

    # Right Half: Two Termination Gates (x=520..1040)
    elems.append(text("rh_title", 520, 55, 500, 24, "2. Hai chốt chặn cấu trúc kết thúc episode", size=19, color="#1e40af"))

    # Gate 1: Stuck Loop Gate (y=85..245)
    elems.append(rect("gate1_box", 520, 85, 520, 160, stroke="#dc2626", bg="#fef2f2", radius=3))
    elems.append(text("g1_title", 535, 95, 490, 22, "Chốt 1: Lặp đối tượng đích (Cùng bid/url liên tiếp)", size=16, color="#b91c1c"))

    # 4 Circles connected cleanly
    c_y = 135
    c_rad = 34
    c_xs = [555, 640, 725, 810]
    for idx, cx in enumerate(c_xs):
        c_num = str(idx + 1)
        c_bg = "#fee2e2" if idx == 3 else ("#fef3c7" if idx == 1 else "#e0f2fe")
        c_stroke = "#dc2626" if idx == 3 else ("#d97706" if idx == 1 else "#0284c7")
        elems.append(ellipse(f"c_circ_{idx}", cx, c_y, c_rad, c_rad, stroke=c_stroke, bg=c_bg))
        elems.append(text(f"c_txt_{idx}", cx + 11, c_y + 6, 15, 20, c_num, size=16, color=c_stroke))
        if idx < 3:
            elems.append(arrow(f"c_arr_{idx}", cx + c_rad, c_y + c_rad // 2, [[0, 0], [c_xs[idx+1] - cx - c_rad, 0]], stroke="#94a3b8", stroke_width=1.5))

    elems.append(text("g1_w2", 620, 175, 90, 35, "cảnh báo\nprompt", size=13, color="#b45309", align="center"))
    elems.append(text("g1_w4", 775, 175, 110, 35, "DỪNG CỨNG\n(loop hard stop)", size=14, color="#b91c1c", align="center"))
    elems.append(text("g1_sub", 535, 215, 490, 20, "Điều kiện: Quan sát không đổi qua nhiều hành động liên tiếp", size=13, color="#64748b"))

    # Gate 2: Step Budget Gate (y=265..425)
    elems.append(rect("gate2_box", 520, 265, 520, 160, stroke="#6d28d9", bg="#faf5ff", radius=3))
    elems.append(text("g2_title", 535, 275, 490, 22, "Chốt 2: Hết ngân sách bước (Budget = 0)", size=16, color="#6d28d9"))

    elems.append(rect("box_b0", 535, 305, 210, 45, stroke="#dc2626", bg="#fee2e2", radius=3))
    elems.append(text("txt_b0", 540, 317, 200, 24, "Ngân sách bước = 0", size=16, color="#b91c1c", align="center"))

    elems.append(arrow("arr_b0_w", 640, 350, [[0, 0], [0, 20]], stroke="#6d28d9", stroke_width=2))

    elems.append(rect("box_wrap", 535, 370, 210, 45, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("txt_wrap", 540, 378, 200, 30, "Lời gọi wrap-up\n(1 lần, thuần văn bản)", size=14, color="#5b21b6", align="center"))

    elems.append(text("txt_wrap_rule", 760, 335, 260, 50, "Chỉ được trả lời:\nsend_msg hoặc\nreport_infeasible", size=15, color="#6d28d9"))

    # End Node (Episode kết thúc) - placed centrally at bottom right
    elems.append(ellipse("end_node", 720, 475, 200, 75, stroke="#047857", bg="#a7f3d0"))
    elems.append(text("txt_end", 730, 495, 180, 35, "Episode\nkết thúc", size=19, color="#065f46", align="center"))

    # Routing all 3 termination routes with ZERO OVERLAPS
    # 1. Normal agent finish (leaves Action box at x=495, y=245, goes down channel at x=508 to y=512, into left of End Node at x=720)
    elems.append(arrow("arr_act_end", 495, 245, [[0, 0], [15, 0], [15, 267], [225, 267]], stroke="#047857", stroke_width=2))
    elems.append(text("lbl_act_end", 525, 490, 175, 20, "agent tự kết thúc ➔", size=14, color="#047857"))

    # 2. Gate 1 to End (leaves Gate 1 at x=1040, y=165, goes right to x=1055, down to y=512, into right of End Node at x=920)
    elems.append(arrow("arr_g1_end", 1040, 165, [[0, 0], [18, 0], [18, 347], [-138, 347]], stroke="#dc2626", stroke_width=2))

    # 3. Gate 2 to End (leaves wrap-up box at x=745, y=392, goes right to x=820, down to y=475 into top of End Node)
    elems.append(arrow("arr_g2_end", 745, 392, [[0, 0], [75, 0], [75, 83]], stroke="#6d28d9", stroke_width=2))

    # Summary band at bottom
    elems.append(rect("sum_solver", 20, 605, 1020, 45, stroke="#1e3a5f", bg="#f0f9ff", radius=3))
    elems.append(text("sum_s_txt", 25, 617, 1010, 22, "Tóm tắt: ReAct loop ➔ (1) Dừng cứng sau 4 lần lặp mục tiêu | (2) Wrap-up đúng 1 lần khi hết ngân sách", size=15, color="#1e40af", align="center"))

    return save_excalidraw("fig_solver.excalidraw", elems)


# ==============================================================================
# 6. FIG_DISCOVERY: Pipeline 4 Bước Phát Hiện Kỹ Năng
# ==============================================================================
def build_fig_discovery():
    elems = []
    # Title
    elems.append(text("title", 100, 15, 880, 26, "Skill Discovery Pipeline: 4 Giai Đoạn Phát Hiện Kỹ Năng", size=22, color="#1e40af", align="center"))

    # Left warning note for failed episodes
    elems.append(rect("fail_card", 20, 65, 200, 55, stroke="#dc2626", bg="#fef2f2", stroke_style="dashed", stroke_width=1.5, radius=3))
    elems.append(text("fail_note", 25, 72, 190, 40, "Episode thất bại:\nkhông vào pipeline này", size=13, color="#dc2626", align="center"))

    # Step 0: Input Trajectory (Oval)
    elems.append(ellipse("el_traj", 250, 60, 580, 65, stroke="#c2410c", bg="#ffedd5"))
    elems.append(text("el_t_txt", 260, 78, 560, 30, "Trajectory (task thành công)", size=20, color="#9a3412", align="center"))

    elems.append(arrow("arr_t_s1", 540, 125, [[0, 0], [0, 45]], stroke="#1e3a5f", stroke_width=2))
    elems.append(text("lbl_t_s1", 555, 137, 240, 22, "URL đổi / axtree giảm", size=15, color="#475569"))

    # Stage 1: Phân cắt (Segmentation)
    elems.append(rect("b_seg", 190, 170, 700, 80, stroke="#1e3a5f", bg="#93c5fd", radius=3))
    elems.append(text("b_seg_t", 200, 182, 680, 26, "1. Phân cắt (Segmentation)", size=19, color="#1e3a5f", align="center"))
    elems.append(text("b_seg_d", 200, 212, 680, 26, "(tách sub-trajectories theo ranh giới trạng thái)", size=16, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_s1_s2", 540, 250, [[0, 0], [0, 45]], stroke="#1e3a5f", stroke_width=2))
    elems.append(text("lbl_s1_s2", 555, 262, 260, 22, "LLM arbitrate + merge nav", size=15, color="#475569"))

    # Stage 2: Gom cụm (Clustering)
    elems.append(rect("b_clust", 190, 295, 700, 80, stroke="#1e3a5f", bg="#bfdbfe", radius=3))
    elems.append(text("b_clust_t", 200, 307, 680, 26, "2. Gom cụm (Clustering)", size=19, color="#1e3a5f", align="center"))
    elems.append(text("b_clust_d", 200, 337, 680, 26, "(cosine threshold / DP-means)", size=16, color="#1e3a5f", align="center"))

    elems.append(arrow("arr_s2_s3", 540, 375, [[0, 0], [0, 45]], stroke="#1e3a5f", stroke_width=2))
    elems.append(text("lbl_s2_s3", 555, 387, 260, 22, "cụm chín (≥ m lần, m=2)", size=15, color="#475569"))

    # Stage 3: Trừu tượng hóa (Abstraction)
    elems.append(rect("b_abs", 190, 420, 640, 80, stroke="#6d28d9", bg="#ede9fe", radius=3))
    elems.append(text("b_abs_t", 200, 432, 620, 26, "3. Trừu tượng hóa (Abstraction)", size=19, color="#5b21b6", align="center"))
    elems.append(text("b_abs_d", 200, 462, 620, 26, "(tham số hóa thành SkillCard)", size=16, color="#5b21b6", align="center"))

    # SkillCard Box on Right
    elems.append(arrow("arr_abs_sc", 830, 460, [[0, 0], [30, 0]], stroke="#6d28d9", stroke_width=2))
    elems.append(rect("b_sc", 860, 415, 180, 95, stroke="#334155", bg="#1e293b", radius=3))
    elems.append(text("sc_t", 870, 423, 160, 20, "SkillCard:", size=16, color="#93c5fd"))
    elems.append(text("sc_c", 870, 445, 160, 60, "• name\n• desc\n• params", size=15, color="#4ade80", font_family=3))

    elems.append(arrow("arr_s3_s4", 510, 500, [[0, 0], [0, 45]], stroke="#6d28d9", stroke_width=2))

    # Stage 4: Kiểm chứng (Verification Diamond)
    elems.append(diamond("dia_ver", 330, 545, 360, 115, stroke="#c2410c", bg="#fffbeb"))
    elems.append(text("dia_v_t", 340, 575, 340, 55, "4. Đạt kiểm chứng?\n(verify ≥ k lần)", size=17, color="#9a3412", align="center"))

    # Branch: Fail (Loại bỏ)
    elems.append(arrow("arr_v_fail", 690, 602, [[0, 0], [60, 0]], stroke="#dc2626", stroke_width=2))
    elems.append(text("lbl_v_fail", 705, 578, 40, 20, "fail", size=15, color="#dc2626"))

    elems.append(rect("b_fail_box", 750, 575, 160, 55, stroke="#dc2626", bg="#fef2f2", radius=3))
    elems.append(text("b_fail_txt", 755, 590, 150, 25, "Loại bỏ", size=17, color="#b91c1c", align="center"))

    # Branch: Pass (Skill Library)
    elems.append(arrow("arr_v_pass", 510, 660, [[0, 0], [0, 50]], stroke="#047857", stroke_width=2))
    elems.append(text("lbl_v_pass", 525, 672, 120, 22, "pass (≥ k lần)", size=15, color="#047857"))

    elems.append(ellipse("el_lib", 200, 710, 620, 65, stroke="#047857", bg="#a7f3d0"))
    elems.append(text("el_lib_t", 210, 728, 600, 30, "Thư viện Kỹ Năng (Skill Library)", size=20, color="#065f46", align="center"))

    return save_excalidraw("fig_discovery.excalidraw", elems)


# ==============================================================================
# 7. FIG_SEMANTIC: Sinh Semantic Task Bằng Ghép Chuỗi Operator
# ==============================================================================
def build_fig_semantic():
    elems = []
    # Title
    elems.append(text("title", 20, 15, 1040, 26, "Sinh Semantic Task Bằng Ghép Chuỗi Operator", size=22, color="#1e40af", align="center"))
    elems.append(text("subtitle", 20, 50, 1040, 22, "Đồ thị Operator: Precondition & Effect ở dạng trạng thái trang (Natural Language predicates)", size=16, color="#475569"))

    # ----------------- ROW 1: w1 -> w2 -----------------
    elems.append(rect("w1_box", 20, 85, 230, 115, stroke="#1e3a5f", bg="#93c5fd", radius=3))
    elems.append(text("w1_t", 25, 93, 220, 26, "w1 · login", size=19, color="#1e3a5f", align="center"))
    elems.append(text("w1_d", 25, 123, 220, 70, "pre: ở trang đăng nhập\neff: đã đăng nhập", size=15, color="#1e3a5f"))

    elems.append(arrow("arr_w1_s1", 250, 142, [[0, 0], [40, 0]], stroke="#1e3a5f", stroke_width=2))

    # Intermediate state 1
    elems.append(rect("s1_box", 290, 115, 185, 55, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("s1_t", 295, 125, 175, 35, "trạng thái: \"đã đăng nhập\"", size=14, color="#9a3412", align="center"))

    elems.append(arrow("arr_s1_w2", 475, 142, [[0, 0], [40, 0]], stroke="#1e3a5f", stroke_width=2))

    # w2: search_product
    elems.append(rect("w2_box", 515, 85, 255, 115, stroke="#1e3a5f", bg="#93c5fd", radius=3))
    elems.append(text("w2_t", 520, 93, 245, 26, "w2 · search_product", size=19, color="#1e3a5f", align="center"))
    elems.append(text("w2_d", 520, 123, 245, 70, "pre: đã đăng nhập\neff: đang xem danh sách SP", size=15, color="#1e3a5f"))

    elems.append(arrow("arr_w2_s2", 770, 142, [[0, 0], [40, 0]], stroke="#1e3a5f", stroke_width=2))

    # Intermediate state 2
    elems.append(rect("s2_box", 810, 115, 205, 55, stroke="#c2410c", bg="#ffedd5", radius=3))
    elems.append(text("s2_t", 815, 125, 195, 35, "trạng thái: \"đang xem DS SP\"", size=14, color="#9a3412", align="center"))

    # ----------------- ROW 2: w5 (branch) & w3 & w4 -----------------
    # w5: view_wishlist (dashed alternative branch)
    elems.append(arrow("arr_w1_w5", 135, 200, [[0, 0], [0, 45]], stroke="#64748b", stroke_style="dashed", stroke_width=1.5))
    elems.append(text("lbl_w5_branch", 145, 212, 80, 20, "nhánh rẽ", size=13, color="#64748b"))

    elems.append(rect("w5_box", 20, 245, 230, 105, stroke="#64748b", bg="#f1f5f9", stroke_style="dashed", stroke_width=1.5, radius=3))
    elems.append(text("w5_t", 25, 253, 220, 24, "w5 · view_wishlist", size=17, color="#475569", align="center"))
    elems.append(text("w5_d", 25, 280, 220, 65, "pre: đã đăng nhập\neff: đang xem wishlist", size=14, color="#64748b"))

    # Arrow from s2 down to w3
    elems.append(arrow("arr_s2_w3", 912, 170, [[0, 0], [0, 45], [-270, 45], [-270, 75]], stroke="#1e3a5f", stroke_width=2))

    # w3: add_to_cart
    elems.append(rect("w3_box", 515, 245, 255, 115, stroke="#1e3a5f", bg="#93c5fd", radius=3))
    elems.append(text("w3_t", 520, 253, 245, 26, "w3 · add_to_cart", size=19, color="#1e3a5f", align="center"))
    elems.append(text("w3_d", 520, 283, 245, 70, "pre: đang xem danh sách SP\neff: giỏ hàng có sản phẩm", size=15, color="#1e3a5f"))

    elems.append(arrow("arr_w3_w4", 770, 302, [[0, 0], [40, 0]], stroke="#64748b", stroke_style="dashed", stroke_width=1.5))

    # w4: checkout (dashed next step)
    elems.append(rect("w4_box", 810, 245, 205, 115, stroke="#64748b", bg="#f1f5f9", stroke_style="dashed", stroke_width=1.5, radius=3))
    elems.append(text("w4_t", 815, 253, 195, 24, "w4 · checkout", size=17, color="#475569", align="center"))
    elems.append(text("w4_d", 815, 280, 195, 70, "pre: giỏ có SP\neff: đơn đã xác nhận", size=14, color="#64748b"))

    # ----------------- ROW 3: Resulting Semantic Task (y=395..575) -----------------
    elems.append(arrow("arr_w3_res", 642, 360, [[0, 0], [0, 35]], stroke="#047857", stroke_width=2.5))

    elems.append(rect("box_res", 20, 395, 1040, 180, stroke="#047857", bg="#ecfdf5", radius=3))
    elems.append(text("res_title", 35, 405, 1010, 26, "Semantic Task sinh ra từ chuỗi ghép nối: w1 ➔ w2 ➔ w3", size=19, color="#065f46"))

    # Instruction Banner inside
    elems.append(rect("b_inst", 35, 440, 1010, 65, stroke="#047857", bg="#ffffff", radius=3))
    elems.append(text("inst_txt", 45, 455, 990, 35, "\"Từ /login: đăng nhập tài khoản, tìm kiếm sản phẩm rồi thêm sản phẩm đó vào giỏ hàng.\"", size=18, color="#047857", align="center"))

    elems.append(text("res_note1", 35, 515, 1010, 22, "• Instruction tổng hợp tự động từ description của w1 ➔ w2 ➔ w3 kèm URL khởi đầu của w1 (/login)", size=15, color="#065f46"))
    elems.append(text("res_note2", 35, 542, 1010, 22, "• Chuỗi operator (≥ 2 bước) tạo thành semantic task dài hạn (GOAL task), vượt khỏi phạm vi của từng trang đơn lẻ.", size=15, color="#065f46"))

    return save_excalidraw("fig_semantic.excalidraw", elems)


def render_all():
    figs = [
        ("fig_roadmap.excalidraw", "fig_roadmap.pdf"),
        ("fig_pipeline.excalidraw", "fig_pipeline.pdf"),
        ("fig_twolevel.excalidraw", "fig_twolevel.pdf"),
        ("fig_frontier.excalidraw", "fig_frontier.pdf"),
        ("fig_solver.excalidraw", "fig_solver.pdf"),
        ("fig_discovery.excalidraw", "fig_discovery.pdf"),
        ("fig_semantic.excalidraw", "fig_semantic.pdf"),
    ]

    for exc_name, pdf_name in figs:
        exc_path = os.path.join(OUT_DIR, exc_name)
        png_path = os.path.join(OUT_DIR, exc_name.replace(".excalidraw", ".png"))
        pdf_path = os.path.join(os.path.dirname(OUT_DIR), pdf_name)

        print(f"Rendering {exc_name}...")
        cmd = [
            "uv", "run", "python", RENDER_SCRIPT,
            exc_path,
            "--output", png_path,
            "--scale", "3",
            "--width", "4000"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Error rendering {exc_name}: {res.stderr}")
            continue

        print(f"Converting to {pdf_name}...")
        img = Image.open(png_path)
        img.convert("RGB").save(pdf_path, "PDF", resolution=300.0)
        print(f"✓ Saved {pdf_name} ({os.path.getsize(pdf_path):,} bytes)")

    print("\nAll figures regenerated successfully!")


if __name__ == "__main__":
    build_fig_roadmap()
    build_fig_pipeline()
    build_fig_twolevel()
    build_fig_frontier()
    build_fig_solver()
    build_fig_discovery()
    build_fig_semantic()
    render_all()
