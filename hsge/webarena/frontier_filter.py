"""Frontier URL filter using automatic template clustering.

Domain-agnostic: works on Magento, Wikipedia, GitLab, or any website
without manual configuration.  No hardcoded domain-specific rules.

Strategy:
  Pass 1  — Extract structural templates by position-based variable detection
            (compare values at each path depth across ALL URLs)
  Pass 1b — Score each template cluster by generic heuristics
  Pass 2  — Diversity-sample within clusters, respecting global budget

Template extraction is the key innovation: instead of per-URL heuristics,
we look at each path position (depth) across the entire URL list.  If a
position takes many distinct values → it's a variable ({slug}, {id}, ...).
If it always has the same value → it's a static segment.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Per-segment token detection (used AFTER position-based variable detection)
# ---------------------------------------------------------------------------
_RE_UUID = re.compile(
    r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
)
_RE_HEX = re.compile(r'^[a-f0-9]{32,}$')
_RE_NUM = re.compile(r'^\d+$')
_KNOWN_EXTENSIONS = {'.html', '.htm', '.php', '.asp', '.jsp', '.aspx'}

# Keywords that influence template priority (all lower-case, domain-agnostic)
_HIGH_KEYWORDS = {
    'login', 'signin', 'logout', 'signout', 'register', 'signup',
    'cart', 'basket', 'checkout', 'order', 'payment',
    'account', 'profile', 'settings', 'dashboard',
    'product', 'item', 'detail',
    'issue', 'merge_request', 'pull', 'blob', 'tree', 'commit',
    'wiki', 'article', 'page', 'readme',
}
_LOW_KEYWORDS = {
    'action', 'query', 'redirect', 'goto', 'print', 'pdf', 'xml',
    'rss', 'feed', 'trackback', 'pingback', 'compare',
    'forgot', 'reset', 'changepass',
    'privacy', 'terms', 'cookie', 'policy', 'newsletter', 'subscribe',
    'uenc',
}
# Variable-position detection thresholds
_VARIABLE_RATIO = 0.15             # if >15% of URLs differ at this depth → var
_VARIABLE_ABSOLUTE_MIN = 3          # OR if ≥3 distinct non-numeric values → var


# ===================================================================
#  Pass 1 — Template extraction (position-based)
# ===================================================================

def _strip_ext(seg: str) -> tuple[str, str]:
    """Return (stem, extension)."""
    for ext in _KNOWN_EXTENSIONS:
        if seg.endswith(ext):
            return seg[:-len(ext)], ext
    return seg, ''


def _token_type(stem: str) -> str:
    """Classify a single segment stem into a placeholder type."""
    if not stem:
        return '{empty}'
    if _RE_UUID.match(stem):
        return '{uuid}'
    if _RE_HEX.match(stem):
        return '{hash}'
    if _RE_NUM.match(stem):
        return '{id}' if len(stem) >= 3 else '{n}'
    return '{slug}'


def extract_templates(urls: list[str]) -> dict[str, list[str]]:
    """Group URLs by their structural template.

    Uses **position-based variable detection**: for each path depth,
    if many URLs have different values at that position, the position
    is treated as a variable placeholder.  Otherwise it's kept static.

    This is the core innovation that makes the filter domain-agnostic.
    """
    if not urls:
        return {}

    # ---- parse all URLs into segment lists ---------------------------------
    parsed: list[tuple[str, list[str]]] = []
    for u in urls:
        path = urlparse(u).path.strip('/')
        segs = [s for s in path.split('/') if s]
        parsed.append((u, segs))

    max_depth = max(len(segs) for _, segs in parsed)

    # ---- determine which positions are variable ----------------------------
    position_is_var: list[bool] = []
    for d in range(max_depth):
        stems_at_d: set[str] = set()
        n_with_depth = 0
        n_numeric = 0

        for _, segs in parsed:
            if d < len(segs):
                n_with_depth += 1
                stem, _ext = _strip_ext(segs[d])
                # Numeric / hash segments are always variable
                if _RE_NUM.match(stem) or _RE_HEX.match(stem) or _RE_UUID.match(stem):
                    n_numeric += 1
                    stems_at_d.add(f'__NUM__{stem[:4]}')  # avoid collapsing all nums
                else:
                    stems_at_d.add(stem.lower())

        n_distinct = len(stems_at_d)
        # Variable if:
        #   - any numeric/hash/uid segments exist, OR
        #   - ratio of distinct values exceeds threshold, OR
        #   - absolute number of distinct values ≥ minimum
        is_var = (
            n_numeric > 0
            or (n_with_depth > 0 and n_distinct / n_with_depth > _VARIABLE_RATIO)
            or (n_distinct - n_numeric) >= _VARIABLE_ABSOLUTE_MIN
        )
        position_is_var.append(is_var)

    # ---- build template for each URL ---------------------------------------
    clusters: dict[str, list[str]] = defaultdict(list)
    for url, segs in parsed:
        parts: list[str] = []
        for i, seg in enumerate(segs):
            stem, ext = _strip_ext(seg)
            if i < len(position_is_var) and position_is_var[i]:
                parts.append(_token_type(stem) + ext)
            else:
                parts.append(stem + ext)
        template = '/' + '/'.join(parts) if parts else '/'
        if urlparse(url).query:
            template += '{?params}'
        clusters[template].append(url)

    return dict(clusters)


# ===================================================================
#  Pass 1b — Priority scoring
# ===================================================================

def template_priority(template: str, cluster_size: int) -> float:
    """Score a template cluster.  Higher = more valuable to explore.

    Heuristics (all domain-agnostic):
      * Fewer placeholders → static pages are more important
      * Shallow depth (1-3 segments) → entry-point / overview pages
      * Deep paths (≥5) → buried content, penalty
      * Keywords in static segments → boost or penalty
      * Cluster size: medium (5-30) → good listing pages
        singleton → unique, potentially important
        huge (>100) → auto-generated spam
      * Query params → dynamic page, slight penalty
    """
    score = 6.0

    # 1. Placeholder count — fewer is better (static > dynamic)
    n_placeholders = template.count('{')
    score -= n_placeholders * 0.5

    # 2. Depth: ideal = 2-3 segments
    depth = template.count('/')
    if depth <= 1:
        score += 0.5                                    # root / top-level
    elif depth <= 3:
        score += 1.0                                    # sweet spot
    elif depth >= 5:
        score -= (depth - 4) * 0.3                      # too deep (reduced penalty)

    # 3. Template string length (very long = likely messy URL)
    if len(template) > 100:
        score -= 0.8
    elif len(template) > 70:
        score -= 0.3

    # 4. Keyword analysis on static segments (lower-cased)
    t_lower = template.lower()
    for kw in _HIGH_KEYWORDS:
        if kw in t_lower:
            score += 0.8
    for kw in _LOW_KEYWORDS:
        if kw in t_lower:
            score -= 0.6                                 # reduced penalty

    # 5. Cluster size
    if cluster_size <= 1:
        score += 1.0
    elif cluster_size <= 5:
        score += 0.5
    elif 6 <= cluster_size <= 30:
        score += 1.0                                    # good listing range
    elif cluster_size <= 100:
        score += 0.0                                     # neutral (was -0.5)
    else:                                                # >100
        score -= 0.5                                     # reduced penalty (was -2.0)

    # 6. Query params present → dynamic, slightly less useful
    if '{?params}' in template:
        score -= 0.4                                     # reduced penalty

    return round(score, 2)


# ===================================================================
#  Pass 2 — Diversity sampling
# ===================================================================

def _sample_diverse(urls: list[dict], k: int) -> list[dict]:
    """Pick k URLs maximising path-depth diversity within a cluster."""
    if len(urls) <= k:
        return urls

    # Sort by path depth
    sorted_items = sorted(urls, key=lambda x: urlparse(x['url']).path.count('/'))
    n = len(sorted_items)

    if k == 1:
        return [sorted_items[n // 2]]                     # median depth

    # Evenly spaced picks
    seen: set[int] = set()
    out: list[dict] = []
    for i in range(k):
        idx = min(int(i * (n - 1) / (k - 1)), n - 1)
        if idx not in seen:
            seen.add(idx)
            out.append(sorted_items[idx])
    return out


# ===================================================================
#  Main API
# ===================================================================

def filter_frontier(
    frontier: list[dict[str, Any]],
    max_output: int = 150,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Filter a frontier list using automatic template clustering.

    Uses position-based variable detection across ALL URLs, so it works
    on any website without domain-specific configuration.

    Parameters
    ----------
    frontier : list of dict
        Each dict must have at least ``'url'`` (str).  ``'depth'`` is
        passed through unchanged when present.
    max_output : int
        Upper bound on returned list length.
    verbose : bool
        Print per-cluster diagnostics.

    Returns
    -------
    list of dict
        Filtered frontier (same dict keys, fewer items).
    """
    if len(frontier) <= max_output:
        return list(frontier)

    # ---- Pass 1 — extract templates across ALL URLs -----------------------
    all_urls = [item['url'] for item in frontier]
    template_to_urls = extract_templates(all_urls)

    # Map back to full items
    url_to_item = {item['url']: item for item in frontier}
    clusters: dict[str, list[dict]] = {}
    for tmpl, urls in template_to_urls.items():
        clusters[tmpl] = [url_to_item[u] for u in urls if u in url_to_item]

    # ---- Pass 1b — score clusters ----------------------------------------
    scored: list[tuple[str, float, list[dict]]] = []
    for tmpl, urls in clusters.items():
        score = template_priority(tmpl, len(urls))
        scored.append((tmpl, score, urls))

    scored.sort(key=lambda x: -x[1])                     # highest score first

    if verbose:
        print(f"\n{'='*70}")
        print(f"  Template clusters ({len(scored)} unique, "
              f"budget={max_output})")
        print(f"{'='*70}")
        for tmpl, score, urls in scored:
            print(f"  [{len(urls):4d}] score={score:+.1f}  {tmpl}")
            if len(urls) <= 5:
                for u in urls:
                    print(f"         {u['url']}")

    # ---- Pass 2 — diversity sample within budget -------------------------
    result: list[dict] = []
    budget = max_output

    for _tmpl, _score, urls in scored:
        if budget <= 0:
            break

        size = len(urls)

        # How many to keep from this cluster
        if size <= 3:
            keep = size
        elif size <= 20:
            keep = min(8, budget)
        elif size <= 60:
            keep = min(12, budget)
        else:
            keep = min(5, budget)                        # huge → 5 reps

        sampled = _sample_diverse(urls, keep)
        result.extend(sampled)
        budget -= len(sampled)

    return result
