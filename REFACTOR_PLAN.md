# Kế hoạch Refactor: Xây dựng HSGE Improved từ HSGE Raw

## Mục tiêu

Xây dựng lại bản **hsge_project** (bản cải tiến cho online dataset) từ bản **hsge_project_raw** (bản offline dataset hoàn chỉnh) theo từng commit có tổ chức. Mỗi commit chỉ thay đổi **1 module cụ thể**, có hướng dẫn kiểm tra thủ công chi tiết.

> **Tham khảo**: `ANALYSIS_IMPROVEMENTS.md` — tài liệu phân tích thiếu sót và đề xuất cải tiến.

---

## Nguyên tắc chung

- **Base**: Copy `hsge_project_raw/hsge_project/` → `hsge_project_clean/`
- **Mỗi commit**: Chỉ sửa file trong **1 module**, có thể thêm file mới
- **Không sửa nhiều module trong cùng 1 commit**
- **Commit message format**: `<module>: <change description>`
- **Luôn chạy test** sau mỗi commit để đảm bảo không break
- **Kiểm tra thủ công**: sau mỗi commit, làm theo hướng dẫn "kiểm tra bằng mắt"

---

## PHASE 0: Khởi tạo

### Commit 0.1 — Copy project raw

```
Mô tả: Copy toàn bộ hsge_project_raw làm base
Thay đổi: Sao chép thư mục
Input:  hsge_project_raw/hsge_project/
Output: hsge_project_clean/ (giống hệt bản raw)
```

**Hướng dẫn kiểm tra:**
1. Mở thư mục `hsge_project_clean/` trong VS Code
2. Chạy `python -m pytest hsge/tests/test_clustering.py -v` — thấy 4 tests passed
3. Chạy `python demo.py` — thấy pipeline in ra kết quả discovery, transfer, curriculum

---

### Commit 0.2 — Xóa file không cần thiết

```
Module: root
Mô tả: Xóa compare_three_way.py (script so sánh 3 chiều, không dùng online)
Thay đổi:
  - Xóa: compare_three_way.py
Input:  hsge_project_clean/compare_three_way.py (tồn tại)
Output: hsge_project_clean/ (không còn file này)
```

**Hướng dẫn kiểm tra:**
1. Mở File Explorer, thấy thư mục gốc không còn `compare_three_way.py`
2. `python demo.py` vẫn chạy được (không import file đã xóa)

---

## PHASE 1: Cải tiến Core Modules (không phụ thuộc lẫn nhau)

### Commit 1.1 — `llm.py`: Thêm vision support

```
Module: hsge/llm.py
Mô tả: Thêm method complete_vision_json cho abstract class LLM
Thay đổi:
  - THÊM method complete_vision_json vào abstract class LLM
    - Signature: (self, system: str, prompt: str, screenshot_base64: bytes | None = None) -> dict
    - Mặc định fallback: return self.complete_json(system, prompt)
    - Parameter screenshot_base64 được khai báo nhưng KHÔNG dùng ở base class
  - KHÔNG thay đổi gì ở MockLLM, Embedder, HashingEmbedder
```

**Cách làm cụ thể:**
1. Mở `hsge/llm.py`
2. Tìm class `LLM` (abstract class)
3. Thêm method mới sau method `complete_text`:
```python
def complete_vision_json(self, system: str, prompt: str,
                         screenshot_base64: bytes | None = None) -> dict:
    """Return parsed JSON, optionally with a screenshot. Falls back to
    complete_json if the backend doesn't support vision."""
    return self.complete_json(system, prompt)
```

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "from hsge.llm import LLM; print(hasattr(LLM, 'complete_vision_json'))"` → in ra `True`
2. Chạy: `python -c "from hsge.llm import MockLLM; m=MockLLM(); print(m.complete_vision_json('sys','prompt'))"` → in ra `{}` (không crash)
3. Chạy `python demo.py` — vẫn chạy bình thường (không có gì thay đổi behavior)

---

### Commit 1.2 — `backends.py`: Cải tiến OpenAILLM

```
Module: hsge/backends.py
Mô tả: Thêm vision support, JSON parsing robust, error handling
Thay đổi:
  1. SỬA OpenAILLM.__init__: thêm `supports_vision: bool = True`
  2. THÊM static method _fix_json(txt: str) -> str
     - Fix trailing commas (`,}` → `}`, `,]` → `]`)
     - Fix single quotes → double quotes (nhưng giữ nguyên quotes trong string values)
     - Fix Python literals (True/False/None → true/false/null)
  3. THÊM static method _parse_json(txt: str | None) -> dict
     - Nếu txt rỗng → return {}
     - Nếu txt là JSON array → wrap thành {"segments": result}
     - Gọi _fix_json trước khi parse
     - Nếu parse lỗi → extract JSON object/array từ text bằng regex
  4. THÊM method complete_vision_json(system, prompt, screenshot_base64)
     - Tạo messages array với system + user content (text + image_url nếu có screenshot)
     - Gọi API chat completions
     - Parse response bằng _parse_json
  5. THÊM method _get_content(msg) -> str | None
     - Nếu content là string → return content
     - Nếu content là list of blocks → tìm block có type="text", return text
  6. SỬA complete_json: dùng _parse_json thay vì regex trực tiếp
  7. SỬA complete_text: dùng _get_content thay vì msg["content"] trực tiếp
```

**Cách làm cụ thể:**
1. Mở `hsge/backends.py`
2. Trong `class OpenAILLM`:
   - **SỬA `__init__`**: thêm `supports_vision: bool = True` sau tham số cuối, gán `self.supports_vision = supports_vision`
   - **THÊM** `_fix_json` (static method) — xử lý chuỗi JSON bị lỗi
   - **THÊM** `_parse_json` (static method) — parse JSON an toàn
   - **THÊM** `_get_content` (static method) — lấy text content từ message
   - **SỬA** `complete_json` — dùng `_parse_json` ở cuối thay vì regex
   - **SỬA** `complete_text` — dùng `_get_content` ở cuối thay vì `msg["content"]`
   - **THÊM** `complete_vision_json` — giống `complete_json` nhưng thêm image_url vào prompt

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "from hsge.backends import OpenAILLM; llm=OpenAILLM(api_key='test', base_url='http://test', model='test', supports_vision=True); print('_fix_json:', llm._fix_json(\"{'a': 1,}\")); print('_parse_json:', llm._parse_json('[{\"x\": 1}]'))"`
   - Kỳ vọng: `_fix_json: {"a": 1}` và `_parse_json: {'segments': [{'x': 1}]}`
2. Chạy `python demo.py` — vẫn chạy bình thường (không dùng OpenAILLM trong demo)

---

### Commit 1.3 — `clustering.py`: Thêm merge_threshold

```
Module: hsge/clustering.py
Mô tả: Thêm merge_threshold parameter cho OnlineClusterer, cho phép merge
       các clusters bị trôi dạt gần nhau
Thay đổi:
  - SỬA OnlineClusterer.__init__: thêm merge_threshold: float = 0.95
  - THÊM method _maybe_merge(self) -> None:
      - Sau mỗi lần partial_fit, kiểm tra tất cả cặp clusters
      - Nếu cosine similarity giữa 2 centroids >= merge_threshold:
        - Merge cluster nhỏ hơn vào cluster lớn hơn
        - Cập nhật centroid (weighted average)
        - Chuyển member_ids từ cluster nhỏ sang cluster lớn
        - Xóa cluster nhỏ
```

**Cách làm cụ thể:**
1. Mở `hsge/clustering.py`
2. Tìm `class OnlineClusterer.__init__`
3. Thêm `merge_threshold: float = 0.95` vào parameter list
4. Gán `self.merge_threshold = merge_threshold`
5. Thêm method `_maybe_merge(self)`:
   - Lấy danh sách tất cả cluster IDs
   - Với mỗi cặp (cid1, cid2) với cid1 < cid2:
     - Tính cosine similarity = centroid1 @ centroid2 (đã L2-normalized)
     - Nếu similarity >= self.merge_threshold:
       - Chọn cluster lớn hơn (nhiều members hơn) làm đích
       - Update centroid = weighted average
       - Chuyển members
       - Xóa cluster nhỏ
6. Trong `partial_fit`, thêm `self._maybe_merge()` ở cuối method

**Hướng dẫn kiểm tra:**
1. Chạy: `python -m pytest hsge/tests/test_clustering.py -v` — 4 tests passed
2. Mở file `hsge/tests/test_clustering.py`, thêm dòng kiểm tra merge hoạt động:
   - Tạo 2 clusters, đẩy centroids lại gần nhau → verify chúng được merge
3. Chạy `python demo.py` — vẫn chạy bình thường

---

### Commit 1.4 — `abstraction.py`: Defensive LLM handling

```
Module: hsge/abstraction.py
Mô tả: Xử lý LLM response invalid, không crash pipeline khi LLM trả về
       response không parse được
Thay đổi:
  1. SỬA _SYS prompt: thêm format JSON chi tiết với các keys EXACT
  2. SỬA abstract_cluster: return type từ SkillCard → SkillCard | None
  3. THÊM validation: nếu LLM trả về None hoặc dict không có key "name":
     - In warning: "[abstraction] WARNING: LLM returned invalid response ..."
     - Return None (không crash)
  4. SỬA: dùng .get() thay vì [] cho tất cả truy cập dict:
     - out.get("name", f"skill_{cluster_id}")
     - out.get("description", "")
     - out.get("action_template", "")
     - out.get("precondition", "")
     - out.get("success_predicate", f"{dominant} completed")
```

**Cách làm cụ thể:**
1. Mở `hsge/abstraction.py`
2. Tìm `_SYS = "..."` — thay bằng prompt mới yêu cầu JSON với keys chính xác
3. Tìm `def abstract_cluster(...) -> SkillCard:` — sửa thành `-> SkillCard | None`
4. Sau dòng `out = llm.complete_json(_SYS, f"<payload>{json.dumps(payload)}</payload>")`:
   - Thêm: `if not out or "name" not in out: print warning; return None`
5. Thay tất cả `out["key"]` bằng `out.get("key", default_value)`
6. Cuối function: vẫn return `SkillCard(...)` như cũ

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "
from hsge.abstraction import abstract_cluster
from hsge.llm import MockLLM
from hsge.schema import SubTrajectory, Step
llm = MockLLM()
members = [SubTrajectory(steps=[Step(url='http://a', action='click')], subgoal='test', source_site='shop')]
card = abstract_cluster(llm, 1, members)
print(f'Got card: {card.name if card else None}')
"` — in ra tên skill (không crash)
2. Chạy `python demo.py` — vẫn chạy bình thường

---

### Commit 1.5 — `verification.py`: Handle empty contexts (FIX CRITICAL BUG)

```
Module: hsge/verification.py
Mô tả: 🔴 FIX: Khi không có môi trường verify (contexts rỗng), admit skill ngay.
       Đây là bước chuẩn bị cho Commit 4.3 nơi verify contexts sẽ được implement
       thật (dùng episodes đã có). Tạm thời admit ngay để pipeline không bị block.
Thay đổi:
  - SỬA verify_skill: thêm early return ở đầu function
    if not contexts:
        skill.verified = True
        return True
```

**Cách làm cụ thể:**
1. Mở `hsge/verification.py`
2. Tìm `def verify_skill(...):`
3. Thêm 4 dòng đầu tiên của function body:
```python
if not contexts:
    # No verification environments available — admit without verification
    skill.verified = True
    return True
```
4. Phần code còn lại giữ nguyên

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "
from hsge.verification import verify_skill
from hsge.schema import SkillCard
skill = SkillCard(name='test', slots=[], action_template='', precondition='', success_predicate='')
result = verify_skill(None, skill, [], k=1)
print(f'Empty contexts admit: {result}')  # Phải in True
print(f'Skill verified: {skill.verified}')  # Phải in True
"`
2. Chạy `python demo.py` — vẫn chạy bình thường

---

### Commit 1.6 — `segmentation.py`: Defensive LLM parsing

```
Module: hsge/segmentation.py
Mô tả: Xử lý LLM output invalid, fallback khi segmentation fail
Thay đổi:
  1. THÊM defensive parsing:
     - segments = out nếu out là list, else out.get("segments", [])
  2. THÊM validation cho mỗi segment (try/except):
     - Kiểm tra seg là dict và có key "span"
     - span là list/tuple, len=2
     - a, b là số nguyên, 0 <= a < b <= len(steps)
     - Nếu invalid → continue (bỏ qua segment đó)
  3. THÊM fallback: nếu LLM trả về unusable (subs rỗng) nhưng spans có dữ liệu
     → dùng URL-boundary segments trực tiếp với subgoal hints
```

**Cách làm cụ thể:**
1. Mở `hsge/segmentation.py`
2. Tìm `out = llm.complete_json(_SYS, prompt)`
3. Thêm ngay sau đó:
```python
# Defensive: if out is a list, treat it as the segments array directly.
segments = out if isinstance(out, list) else out.get("segments", [])
```
4. Thay vòng lặp `for seg in segments` cũ, thêm try/catch:
```python
subs: list[SubTrajectory] = []
for seg in segments:
    if not isinstance(seg, dict) or "span" not in seg:
        continue
    try:
        span = seg["span"]
        if not isinstance(span, (list, tuple)) or len(span) != 2:
            continue
        a, b = int(span[0]), int(span[1])
        if not (0 <= a < b <= len(steps)):
            continue
        subs.append(SubTrajectory(
            steps=steps[a:b], subgoal=seg.get("subgoal", ""),
            source_site=site, source_task=task, success=True,
        ))
    except (TypeError, ValueError):
        continue
```
5. Sau vòng lặp, thêm fallback:
```python
# Fallback: if LLM returned unusable output, use the seeded spans directly.
if not subs and spans:
    subs = [
        SubTrajectory(
            steps=steps[a:b],
            subgoal=hints[i] if i < len(hints) else f"segment {i}",
            source_site=site, source_task=task, success=True,
        )
        for i, (a, b) in enumerate(spans)
    ]
```

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "
from hsge.segmentation import segment_trajectory
from hsge.llm import MockLLM
from hsge.schema import Step
steps = [Step(url='http://a', action='click'), Step(url='http://b', action='type')]
subs = segment_trajectory(MockLLM(), steps, 'shop', 'test task')
print(f'Segments: {len(subs)}')  # Phải in ra số segments > 0
for s in subs:
    print(f'  subgoal={s.subgoal}, steps={len(s.steps)}')
"`
2. Chạy `python demo.py` — vẫn chạy bình thường

---

### Commit 1.7 — `library.py`: Callback + retry mechanism

```
Module: hsge/library.py
Mô tả: Thêm admit callback, retry khi abstraction/verification fail, log chi tiết
Thay đổi:
  1. THÊM self._on_admit = None trong __init__ (callback function)
  2. THÊM logging trong observe: in "[library] cluster X reached maturity..."
  3. SỬA _try_admit:
     - Nếu abstract_cluster trả về None → in warning, return None (retry sau)
     - Chỉ mark _abstracted SAU KHI verify thành công (raw: mark trước verify)
     - THÊM logging: abstracted → verifying → VERIFIED/FAILED
  4. THÊM: gọi self._on_admit(card) khi admit thành công
```

**Cách làm cụ thể:**
1. Mở `hsge/library.py`
2. Trong `__init__`, thêm `self._on_admit = None` sau `self._abstracted: set[int] = set()`
3. Trong `observe`, thêm dòng in khi cluster đạt maturity:
   - Tìm chỗ `if n >= self.maturity and cid not in self._abstracted:`
   - Thêm `print(f"  [library] cluster {cid} reached maturity ({n} members), attempting abstraction...")`
4. Trong `_try_admit`:
   - Sau `card = abstract_cluster(...)`, thêm check None:
     ```python
     if card is None:
         print(f"  [library] cluster {cid}: abstraction FAILED, will retry later")
         return None
     ```
   - Thêm logging: `print(f"  [library] cluster {cid}: abstracted → \"{card.name}\", verifying...")`
   - Chỉ `self._abstracted.add(cid)` sau khi `verify_skill` thành công
   - Thêm logging VERIFIED/FAILED
   - Gọi `self._on_admit(card)` nếu không None

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "
from hsge.library import SkillLibrary
from hsge.llm import MockLLM, HashingEmbedder
lib = SkillLibrary(MockLLM(), HashingEmbedder(8))
admitted = []
lib._on_admit = lambda c: admitted.append(c.name)
print('_on_admit set OK')
print(f'Type: {type(lib._on_admit)}')  # Phải in ra <class 'function'>
"`
2. Chạy `python demo.py` — thấy thêm các dòng log `[library] cluster X ...`

---

### Commit 1.8 — `discovery.py`: Warning khi segmentation rỗng + FIX composition edges

```
Module: hsge/discovery.py
Mô tả: 🟠 FIX: Thêm warning khi segmentation rỗng và KHÔNG tạo composition edges
       từ co-occurrence (consecutive skills trong cùng trajectory ≠ composition).
       Đây là bug quan trọng: skill A → skill B chỉ vì chúng xuất hiện cạnh nhau,
       không phải vì A thiết lập precondition cho B.
Thay đổi:
  1. THÊM warning sau khi gọi segment_trajectory nếu trả về 0 segments
  2. XÓA (hoặc comment) đoạn tạo composition edges từ co-occurrence:
     for a, b in zip(just_admitted_in_order, just_admitted_in_order[1:]):
         self.graph.link_skills(a, b)
     → Composition edges sẽ được đồng bộ từ OperatorGraph sau này
```

**Cách làm cụ thể:**
1. Mở `hsge/discovery.py`
2. Tìm `subs = segment_trajectory(...)`
3. Thêm ngay sau:
```python
if not subs:
    print(f"  [discovery] WARNING: segment_trajectory returned 0 segments "
          f"(task={task[:60]}, steps={len(steps)})")
```
4. Tìm đoạn:
```python
# 4. composition edges: consecutive admitted skills in one trajectory
for a, b in zip(just_admitted_in_order, just_admitted_in_order[1:]):
    self.graph.link_skills(a, b)
```
5. Comment hoặc xóa đoạn này (kèm comment giải thích lý do)

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "
from hsge.discovery import Discovery
from hsge.llm import MockLLM, HashingEmbedder
from hsge.graph import HierarchicalGraph
d = Discovery(MockLLM(), HashingEmbedder(8), HierarchicalGraph())
print('discovery module loaded OK')
"`
2. Chạy `python demo.py` — vẫn chạy bình thường

---

## PHASE 2: WebArena Integration Improvements

### Commit 2.1 — `webarena/browser.py`: Screenshot + robust link extraction

```
Module: hsge/webarena/browser.py
Mô tả: Thêm screenshot support, DOM link extraction, error handling
Thay đổi:
  1. THÊM imports: asyncio, urljoin, urlparse
  2. THÊM hàm _is_same_origin(base, url) → bool
  3. SỬA __init__: thêm screenshot: bool = False
     - THÊM logging.getLogger('browsergym').setLevel(logging.WARNING)
  4. SỬA reset: thêm try/except, nếu fail → return fallback dict
  5. SỬA observation: thêm screenshot_base64 nếu screenshot_enabled
  6. THÊM _safe_page_evaluate(js, default=None)
  7. SỬA act: thêm try/except, fallback observation
  8. SỬA links: thêm DOM querySelectorAll('a[href]') fallback
  9. SỬA close: thêm asyncio.CancelledError trong except
```

**Cách làm cụ thể:**
1. Mở `hsge/webarena/browser.py`
2. Thêm imports ở đầu file
3. Thêm hàm `_is_same_origin` trước class
4. Trong `__init__`: thêm parameter `screenshot`, thêm logging config
5. Trong `reset`: wrap trong try/except
6. Trong `observation`: thêm code chụp screenshot
7. Thêm method `_safe_page_evaluate`
8. Trong `act`: wrap trong try/except
9. Trong `links`: thêm DOM query fallback
10. Trong `close`: thêm `asyncio.CancelledError`

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "from hsge.webarena.browser import WebArenaBrowser; print('import OK')"`
2. Chạy `python run_webarena.py --dry-run` — dry run vẫn chạy được

---

### Commit 2.2 — `webarena/agents.py`: Skill hints + vision

```
Module: hsge/webarena/agents.py
Mô tả: Thêm skill hints vào system prompt, vision support cho Solver
Thay đổi:
  1. THÊM hàm _build_solver_sys(skill_hints: str = '') → str
     - Build system prompt động: nếu có hints, thêm vào trước base prompt
  2. SỬA PageExplorer.propose: thêm skill_hints: str = '' parameter
     - Nếu có hints, prepend vào system prompt
  3. SỬA Solver.solve:
     - THÊM skill_hints: str = '' parameter
     - THÊM return screenshots: list[bytes | None]
     - THÊM vision support: nếu screenshot có sẵn → complete_vision_json
```

**Cách làm cụ thể:**
1. Mở `hsge/webarena/agents.py`
2. Thêm hàm `_build_solver_sys` trước class `PageExplorer`
3. Trong `PageExplorer.propose`: thêm `skill_hints: str = ""`, prepend vào sys
4. Trong `Solver.solve`:
   - Thêm `skill_hints: str = ""` parameter
   - Thêm `screenshots: list[bytes | None] = []` và populate
   - Thêm vision check: nếu screenshot có sẵn → `complete_vision_json`
   - Return thêm `screenshots`

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "
from hsge.webarena.agents import PageExplorer, Solver, _build_solver_sys
hints = _build_solver_sys('test hints')
print(f'Hints in sys: {\"test hints\" in hints}')
print('agents module loaded OK')
"`
2. Chạy `python run_webarena.py --dry-run` — dry run vẫn chạy

---

### Commit 2.3 — `webarena/frontier_filter.py`: FILE MỚI

```
Module: hsge/webarena/frontier_filter.py (FILE MỚI)
Mô tả: Frontier URL filter dùng template clustering, domain-agnostic
Thay đổi: Tạo file mới ~350 dòng
Function:
  - extract_templates(urls): position-based variable detection → template clusters
  - template_priority(template, cluster_size): score template
  - _sample_diverse(urls, k): diversity sampling
  - filter_frontier(frontier, max_output, verbose): main API
```

**Cách làm cụ thể:**
1. Tạo file mới `hsge/webarena/frontier_filter.py`
2. Copy toàn bộ nội dung từ file tương ứng trong bản improved cũ
   (hoặc viết mới theo design trong `docs/05_frontier_filter.md`)
3. Đảm bảo các function được export: `extract_templates`, `template_priority`,
   `_sample_diverse`, `filter_frontier`

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "
from hsge.webarena.frontier_filter import extract_templates, template_priority, filter_frontier
urls = ['http://shop.com/item/1', 'http://shop.com/item/2', 'http://shop.com/cart']
templates = extract_templates(urls)
print(f'Templates: {len(templates)}')
for tmpl, urls in templates.items():
    print(f'  {tmpl}: {len(urls)} URLs')
print('frontier_filter module loaded OK')
"`
2. Chạy `python run_webarena.py --dry-run` — dry run vẫn chạy

---

### Commit 2.4 — `webarena/runtime.py`: Đại tu toàn bộ

```
Module: hsge/webarena/runtime.py
Mô tả: WebArena exploration runtime với checkpoint/resume, frontier filter,
       dual LLM, skill hints, periodic export
Thay đổi: Đây là commit lớn nhất, thay đổi gần như toàn bộ file.

🔴 CRITICAL: Khi implement verify_contexts_fn, KHÔNG dùng lambda: [] như bản cũ.
             Dùng method thật _build_verify_contexts (xem ANALYSIS_IMPROVEMENTS.md mục 2).

🟠 IMPORTANT: Operator mining cần lấy predicates từ nhiều steps (không chỉ first/last).
              Xem ANALYSIS_IMPROVEMENTS.md mục 3.

🟠 IMPORTANT: Curriculum cần dùng planner (OperatorGraph) thay vì composition edges.
              Xem ANALYSIS_IMPROVEMENTS.md mục 5.

Các thay đổi chi tiết:
  1. THÊM imports: generate_curriculum, TransferResult, Step, frontier_filter.*
  2. SỬA __init__:
     - explorer_llm, solver_llm riêng
     - resume: bool = False
     - denylist_patterns
     - library._on_admit = self._on_skill_admitted
     - frontier filter params
     - denylist mặc định: /logout
     - log file: run.log
     - frontier snapshot: frontier.jsonl
     - 🔴 verify_contexts_fn dùng method THẬT
  3. THÊM _build_skill_hints(page_url, task) → str
  4. THÊM _filter_links(links, already_queued) → list[str]
  5. THÊM _on_skill_admitted(card)
  6. THÊM _write_graph(): export graph.json
  7. THÊM _write_curriculum(): export curriculum.json (dùng planner)
  8. THÊM transfer_eval(query, top_k): export transfer.json
  9. SỬA _record: thêm screenshots
  10. 🟠 SỬA _mine_operator: predicates từ nhiều steps
  11. THÊM checkpoint methods
  12. SỬA run: URL normalization, checkpoint resume, error handling,
      frontier filter, skill hints, periodic export
```

**Cách làm cụ thể:**
1. Mở `hsge/webarena/runtime.py`
2. Thêm imports ở đầu file
3. Viết lại `class WebArenaExplorer` với tất cả thay đổi trên
4. **Đặc biệt chú ý**:
   - `verify_contexts_fn` phải là method thật, không phải lambda
   - `_mine_operator` phải xử lý multiple steps
   - `_write_curriculum` phải dùng `plan()` từ OperatorGraph

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "from hsge.webarena.runtime import WebArenaExplorer; print('import OK')"`
2. Chạy `python run_webarena.py --dry-run` — dry run chạy được, in ra các bước
3. Mở file `run.log` sau dry run — thấy log chi tiết từng node
4. Mở thư mục output — thấy `skills.json`, `graph.json`, `curriculum.json`, `frontier.jsonl`

---

## PHASE 3: Root Scripts Improvements

### Commit 3.1 — `run_webarena.py`: Provider system + dual model

```
Module: run_webarena.py (root)
Mô tả: Thêm provider system, dual model CLI, .env loader, screenshot flag
Thay đổi:
  1. THÊM _load_dotenv(path='.env'): đọc .env không cần python-dotenv
  2. THÊM _resolve_models(args): CLI flag > env var > provider preset
  3. THÊM _resolve_api_config(provider): api_key, base_url, default_model
  4. THÊM _check_overwrite_safety(out_dir): cảnh báo nếu có data cũ
  5. SỬA _DryLLM: thêm complete_vision_json fallback
  6. THÊM CLI arguments:
     --provider, --model, --explorer-model, --solver-model
     --screenshot, --timeout, --resume, --transfer-query, --denylist
  7. SỬA logic khởi tạo: explorer_llm vs solver_llm riêng
```

**Cách làm cụ thể:**
1. Mở `run_webarena.py`
2. Thêm `_load_dotenv()` ở đầu (sau imports, trước khi dùng os.environ)
3. Thêm `_resolve_models`, `_resolve_api_config`, `_check_overwrite_safety`
4. SỬA `_DryLLM`: thêm `complete_vision_json`
5. Thêm argparse arguments mới
6. SỬA logic tạo `WebArenaExplorer`: dùng `explorer_llm`, `solver_llm` riêng

**Hướng dẫn kiểm tra:**
1. Chạy: `python run_webarena.py --help`
   - Thấy các argument mới: `--provider`, `--model`, `--explorer-model`, `--solver-model`, `--screenshot`, `--resume`, `--transfer-query`, `--denylist`
2. Chạy: `python run_webarena.py --dry-run --screenshot`
   - Dry run chạy được, không crash vì screenshot flag
3. Chạy: `python run_webarena.py --dry-run --out /tmp/test_out`
   - Tạo output ở thư mục mới

---

### Commit 3.2 — `analyze_frontier.py`: FILE MỚI

```
Module: analyze_frontier.py (FILE MỚI, root)
Mô tả: Script phân tích nhanh frontier URLs đã clean
Thay đổi: Tạo file mới
  - Đọc frontier.jsonl (dòng nào có "frontier" key)
  - Phân loại URLs: FUNC (functional), CAT (category), PROD (product)
  - In thống kê: tổng số URLs, số lượng mỗi loại, top templates
```

**Cách làm cụ thể:**
1. Tạo file mới `analyze_frontier.py`
2. Code:
   - Đọc `frontier.jsonl`, parse từng dòng
   - Với mỗi URL trong "frontier" array:
     - Phân loại dựa trên path segments
     - Đếm số lượng mỗi loại
   - In bảng thống kê

**Hướng dẫn kiểm tra:**
1. Chạy với dữ liệu mẫu: `python analyze_frontier.py outputs/wa_deepseek/frontier.jsonl`
   - Nếu chưa có file, chạy `python run_webarena.py --dry-run --out /tmp/test_out` trước
   - Thấy bảng thống kê URLs

---

### Commit 3.3 — `recover_checkpoint.py`: FILE MỚI

```
Module: recover_checkpoint.py (FILE MỚI, root)
Mô tả: Script khôi phục checkpoint từ episodes khi bị overwrite
Thay đổi: Tạo file mới
  - Đọc tất cả episode_meta.json để lấy visited URLs
  - Đọc episode.jsonl để lấy thêm URLs từ steps
  - Đọc frontier.jsonl để lấy frontier URLs
  - Build checkpoint.json
```

**Cách làm cụ thể:**
1. Tạo file mới `recover_checkpoint.py`
2. Code:
   - Duyệt thư mục `episodes/`
   - Với mỗi episode, đọc `episode_meta.json` + `episode.jsonl`
   - Extract URLs
   - Đọc `frontier.jsonl` để lấy frontier list
   - Ghi `checkpoint.json`

**Hướng dẫn kiểm tra:**
1. Chạy: `python recover_checkpoint.py outputs/wa_deepseek`
   - Nếu có episodes, thấy thông báo đã recover bao nhiêu URLs
   - File `checkpoint.json` được tạo
2. Mở `checkpoint.json` — thấy có `frontier`, `visited`, `queued`

---

## PHASE 4: Cải tiến theo ANALYSIS_IMPROVEMENTS.md

### Commit 4.1 — `library.py`: Cải tiến retrieval (skill card embedding)

```
Module: hsge/library.py
Mô tả: 🟡 Cải tiến retrieval: dùng skill card text (name + description) làm
       embedding thay vì sub-trajectory text ("GOAL: ... | ACTIONS: ...").
       Query là task description nên cần match với skill description.
Thay đổi:
  1. THÊM self._skill_embeddings: dict[int, np.ndarray] = {} trong __init__
  2. THÊM method _rebuild_skill_embeddings(self):
     - Với mỗi skill card, tạo text = f"{card.name}: {card.description}..."
     - Encode và lưu vào _skill_embeddings
  3. SỬA retrieve(self, query, top_k):
     - Nếu _skill_embeddings rỗng, gọi _rebuild_skill_embeddings
     - Dùng _skill_embeddings thay vì clusterer.clusters[cid].centroid
```

**Cách làm cụ thể:**
1. Mở `hsge/library.py`
2. Trong `__init__`, thêm `self._skill_embeddings: dict[int, np.ndarray] = {}`
3. Thêm method `_rebuild_skill_embeddings`
4. Sửa method `retrieve`: dùng skill embeddings

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "
from hsge.library import SkillLibrary
from hsge.llm import MockLLM, HashingEmbedder
lib = SkillLibrary(MockLLM(), HashingEmbedder(8))
# Test retrieve không crash khi chưa có skills
result = lib.retrieve('test query', top_k=3)
print(f'Empty retrieve: {result}')  # []
print('library retrieval OK')
"`
2. Chạy `python demo.py` — vẫn chạy bình thường

---

### Commit 4.2 — `agents.py`: Nâng cấp skill hints lên tool-use (function calling)

```
Module: hsge/webarena/agents.py
Mô tả: 🔴 NÂNG CẤP LỚN: Chuyển skill hints từ text prompt → function calling.
       Agent có thể gọi skill như tool, runtime tự động bind parameters + execute.
       Yêu cầu backend LLM support function calling (OpenAI, DeepSeek đều có).
Thay đổi:
  1. THÊM hàm _skills_to_tools(skills: list[SkillCard]) → list[dict]:
     - Convert skill cards thành OpenAI/DeepSeek tool definitions
     - Mỗi slot → một parameter
  2. THÊM class ToolExecutor:
     - __init__(self, browser, skills)
     - execute(tool_name, arguments) → str (kết quả)
     - Bind arguments vào action_template
     - Execute từng step qua browser
     - Kiểm tra success_predicate
     - Trả về kết quả (success/fail + observation)
  3. SỬA Solver.solve:
     - Nhận tools list
     - Gọi API với tools parameter (không phải text hints)
     - Xử lý tool_call response
     - Execute tool → nhận kết quả → gửi lại cho LLM
  4. SỬA _build_solver_sys: bỏ skill hints text (đã có tool)
```

**Cách làm cụ thể:**
1. Mở `hsge/webarena/agents.py`
2. Thêm hàm `_skills_to_tools(skills) → list[dict]`
3. Thêm class `ToolExecutor`:
   - `__init__(self, browser, skills_map: dict[str, SkillCard])`
   - `execute(self, tool_name, arguments) → str`
4. Sửa `Solver.solve`:
   - Thêm `tools: list[dict] = None` parameter
   - Khi gọi LLM, pass `tools` parameter
   - Nếu response có `tool_calls`:
     - Gọi `ToolExecutor.execute`
     - Append kết quả vào messages
     - Gọi LLM tiếp để lấy text response
5. Sửa `_build_solver_sys`: bỏ phần skill hints text

**Hướng dẫn kiểm tra:**
1. Chạy: `python -c "
from hsge.webarena.agents import _skills_to_tools, ToolExecutor
from hsge.schema import SkillCard, ParamSlot
skill = SkillCard(name='search', description='Search product', slots=[
    ParamSlot(name='query', slot_type='value', description='search keyword')
], action_template=['fill(\"#search\", \"{query}\")'], precondition='', success_predicate='results', cluster_id='1')
tools = _skills_to_tools([skill])
print(f'Tools: {len(tools)}')
print(f'Tool name: {tools[0][\"function\"][\"name\"]}')
print(f'Params: {tools[0][\"function\"][\"parameters\"]}')
"`
2. Chạy `python run_webarena.py --dry-run` — dry run vẫn chạy

---

### Commit 4.3 — `runtime.py`: Verification gate thật (dùng episodes)

```
Module: hsge/webarena/runtime.py
Mô tả: 🔴 FIX: Thay verify_contexts_fn=lambda: [] bằng method thật
       _build_verify_contexts(). Verification contexts được xây dựng từ
       các successful episodes đã thu thập trên các URLs khác nhau.
Thay đổi:
  1. THÊM method _build_verify_contexts(self) → list:
     - Duyệt thư mục episodes/
     - Lọc successful episodes
     - Mỗi URL gốc chỉ lấy 1 context (đa dạng)
     - Trả về list các _EpisodeContext objects
  2. THÊM class _EpisodeContext:
     - wrap episode data
     - Có method ground_and_execute(skill) → bool
  3. SỬA __init__: verify_contexts_fn=self._build_verify_contexts
     (thay vì lambda: [])
```

**Cách làm cụ thể:**
1. Mở `hsge/webarena/runtime.py`
2. Thêm class `_EpisodeContext`:
   ```python
   class _EpisodeContext:
       def __init__(self, ep_dir, ep_name):
           self.ep_dir = ep_dir
           self.ep_name = ep_name
           # Load steps + obs_texts từ episode files
       
       def ground_and_execute(self, llm, skill):
           # Dùng steps/obs_texts để verify skill
           # Tương tự ground_and_execute trong verification.py
           # nhưng dùng data có sẵn thay vì browser
           pass
   ```
3. Thêm method `_build_verify_contexts(self)`:
   ```python
   def _build_verify_contexts(self):
       contexts = []
       ep_dir = os.path.join(self.out_dir, "episodes")
       if not os.path.isdir(ep_dir):
           return contexts
       seen_urls = set()
       for ep_name in sorted(os.listdir(ep_dir)):
           if not ep_name.startswith("ep_"):
               continue
           # ... load meta, check success, check URL diversity
           contexts.append(_EpisodeContext(ep_dir, ep_name))
           if len(contexts) >= 5:
               break
       return contexts
   ```
4. Trong `__init__`, sửa:
   ```python
   self.library = SkillLibrary(
       _explorer_llm, embedder,
       verify_contexts_fn=self._build_verify_contexts,  # Thay vì lambda: []
       maturity=3, verify_k=2
   )
   ```

**Hướng dẫn kiểm tra:**
1. Chạy `python run_webarena.py --dry-run --out /tmp/test_verify`
2. Sau khi chạy, mở `run.log` — tìm dòng `[library] ... VERIFIED → skill admitted`
   (trước đây không có dòng này vì verify luôn pass)
3. Nếu có episodes, skill được verify thật (không admit ngay)

---

### Commit 4.4 — `runtime.py`: Đồng bộ OperatorGraph + HierarchicalGraph

```
Module: hsge/webarena/runtime.py
Mô tả: 🟠 Đồng bộ 2 graph: khi operator được mine, tự động cập nhật
       HierarchicalGraph để export graph.json có dữ liệu đầy đủ.
Thay đổi:
  1. THÊM method _sync_operator_to_graph(self, op: Operator):
     - Tạo SkillCard ảo từ operator
     - Thêm vào HierarchicalGraph.skills
     - Tạo state→skill và skill→state edges từ preconditions/effects
     - Tạo skill→skill composition edges từ precondition/effect matching
  2. SỬA _mine_operator: gọi _sync_operator_to_graph sau khi add operator
```

**Cách làm cụ thể:**
1. Mở `hsge/webarena/runtime.py`
2. Thêm method `_sync_operator_to_graph(self, op: Operator)`:
   - Tạo skill_id từ op.name
   - Tạo SkillCard ảo
   - Thêm vào `self.graph.skills`
   - Với mỗi precondition state → `self.graph.state_to_skill[state].add(skill_id)`
   - Với mỗi effect state → `self.graph.skill_to_state[skill_id].add(state)`
   - Với mỗi operator khác trong opgraph:
     - Nếu op.effects & other.preconditions → composition edge
     - Nếu other.effects & op.preconditions → composition edge ngược
3. Trong `_mine_operator`, sau `self.opgraph.add(...)`, thêm `self._sync_operator_to_graph(op)`

**Hướng dẫn kiểm tra:**
1. Chạy `python run_webarena.py --dry-run --out /tmp/test_sync`
2. Mở `graph.json` — thấy high_level có skills và skill_to_skill edges
   (trước đây graph.json chỉ có low_level data)

---

### Commit 4.5 — `runtime.py + curriculum.py`: Curriculum từ planner

```
Module: hsge/curriculum.py + hsge/webarena/runtime.py
Mô tả: 🟠 Curriculum dùng BFS planner trên OperatorGraph thay vì DFS trên
       HierarchicalGraph composition edges. Đảm bảo mọi task chain đều khả thi.
Thay đổi:
  1. THÊM curriculum.py: generate_curriculum_from_operators(opgraph, max_len, site)
     - Dùng plan() (BFS) từ initial state đến mỗi operator's preconditions
     - Single-skill tasks: operators đã enabled từ initial state
     - Multi-skill tasks: plan chain + final operator
     - Terminal goal tasks: plan đến terminal predicate
  2. SỬA runtime._write_curriculum():
     - Gọi generate_curriculum_from_operators(self.opgraph, ...)
     - Fallback: nếu opgraph rỗng, gọi generate_curriculum cũ
```

**Cách làm cụ thể:**
1. Mở `hsge/curriculum.py`
2. Thêm function `generate_curriculum_from_operators(opgraph, max_len, site)`:
   ```python
   def generate_curriculum_from_operators(opgraph, max_len=3, site=""):
       tasks = []
       initial = frozenset()
       # Single-skill
       for op in opgraph.ops.values():
           if op.preconditions <= initial:
               tasks.append(Task(instruction=f"'{op.name}'", skill_chain=[op.name], difficulty=1, site=site))
       # Multi-skill: plan từ initial đến mỗi op's preconditions
       for op in opgraph.ops.values():
           if op.preconditions <= initial:
               continue
           chain = plan(opgraph, initial, list(op.preconditions)[0])
           if chain and len(chain) <= max_len:
               tasks.append(Task(instruction=" → ".join(chain + [op.name]), skill_chain=chain + [op.name], difficulty=len(chain)+1, site=site))
       tasks.sort(key=lambda t: t.difficulty)
       return tasks
   ```
3. Mở `hsge/webarena/runtime.py`
4. Sửa `_write_curriculum`:
   ```python
   def _write_curriculum(self):
       if self.opgraph.ops:
           tasks = generate_curriculum_from_operators(self.opgraph, max_len=3, site="webarena")
       elif self.graph.skills:
           tasks = generate_curriculum(self.graph, max_len=3, site="webarena")
       else:
           return
       # ... export như cũ
   ```

**Hướng dẫn kiểm tra:**
1. Chạy `python run_webarena.py --dry-run --out /tmp/test_curriculum`
2. Mở `curriculum.json` — thấy tasks có difficulty tăng dần
3. Kiểm tra: mỗi task's skill_chain có thể plan được (precondition → effect)

---

### Commit 4.6 — `runtime.py`: Checkpoint lưu full state

```
Module: hsge/webarena/runtime.py
Mô tả: 🟡 Checkpoint lưu thêm OperatorGraph state và clusterer state để resume
       chính xác, không cần replay episodes.
Thay đổi:
  1. SỬA save_checkpoint: thêm operator_graph, clusterer state
  2. SỬA _resume_from_checkpoint: restore operator_graph + clusterer
  3. THÊM _serialize_clusterer() / _deserialize_clusterer(data)
```

**Cách làm cụ thể:**
1. Mở `hsge/webarena/runtime.py`
2. Sửa `save_checkpoint`:
   ```python
   ckpt = {
       # ... existing fields ...
       "operator_graph": {
           "ops": {
               name: {
                   "preconditions": sorted(op.preconditions),
                   "effects": sorted(op.effects),
                   "terminal": op.terminal,
               }
               for name, op in self.opgraph.ops.items()
           }
       },
       "clusterer": self._serialize_clusterer(),
   }
   ```
3. Thêm `_serialize_clusterer`:
   ```python
   def _serialize_clusterer(self):
       clusters = self.library.clusterer.clusters
       return {
           str(cid): {
               "centroid": c.centroid.tolist(),
               "member_ids": list(c.member_ids),
               "n": c.n,
           }
           for cid, c in clusters.items()
       }
   ```
4. Sửa `_resume_from_checkpoint`:
   - Restore operator_graph từ ckpt
   - Restore clusterer từ ckpt
   - KHÔNG gọi `_replay_episodes()` nếu đã có operators

**Hướng dẫn kiểm tra:**
1. Chạy `python run_webarena.py --dry-run --out /tmp/test_ckpt`
2. Mở `checkpoint.json` — thấy có `operator_graph` và `clusterer` fields
3. Chạy lại với `--resume`: `python run_webarena.py --dry-run --out /tmp/test_ckpt --resume`
   - Thấy dòng `[resume] Loaded checkpoint: X nodes done...`
   - Không cần replay episodes (nếu đã có operators)

---

### Commit 4.7 — `runtime.py`: Transfer execution thật

```
Module: hsge/webarena/runtime.py
Mô tả: 🟡 Transfer không chỉ retrieval mà còn ground-and-execute thật trên
       browser, kèm adaptation nếu skill fail.
Thay đổi:
  1. THÊM method transfer_and_adapt(target_url, query, top_k):
     - Retrieve skills
     - Mở browser trên target URL
     - Thử ground-and-execute từng skill
     - Nếu fail → adaptation (hỏi LLM điều chỉnh)
     - Lưu adapted skills
     - Trả về TransferResult
  2. THÊM method _adapt_skill(browser, card) → SkillCard | None
```

**Cách làm cụ thể:**
1. Mở `hsge/webarena/runtime.py`
2. Thêm method `transfer_and_adapt(self, target_url, query, top_k=5)`:
   ```python
   def transfer_and_adapt(self, target_url, query, top_k=5):
       cards = self.library.retrieve(query, top_k=top_k)
       transferred = []
       for card in cards:
           browser = self.browser_factory(target_url)
           browser.reset()
           success = self._try_ground_and_execute(browser, card)
           if success:
               transferred.append(card.skill_id)
               card.stats.sites_seen.add(target_url)
           else:
               adapted = self._adapt_skill(browser, card)
               if adapted:
                   self._save_adapted_skill(card, adapted, target_url)
                   transferred.append(adapted.skill_id)
           browser.close()
       return TransferResult(site=target_url, attempted=len(cards), succeeded=len(transferred), transferred_skill_ids=transferred)
   ```
3. Thêm `_adapt_skill(self, browser, card)`:
   - Gọi LLM với prompt: "Skill X failed, adapt action_template for current page"
   - Parse response → new action_template
   - Tạo SkillCard mới với adapted template

**Hướng dẫn kiểm tra:**
1. Chạy `python run_webarena.py --dry-run --out /tmp/test_transfer`
2. Mở `transfer.json` — thấy transfer results (dù dry run không có browser thật)

---

### Commit 4.8 — `runtime.py`: Error handling + Monitoring

```
Module: hsge/webarena/runtime.py
Mô tả: 🟢 Thêm error handling toàn diện và monitoring metrics
Thay đổi:
  1. THÊM class RunMetrics để track: nodes, tasks, skills, operators, tokens
  2. THÊM try/except trong run loop: mỗi node được xử lý độc lập
  3. THÊM metrics tracking trong _on_skill_admitted, _mine_operator, solve
  4. THÊM summary log ở cuối run
```

**Cách làm cụ thể:**
1. Mở `hsge/webarena/runtime.py`
2. Thêm `@dataclass RunMetrics` ở đầu file:
   ```python
   @dataclass
   class RunMetrics:
       nodes_visited: int = 0
       tasks_proposed: int = 0
       tasks_solved: int = 0
       skills_discovered: int = 0
       skills_verified: int = 0
       operators_mined: int = 0
       start_time: float = 0.0
       total_llm_calls: int = 0
       
       def summary(self):
           elapsed = time.time() - self.start_time
           return f"..."
   ```
3. Trong `__init__`: `self.metrics = RunMetrics(); self.metrics.start_time = time.time()`
4. Thêm try/except trong run loop:
   ```python
   try:
       self._process_node(url, depth, ...)
   except Exception as e:
       print(f"[ERROR] node {node_num}: {e}")
       import traceback; traceback.print_exc()
       self.save_checkpoint(frontier, visited, queued)
       continue
   ```
5. Cuối run: in `self.metrics.summary()`

**Hướng dẫn kiểm tra:**
1. Chạy `python run_webarena.py --dry-run --out /tmp/test_metrics`
2. Cuối run thấy bảng summary: nodes, tasks solved, skills verified, operators mined

---

### Commit 4.9 — `runtime.py`: Callback-based URL discovery + Scored frontier

```
Module: hsge/webarena/runtime.py
Mô tả: 🟠 Áp dụng cơ chế của go-browse:
       1. Callback-based URL discovery: phát hiện URL mới NGAY TRONG LÚC
          thực thi task (qua open_pages_urls sau mỗi step), không phải query
          DOM sau khi task hoàn thành. URL đã được visit → state còn nguyên.
       2. Scored frontier (UVD): thay FIFO queue bằng scoring system
          (Uncertainty + Value + Diversity) để chọn node tốt nhất.

       Giải quyết triệt để vấn đề cart/checkout expire. URL từ DOM links
       vẫn được lấy ở homepage (depth=0) để đảm bảo coverage categories.

Lý do thay đổi (xem ANALYSIS_IMPROVEMENTS.md mục 14):
  - BFS hiện tại: phát hiện URL /checkout/cart/configure từ DOM ở node 13
    nhưng đến node 46 mới goto → cart empty → redirect → SKIP
  - go-browse: callback sau mỗi step phát hiện URL NGAY khi agent vừa click
    → URL đã được visit → state còn nguyên → không expire
  - Scored frontier: ưu tiên URL có nhiều uncertainty, value, diversity

Thay đổi:
  1. THÊM _on_step_completed callback: gọi sau mỗi step của Solver
     - Đọc open_pages_urls từ browser observation
     - Nếu phát hiện URL mới (khác với URL hiện tại) → thêm vào discovered list
     - Lưu prefix (trace các steps từ node hiện tại đến URL mới)
  
  2. THÊM class FrontierScorer:
     - compute(node_info) → score = alpha*U + beta*V + theta*D
     - U (Uncertainty): dựa trên số lần node đã được explore
     - V (Value): dựa trên success rate của parent node
     - D (Diversity): dựa trên embedding similarity với các node đã explore
     - Tham số alpha, beta, theta có thể config
  
  3. SỬA _filter_links: chỉ dùng cho homepage (depth=0)
     - Depth≥1: URL chỉ đến từ callback, không từ DOM links
  
  4. SỬA run method:
     - Homepage: BFS + DOM links (giữ nguyên) → lấy categories
     - Depth≥1: URL từ callback → thêm vào frontier
     - Frontier được sort theo score mỗi khi chọn node tiếp theo
     - Node có score cao nhất được chọn (không phải FIFO)
  
  5. SỬA Solver.solve: thêm step callback parameter
     - Mỗi step gọi callback với (browser, step_num, traj_steps, obs)
     - Runtime dùng callback này để phát hiện URL mới
  
  6. THÊM _reset_env method:
     - Gọi full_reset_url (nếu có) trước mỗi node mới
     - Reset server state: xóa cart, xóa session
     - Đảm bảo mỗi node bắt đầu với state sạch
```

**Cách làm cụ thể:**
1. Mở `hsge/webarena/runtime.py`
2. Thêm class `FrontierScorer`:
```python
class FrontierScorer:
    """Score frontier nodes by Uncertainty (U), Value (V), Diversity (D).
    
    S = alpha * U + beta * V + theta * D
    
    - U: node càng ít explore → càng cao (khuyến khích khám phá)
    - V: node từ parent có success rate cao → càng cao (khai thác nhánh tốt)
    - D: node khác biệt với các node đã explore → càng cao (tránh trùng lặp)
    """
    def __init__(self, alpha=1.0, beta=1.0, theta=1.0, epsilon=1e-5):
        self.alpha = alpha
        self.beta = beta
        self.theta = theta
        self.epsilon = epsilon
    
    def compute(self, node_info):
        """Tính composite score cho 1 node.
        
        node_info = {
            "exploration_count": int,  # số lần đã explore
            "parent_success_rate": float,  # success rate của parent
            "parent_total_trajs": int,  # total trajs của parent
            "embedding": list[float] | None,  # embedding cho diversity
            "explored_embeddings": list[list[float]],  # embeddings đã explore
        }
        """
        # U: Uncertainty — càng ít explore càng uncertain
        n = node_info.get("exploration_count", 0)
        U = 1.0 / (n + 1.0)
        
        # V: Value — success rate của parent
        parent_sr = node_info.get("parent_success_rate", 0.0)
        parent_n = node_info.get("parent_total_trajs", 0)
        V = parent_sr if parent_n > 0 else 0.5  # mặc định 0.5 nếu chưa có data
        
        # D: Diversity — 1 - max similarity với các node đã explore
        emb = node_info.get("embedding")
        explored_embs = node_info.get("explored_embeddings", [])
        if emb is not None and explored_embs:
            import numpy as np
            emb = np.array(emb)
            max_sim = max(
                np.dot(emb, np.array(e)) / (np.linalg.norm(emb) * np.linalg.norm(np.array(e)) + self.epsilon)
                for e in explored_embs
            )
            D = 1.0 - max_sim
        else:
            D = 1.0  # chưa có embedding → diversity max
        
        score = self.alpha * U + self.beta * V + self.theta * D
        return {"score": round(score, 4), "U": round(U, 4), "V": round(V, 4), "D": round(D, 4)}
```
3. Thêm method `_on_step_completed(self, browser, step, traj_steps, obs)`:
```python
def _on_step_completed(self, browser, step_num, traj_steps, obs):
    """Callback sau mỗi step — phát hiện URL mới NGAY LẬP TỨC.
    
    URL được phát hiện từ open_pages_urls (browser đang ở trang đó).
    Không có khoảng cách thời gian → state còn nguyên, không expire.
    """
    try:
        open_urls = obs.get('open_pages_urls', [])
        if not open_urls:
            # Fallback: lấy từ page evaluate
            open_urls = [browser.env.unwrapped.page.url]
    except:
        return
    
    for url in open_urls:
        if url and url != self._current_url and self.allow.search(url):
            if url not in self._discovered_urls and url not in self.visited:
                self._discovered_urls[url] = {
                    "source_url": self._current_url,
                    "prefix_steps": list(traj_steps),  # steps đã thực thi
                    "depth": self._current_depth + 1,
                }
                print(f"  [discover] New URL from step {step_num}: {url[:80]}")
            self._current_url = url
```
4. Thêm method `_reset_env(self)`:
```python
def _reset_env(self):
    """Reset server state trước mỗi node mới.
    
    Gọi full_reset_url (nếu được config) để xóa cart, session, search params.
    Đảm bảo mỗi node bắt đầu với state sạch như go-browse.
    """
    if self.full_reset_url:
        try:
            import requests
            resp = requests.post(self.full_reset_url, timeout=15)
            if resp.status_code == 200:
                print(f"  [reset] Full env reset OK")
            else:
                print(f"  [reset] Full reset returned {resp.status_code}")
        except Exception as e:
            print(f"  [reset] Failed: {e}")
```
5. Thêm `full_reset_url` vào `__init__`
6. Sửa `Solver.solve` để gọi step callback:
```python
# agents.py
class Solver:
    def solve(self, browser, goal, goal_predicate=None, skill_hints="",
              step_callback=None):
        """step_callback(browser, step_num, traj_steps, obs) → gọi sau mỗi step."""
        steps = []
        screenshots = []
        # ...
        for step_num in range(self.max_steps):
            # ... execute action ...
            if step_callback:
                step_callback(browser, step_num, steps, obs)
        # ...
```
7. Sửa `run` method — scored frontier:
```python
def run(self, root_url):
    frontier = [(root_url, 0)]  # list of (url, depth)
    visited = set()
    self.visited = visited
    self._current_url = root_url
    self._current_depth = 0
    self._discovered_urls = {}
    
    while frontier and len(visited) < self.max_nodes:
        # Scored frontier selection (thay vì FIFO pop(0))
        scored = []
        for url, depth in frontier:
            node_info = self._build_node_info(url, depth)
            score = self.frontier_scorer.compute(node_info)
            scored.append((score["score"], url, depth))
        scored.sort(key=lambda x: -x[0])
        
        # Chọn node tốt nhất
        best_score, url, depth = scored[0]
        frontier.remove((url, depth))
        
        if url in visited:
            continue
        visited.add(url)
        self._current_depth = depth
        
        # Reset env trước mỗi node (giống go-browse)
        self._reset_env()
        
        # Process node với step callback
        browser = self.browser_factory(url)
        obs = browser.reset()
        
        if depth == 0:
            # Homepage: BFS + DOM links
            for task in self.explorer.propose(obs):
                # ... solve với step_callback=self._on_step_completed ...
                pass
            # Lấy DOM links
            for link in self._filter_links(browser.links(), visited):
                frontier.append((link, depth + 1))
        else:
            # Depth≥1: URL chỉ từ callback, không từ DOM
            for task in self.explorer.propose(obs):
                # ... solve với step_callback=self._on_step_completed ...
                pass
        
        # Thêm URL mới từ callback vào frontier
        for url, info in self._discovered_urls.items():
            if url not in visited:
                frontier.append((url, info["depth"]))
        self._discovered_urls = {}
        
        browser.close()
```

**Hướng dẫn kiểm tra:**
1. Chạy `python run_webarena.py --dry-run --out /tmp/test_gobrowse`
2. Mở `run.log` — kiểm tra:
   - Node 1 (depth=0): vẫn có dòng `[filter] X links → Y` (BFS homepage)
   - Node 2+ (depth≥1): có dòng `[discover] New URL from step X: ...` 
     (URL được phát hiện NGAY trong lúc execute task)
   - Không còn dòng `SKIP ... redirect to already-visited` cho checkout URLs
     (vì URL được phát hiện khi browser đang ở trang đó → state còn nguyên)
3. Kiểm tra frontier snapshot: thấy score, U, V, D cho mỗi URL
4. Chạy với `--full-reset-url` nếu có: 
   `python run_webarena.py --full-reset-url "http://..." --dry-run --out /tmp/test_reset`
   - Thấy dòng `[reset] Full env reset OK` trước mỗi node

---

## PHASE 5: Testing & Validation

### Commit 5.1 — Chạy test clustering

```
Module: hsge/tests/test_clustering.py
Mô tả: Chạy test suite để đảm bảo core modules hoạt động
Command: python -m pytest hsge/tests/test_clustering.py -v
Expected: 4 tests passed
```

**Hướng dẫn kiểm tra:**
1. Chạy `python -m pytest hsge/tests/test_clustering.py -v`
2. Thấy `4 passed` (hoặc 5 nếu đã thêm test merge)

---

### Commit 5.2 — Chạy demo.py (mock pipeline)

```
Module: demo.py (root)
Mô tả: Chạy demo end-to-end với mock để verify pipeline
Command: python demo.py
Expected: Pipeline chạy không lỗi, in ra kết quả discovery → transfer → curriculum
```

**Hướng dẫn kiểm tra:**
1. Chạy `python demo.py`
2. Thấy các dòng log: `[library]`, `[discovery]`, `[graph]`, `[curriculum]`, `[transfer]`
3. Cuối cùng thấy bảng so sánh Flat vs AWM vs HSGE

---

### Commit 5.3 — Chạy dry-run WebArena

```
Module: run_webarena.py (root)
Mô tả: Chạy dry-run mode để test wiring không cần WebArena thật
Command: python run_webarena.py --dry-run --out /tmp/final_test
Expected: Script chạy không lỗi, tạo đủ output files
```

**Hướng dẫn kiểm tra:**
1. Chạy `python run_webarena.py --dry-run --out /tmp/final_test`
2. Mở thư mục `/tmp/final_test/`:
   - `run.log` — có log chi tiết
   - `frontier.jsonl` — có frontier snapshot
   - `skills.json` — có skills đã admit
   - `graph.json` — có graph structure
   - `curriculum.json` — có curriculum tasks
   - `transfer.json` — có transfer results
   - `checkpoint.json` — có checkpoint với đầy đủ state
   - `episodes/` — có episodes data
3. Chạy lại với `--resume`: `python run_webarena.py --dry-run --out /tmp/final_test --resume`
   - Thấy `[resume]` message
   - Không crash

---

## Phân công thành viên & Thứ tự thực hiện

### Nguyên tắc phân công

- **Thành viên A (Người 1)**: Làm các module độc lập, không phụ thuộc vào module khác — có thể làm song song với B. Nhận các commit dễ/trung bình ở PHASE 1+3.
- **Thành viên B (Người 2)**: Làm các module phức tạp, có nhiều phụ thuộc — cần hiểu sâu về kiến trúc. Nhận runtime (commit lớn nhất) và các cải tiến nâng cao.
- **Cả 2 cùng làm**: Các commit test ở PHASE 5.
- **Mũi tên**: A → B nghĩa là A làm xong thì B mới bắt đầu được (có phụ thuộc).

### Sơ đồ thực hiện song song

```
Thành viên A (luồng 1)           Thành viên B (luồng 2)
─────────────────────             ─────────────────────
                                  
0.1 Copy project (cả 2)          
0.2 Xóa file (cả 2)              
│                                
├── 1.1 llm.py ──────────────────┤ 1.3 clustering.py
├── 1.2 backends.py              │ 1.4 abstraction.py
├── 1.6 segmentation.py          │ 1.5 verification.py 🔴
├── 2.1 browser.py               │
├── 2.3 frontier_filter.py (MỚI) │
├── 3.2 analyze_frontier.py(MỚI) │
├── 3.3 recover_checkpoint(MỚI)  │
│                                │
├── (chờ B xong 1.4,1.5)        ├── 1.7 library.py
│                                ├── 1.8 discovery.py 🟠
│                                │
├── 2.2 agents.py ───────────────┤
│                                │
├── (chờ B xong 1.7,1.8,2.1,2.3)│
│                  ╔═════════════╧══════════════╗
│                  ║  2.4 runtime.py 🔴🟠 (KHÓ) ║
│                  ╚═════════════╤══════════════╝
│                                │
├── 3.1 run_webarena.py ────────┤
│                                │
├── (chờ B xong)                ├── 4.1 library retrieval 🟡
│                                ├── 4.2 agents tool-use 🔴 (KHÓ)
│                                ├── 4.3 runtime verify 🔴
│                                ├── 4.4 runtime sync graph 🟠
│                                ├── 4.5 curriculum planner 🟠
│                                ├── 4.6 runtime checkpoint 🟡
│                                ├── 4.7 runtime transfer 🟡 (KHÓ)
│                                ├── 4.8 runtime monitoring 🟢
│                                ├── 4.9 runtime callback discovery + scored frontier 🟠 (MỚI)
│                                │
├── 5.1 test clustering ────────┤
├── 5.2 demo.py ────────────────┤
├── 5.3 dry-run ────────────────┤
```

### Bảng phân công chi tiết

| Phase | # | Commit message | Module | Người | Mức độ | Phụ thuộc |
|-------|---|---------------|--------|-------|--------|-----------|
| **0** | 0.1 | `chore: init project from hsge_project_raw` | root | **Cả 2** | Dễ | — |
| **0** | 0.2 | `chore: remove compare_three_way.py (unused)` | root | **Cả 2** | Dễ | 0.1 |
| **1** | 1.1 | `feat(llm): add complete_vision_json with fallback` | hsge/llm | **A** | Dễ | 0.2 |
| **1** | 1.2 | `feat(backends): robust JSON parsing + vision support` | hsge/backends | **A** | TB | 1.1 |
| **1** | 1.3 | `feat(clustering): add merge_threshold for online merging` | hsge/clustering | **B** | Dễ | 0.2 |
| **1** | 1.4 | `fix(abstraction): handle invalid LLM response gracefully` | hsge/abstraction | **B** | Dễ | 0.2 |
| **1** | 1.5 | `fix(verification): admit skill when no verify contexts` | hsge/verification | **B** | Dễ | 0.2 |
| **1** | 1.6 | `fix(segmentation): defensive LLM parsing + fallback` | hsge/segmentation | **A** | TB | 1.1 |
| **1** | 1.7 | `feat(library): add admit callback + retry mechanism` | hsge/library | **B** | TB | 1.4, 1.5 |
| **1** | 1.8 | `fix(discovery): remove co-occurrence composition edges` | hsge/discovery | **B** | Dễ | 1.6, 1.7 |
| **2** | 2.1 | `feat(browser): screenshot + DOM link extraction + error handling` | hsge/webarena/browser | **A** | TB | 0.2 |
| **2** | 2.2 | `feat(agents): skill hints in prompt + vision support` | hsge/webarena/agents | **A** | TB | 1.1, 1.2 |
| **2** | 2.3 | `feat(webarena): add frontier URL filter (template clustering)` | hsge/webarena/frontier_filter | **A** | TB | 0.2 |
| **2** | 2.4 | `feat(runtime): checkpoint/resume + frontier filter + dual LLM` | hsge/webarena/runtime | **B** | **Khó** | 1.7, 1.8, 2.1, 2.2, 2.3 |
| **3** | 3.1 | `feat(cli): provider system + dual model + .env loader` | run_webarena.py | **A** | TB | 1.2, 2.4 |
| **3** | 3.2 | `feat(scripts): add analyze_frontier.py for URL stats` | analyze_frontier.py | **A** | Dễ | 0.2 |
| **3** | 3.3 | `feat(scripts): add recover_checkpoint.py` | recover_checkpoint.py | **A** | Dễ | 0.2 |
| **4** | 4.1 | `fix(library): use skill card embedding for retrieval` | hsge/library | **B** | TB | 1.7 |
| **4** | 4.2 | `feat(agents): upgrade skill hints to tool-use (function calling)` | hsge/webarena/agents | **B** | **Khó** | 2.2 |
| **4** | 4.3 | `fix(runtime): implement real verification from episodes` | hsge/webarena/runtime | **B** | TB | 2.4 |
| **4** | 4.4 | `feat(runtime): sync OperatorGraph to HierarchicalGraph` | hsge/webarena/runtime | **B** | TB | 2.4 |
| **4** | 4.5 | `feat(curriculum): generate tasks from planner (not composition)` | hsge/curriculum + runtime | **B** | TB | 2.4 |
| **4** | 4.6 | `feat(runtime): save full state in checkpoint (opgraph + clusterer)` | hsge/webarena/runtime | **B** | TB | 2.4 |
| **4** | 4.7 | `feat(runtime): transfer with real execution + adaptation` | hsge/webarena/runtime | **B** | **Khó** | 2.4 |
| **4** | 4.8 | `feat(runtime): add error handling + monitoring metrics` | hsge/webarena/runtime | **B** | TB | 2.4 |
| **4** | 4.9 | `feat(runtime): callback-based URL discovery + scored frontier (UVD)` | hsge/webarena/runtime | **B** | **Khó** | 2.4 |
| **5** | 5.1 | `test: verify clustering tests pass` | hsge/tests | **Cả 2** | Dễ | Tất cả |
| **5** | 5.2 | `test: verify demo.py end-to-end pipeline` | demo.py | **Cả 2** | Dễ | Tất cả |
| **5** | 5.3 | `test: verify dry-run WebArena exploration` | run_webarena.py | **Cả 2** | Dễ | Tất cả |

### Hướng dẫn làm việc song song

#### Luồng của Thành viên A (các module độc lập)

```
Bước 1: Làm 0.1 + 0.2 (cùng B)
Bước 2: Làm song song với B:
  ├── 1.1 llm.py
  ├── 1.2 backends.py (sau 1.1)
  ├── 1.6 segmentation.py (sau 1.1)
  ├── 2.1 browser.py
  ├── 2.3 frontier_filter.py (MỚI)
  ├── 3.2 analyze_frontier.py (MỚI)
  └── 3.3 recover_checkpoint.py (MỚI)
Bước 3: Chờ B xong 1.4 + 1.5 → làm 2.2 agents.py (cần backends từ 1.2)
Bước 4: Chờ B xong 2.4 (runtime) → làm 3.1 run_webarena.py
Bước 5: Cùng B test (PHASE 5)
```

#### Luồng của Thành viên B (core + runtime)

```
Bước 1: Làm 0.1 + 0.2 (cùng A)
Bước 2: Làm song song với A:
  ├── 1.3 clustering.py
  ├── 1.4 abstraction.py
  └── 1.5 verification.py
Bước 3: Làm tiếp (sau 1.4, 1.5):
  ├── 1.7 library.py
  └── 1.8 discovery.py
Bước 4: Chờ A xong 1.6, 2.1, 2.2, 2.3 → làm 2.4 runtime.py (LỚN NHẤT)
Bước 5: Làm các cải tiến Phase 4 (sau 2.4):
  ├── 4.1 library retrieval 🟡
  ├── 4.2 agents tool-use 🔴 (cần A xong 2.2)
  ├── 4.3 runtime verify 🔴
  ├── 4.4 runtime sync graph 🟠
  ├── 4.5 curriculum planner 🟠
  ├── 4.6 runtime checkpoint 🟡
  ├── 4.7 runtime transfer 🟡
  ├── 4.8 runtime monitoring 🟢
  └── 4.9 runtime callback discovery + scored frontier 🟠 (MỚI)
Bước 6: Cùng A test (PHASE 5)
```

### Kiểm tra tích hợp cuối mỗi phase

Sau khi cả 2 hoàn thành xong mỗi phase, cùng chạy:

```bash
# Phase 1 xong
python -m pytest hsge/tests/test_clustering.py -v
python demo.py

# Phase 2 xong
python run_webarena.py --dry-run --out /tmp/phase2_test

# Phase 3 xong
python run_webarena.py --help
python run_webarena.py --dry-run --out /tmp/phase3_test

# Phase 4 xong
python run_webarena.py --dry-run --out /tmp/phase4_test
python run_webarena.py --dry-run --out /tmp/phase4_test --resume

# Phase 4 — Kiểm tra callback discovery + scored frontier
python run_webarena.py --dry-run --out /tmp/test_gobrowse
# Mở run.log: có dòng [discover] New URL from step X: ...
# Kiểm tra frontier snapshot có score, U, V, D

# Phase 5 xong (final)
python run_webarena.py --dry-run --out /tmp/final_test
python run_webarena.py --dry-run --out /tmp/final_test --resume
```

### Chú thích
- **Dễ**: Thêm vài dòng code, không thay đổi logic
- **Trung bình**: Thay đổi logic trong 1 function, cần hiểu code
- **Khó**: Thay đổi kiến trúc, nhiều function, cần thiết kế cẩn thận
- 🔴 = Critical fix (P0)  🟠 = Important fix (P1)  🟡 = Reliability (P2)  🟢 = Polish (P3)
