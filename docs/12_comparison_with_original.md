# HSGE Project Comparison: `hsge_project` vs `hsge_project_raw`

> **Date:** 2026-06-11  
> **Purpose:** Ghi nhận đầy đủ mọi thay đổi đã thực hiện so với bản gốc (`hsge_project_raw`).

---

## Tổng quan

| | `hsge_project_raw` (gốc) | `hsge_project` (hiện tại) |
|---|---|---|
| Số file nguồn | 38 | **48** (+10 mới, −1 xóa) |
| Tổng dòng code runtime | ~135 | ~641 (+506) |
| Tổng dòng run_webarena | ~91 | ~266 (+175) |
| File bị xóa | — | `compare_three_way.py` |

**10 file mới thêm vào:**

| File | Mô tả |
|---|---|
| `.env` / `.env.example` / `.gitignore` | Cấu hình môi trường & git |
| `analyze_frontier.py` | Script phân tích frontier clusters |
| `recover_checkpoint.py` | Script khôi phục checkpoint |
| `hsge/webarena/frontier_filter.py` | **Frontier Filter** — lọc URL theo template clustering |
| `docs/05_frontier_filter.md` | Tài liệu frontier filter |
| `docs/06_code_reference.md` | Tài liệu tham khảo code |
| `docs/07_presenting_code.md` | Hướng dẫn trình bày code |
| `docs/10_changelog.md` | Changelog |
| `docs/11_frontier_filter_deep_dive.md` | Phân tích sâu frontier filter |

**1 file bị xóa:** `compare_three_way.py`

---

## VẤN ĐỀ 1: Multi-Provider LLM & Tách Explorer/Solver

### Vấn đề gốc
Code gốc chỉ hỗ trợ OpenAI, một model duy nhất cho cả explorer & solver, không có `.env` loader, không có vision support.

### Thay đổi

| File | Thay đổi chính |
|---|---|
| **`run_webarena.py`** | +175 dòng. Thêm: `.env` loader (`_load_dotenv`), provider presets (deepseek/openai/custom), `_resolve_models()` tách explorer_model & solver_model, `_resolve_api_config()`, `_check_overwrite_safety()`, CLI args mới (`--provider`, `--explorer-model`, `--solver-model`, `--resume`, `--screenshot`), hỗ trợ `complete_vision_json` trong `_DryLLM` |
| **`hsge/backends.py`** | +81 dòng. Thêm: `supports_vision`, `_parse_json()` robust hơn (xử lý list response, escape sequences), `_get_content()` an toàn, `_fix_json_escapes()` |
| **`hsge/llm.py`** | +6 dòng. Thêm: `complete_vision_json()` abstract method trong base `LLM` class |
| **`requirements.txt`** | Cập nhật dependencies |
| **`hsge/webarena/__init__.py`** | Package marker |

---

## VẤN ĐỀ 2: Frontier Filter — Template-Based URL Clustering

### Vấn đề gốc
Code gốc thêm **tất cả** link vào frontier → bùng nổ số lượng URL. Trên Magento root page có ~334 links, sau 6 node → 2085 URLs. Không có cơ chế lọc.

### Thay đổi

| File | Thay đổi chính |
|---|---|
| **`hsge/webarena/frontier_filter.py`** | **File mới (400 dòng).** Cốt lõi: `extract_templates()` — phát hiện biến trong URL bằng position-based detection (so sánh giá trị ở mỗi depth path trên TOÀN BỘ URL). `template_priority()` — chấm điểm cluster theo heuristics domain-agnostic (số placeholder, depth, keywords, cluster size). `_sample_diverse()` — chọn mẫu đa dạng theo path depth. `filter_frontier()` — API chính. |
| **`hsge/webarena/runtime.py`** | Tích hợp `_filter_links()` dùng template clustering + **global quota** (`_template_max=10` URLs/template trên toàn bộ nodes). Import `extract_templates`, `template_priority`, `_sample_diverse`. |
| **`docs/05_frontier_filter.md`** | Tài liệu kiến trúc & benchmark (giảm 83% URLs) |
| **`docs/11_frontier_filter_deep_dive.md`** | Phân tích sâu thuật toán |
| **`analyze_frontier.py`** | Script phân tích cluster độc lập |

### Thuật toán (3 pass):

```
Pass 1  – extract_templates(): Với mỗi depth của path, nếu >15% URLs khác nhau
          hoặc ≥3 giá trị non-numeric → vị trí đó là VARIABLE ({slug}/{id}/{hash}).
          Kết quả: template string như "/customer/account/{slug}/".
Pass 1b – template_priority(): Chấm điểm mỗi cluster (placeholder count, depth,
          keywords như login/cart/checkout, cluster size).
Pass 2  – _sample_diverse(): Trong mỗi cluster, chọn k URLs đa dạng theo depth.
          Global quota: tối đa 10 URLs/template trên toàn bộ run.
```

---

## VẤN ĐỀ 3: State Restoration — Multi-Level Reset & Prefix Replay

### Vấn đề gốc
URL ghi nhận trong frontier khi được explore từ node cha có thể không còn tồn tại hoặc redirect (về login, 404) vì browser mới không có session/state cũ. Code gốc chỉ skip cứng các URL redirect.

### Giải pháp: Mượn cơ chế "prefix" từ Semantic-Agent

Khi một URL được discover, ghi lại chuỗi actions dẫn đến nó. Khi pop từ frontier, thử 3 chiến lược tuần tự để khôi phục trạng thái.

| File | Thay đổi chính |
|---|---|
| **`hsge/schema.py`** | Thêm `PrefixTrace` dataclass: `start_url`, `end_url`, `actions`, `metadata`. Có `to_dict()`/`from_dict()`. |
| **`hsge/webarena/runtime.py`** | Thêm: `_norm_url()`, `_urls_match()`, `_normalized_url()` — 3 hàm helper chuẩn hóa URL. `_reset_to_url()` — multi-level reset (direct goto → parent-then-child → prefix replay), trả về `(browser, obs)`. `_extract_prefix_from_steps()` — trích `PrefixTrace` từ solver steps. `_record_prefixes_from_task()` — quét solver trajectory ghi prefix cho mọi URL visited. `run()` — frontier giờ là `list[dict]` (có `url`, `depth`, `parent_url`, `prefix`). `save_checkpoint()` — serialize prefix. `frontier.jsonl` — thêm `has_prefix`, `parent_url`. |
| **`hsge/webarena/browser.py`** | +46 dòng. Thêm: `_is_same_origin()` — kiểm tra same-origin. `links()` — trích xuất `<a href>` từ DOM thực (dùng `page.evaluate`) + fallback `open_pages_urls`. `screenshot` support trong observation. |

### Cơ chế 3-level reset:

```
Level 1 – Direct goto:       browser_factory(url) → reset
Level 2 – Parent-then-child:  browser_factory(parent_url) → reset → goto(url)
Level 3 – Prefix replay:      browser_factory(prefix.start_url) → reset → replay actions
```

---

## VẤN ĐỀ 4: Skill Hints & Login-Aware Agents

### Vấn đề gốc
PageExplorer chỉ propose tasks dựa trên page content. Solver không biết cách login hoặc dùng skills đã học. Không có skill hints.

### Thay đổi

| File | Thay đổi chính |
|---|---|
| **`hsge/webarena/agents.py`** | +65 dòng. `PageExplorer.propose()` nhận thêm `skill_hints` param. Thêm `_accounts_hint()` — đọc credentials từ env vars (`WA_ACCOUNT_SHOPPING_USERNAME`, ...). `_build_solver_sys()` — build system prompt động với skill_hints + login procedure. `EXPLORER_SYS` thêm hướng dẫn `[LOGIN_REQUIRED]` prefix. `Solver.solve()` nhận `skill_hints` param, hỗ trợ vision (`complete_vision_json`), trả về thêm `screenshots`. |
| **`hsge/webarena/runtime.py`** | `_build_skill_hints()` — lấy top-5 skills liên quan từ library, format thành prompt hint. Truyền skill_hints vào PageExplorer và Solver. |

---

## VẤN ĐỀ 5: Skill Library — Callback & Retry Logic

### Vấn đề gốc
Library abstraction & verification là fire-and-forget. Không có callback khi skill được admit. Nếu abstraction hoặc verification fail, cluster bị đánh dấu "đã abstracted" → không bao giờ thử lại.

### Thay đổi

| File | Thay đổi chính |
|---|---|
| **`hsge/library.py`** | +16 dòng. Thêm `_on_admit` callback — được gọi khi skill được verify & admit. `_try_admit()` không đánh dấu `_abstracted` nếu abstraction hoặc verification fail → retry được. Thêm logging chi tiết. |
| **`hsge/abstraction.py`** | +18 dòng. `abstract_cluster()` trả về `SkillCard | None` (thay vì luôn trả về). System prompt chi tiết hơn với JSON schema cụ thể. Xử lý LLM response rỗng/invalid. |
| **`hsge/webarena/runtime.py`** | `_on_skill_admitted()` callback — log + ghi `skills.json` ngay lập tức. `_skills_log`, `_curriculum_log`, `_transfer_log` lists. |

---

## VẤN ĐỀ 6: Resume/Checkpoint & Persistence

### Vấn đề gốc
Không có cơ chế resume. Nếu run bị crash, mất toàn bộ state. Không có log file.

### Thay đổi

| File | Thay đổi chính |
|---|---|
| **`hsge/webarena/runtime.py`** | Thêm: `_ckpt` load/save. `save_checkpoint()` — serialize frontier + visited + queued + template_quota. `_load_checkpoint()` / `_resume_from_checkpoint()` — khôi phục state. `_replay_episodes()` — replay episodes cũ để rebuild library. `_log_file` — `run.log` append. `_frontier_file` — `frontier.jsonl` append. `_nodes_done` property. `--resume` flag. |
| **`recover_checkpoint.py`** | **File mới.** Script khôi phục checkpoint từ `frontier.jsonl` nếu `checkpoint.json` bị mất. |
| **`run_webarena.py`** | `_check_overwrite_safety()` — cảnh báo nếu output dir đã có data. |

---

## VẤN ĐỀ 7: Graph & Curriculum Export

### Vấn đề gốc
Không export được hierarchical graph hay curriculum.

### Thay đổi

| File | Thay đổi chính |
|---|---|
| **`hsge/webarena/runtime.py`** | Thêm: `_write_graph()` — export `graph.json` (low-level states + edges, high-level skills + state↔skill + composition edges). `_write_curriculum()` — gọi `generate_curriculum()` → `curriculum.json`. `transfer_eval()` — cross-domain retrieval → `transfer.json`. Chạy định kỳ mỗi 5 nodes và khi kết thúc. |
| **`hsge/discovery.py`** | +3 dòng. Thêm `subgoal_hints` param vào `on_trajectory()`. |

---

## VẤN ĐỀ 8: Browser Improvements

### Vấn đề gốc
`WebArenaBrowser.links()` chỉ dùng `open_pages_urls` từ observation (thiếu nhiều link). Không có screenshot support.

### Thay đổi

| File | Thay đổi chính |
|---|---|
| **`hsge/webarena/browser.py`** | +46 dòng. `links()` — dùng `page.evaluate()` để extract tất cả `<a href>` từ DOM thực + fallback `open_pages_urls`. `_is_same_origin()` — helper kiểm tra same-origin. `screenshot` param trong constructor + `screenshot_base64` trong observation. |

---

## VẤN ĐỀ 9: Segmentation & Verification Cải Tiến

| File | Thay đổi chính |
|---|---|
| **`hsge/segmentation.py`** | +16 dòng. Cải thiện system prompt, xử lý edge cases. |
| **`hsge/verification.py`** | +9 dòng. Cải thiện verify logic, logging. |
| **`hsge/backends.py`** | `_parse_json()` robust — xử lý list response, escape sequences không hợp lệ. |

---

## VẤN ĐỀ 10: Documentation

| File mới | Nội dung |
|---|---|
| **`docs/05_frontier_filter.md`** | Kiến trúc & benchmark frontier filter |
| **`docs/06_code_reference.md`** | Tham khảo code toàn bộ pipeline |
| **`docs/07_presenting_code.md`** | Hướng dẫn trình bày code (cho paper) |
| **`docs/10_changelog.md`** | Lịch sử thay đổi |
| **`docs/11_frontier_filter_deep_dive.md`** | Phân tích sâu thuật toán template extraction |
| **`docs/09_run_on_webarena.md`** | +46 dòng, cập nhật hướng dẫn chạy với provider mới, resume, screenshot |

---

## Tóm tắt: 10 vấn đề chính

| # | Vấn đề | Files chính | Impact |
|---|---|---|---|
| 1 | **Multi-Provider LLM & Tách Explorer/Solver** | `run_webarena.py`, `backends.py`, `llm.py` | Hỗ trợ DeepSeek, OpenAI, custom; explorer/solver model riêng; vision |
| 2 | **Frontier Filter** | `frontier_filter.py` (mới), `runtime.py` | Giảm 83% URLs, domain-agnostic |
| 3 | **State Restoration (Prefix Replay)** | `runtime.py`, `schema.py`, `browser.py` | 3-level reset, khôi phục state URL bị mất |
| 4 | **Skill Hints & Login-Aware** | `agents.py`, `runtime.py` | Agent biết dùng skills đã học + tự động login |
| 5 | **Library Retry & Callback** | `library.py`, `abstraction.py` | Retry abstraction/verification, callback on admit |
| 6 | **Resume/Checkpoint** | `runtime.py`, `recover_checkpoint.py` (mới) | Chịu lỗi, resume từ checkpoint |
| 7 | **Graph & Curriculum Export** | `runtime.py`, `discovery.py` | Export graph.json, curriculum.json, transfer.json |
| 8 | **Browser Improvements** | `browser.py` | DOM links, screenshot, same-origin filter |
| 9 | **Segmentation & Verification** | `segmentation.py`, `verification.py` | Cải thiện robustness |
| 10 | **Documentation** | 5 docs mới, 1 docs cập nhật | Toàn bộ kiến trúc & thuật toán được ghi lại |

---

## Cây thư mục thay đổi

```
hsge_project/                          ← MODIFIED
├── .env                               ← NEW
├── .env.example                       ← NEW
├── .gitignore                         ← NEW
├── analyze_frontier.py                ← NEW
├── build_sft_dataset.py               ← MODIFIED
├── compare.py                         ← MODIFIED
├── demo.py                            ← MODIFIED
├── demo_purchase.py                   ← MODIFIED
├── demo_shopping.py                   ← MODIFIED
├── explore.py                         ← MODIFIED
├── README.md                          ← MODIFIED
├── recover_checkpoint.py              ← NEW
├── requirements.txt                   ← MODIFIED
├── run_webarena.py                    ← MODIFIED (+175 lines)
├── docs/
│   ├── 05_frontier_filter.md          ← NEW
│   ├── 06_code_reference.md           ← NEW
│   ├── 07_presenting_code.md          ← NEW
│   ├── 09_run_on_webarena.md          ← MODIFIED (+46 lines)
│   ├── 10_changelog.md                ← NEW
│   └── 11_frontier_filter_deep_dive.md← NEW
└── hsge/
    ├── abstraction.py                 ← MODIFIED (+18 lines)
    ├── backends.py                    ← MODIFIED (+81 lines)
    ├── discovery.py                   ← MODIFIED (+3 lines)
    ├── library.py                     ← MODIFIED (+16 lines)
    ├── llm.py                         ← MODIFIED (+6 lines)
    ├── schema.py                      ← MODIFIED (PrefixTrace)
    ├── segmentation.py                ← MODIFIED (+16 lines)
    ├── verification.py                ← MODIFIED (+9 lines)
    └── webarena/
        ├── agents.py                  ← MODIFIED (+65 lines)
        ├── browser.py                 ← MODIFIED (+46 lines)
        ├── frontier_filter.py         ← NEW (400 lines)
        └── runtime.py                 ← MODIFIED (+506 lines)

hsge_project_raw/                      ← ORIGINAL (unchanged)
└── hsge_project/
    └── compare_three_way.py           ← REMOVED
```
