#!/usr/bin/env python3
"""
Generate Excalidraw diagrams for HSGE Exploration:
1. fig_explore_control_flow.excalidraw: Control Flow của toàn bộ vòng lặp Explore (WebArenaExplorer)
2. fig_explore_dataflow.excalidraw: Dataflow chi tiết từ Web Environment -> Agents -> Discovery -> Operators -> Dataset

Can be opened and manually edited in Excalidraw (https://excalidraw.com) or VS Code Excalidraw extension.
"""

import json
import os
import sys
from pathlib import Path

def base_elem(id_val, el_type, x, y, width, height, **kwargs):
    return {
        "id": id_val,
        "type": el_type,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0,
        "strokeColor": kwargs.get("stroke", "#1e293b"),
        "backgroundColor": kwargs.get("bg", "transparent"),
        "fillStyle": kwargs.get("fill_style", "solid"),
        "strokeWidth": kwargs.get("stroke_width", 2),
        "strokeStyle": kwargs.get("stroke_style", "solid"),
        "roughness": kwargs.get("roughness", 0),
        "opacity": kwargs.get("opacity", 100),
        "groupIds": [],
        "frameId": None,
        "roundness": {"type": 3} if kwargs.get("radius", True) else None,
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
        "fontSize": kwargs.get("size", 14),
        "fontFamily": kwargs.get("font_family", 2),  # 2: Clean Helvetica/Sans
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

def save_excalidraw(filepath, elements):
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
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved Excalidraw config: {filepath}")


# ==============================================================================
# 1. DIAGRAM 1: CONTROL FLOW
# ==============================================================================
def build_control_flow():
    elems = []
    
    # Title
    elems.append(text("title", 40, 25, 1400, 35, 
                      "Luồng Điều Khiển Chi Tiết Quá Trình Khám Phá (Exploration Control Flow)", 
                      size=24, color="#1e3a8a", align="center"))
    elems.append(text("subtitle", 40, 65, 1400, 20, 
                      "WebArenaExplorer: Vòng lặp duyệt Frontier, Sinh tác vụ Cục bộ/Mục tiêu, Khai phá Kỹ năng & Mở rộng Không gian", 
                      size=14, color="#475569", align="center"))

    # Stage 1: Initialization & Frontier Queue (Top Left)
    elems.append(rect("s1_box", 40, 100, 320, 210, bg="#fff7ed", stroke="#ea580c", stroke_width=2))
    elems.append(text("s1_header", 55, 115, 290, 25, "1. KHỞI TẠO & HÀNG ĐỢI FRONTIER", size=15, color="#9a3412"))
    elems.append(text("s1_body", 55, 145, 290, 150, 
                      "• Bắt đầu từ root_url (Tier 0, Depth 0)\n"
                      "• Priority Queue: (tier, novelty, depth, seq, url)\n"
                      "   - Tier 0: Reached URLs (Ưu tiên cao nhất)\n"
                      "   - Tier 1: Mined <a href> từ trang\n"
                      "   - Novelty: Đếm số lần ghé template\n"
                      "• Bộ lọc: allow_pattern, deny_pattern\n"
                      "• Khôi phục trạng thái nếu --resume (checkpoint)", size=12, color="#7c2d12"))

    # Arrow S1 -> Decision Loop
    elems.append(arrow("a1", 360, 205, [[0, 0], [60, 0]], stroke="#ea580c", stroke_width=2))

    # Decision Diamond: Loop condition
    elems.append(diamond("d_loop", 420, 145, 200, 120, bg="#fef08a", stroke="#ca8a04", stroke_width=2))
    elems.append(text("d_loop_txt", 440, 180, 160, 50, "Frontier còn URL\n& Visited < max_nodes?", size=13, color="#713f12", align="center"))

    # End Node (If No)
    elems.append(arrow("a_end", 520, 265, [[0, 0], [0, 40]], stroke="#dc2626", stroke_width=2))
    elems.append(rect("end_box", 440, 305, 160, 70, bg="#fee2e2", stroke="#dc2626", stroke_width=2))
    elems.append(text("end_txt", 450, 320, 140, 40, "KẾT THÚC RUN\nXuất Dataset & Summary", size=13, color="#991b1b", align="center"))

    # Arrow Decision -> Stage 2 (If Yes)
    elems.append(arrow("a2", 620, 205, [[0, 0], [60, 0]], stroke="#16a34a", stroke_width=2))
    elems.append(text("a2_label", 625, 185, 50, 20, "Có (Pop)", size=12, color="#16a34a"))

    # Stage 2: Page Loading, Deduplication & Site Seeding
    elems.append(rect("s2_box", 680, 100, 350, 210, bg="#f0f9ff", stroke="#0284c7", stroke_width=2))
    elems.append(text("s2_header", 695, 115, 320, 25, "2. LOAD TRANG & KHỬ TRÙNG LẶP", size=15, color="#0369a1"))
    elems.append(text("s2_body", 695, 145, 320, 150, 
                      "• Kiểm tra per-template cap (ngừa bão hòa)\n"
                      "• Mở Browser: browser_factory(url).reset()\n"
                      "   - Bắt lỗi timeout / fail-soft an toàn\n"
                      "• Khử trùng lặp đa tầng:\n"
                      "   - landed URL: URL thực tế sau redirect\n"
                      "   - content_hash: SHA-256(axtree) (bỏ qua)\n"
                      "• Site Seeding (Node 1): Tạo hồ sơ website\n"
                      "   SiteSeeder.derive(obs) -> {description, capabilities}", size=12, color="#075985"))

    # Arrow S2 -> Stage 3
    elems.append(arrow("a3", 1030, 205, [[0, 0], [60, 0]], stroke="#0284c7", stroke_width=2))

    # Stage 3: Task Proposals & Solving (Right Column)
    elems.append(rect("s3_container", 1090, 100, 400, 830, bg="#f8fafc", stroke="#64748b", stroke_width=2, stroke_style="dashed"))
    elems.append(text("s3_header", 1105, 115, 370, 25, "3. THỰC THI NHIỆM VỤ TẠI TRANG (TASKS)", size=16, color="#1e293b", align="center"))

    # Step 3A: Local Tasks
    elems.append(rect("s3a_box", 1105, 150, 370, 190, bg="#ecfdf5", stroke="#059669", stroke_width=2))
    elems.append(text("s3a_title", 1115, 160, 350, 25, "3A. Local Exploration (PageExplorer)", size=14, color="#065f46"))
    elems.append(text("s3a_body", 1115, 185, 350, 145, 
                      "• PageExplorer.propose(obs, screenshot, seed):\n"
                      "   - Đề xuất task thực tế: COMPOSITE, MOD, INFO\n"
                      "• Solver.solve(browser, task, max_steps):\n"
                      "   - Vòng lặp quan sát [bid] -> suy nghĩ -> action\n"
                      "   - Hỗ trợ task_retries khi gặp sự cố\n"
                      "• Ghi chép Episode: _record(...) -> SFT data\n"
                      "• Nếu Thành công -> nạp vào Discovery Loop", size=12, color="#047857"))

    # Step 3B: Unprefixed Sampling (Optional)
    elems.append(rect("s3b_box", 1105, 355, 370, 160, bg="#eff6ff", stroke="#3b82f6", stroke_width=2))
    elems.append(text("s3b_title", 1115, 365, 350, 25, "3B. Unprefixed Sampling (Tùy chọn)", size=14, color="#1e40af"))
    elems.append(text("s3b_body", 1115, 390, 350, 120, 
                      "• Chạy lại các task vừa giải thành công tại node,\n"
                      "  nhưng bắt đầu từ trang gốc (root_url).\n"
                      "• Mục đích: Rèn luyện kỹ năng điều hướng tìm trang\n"
                      "  cho Agent, khắc phục thiên kiến quỹ đạo 1 bước.", size=12, color="#1d4ed8"))

    # Step 3C: Goal Tasks
    elems.append(rect("s3c_box", 1105, 530, 370, 220, bg="#f5f3ff", stroke="#7c3aed", stroke_width=2))
    elems.append(text("s3c_title", 1115, 540, 350, 25, "3C. Goal-Conditioned Tasks (GOAL)", size=14, color="#5b21b6"))
    elems.append(text("s3c_body", 1115, 565, 350, 175, 
                      "• Sinh tác vụ phức hợp từ _goal_task(url):\n"
                      "   1) Operator Chains (opgraph.all_chains len>=2)\n"
                      "   2) Seed Capabilities từ site_seed\n"
                      "   3) Terminal Goal (e.g. order_confirmed)\n"
                      "• Phân rã mục tiêu: GoalPlanner.plan -> subgoals\n"
                      "• Solver thực thi với ngân sách goal_max_steps\n"
                      "• Thẩm định Episode: EpisodeJudge (LLM Judge)\n"
                      "  loại bỏ các ca Agent tự ngộ nhận (False Success)", size=12, color="#6d28d9"))

    # Step 3D: Summary at task container
    elems.append(text("s3_note", 1115, 765, 350, 150, 
                      "✦ Ghi nhận URLs đi qua (seen_urls)\n"
                      "✦ Thu thập toàn bộ Tab / Navigation events\n"
                      "✦ Cập nhật thống kê task_stats (Success/Fail/Infeasible)", size=12, color="#475569"))

    # Stage 4: Discovery & Operator Promotion (Bottom Left)
    elems.append(rect("s4_box", 560, 480, 470, 260, bg="#faf5ff", stroke="#9333ea", stroke_width=2))
    elems.append(text("s4_header", 575, 495, 440, 25, "4. DISCOVERY & TIẾN HÓA OPERATOR", size=15, color="#6b21a8"))
    elems.append(text("s4_body", 575, 525, 440, 205, 
                      "• Trajectory Ingestion: Discovery.on_trajectory(steps)\n"
                      "   - Segmentation: TrajectorySegmenter cắt sub-trajectories\n"
                      "   - Clustering: Gom cụm ngữ nghĩa & Embedder\n"
                      "   - SkillAbstractor: Trừu tượng hóa thành SkillCard\n"
                      "• Điều kiện chín muồi: Xuất hiện lặp lại >= maturity (2 lần)\n"
                      "• Quy nạp Toán tử (_promote_skill_to_operator):\n"
                      "   - OperatorInducer: Suy diễn Preconditions & Effects\n"
                      "   - PredicateRegistry: Chuẩn hóa NL -> Canonical IDs (p0, p1..)\n"
                      "   - Lọc Tautology & Grounding check (độ chính xác >= 50%)\n"
                      "• Nạp Operator mới vào OperatorGraph để phục vụ bước 3C", size=12, color="#581c87"))

    # Arrow from 3A/3B/3C to 4 (Skill feeding)
    elems.append(arrow("a_disc", 1105, 290, [[0, 0], [-75, 0], [-75, 230]], stroke="#9333ea", stroke_width=2))
    elems.append(text("a_disc_lbl", 985, 380, 100, 40, "Quỹ đạo\nthành công", size=12, color="#9333ea", align="center"))

    # Arrow from 4 to 3C (Operators feed Goal Planner)
    elems.append(arrow("a_op_feed", 1030, 640, [[0, 0], [75, 0]], stroke="#7c3aed", stroke_width=2))
    elems.append(text("a_op_lbl", 1035, 615, 70, 20, "Cung cấp Op", size=11, color="#7c3aed"))

    # Stage 5: Frontier Expansion (Bottom Left)
    elems.append(rect("s5_box", 40, 480, 470, 260, bg="#fff1f2", stroke="#e11d48", stroke_width=2))
    elems.append(text("s5_header", 55, 495, 440, 25, "5. MỞ RỘNG FRONTIER (FRONTIER EXPANSION)", size=15, color="#9f1239"))
    elems.append(text("s5_body", 55, 525, 440, 205, 
                      "• Nếu depth < max_depth:\n"
                      "   [Tier 0 - Ưu tiên tuyệt đối]:\n"
                      "   - URLs mà Solver thực sự đã điều hướng tới khi giải task\n"
                      "   - Các open tabs phát sinh trong phiên duyệt\n"
                      "   - Áp dụng reached_template_cap (tránh spam cùng loại)\n\n"
                      "   [Tier 1 - Khai phá liên kết tĩnh]:\n"
                      "   - Quét các thẻ <a href> trên trang (page_hrefs)\n"
                      "   - Gated bởi per_template_cap nghiêm ngặt\n"
                      "• Đẩy vào Priority Queue Frontier: _push(tier, url, depth+1, novelty)", size=12, color="#881337"))

    # Arrow from Stage 3 to Stage 5
    elems.append(arrow("a_seen", 1105, 730, [[0, 0], [-70, 0], [-70, 100], [-800, 100], [-800, -90]], stroke="#e11d48", stroke_width=2))
    elems.append(text("a_seen_lbl", 600, 810, 250, 20, "seen_urls & page hrefs -> Frontier", size=12, color="#e11d48", align="center"))

    # Stage 6: Persistence & Checkpoint (Bottom)
    elems.append(rect("s6_box", 40, 790, 990, 140, bg="#f0fdfa", stroke="#0d9488", stroke_width=2))
    elems.append(text("s6_header", 55, 805, 960, 25, "6. LƯU CHECKPOINT & XUẤT ARTIFACTS DỮ LIỆU", size=15, color="#115e59"))
    elems.append(text("s6_body", 55, 835, 960, 85, 
                      "• Ghi checkpoint.pkl an toàn (Atomic dump, tách backends unpicklable) -> Hỗ trợ resume mọi lúc.\n"
                      "• Xuất bản tệp trạng thái: skills.json (thư viện kỹ năng), operators.json & predicates.json (đồ thị toán tử),\n"
                      "  graph.json (đồ thị trạng thái), nodes.json & summary.json (báo cáo tiến độ & thống kê), run_log.jsonl (event stream).", size=12, color="#134e4a"))

    # Loop Back Arrow from S6 to Decision Node
    elems.append(arrow("a_loop_back", 40, 860, [[0, 0], [-20, 0], [-20, -655], [480, -655]], stroke="#ea580c", stroke_width=2, stroke_style="dashed"))
    elems.append(text("a_loop_lbl", 10, 450, 20, 100, "VÒNG LẶP TIẾP THEO", size=11, color="#ea580c"))

    return elems


# ==============================================================================
# 2. DIAGRAM 2: DATAFLOW
# ==============================================================================
def build_dataflow():
    elems = []
    
    # Title
    elems.append(text("df_title", 40, 25, 1520, 35, 
                      "Luồng Dữ Liệu Chi Tiết Quá Trình Khám Phá (Exploration Dataflow & Representations)", 
                      size=24, color="#1e3a8a", align="center"))
    elems.append(text("df_subtitle", 40, 65, 1520, 20, 
                      "Chi tiết định dạng dữ liệu vào/ra qua từng Agent, Trạng thái Web, Thư viện Kỹ năng và Tập dữ liệu SFT", 
                      size=14, color="#475569", align="center"))

    # Column 1: Web Environment & Profiling (X: 40 - 280)
    col1_x = 40
    elems.append(rect("c1_bg", col1_x, 100, 260, 820, bg="#f8fafc", stroke="#94a3b8", stroke_width=1, stroke_style="dashed"))
    elems.append(text("c1_hdr", col1_x + 10, 110, 240, 25, "1. WEB ENVIRONMENT", size=15, color="#1e293b", align="center"))

    elems.append(rect("c1_browser", col1_x + 10, 150, 240, 120, bg="#e0f2fe", stroke="#0284c7", stroke_width=2))
    elems.append(text("c1_b_title", col1_x + 20, 160, 220, 20, "Playwright Browser", size=14, color="#0369a1"))
    elems.append(text("c1_b_body", col1_x + 20, 185, 220, 75, 
                      "• Live DOM & Accessibility Tree\n"
                      "• Element [bid] tags\n"
                      "• Screenshots + Set-of-Marks\n"
                      "• Navigation & Active tabs", size=11, color="#075985"))

    elems.append(rect("c1_seed", col1_x + 10, 300, 240, 150, bg="#fef3c7", stroke="#d97706", stroke_width=2))
    elems.append(text("c1_s_title", col1_x + 20, 310, 220, 20, "SiteSeeder Agent", size=14, color="#92400e"))
    elems.append(text("c1_s_body", col1_x + 20, 335, 220, 105, 
                      "[Input]: Landing page axtree\n"
                      "[Prompt]: SEEDER_SYS\n"
                      "[Output]: site_seed JSON\n"
                      "• description\n"
                      "• capabilities: [{name, goal}]", size=11, color="#78350f"))

    elems.append(rect("c1_frontier", col1_x + 10, 480, 240, 200, bg="#fff7ed", stroke="#ea580c", stroke_width=2))
    elems.append(text("c1_f_title", col1_x + 20, 490, 220, 20, "Frontier Priority Queue", size=14, color="#9a3412"))
    elems.append(text("c1_f_body", col1_x + 20, 515, 220, 155, 
                      "Heapq Data Structure:\n"
                      "Tuple: (tier, novelty, depth, seq, url)\n"
                      "• Tier 0: Reached URLs\n"
                      "• Tier 1: Mined <a href>\n"
                      "• Per-template counts\n"
                      "• Deduplication sets:\n"
                      "   - visited, queued, landed\n"
                      "   - seen_content (SHA-256)", size=11, color="#7c2d12"))

    # Column 2: Dual Task Generation (X: 330 - 590)
    col2_x = 330
    elems.append(rect("c2_bg", col2_x, 100, 270, 820, bg="#f8fafc", stroke="#94a3b8", stroke_width=1, stroke_style="dashed"))
    elems.append(text("c2_hdr", col2_x + 10, 110, 250, 25, "2. TASK GENERATION", size=15, color="#1e293b", align="center"))

    elems.append(rect("c2_pexp", col2_x + 10, 150, 250, 220, bg="#ecfdf5", stroke="#059669", stroke_width=2))
    elems.append(text("c2_pe_title", col2_x + 20, 160, 230, 20, "PageExplorer Agent", size=14, color="#065f46"))
    elems.append(text("c2_pe_body", col2_x + 20, 185, 230, 175, 
                      "[Inputs]:\n"
                      "• obs: axtree, url\n"
                      "• screenshot_b64 (SoM)\n"
                      "• site_seed context\n"
                      "[Prompt]: EXPLORER_SYS\n"
                      "[Output Data]: JSON tasks\n"
                      "• COMPOSITE (multi-step intent)\n"
                      "• MOD (state mutating)\n"
                      "• INFO (read-only fact lookup)", size=11, color="#047857"))

    elems.append(rect("c2_planner", col2_x + 10, 400, 250, 240, bg="#f5f3ff", stroke="#7c3aed", stroke_width=2))
    elems.append(text("c2_pl_title", col2_x + 20, 410, 230, 20, "GoalPlanner & Chaining", size=14, color="#5b21b6"))
    elems.append(text("c2_pl_body", col2_x + 20, 435, 230, 195, 
                      "[Inputs]:\n"
                      "• OperatorGraph structure\n"
                      "• site_seed capabilities\n"
                      "[Mechanism]:\n"
                      "• all_chains(min_len=2)\n"
                      "• Subgoal decomposition\n"
                      "[Output Data]: Composed Goal\n"
                      "• Goal text: '1) OpA 2) OpB..'\n"
                      "• difficulty = chain length\n"
                      "• goal_predicate check", size=11, color="#6d28d9"))

    # Arrows Col 1 -> Col 2
    elems.append(arrow("a_c1_c2_a", col1_x + 250, 210, [[0, 0], [40, 0]], stroke="#059669", stroke_width=2))
    elems.append(arrow("a_c1_c2_b", col1_x + 250, 375, [[0, 0], [40, 0], [40, -100]], stroke="#d97706", stroke_width=1.5, stroke_style="dashed"))

    # Column 3: Online Solving & Trajectory (X: 630 - 910)
    col3_x = 630
    elems.append(rect("c3_bg", col3_x, 100, 280, 820, bg="#f8fafc", stroke="#94a3b8", stroke_width=1, stroke_style="dashed"))
    elems.append(text("c3_hdr", col3_x + 10, 110, 260, 25, "3. SOLVER & TRAJECTORY", size=15, color="#1e293b", align="center"))

    elems.append(rect("c3_solver", col3_x + 10, 150, 260, 240, bg="#eff6ff", stroke="#2563eb", stroke_width=2))
    elems.append(text("c3_sv_title", col3_x + 20, 160, 240, 20, "Solver / GoalSolver Agent", size=14, color="#1e40af"))
    elems.append(text("c3_sv_body", col3_x + 20, 185, 240, 195, 
                      "[Inputs]: task, browser, max_steps\n"
                      "[Step-by-Step Action Loop]:\n"
                      "• Step Obs: url, axtree [bid], error\n"
                      "• Solver LLM -> {\n"
                      "    'thought': 'click add to cart..',\n"
                      "    'action': 'click(\"45\")'\n"
                      "  }\n"
                      "[Outputs]:\n"
                      "• steps: list[Step]\n"
                      "• success: bool, infeasible: bool\n"
                      "• urls_seen: set[str]", size=11, color="#1d4ed8"))

    elems.append(rect("c3_judge", col3_x + 10, 420, 260, 150, bg="#fdf2f8", stroke="#db2777", stroke_width=2))
    elems.append(text("c3_j_title", col3_x + 20, 430, 240, 20, "EpisodeJudge (Verifier)", size=14, color="#9d174d"))
    elems.append(text("c3_j_body", col3_x + 20, 455, 240, 105, 
                      "[Inputs]: goal, action history,\n"
                      "  final_url, final_axtree\n"
                      "[Prompt]: JUDGE_SYS\n"
                      "[Output]: {verdict: PASS/FAIL}\n"
                      "-> Chống Agent tự tích điểm ảo", size=11, color="#831843"))

    elems.append(rect("c3_record", col3_x + 10, 600, 260, 140, bg="#f1f5f9", stroke="#475569", stroke_width=2))
    elems.append(text("c3_rec_title", col3_x + 20, 610, 240, 20, "Episode Recording (_record)", size=14, color="#334155"))
    elems.append(text("c3_rec_body", col3_x + 20, 635, 240, 95, 
                      "Lưu vào episodes/ep_XXXX/:\n"
                      "• episode.jsonl (step records)\n"
                      "• episode_meta.json (outcome, tags)\n"
                      "• page_state/step_XXX_axtree.txt\n"
                      "• page_state/step_XXX_screenshot.jpg", size=11, color="#1e293b"))

    # Arrows Col 2 -> Col 3
    elems.append(arrow("a_c2_c3_a", col2_x + 260, 260, [[0, 0], [40, 0]], stroke="#2563eb", stroke_width=2))
    elems.append(arrow("a_c2_c3_b", col2_x + 260, 520, [[0, 0], [30, 0], [30, -250], [40, -250]], stroke="#7c3aed", stroke_width=2))

    # Arrow inside Col 3
    elems.append(arrow("a_sv_j", col3_x + 140, 390, [[0, 0], [0, 30]], stroke="#db2777", stroke_width=2))
    elems.append(arrow("a_j_rec", col3_x + 140, 570, [[0, 0], [0, 30]], stroke="#475569", stroke_width=2))

    # Column 4: Discovery, Skills & Hierarchical Graph (X: 940 - 1220)
    col4_x = 940
    elems.append(rect("c4_bg", col4_x, 100, 280, 820, bg="#f8fafc", stroke="#94a3b8", stroke_width=1, stroke_style="dashed"))
    elems.append(text("c4_hdr", col4_x + 10, 110, 260, 25, "4. DISCOVERY & SKILLS", size=15, color="#1e293b", align="center"))

    elems.append(rect("c4_segment", col4_x + 10, 150, 260, 160, bg="#faf5ff", stroke="#9333ea", stroke_width=2))
    elems.append(text("c4_seg_title", col4_x + 20, 160, 240, 20, "TrajectorySegmenter", size=14, color="#6b21a8"))
    elems.append(text("c4_seg_body", col4_x + 20, 185, 240, 115, 
                      "[Inputs]: Successful steps, task\n"
                      "[Mechanism]: Phân tích ngữ nghĩa +\n"
                      "  chuyển dịch trạng thái axtree\n"
                      "[Output]: list[SubTrajectory]\n"
                      "  (Các đơn vị thao tác nguyên tử)", size=11, color="#581c87"))

    elems.append(rect("c4_lib", col4_x + 10, 340, 260, 220, bg="#faf5ff", stroke="#9333ea", stroke_width=2))
    elems.append(text("c4_lib_title", col4_x + 20, 350, 240, 20, "SkillLibrary & Abstractor", size=14, color="#6b21a8"))
    elems.append(text("c4_lib_body", col4_x + 20, 375, 240, 175, 
                      "[Inputs]: SubTrajectories\n"
                      "[Mechanism]:\n"
                      "• Embedder: vector hóa sub-trajectories\n"
                      "• Clustering: gom cụm tương đồng\n"
                      "• SkillAbstractor LLM -> SkillCard\n"
                      "• Maturity Gate: Số lần lặp >= 2\n"
                      "[Output]: Admitted SkillCard\n"
                      "  {skill_id, name, description, members}", size=11, color="#581c87"))

    elems.append(rect("c4_hgraph", col4_x + 10, 590, 260, 150, bg="#faf5ff", stroke="#9333ea", stroke_width=2))
    elems.append(text("c4_hg_title", col4_x + 20, 600, 240, 20, "HierarchicalGraph", size=14, color="#6b21a8"))
    elems.append(text("c4_hg_body", col4_x + 20, 625, 240, 105, 
                      "Biểu diễn phân cấp trạng thái:\n"
                      "• Low-level URL trajectory edges\n"
                      "• State -> Skill mapping\n"
                      "• Skill -> Skill composition links\n"
                      "-> Xuất ra graph.json", size=11, color="#581c87"))

    # Arrow Col 3 -> Col 4 (Successful trajectories feed discovery)
    elems.append(arrow("a_c3_c4", col3_x + 270, 230, [[0, 0], [40, 0]], stroke="#9333ea", stroke_width=2))
    elems.append(text("a_c3_c4_lbl", col3_x + 275, 205, 70, 20, "Success", size=11, color="#9333ea"))

    # Arrows inside Col 4
    elems.append(arrow("a_seg_lib", col4_x + 140, 310, [[0, 0], [0, 30]], stroke="#9333ea", stroke_width=2))
    elems.append(arrow("a_lib_hg", col4_x + 140, 560, [[0, 0], [0, 30]], stroke="#9333ea", stroke_width=2))

    # Column 5: Operator Induction & Dataset (X: 1250 - 1530)
    col5_x = 1250
    elems.append(rect("c5_bg", col5_x, 100, 280, 820, bg="#f8fafc", stroke="#94a3b8", stroke_width=1, stroke_style="dashed"))
    elems.append(text("c5_hdr", col5_x + 10, 110, 260, 25, "5. OPERATOR & DATASET", size=15, color="#1e293b", align="center"))

    elems.append(rect("c5_inducer", col5_x + 10, 150, 260, 220, bg="#fdf4ff", stroke="#c026d3", stroke_width=2))
    elems.append(text("c5_ind_title", col5_x + 20, 160, 240, 20, "Operator Induction & Predicates", size=14, color="#86198f"))
    elems.append(text("c5_ind_body", col5_x + 20, 185, 240, 175, 
                      "[Inputs]: SkillCard + boundary axtrees\n"
                      "[Mechanism]:\n"
                      "• OperatorInducer: Rút trích NL Pre/Eff\n"
                      "• PredicateRegistry: Chuẩn hóa NL\n"
                      "  thành Canonical Predicate IDs (p0, p1..)\n"
                      "• Grounding Verifier: Kiểm tra độ chính\n"
                      "  xác effect trên mọi member (>= 50%)\n"
                      "[Output]: Operator(name, pre, eff)", size=11, color="#701a75"))

    elems.append(rect("c5_opgraph", col5_x + 10, 400, 260, 150, bg="#fdf4ff", stroke="#c026d3", stroke_width=2))
    elems.append(text("c5_opg_title", col5_x + 20, 410, 240, 20, "OperatorGraph (Planning)", size=14, color="#86198f"))
    elems.append(text("c5_opg_body", col5_x + 20, 435, 240, 105, 
                      "Đồ thị tiền điều kiện / hiệu ứng:\n"
                      "• Graph các toán tử logic\n"
                      "• Tìm chuỗi thực thi (all_chains)\n"
                      "-> Xuất operators.json & predicates.json", size=11, color="#701a75"))

    elems.append(rect("c5_sft", col5_x + 10, 590, 260, 150, bg="#ecfdf5", stroke="#059669", stroke_width=2))
    elems.append(text("c5_sft_title", col5_x + 20, 600, 240, 20, "SFT Dataset & SLM Training", size=14, color="#065f46"))
    elems.append(text("c5_sft_body", col5_x + 20, 625, 240, 105, 
                      "Đầu ra huấn luyện Web Agent:\n"
                      "• build_sft_dataset.py đọc episodes/\n"
                      "• Format dữ liệu đa phương thức\n"
                      "  (Axtree/SoM -> Thought + Action)\n"
                      "• Fine-tuning SLMs (Qwen, LLaMA..)", size=11, color="#047857"))

    # Arrow Col 4 -> Col 5 (Admitted skills promoted to operators)
    elems.append(arrow("a_c4_c5", col4_x + 270, 450, [[0, 0], [40, 0], [40, -190], [50, -190]], stroke="#c026d3", stroke_width=2))
    elems.append(text("a_c4_c5_lbl", col4_x + 275, 340, 70, 20, "Promotion", size=11, color="#c026d3"))

    # Arrow inside Col 5
    elems.append(arrow("a_ind_opg", col5_x + 140, 370, [[0, 0], [0, 30]], stroke="#c026d3", stroke_width=2))

    # Feedback Loop Arrow: Col 5 (OperatorGraph) back to Col 2 (GoalPlanner)
    elems.append(arrow("a_feedback_op", col5_x + 140, 550, [[0, 0], [0, 280], [-800, 280], [-800, 100], [-810, 100]], stroke="#7c3aed", stroke_width=2, stroke_style="dashed"))
    elems.append(text("a_feed_lbl", 800, 840, 300, 25, "FEEDBACK LOOP: OperatorGraph cung cấp chuỗi cho GoalPlanner sinh Task mới", size=12, color="#7c3aed", align="center"))

    # Arrow Episodes -> SFT Dataset (Direct Build)
    elems.append(arrow("a_rec_sft", col3_x + 270, 670, [[0, 0], [350, 0]], stroke="#059669", stroke_width=2))
    elems.append(text("a_sft_lbl", col3_x + 360, 645, 230, 20, "Direct Build (Không cần lọc ngoại tuyến)", size=11, color="#059669", align="center"))

    return elems


# ==============================================================================
# 3. DIAGRAM 3: DIRECT SFT DATASET PACKAGING (FOR SLIDE 11)
# ==============================================================================
def build_fig_curation():
    elems = []
    # Title
    elems.append(text("cur_title", 20, 15, 340, 24, "Kiểm Định Trực Tuyến & Đóng Gói SFT", size=16, color="#1e40af", align="center"))

    # Stage 1: Inline Quality Gates in Runtime Loop
    elems.append(rect("b_inline", 20, 50, 340, 160, stroke="#0284c7", bg="#f0f9ff", radius=3))
    elems.append(text("b_in_t", 30, 60, 320, 20, "1. CỔNG CHẤT LƯỢNG TRỰC TUYẾN", size=13, color="#0369a1", align="center"))
    elems.append(text("b_in_d", 30, 85, 320, 115, 
                      "• Chạy ngay trong vòng lặp khám phá (runtime)\n"
                      "• Inline LLM Judge: Chấm lại trạng thái đích\n"
                      "  loại bỏ 801 episode (27.4%) báo đỗ ảo\n"
                      "• Cổng Effective Action: Chặn task tự khai\n"
                      "  nhưng không làm đổi trạng thái web", size=11, color="#075985"))

    elems.append(arrow("a_in_ep", 190, 210, [[0, 0], [0, 35]], stroke="#0284c7", stroke_width=2))

    # Stage 2: Clean Trajectories Storage
    elems.append(rect("b_eps", 20, 245, 340, 120, stroke="#7c3aed", bg="#f5f3ff", radius=3))
    elems.append(text("b_ep_t", 30, 255, 320, 20, "2. KHO TRAJECTORIES SẠCH", size=13, color="#5b21b6", align="center"))
    elems.append(text("b_ep_d", 30, 280, 320, 75, 
                      "• Thư mục episodes/ep_XXXX/ đạt chuẩn\n"
                      "• 1760 trajectory sạch / 8554 mẫu SFT\n"
                      "• Giữ nguyên lịch sử quan sát & CoT chuẩn", size=11, color="#6d28d9"))

    elems.append(arrow("a_ep_sft", 190, 365, [[0, 0], [0, 35]], stroke="#059669", stroke_width=2.5))
    elems.append(text("a_ep_lbl", 195, 375, 120, 18, "Build trực tiếp", size=11, color="#059669"))

    # Stage 3: Direct SFT Dataset Packaging
    elems.append(rect("b_direct", 20, 400, 340, 175, stroke="#059669", bg="#ecfdf5", radius=3))
    elems.append(text("b_dir_t", 30, 410, 320, 20, "3. ĐÓNG GÓI SFT TRỰC TIẾP", size=13, color="#065f46", align="center"))
    elems.append(text("b_dir_d", 30, 435, 320, 130, 
                      "• build_sft_dataset.py xuất trực tiếp dataset\n"
                      "• KHÔNG CẦN khâu lọc ngoại tuyến (no curation)\n"
                      "• Nguyên tắc Prompt Parity: Khớp từng byte\n"
                      "  giữa prompt huấn luyện và suy luận\n"
                      "• Đưa thẳng vào Fine-tuning LoRA SLM", size=11, color="#047857"))

    return elems


def main():
    target_dirs = [
        Path("/Users/Kiet/Documents/Code/WebAgent/Phat/Skill_Operator/Thesis_report/Slide_KLTN_HSGE/images"),
        Path("/Users/Kiet/Documents/Code/WebAgent/Phat/Skill_Operator/Thesis_report/thesis_hsge_vi/Figures/excalidraw_src"),
    ]

    cf_elems = build_control_flow()
    df_elems = build_dataflow()
    cur_elems = build_fig_curation()

    for out_dir in target_dirs:
        out_dir.mkdir(parents=True, exist_ok=True)
        cf_path = out_dir / "fig_explore_control_flow.excalidraw"
        df_path = out_dir / "fig_explore_dataflow.excalidraw"
        cur_path = out_dir / "fig_curation.excalidraw"
        
        save_excalidraw(str(cf_path), cf_elems)
        save_excalidraw(str(df_path), df_elems)
        save_excalidraw(str(cur_path), cur_elems)

    # Render directly
    render_script = Path("/Users/Kiet/Documents/Code/WebAgent/Phat/Skill_Operator/.claude/skills/excalidraw-diagram/references/render_excalidraw.py")
    if render_script.exists():
        from PIL import Image
        import subprocess
        for name in ["fig_explore_control_flow", "fig_explore_dataflow", "fig_curation"]:
            src = target_dirs[0] / f"{name}.excalidraw"
            png = target_dirs[0] / f"{name}.png"
            pdf = target_dirs[0] / f"{name}.pdf"
            print(f"Rendering {name}...")
            subprocess.run(["python3", str(render_script), str(src), "--output", str(png)], check=True)
            img = Image.open(png)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(pdf, "PDF", resolution=300.0)
            print(f"✓ Saved {pdf}")

    print("\n✅ Successfully generated and rendered all Excalidraw diagrams!")

if __name__ == "__main__":
    main()
