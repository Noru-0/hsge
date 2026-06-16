# Debug: WebArena Shopping Auto-Login & Sign-Out Issue

**Date**: 2026-06-16 | **Setup**: HSGE agent eval on WebArena shopping domain via SSH (`root@146.115.17.156:63558`)

## Symptom

Task 47 (và các task cần login sau đó) bị sign out ngay action đầu tiên. Agent bắt đầu logged in ở homepage (hiện "Sign Out") nhưng khi click "My Account" → redirect tới `/customer/account/logoutSuccess/`.

## Root Cause Analysis

### 1. Thiếu `wait_for_load_state` sau khi click Sign In (✅ Fixed)

**File**: `browser_env/auto_login.py` – hàm `renew_comb()`

Sau `page.get_by_role("button", name="Sign In").click()`, code lưu `storage_state` ngay lập tức mà không đợi login hoàn tất → cookie được save trước khi session authenticated được thiết lập → race condition.

**Fix**: Thêm `page.wait_for_load_state("networkidle")` sau mỗi lần click Sign In ở tất cả 4 sites (shopping, reddit, shopping_admin, gitlab).

### 2. `is_expired` test sai URL (✅ Fixed)

**File**: `browser_env/auto_login.py` – constant `URLS`

Validation cookie dùng URL `/wishlist/` – trang này có thể truy cập không cần login trong Magento → `is_expired` báo "valid" dù session thực sự đã hỏng. Khi agent access `/customer/account/` (trang protected), Magento phát hiện session lỗi → redirect `logoutSuccess`.

**Fix**: Đổi URL validation từ `/wishlist/` → `/customer/account/` + keyword `"My Account"`, dùng `url_exact=False`.

### 3. Không verify login success (✅ Fixed)

**File**: `browser_env/auto_login.py` – hàm `renew_comb()`

Không có bước kiểm tra login có thực sự thành công không. Nếu sai password hoặc bị CAPTCHA, code vẫn lưu storage state với cookie không valid.

**Fix**: Thêm `assert "login" not in page.url.lower()` sau khi login + in log xác nhận.

### 4. Thiếu error handling trong subprocess call (✅ Fixed)

**File**: `run.py` – hàm `test()`

`subprocess.run()` gọi `auto_login.py` không check return code → nếu auto_login fail thì eval vẫn chạy tiếp với cookie hỏng.

**Fix**: Thêm `capture_output=True`, check `returncode`, log `[AutoLogin]` status.

### 5. PHPSESSID collision giữa Shopping & Reddit (⚠️ Cần fix phía server)

Cả Shopping (Magento) và Reddit (Postmill) đều dùng `PHPSESSID` làm tên session cookie. Khi cả 2 chạy trên cùng domain (localhost, khác port), browser coi chúng là cùng 1 cookie → login site này sẽ overwrite session của site kia.

**Fix đề xuất**: Đổi tên session cookie cho Reddit trong PHP config:

```ini
; Trong php.ini của Reddit container
session.name = REDDITSESSID
```

Hoặc sửa trong Postmill app config nếu có setting riêng.

## Files Modified

| File | Changes |
|------|---------|
| `webarena-main/browser_env/auto_login.py` | `wait_for_load_state` + URL fix + login verification |
| `webarena-main-lora/browser_env/auto_login.py` | Same |
| `webarena-main/run.py` | Subprocess error handling + AutoLogin logging |
| `webarena-main-lora/run.py` | Same |

## Key Observation: Session Still Invalidates

Dù tất cả fix trên đã được apply và `[AutoLogin] Shopping login OK → .../customer/account/` đã xác nhận login thành công, eval v5 vẫn bị sign out ở task 47.

**Giả thuyết**: Magento dùng `session_regenerate_id()` sau login để chống session fixation. `networkidle` có thể fire trước khi session ID mới được set → storage state lưu session ID cũ (đã bị invalidate). Cần thêm `time.sleep(2-3)` sau `networkidle`.

Hoặc Magento Full Page Cache render homepage với trạng thái logged-in từ cache, nhưng session thực sự không valid khi access dynamic page như `/customer/account/`.

## Next Steps

1. Thêm `time.sleep(3)` sau `wait_for_load_state` trong `renew_comb`
2. Đổi tên PHPSESSID cho Reddit (phía Docker container)
3. Test thêm: dùng `page.context.add_cookies()` thay vì `storage_state` để set cookie trực tiếp
