# Frontier Filter — Template-Based URL Clustering

> **Version:** current (2026-06-10)  
> **Files:** `hsge/webarena/frontier_filter.py`, `hsge/webarena/runtime.py`  
> **Status:** integrated into runtime loop + standalone `clean_frontier.py`

---

## 1. Overview

The **frontier filter** reduces the number of URLs queued for exploration by
grouping structurally similar URLs and keeping only a small, diverse sample
from each group.  It is **domain-agnostic** — no hardcoded rules about
Magento, Wikipedia, GitLab, or any specific site.

**Core idea:** a URL like `/electronics/camera-photo.html` and
`/electronics/headphones.html` share the same structural *template*
(`/electronics/{slug}.html`).  Instead of exploring all 13 electronics
subcategories, we keep only 2–3 representatives and move on.

### Key numbers (Magento benchmark)

| Metric | Before | After |
|--------|--------|-------|
| URLs queued per node (root) | 334 | **≤60** |
| Total URLs across 6 nodes | 2085 | **≤360** |
| Reduction | — | **−83%** |

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                       FRONTIER FILTER                            │
│                                                                  │
│  INPUT:  list[str]  (eligible URLs from one page)               │
│           set[str]   (already queued URLs)                       │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ PASS 1: extract_templates(urls)                            │  │
│  │   • Parse all URLs into path-segment lists                 │  │
│  │   • For each depth position:                               │  │
│  │       if >25% of URLs differ at this depth → VARIABLE      │  │
│  │       else → STATIC                                        │  │
│  │   • Build template string with {slug}/{id}/{hash} tokens   │  │
│  │   • Group URLs by template                                 │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ PASS 1b: template_priority(tmpl, size)                     │  │
│  │   • Score each cluster (domain-agnostic heuristics)        │  │
│  │   • Sort highest-first                                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ PASS 2: _sample_diverse(urls, k)                           │  │
│  │   • Per cluster, pick k URLs with diverse path depths      │  │
│  │   • Respect GLOBAL template quota (_template_max = 2)      │  │
│  │   • Respect per-node budget (_frontier_max = 60)           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  OUTPUT: list[str]  (filtered URLs, ≤60 per node)               │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Pass 1 — Template Extraction (position-based)

This is the **core innovation**.  Instead of per-URL heuristics, we compare
values at each path depth across **all** candidate URLs.

### 3.1 Algorithm

```
Given URLs: [
  /electronics/camera-photo.html
  /electronics/headphones.html
  /electronics/computers-accessories.html
  /checkout/cart
  /customer/account/login
  /sales/order/view/order_id/170
  /sales/order/view/order_id/180
]

Step 1: Split into position columns
  depth=0: [electronics, electronics, electronics, checkout, customer, sales, sales]
  depth=1: [camera-photo, headphones, computers-accessories, cart, account, order, order]
  depth=2: [  —  ,    —  ,      —  ,  — , login, view, view]
  depth=3: [  —  ,    —  ,      —  ,  — ,  —  , order_id, order_id]
  depth=4: [  —  ,    —  ,      —  ,  — ,  —  , 170, 180]

Step 2: For each depth, count distinct values
  depth=0: 4 distinct / 7 URLs = 57% → VARIABLE ({slug})
  depth=1: 5 distinct / 7 URLs = 71% → VARIABLE ({slug})
  depth=2: 2 distinct / 4 URLs = 50% → VARIABLE ({slug})
  depth=3: 1 distinct / 2 URLs = 0% → STATIC (order_id)
  depth=4: 2 distinct / 2 URLs = 100% → NUMERIC → VARIABLE ({id})

Step 3: Build templates
  /electronics/camera-photo.html             → /{slug}/{slug}.html
  /electronics/headphones.html               → /{slug}/{slug}.html    (same!)
  /customer/account/login                    → /{slug}/{slug}/{slug}
  /sales/order/view/order_id/170             → /{slug}/{slug}/{slug}/order_id/{id}
  /sales/order/view/order_id/180             → /{slug}/{slug}/{slug}/order_id/{id}  (same!)

Result: 4 templates instead of 7 individual URLs, with URL counts:
  /{slug}/{slug}.html                    : 3 URLs
  /{slug}/{slug}/{slug}                  : 1 URL
  /checkout/{slug}                       : 1 URL
  /{slug}/{slug}/{slug}/order_id/{id}    : 2 URLs
```

### 3.2 Token types

| Placeholder | Detects | Example |
|-------------|---------|---------|
| `{n}` | 1–2 digit number | `/page/{n}` |
| `{id}` | 3+ digit number | `/order/{id}` |
| `{hash}` | 32+ hex chars | `/commit/{hash}` |
| `{uuid}` | UUID format | `/api/{uuid}` |
| `{slug}` | Text (with optional hyphens) | `/{slug}/{slug}.html` |
| `{?params}` | Query string present | `/search{?params}` |

### 3.3 Static vs variable threshold

- **Variable** if >25% of URLs differ at this depth, OR any numeric/hash segment exists
- **Static** otherwise (kept as literal text)
- This threshold is configurable via `_VARIABLE_THRESHOLD` (default `0.25`)

---

## 4. Pass 1b — Priority Scoring

Each template cluster gets a score.  Highest-scoring clusters are sampled first.

### Scoring formula (all domain-agnostic)

```
score = 5.0                          (base)
      − n_placeholders × 1.2         (fewer vars = more important)
      + depth_bonus                   (+0.5 for root, +1.0 for depth 2-3, −0.8/depth for ≥5)
      − length_penalty                (−0.5 if >70 chars, −1.5 if >100)
      ± keyword_bonus                 (+0.8 for high-value, −1.2 for low-value)
      + cluster_size_bonus            (+1.0 for singletons, +0.5 for small, +1.0 for medium)
      − query_penalty                 (−0.8 if query params present)
```

### Keyword sets

| Category | Keywords |
|----------|----------|
| **HIGH** (boost) | login, cart, checkout, account, settings, product, detail, issue, wiki, readme |
| **LOW** (penalty) | action, query, redirect, print, pdf, rss, forgot, privacy, newsletter, uenc |

### Example scores (real Magento data)

```
Template                                  Size  Score   Keep
────────────────────────────────────────  ────  ──────  ────
/checkout/{slug}                          1     +8.6   1
/office-products.html                     1     +7.3   1
/{slug}.html (top-level category)         14    +6.5   2  ← global quota
/{slug}/{slug}.html (subcategory L1)      54    +5.8   2  ← per template
/{slug}/{slug}/{slug}.html (L2)           150   +3.1   1
/{slug}/{slug}/{slug}/order_id/{id}       5     −0.1   1
/checkout/{slug}/{slug}/{slug}/{id}/{slug}/{id}  3  −3.3   0
```

---

## 5. Pass 2 — Diversity Sampling with Global Quota

### 5.1 Within-cluster diversity

From each cluster, we pick *k* URLs that maximise path-depth diversity:

```
Cluster: /{slug}/{slug}.html (54 URLs)

Sorted by path depth (number of /):
  [0]  /electronics/camera-photo.html        (depth=2)
  ...
  [27] /home-kitchen/kitchen-dining.html     (depth=2)  ← median
  ...
  [53] /video-games/playstation-4.html       (depth=2)

Keep k=2 → pick evenly spaced: index 0, index 53
```

### 5.2 Global template quota (the critical fix)

**Problem without quota:** Each node independently filters its links.
`/electronics/{slug}.html` gets 2 URLs at node 1, 2 more at node 2, 2 more
at node 3 → 6 total → frontier grows 60→119→154→187.

**Fix:** `_template_quota: dict[str, int]` tracks how many URLs of each
template have been queued across ALL nodes.  `_template_max = 2` means at
most 2 URLs per template globally.

| Node | Template | Quota before | Added | Quota after |
|------|----------|-------------|-------|-------------|
| 1 | `/{slug}/{slug}.html` | 0 | +2 | 2 |
| 2 | `/{slug}/{slug}.html` | 2 | 0 (full) | 2 |
| 3 | `/{slug}/{slug}.html` | 2 | 0 (full) | 2 |

### 5.3 Configurable parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `_frontier_max` | 60 | Max URLs added per node |
| `_template_max` | 2 | Max URLs per template globally |
| `_VARIABLE_RATIO` | 0.15 | Fraction of distinct values → variable position |
| `_VARIABLE_ABSOLUTE_MIN` | 3 | OR: if ≥3 distinct non-numeric values → variable |

---

## 6. Integration Points

### 6.1 Runtime (`hsge/webarena/runtime.py`)

```python
# In WebArenaExplorer.__init__:
self._template_quota: dict[str, int] = {}
self._template_max = 2
self._frontier_max = 60

# In WebArenaExplorer.run() — inside while loop, at every node:
raw_links = [_norm(link) for link in browser.links()]
eligible = [l for l in raw_links if self.allow.search(l) and l not in queued]
for link in self._filter_links(eligible, queued):   # ← global-quota-aware
    queued.add(link)
    frontier.append((link, depth + 1))
```

### 6.2 Standalone (`clean_frontier.py`)

Reads `frontier.jsonl`, applies `filter_frontier()` (stateless,
no global quota), writes `frontier_clean.jsonl`.

### 6.3 API

```python
# Core extraction (stateless)
from hsge.webarena.frontier_filter import extract_templates, template_priority

templates = extract_templates(["/a/b.html", "/a/c.html"])
# → {"/a/{slug}.html": ["/a/b.html", "/a/c.html"]}

# Batch filtering (stateless, for post-hoc analysis)
from hsge.webarena.frontier_filter import filter_frontier

filtered = filter_frontier(items, max_output=60)

# Runtime filtering (stateful, global quota — in WebArenaExplorer)
kept = self._filter_links(eligible_links, already_queued_set)
```

---

## 7. Domain-Agnostic Guarantees

The filter works on any website because it **infers structure from data**:

| Domain | URL pattern | Auto-detected template |
|--------|-------------|----------------------|
| Magento | `/electronics/camera-photo.html` | `/{slug}/{slug}.html` |
| Wikipedia | `/wiki/Quantum_Mechanics` | `/wiki/{slug}` |
| Wikipedia | `/wiki/Category:Physics` | `/wiki/Category:{slug}` |
| GitLab | `/ns/proj/-/issues/42` | `/{slug}/{slug}/-/issues/{id}` |
| GitLab | `/ns/proj/-/blob/main/src/app.py` | `/{slug}/{slug}/-/blob/{slug}/{slug}` |
| Shopify blog | `/blogs/news/article-title` | `/{slug}/{slug}/{slug}` |
| Any REST API | `/api/v1/users/123/orders` | `/api/v1/users/{id}/orders` |

No manual configuration needed — zero hardcoded rules about specific domains.

---

## 8. Limitations & Future Work

1. **Single-batch template extraction**: `extract_templates()` sees only the
   current node's eligible URLs, not the global frontier.  If a template
   appears with only 1 URL in one batch, it won't be detected as variable
   until later batches reveal the pattern.  *Mitigated by global quota.*

2. **Keyword sets are English-only**: Priority scoring uses English keywords.
   Non-English sites (e.g., French, Japanese) won't get keyword bonuses.
   *Impact is minor — other heuristics still work.*

3. **No content-based dedup**: Two pages with identical content but different
   URLs (e.g., `/product/123` and `/product/123?ref=abc`) are treated as
   separate URLs.  *Mitigated by `{?params}` normalization.*

4. **`_VARIABLE_THRESHOLD` tuning**: The 25% threshold works for most sites
   but may need adjustment for sites with very few or very many distinct URLs
   per depth.
