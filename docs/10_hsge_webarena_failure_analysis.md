# HSGE WebArena Failure Analysis

Phân tích này dựa trên kết quả trong:

```bash
webarena-main 2/results/lora_model
webarena-main 2/log_files/log_20260616072729_261.log
```

## Tóm tắt kết quả

| Chỉ số | Giá trị |
|--------|---------|
| Render HTML | 72 |
| Trace ZIP | 69 |
| PASS | 10 |
| FAIL | 59 |
| ERROR | 2 |
| Chưa có result trong log | 1 |

Kết luận chính: agent không fail chủ yếu vì WebArena crash. Phần lớn fail đến từ mismatch giữa action semantics HSGE/BrowserGym và WebArena, cộng với grounding yếu khi chọn element ID trong accessibility tree.

## Failure modes chính

| Nhóm lỗi | Số task fail/error bị ảnh hưởng | Mức độ |
|----------|----------------------------------|--------|
| Click/type vào element sai hoặc không tương tác | ~34 | Critical |
| Early stop do lặp action | ~26 | Critical |
| `select_option()` bị map thành `type` | ~13 | High |
| Dừng sớm với câu trả lời "không tìm thấy" | ~11 | High |
| `fill()` submit form ngoài ý muốn | nhiều login/search task | Critical |
| JSON parse fail | ~4 | Medium |
| Credential placeholder | ~4 rõ ràng, thực tế nhiều hơn | High |
| Runtime error | 2 | Medium |

## 1. `fill()` bị map sai sang `type ... [1]`

### Triệu chứng

HSGE model sinh:

```json
{"action": "fill('10923','user_email')"}
```

Bridge hiện convert thành:

```text
type [10923] [user_email] [1]
```

Trong WebArena, tham số cuối `[1]` nghĩa là press Enter sau khi type. Với BrowserGym/HSGE, `fill()` thường chỉ điền text, không submit.

### Hậu quả

Login/search forms bị submit quá sớm. Ví dụ:

```text
fill email -> press Enter -> form báo thiếu password
agent fill lại email -> loop -> Early stop: Same typing action
```

Các task bị ảnh hưởng rõ: `47`, `96`, `189`, `231`, `232`, `233`, một số search/category task.

### Fix đề xuất

Trong `webarena-main 2/agent/prompts/prompt_constructor.py`, đổi mapping:

```python
elif fn == "fill":
    if len(args) < 2:
        raise ActionParsingError("fill() needs bid and text")
    return f"type [{args[0]}] [{args[1]}] [0]"
```

Nếu muốn submit search, model cần sinh action riêng:

```text
press('Enter')
```

hoặc:

```text
click('search_button_id')
```

## 2. Thiếu WebArena action vocabulary

### Triệu chứng

Prompt HSGE hiện chỉ dạy:

```text
click
fill
select_option
goto
go_back
send_msg_to_user
```

Trong WebArena, agent cần thêm:

```text
scroll
press
hover
type with enter/no-enter
```

Review tasks fail vì agent không scroll/xem toàn bộ review rồi kết luận không có. Menu/category tasks fail vì không có `hover` hoặc action phù hợp để mở menu. Search tasks fail vì `fill()` vừa type vừa submit hoặc không có cách explicit để submit.

### Fix đề xuất

Mở rộng HSGE prompt action schema:

```text
click('bid')
type('bid','text','0_or_1')
fill('bid','text')
press('key')
scroll('down'|'up')
hover('bid')
goto('url')
go_back()
send_msg_to_user('answer')
```

Và thêm mapping trong `HSGEPromptConstructor`:

```python
"type": "type",
"press": "press",
"scroll": "scroll",
"hover": "hover",
```

Mapping cụ thể:

```python
elif fn == "type":
    if len(args) < 2:
        raise ActionParsingError("type() needs bid and text")
    enter = args[2] if len(args) >= 3 else "1"
    return f"type [{args[0]}] [{args[1]}] [{enter}]"

elif fn == "press":
    if not args:
        raise ActionParsingError("press() missing key")
    return f"press [{args[0]}]"

elif fn == "scroll":
    direction = args[0] if args else "down"
    return f"scroll [{direction}]"

elif fn == "hover":
    if not args:
        raise ActionParsingError("hover() missing bid")
    return f"hover [{args[0]}]"
```

## 3. `select_option()` map sai sang `type`

### Triệu chứng

Agent sinh:

```json
{"action": "select_option('4098','Electronics')"}
```

Bridge convert:

```text
type [4098] [Electronics] [1]
```

Nhưng nhiều element là:

```text
menuitem '\ue622 Cell Phones & Accessories'
combobox 'Sort By'
```

Type vào các element này không tương đương select option.

### Hậu quả

Task category/filter/sort bị loạn, ví dụ:

```text
type [25712] [Amazon Basics] where [25712] is combobox 'Sort By'
```

Các task bị ảnh hưởng rõ: `124`, `158`, `160`, `226`, `229`, `230`, `239`, `240`, `270`, `273`, `276`.

### Fix đề xuất

Ngắn hạn: không dạy `select_option()` trong prompt HSGE khi dùng `id_accessibility_tree`.

Thay bằng:

```text
click('bid') để mở dropdown/menu
click('option_bid') để chọn option
```

Nếu vẫn muốn giữ `select_option`, cần chuyển sang `action_set_tag=playwright` hoặc implement action WebArena riêng, không nên map nó thành `type`.

## 4. Agent chọn sai element ID

### Triệu chứng

Action hợp lệ về format, nhưng ID sai:

```text
click [4224] where [4224] is StaticText 'Items '
click [4152] where [4152] is heading "Search results..."
click [5193] where [5193] is RootWebArea
type [8488] where [8488] is link 'Advanced Search'
```

### Nguyên nhân

Model không bám chặt accessibility tree. Nó suy luận đúng hướng ở mức natural language nhưng chọn ID không tương ứng với element tương tác.

Ví dụ task `276`:

```text
Mục tiêu: Search for "switch accessories"
Agent đã search xong nhưng lại click heading/static text/root web area thay vì stop hoặc chọn product/filter hợp lệ.
```

### Fix đề xuất

Thêm rule mạnh vào prompt:

```text
Only click interactive elements: link, button, checkbox, radio, menuitem, option.
Do not click StaticText, heading, RootWebArea, paragraph, or generic text.
Only fill/type into textbox, searchbox, combobox, or textarea-like inputs.
If the target bid is not interactive, choose another bid or scroll.
```

Thêm validation guard trong runtime trước khi execute:

- Nếu `click` vào `StaticText`, `heading`, `RootWebArea`: reject và retry LLM với message lỗi.
- Nếu `type/fill` vào `link`, `StaticText`, `heading`, `menuitem`: reject và retry.

Guard này nên nằm trong `PromptAgent.next_action()` sau khi parse action nhưng trước khi return action, vì lúc đó có `state_info["info"]["observation_metadata"]` để kiểm tra role/name của element.

## 5. Credential placeholder

### Triệu chứng

Agent gõ:

```text
user_email
my_email
user@example.com
my_password
user_password
```

Ví dụ task `96`, `231`, `233`.

### Nguyên nhân

Prompt HSGE không chứa WebArena account hints. Trong WebArena gốc, prompt có đoạn hướng dẫn vào homepage/password page hoặc dùng account có sẵn. Nếu `storage_state` không login sẵn hoặc bị fail, agent không biết credential thật.

### Fix đề xuất

Ưu tiên 1: đảm bảo auto-login hoạt động và `storage_state` đúng.

Kiểm tra:

```bash
ls -la .auth
python3 browser_env/auto_login.py
```

Ưu tiên 2: thêm account hint vào prompt HSGE:

```text
Known shopping account:
email: emma.lopez@gmail.com
password: Password.123
```

Hoặc thêm đoạn WebArena gốc:

```text
http://homepage.com/password.html lists all account names and passwords.
```

## 6. Dừng sớm với "No reviewers/no criticisms found"

### Triệu chứng

Review tasks dừng sau 1 bước:

```text
stop [No reviewers mentioned ...]
stop [No criticisms found for this product.]
```

Nhưng reference answer có reviewer/sentence thật.

Các task rõ: `23`, `25`, `26`, `163`, `164`, `165`, `167`.

### Nguyên nhân

Agent chỉ nhìn current viewport hoặc phần product summary, không scroll tới reviews hoặc không mở review section. `current_viewport_only=True` làm observation hẹp hơn.

### Fix đề xuất

Prompt rule:

```text
For review/criticism tasks, never answer "not found" until you have opened or scrolled through the review section.
If a page has a Reviews link, click it first.
If reviews are not visible, scroll down before concluding.
```

Runtime/config option:

- Có thể thử bỏ `--current_viewport_only` cho các task review, nhưng chi phí context tăng.
- Hoặc giữ viewport-only nhưng dạy agent dùng `scroll('down')`.

## 7. JSON parse fail

### Triệu chứng

Một số raw output không parse được:

```json
{"thought": "..." "action": "fill('4210','my_email')"}
```

hoặc nested quotes:

```json
{"action": "send_msg_to_user('No products found for the search term "switch accessories"')"}
```

### Fix đề xuất

Prompt:

```text
Return valid JSON only.
Use double quotes for JSON keys and values.
Inside the action string, do not use unescaped double quotes.
Prefer single quotes inside action arguments.
```

Parser hardening:

- Nếu JSON parse fail, regex fallback lấy `"action": "..."`
- Normalize nested quote patterns.
- Với `send_msg_to_user`, cho phép parse action trực tiếp nếu response chứa `send_msg_to_user(...)`.

## 8. Runtime errors

### `punkt_tab` missing

Lỗi:

```text
Resource 'punkt_tab' not found
```

Fix:

```bash
/usr/bin/python3 -m nltk.downloader punkt punkt_tab
```

### Unicode `KeyError('’')`

Lỗi:

```text
KeyError('’')
```

Nguyên nhân: WebArena `_keys2ids()` không map được smart quote.

Fix nhanh trong bridge trước khi trả action:

```python
def _normalize_text(text: str) -> str:
    return (
        text.replace("’", "'")
            .replace("‘", "'")
            .replace("“", '"')
            .replace("”", '"')
            .replace("–", "-")
            .replace("—", "-")
    )
```

Áp dụng cho argument text trong `fill`, `type`, `send_msg_to_user`.

## Patch plan ưu tiên

### P0: Sửa semantic mismatch

- `fill()` -> `type [id] [text] [0]`
- Thêm `type(id,text,enter)`, `press`, `scroll`, `hover`
- Bỏ hoặc hạn chế `select_option`

### P1: Sửa prompt grounding

- Cấm click/type vào non-interactive roles.
- Thêm workflow cho review tasks: click reviews, scroll, không kết luận sớm.
- Thêm credential/account hint hoặc đảm bảo auto-login.

### P2: Robustness

- JSON/action fallback parser.
- Unicode normalization.
- NLTK data install.

### P3: Runtime guard

Thêm guard kiểm tra role trước khi execute action. Nếu action sai role, retry LLM với feedback:

```text
The previous action targeted a non-interactive element:
click [4224] where [4224] is StaticText 'Items'.
Choose a valid clickable element instead.
```

## Quick checklist trước khi chạy lại

```bash
cd /root/webarena-main

# Verify model server
curl -s http://localhost:8000/v1/models -H "Authorization: Bearer not-needed"

# Verify NLTK
/usr/bin/python3 -m nltk.downloader punkt punkt_tab

# Verify prompt constructor
/usr/bin/python3 - <<'PY'
import json
p='agent/prompts/jsons/p_hsge_actree_2s.json'
j=json.load(open(p))
print(j['meta_data']['prompt_constructor'])
PY

# Should print:
# HSGEPromptConstructor
```

## Kỳ vọng sau fix

Các fix trên không đảm bảo pass rate cao ngay, nhưng sẽ giảm mạnh các lỗi "ngu":

- không submit form ngay sau `fill`
- không type vào dropdown/menu/link
- ít loop login/search hơn
- review tasks có cơ hội scroll tới nội dung cần tìm
- ít parse failure do JSON

Nếu sau P0/P1 mà pass rate vẫn thấp, nguyên nhân còn lại nhiều khả năng là năng lực model/LoRA chưa đủ cho WebArena reasoning và grounding, cần bổ sung dữ liệu SFT đúng action format WebArena hoặc fine-tune trên trajectory WebArena.
