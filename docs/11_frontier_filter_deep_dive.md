# Frontier Filter — Deep Dive

> File: `hsge/webarena/frontier_filter.py`

Bộ lọc URL tự động, hoạt động trên **mọi website** không cần cấu hình thủ công. Dùng để giảm hàng trăm link trên một trang xuống còn vài chục URL chất lượng, tránh lãng phí credit LLM vào các trang vô nghĩa.

---

## Tổng quan Pipeline

```
300+ links từ 1 trang
       ↓
  Pass 1: extract_templates()      Gom URL theo mẫu cấu trúc
       ↓
  7-15 template clusters           Mỗi cluster = 1 kiểu URL
       ↓
  Pass 1b: template_priority()     Chấm điểm từng cluster
       ↓
  Sắp xếp theo điểm giảm dần
       ↓
  Pass 2: _sample_diverse()        Chọn k URL đại diện/cluster
       ↓
  27-60 URLs                       Output đã lọc
```

---

## Pass 1 — `extract_templates(urls)`

### Ý tưởng cốt lõi: Position-based variable detection

Thay vì dùng regex cố định cho từng domain, ta **so sánh giá trị ở cùng vị trí path depth trên TOÀN BỘ danh sách URL**. Nếu một vị trí có nhiều giá trị khác nhau → đó là biến (variable).

### Ví dụ với 4 URLs

```
URL 1: /beauty-personal-care/foot-hand-nail-care.html
URL 2: /beauty-personal-care/makeup.html
URL 3: /video-games/xbox-one.html
URL 4: /video-games/xbox-one/accessories.html
```

**Bước 1: Parse thành các segment**

```
         depth=0              depth=1                 depth=2
URL 1: [beauty-personal-care, foot-hand-nail-care,  (none)       ]
URL 2: [beauty-personal-care, makeup,               (none)       ]
URL 3: [video-games,         xbox-one,              (none)       ]
URL 4: [video-games,         xbox-one,              accessories  ]
```

**Bước 2: Phân tích từng depth**

| Depth | Các giá trị | Số distinct | Là biến? |
|-------|------------|-------------|----------|
| 0 | `beauty-personal-care`, `video-games` | 2/4 = 50% | ✅ CÓ (>15%) |
| 1 | `foot-hand-nail-care`, `makeup`, `xbox-one` | 3/4 = 75% | ✅ CÓ (>15%) |
| 2 | `accessories` (chỉ URL 4 có) | 1/1 = 100% | ⚠️ Chỉ 1 URL có depth này → không đủ để kết luận → coi là tĩnh |

**Bước 3: Sinh template**

```
URL 1: /{slug}/{slug}               → "beauty-personal-care" và "foot-hand-nail-care" đều là biến
URL 2: /{slug}/{slug}               → cùng template với URL 1
URL 3: /{slug}/{slug}               → cùng template
URL 4: /{slug}/{slug}/accessories   → template riêng vì có depth=2 tĩnh
```

**Kết quả:**
```
Cluster "/{slug}/{slug}":         [URL 1, URL 2, URL 3]  (3 URLs)
Cluster "/{slug}/{slug}/accessories": [URL 4]             (1 URL)
```

### Token types

Sau khi xác định vị trí là biến, mỗi segment được phân loại:

| Pattern | Placeholder | Ví dụ |
|---------|-------------|-------|
| UUID | `{uuid}` | `a1b2c3d4-e5f6-...` |
| Hash ≥ 32 hex chars | `{hash}` | `a1b2c3d4e5f6...` |
| Số ≥ 3 chữ số | `{id}` | `12345` |
| Số < 3 chữ số | `{n}` | `42` |
| Chữ thường | `{slug}` | `apple-iphone-11` |
| Rỗng | `{empty}` | (segment trống) |

### Tham số

| Tham số | Default | Ý nghĩa |
|---------|---------|---------|
| `_VARIABLE_RATIO` | `0.15` | Nếu >15% URL khác nhau ở depth này → biến |
| `_VARIABLE_ABSOLUTE_MIN` | `3` | HOẶC nếu ≥3 giá trị text khác nhau → biến |
| `_KNOWN_EXTENSIONS` | `.html`, `.htm`, `.php`, `.asp`, `.jsp`, `.aspx` | Tách đuôi file trước khi phân loại |

> **Mẹo tuning**: Giảm `_VARIABLE_RATIO` (vd 0.05) → ít vị trí bị coi là biến → **nhiều template hơn** → giữ được nhiều URL hơn.

---

## Pass 1b — `template_priority(template, cluster_size)`

Chấm điểm mỗi cluster để biết cluster nào quan trọng, cluster nào ít giá trị.

### Công thức

```
score = 6.0                              (base)
      - n_placeholders × 0.5             (1)
      + depth_bonus                      (2)
      - length_penalty                   (3)
      ± keyword_match                    (4)
      + cluster_size_bonus               (5)
      - query_param_penalty              (6)
```

### (1) Placeholder penalty: `-0.5 / placeholder`

Template càng nhiều `{variable}` → càng "động" → điểm thấp hơn.

| Template | n_placeholders | Penalty |
|----------|:---:|--------|
| `/checkout/cart` | 0 | 0 |
| `/catalog/{slug}.html` | 1 | −0.5 |
| `/{slug}/{slug}.html{?params}` | 3 | −1.5 |

### (2) Depth scoring

| Độ sâu (# `/`) | Điểm | Logic |
|:---:|------|-------|
| ≤ 1 | **+0.5** | Trang gốc, top-level |
| 2-3 | **+1.0** | **Sweet spot** — category, listing |
| 4 | 0 | Trung tính |
| ≥ 5 | **−0.3 / level** | Quá sâu, nội dung bị chôn |

### (3) Length penalty

| Độ dài template | Penalty |
|:---:|------|
| > 100 ký tự | −0.8 |
| > 70 ký tự | −0.3 |

### (4) Keyword boost/penalty

Template chứa keyword trong static segments:

| Nhóm | Keywords | Điểm |
|------|----------|:---:|
| **HIGH** | `login`, `cart`, `checkout`, `product`, `detail`, `account`, `wiki`, `article`... | **+0.8 / từ** |
| **LOW** | `redirect`, `print`, `pdf`, `rss`, `privacy`, `terms`, `newsletter`... | **−0.6 / từ** |

### (5) Cluster size scoring

| Số URL trong cluster | Điểm | Logic |
|:---:|:---:|-------|
| 1 | **+1.0** | Trang độc nhất, quan trọng |
| 2-5 | **+0.5** | Cluster nhỏ |
| **6-30** | **+1.0** | Listing page lý tưởng |
| 31-100 | 0.0 | Trung tính |
| > 100 | **−0.5** | Nghi ngờ auto-generated spam |

### (6) Query param penalty

Có `{?params}` → **−0.4** (trang động, ít giá trị).

---

## Pass 2 — `_sample_diverse(urls, k)`

Với mỗi cluster, chọn `k` URL đại diện, ưu tiên **đa dạng về độ sâu path**:

- Sắp xếp URL theo path depth
- Chọn `k` vị trí cách đều trong danh sách đã sắp xếp
- Nếu `k=1`: chọn URL ở vị trí median

### Phân bổ `k` theo kích thước cluster

| Cluster size | Số URL giữ (`k`) |
|:---:|:---:|
| ≤ 3 | Giữ hết |
| 4-20 | 5 |
| 21-60 | 8 |
| > 60 | 3 |

---

## Main API — `filter_frontier(frontier, max_output=150, verbose=False)`

### Input

```python
frontier = [
    {"url": "http://shop/beauty.html", "depth": 1},
    {"url": "http://shop/product/123.html", "depth": 2},
    ...
]
```

### Output

```python
filtered = [
    {"url": "http://shop/beauty.html", "depth": 1},
    {"url": "http://shop/product/123.html", "depth": 2},
    ...  # ≤ max_output items
]
```

### Verbose mode

Khi `verbose=True`, in bảng diagnostic:

```
======================================================================
  Template clusters (7 unique, budget=150)
======================================================================
  [  45] score=+5.2  /{slug}/{slug}.html
  [  12] score=+4.8  /checkout/cart
  [   3] score=+3.1  /customer/account/login
  [ 200] score=+2.0  /catalog/product_compare/index{?params}
  ...
```

---

## Runtime integration (`runtime.py`)

Trong `WebArenaExplorer`, frontier filter được dùng qua method `_filter_links()` với cơ chế **global template quota**:

```python
self._frontier_max = 120    # max URLs giữ mỗi node
self._template_max = 5      # max URLs mỗi template TRÊN TOÀN BỘ run
```

Điều này ngăn việc cùng 1 kiểu URL (vd: `/product/{id}.html`) bị thêm vào frontier quá nhiều lần từ các node khác nhau.

### Khác biệt với `filter_frontier()` standalone

| | `filter_frontier()` | `_filter_links()` |
|---|---|---|
| Phạm vi | 1 batch (1 node) | **Toàn cục** (cross-node) |
| Template quota | Không | Có (`_template_max`) |
| Gọi bởi | `clean_frontier.py` | Runtime exploration loop |

---

## Ví dụ thực tế từ run WebArena

```
[filter] 315 links → 27 (global quotas: 7 templates)
```

315 links trên homepage → gom thành 7 template → giữ 27 URL (~8.5%):

```
Template                          Score   Size   Keep
/{slug}/{slug}.html               5.2     200    3    (huge → 3 reps)
/checkout/cart                    4.8     1      1
/customer/account/login           3.1     1      1
/{slug}/{slug}/{slug}.html        2.8     45     8    (listing → 8 reps)
/catalogsearch/advanced           2.5     1      1
/contact                          2.0     1      1
/catalog/product_compare/...      1.5     66     3    (huge → 3 reps)
─────────────────────────────────────────────────
TOTAL                                                 27
```

---

## Tuning guide

| Mục tiêu | Tham số | Hướng |
|----------|---------|-------|
| **Tăng số lượng node frontier** | `max_output` | ↑ (150→300) |
| | Keep counts `(5,8,3)` | ↑ (8,12,5) |
| | `_template_max` | ↑ (5→10) |
| **Tạo nhiều template hơn** | `_VARIABLE_RATIO` | ↓ (0.15→0.05) |
| | `_VARIABLE_ABSOLUTE_MIN` | ↑ (3→10) |
| **Ưu tiên trang sâu hơn** | Depth ≥5 penalty | ↓ (−0.3→0) |
| **Giữ nhiều URL listing** | Cluster 6-30 bonus | ↑ (+1.0→+2.0) |
| **Giảm penalty cluster lớn** | >100 penalty | ↑ (−0.5→0) |
