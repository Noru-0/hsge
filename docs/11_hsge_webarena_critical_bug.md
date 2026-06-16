# HSGE WebArena Critical Bug

## Bug chính

`HSGEPromptConstructor` đang map action HSGE/BrowserGym `fill()` sang WebArena `type` với flag submit:

```text
fill('bid','text') -> type [bid] [text] [1]
```

Trong WebArena, `[1]` nghĩa là **press Enter sau khi type**. Nhưng trong HSGE/BrowserGym, `fill()` chỉ có nghĩa là điền text vào field, không submit form.

## Vì sao gây FAIL nhiều

Khi agent điền email/search box, WebArena tự bấm Enter ngay:

```text
fill email -> submit form quá sớm -> báo thiếu password
fill lại email/password -> loop -> Early stop
```

Các trajectory trong `results/lora_model` cho thấy nhiều task fail kiểu:

```text
Early stop: Same typing action for 5 times
Early stop: Failed to parse actions for 5 times
```

Ví dụ task login/order:

```text
fill('10923','user_email')
=> type [10923] [user_email] [1]
=> form submit khi password chưa có
=> agent lặp lại email field
```

## File cần sửa

```text
webarena-main 2/agent/prompts/prompt_constructor.py
```

Đoạn hiện tại:

```python
elif fn == "fill":
    if len(args) < 2:
        raise ActionParsingError("fill() needs bid and text")
    return f"type [{args[0]}] [{args[1]}] [1]"
```

## Fix đề xuất

Đổi `[1]` thành `[0]`:

```python
elif fn == "fill":
    if len(args) < 2:
        raise ActionParsingError("fill() needs bid and text")
    return f"type [{args[0]}] [{args[1]}] [0]"
```

Nếu agent cần submit search/form, prompt nên dạy model dùng action riêng:

```text
press('Enter')
click('search_button_id')
```

## Verify nhanh

Chạy test converter:

```bash
cd "webarena-main 2"
python3 - <<'PY'
from agent.prompts.prompt_constructor import HSGEPromptConstructor
print(HSGEPromptConstructor._hsge_to_webarena("fill('123','hello')"))
PY
```

Kết quả đúng:

```text
type [123] [hello] [0]
```

## Bug liên quan

`select_option()` cũng đang bị map thành `type`, không tương đương với select/dropdown trong WebArena:

```text
select_option('bid','option') -> type [bid] [option] [1]
```

Nên tạm thời bỏ `select_option()` khỏi prompt HSGE khi chạy với `id_accessibility_tree`, hoặc thay bằng workflow:

```text
click dropdown/menu
click option
```

