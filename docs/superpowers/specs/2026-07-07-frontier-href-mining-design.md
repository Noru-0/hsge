# Frontier href-mining + template-priority (design)

**Date:** 2026-07-07
**Status:** approved, in implementation
**Context:** [`docs/13_run02_reddit_exploration_log.md`](../../13_run02_reddit_exploration_log.md)

## Problem

The WebArena `run_webarena.py` exploration stops early when the frontier empties
out, well short of `max_nodes`/`max_depth` (run 02: 57/500 nodes, depth 6/300).
Root cause (already documented as a "Known gap" in
[`.claude/rules/architecture.md`](../../../.claude/rules/architecture.md)): the
frontier only grows from URLs the Solver **actually navigates to while solving a
proposed task** (`Step.url` + open tabs). Page `<a href>` links are never mined, so
on read-heavy / link-dense sites (e.g. reddit) the reachable "novel" URL surface is
exhausted quickly even though the pages are full of unclicked links.

`runtime.py` — [`hsge/webarena/runtime.py`](../../../hsge/webarena/runtime.py) —
frontier expansion is at lines ~398-407; the FIFO frontier is a plain list
(`frontier.pop(0)`); `_admit_url` (lines ~206-208) is the allow/deny/visited gate.

## Goal

Reach the node/depth budget by mining `<a href>` links directly, **without** burning
the budget on hundreds of near-identical pages (per-post / per-comment / per-user
URLs on a forum). Both coverage *and* skill/operator diversity, with prioritization.

## Design

### Two tiers of frontier candidates

- **Tier 0 — URLs the agent actually reached** (`Step.url` across all episodes at a
  node + open tabs via `browser.links()`). High signal. **No** template dedup, **no**
  novelty scoring — admitted directly, highest priority. Still subject to the two
  existing safety guards: not already `visited`, and passes allow/deny (so a `logout`
  URL the agent brushed against never enters the frontier).
- **Tier 1 — mined `<a href>`** (`browser.page_hrefs()`). Cheap and abundant; must
  pass template dedup + novelty prioritization.

### Component 1 — href mining (`browser.py`)

New `WebArenaBrowser.page_hrefs(limit: int = 100) -> list[str]`: pulls every
`<a href>` off the current page via the underlying Playwright page
(`self.env.unwrapped.page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")`),
returning absolute URLs (more robust than parsing the flattened axtree, which drops
hrefs). Dedup preserving order, cap at `limit`. Returns `[]` on any failure, mirroring
`observation()` / `screenshot_bytes()`'s fail-soft pattern.

`_FakeBrowser` in `run_webarena.py` gets a matching `page_hrefs()` stub returning a
couple of in-host URLs so `--dry-run` exercises the mining path.

### Component 2 — URL template dedup (`runtime.py`, tier 1 only)

New static `_url_template(url) -> str`: normalizes a URL into a "shape" that groups
same-kind pages:
- Drop scheme, query string, fragment; keep host + path.
- Replace each path segment that is **all digits** or a **long id-like slug**
  (contains a digit, or is longer than a threshold) with `*`.
- Keep type-identifying segments (forum names like `AskReddit`, `gaming`) so
  *different* forums stay *different* templates and all get explored.
- Examples: `/f/AskReddit/comments/12345/some-title` → `/f/AskReddit/comments/*/*`;
  `/user/alice/comments` → `/user/*/comments`.

The exact regex is nuanced; it gets its own unit test.

**Template cap:** a `Counter` of templates of **visited** nodes. A tier-1 URL is only
admitted while its template count is `< per_template_cap` (default 3). Re-checked
**lazily at pop time** (counts grow during the run: a template can be under cap when
pushed but full when popped). Tier 0 bypasses this entirely.

### Component 3 — priority queue (`runtime.py`)

Replace the FIFO list with a `heapq`. Entry key `(tier, novelty, depth, seq, url)`:
1. **tier** — 0 (reached) before 1 (mined), absolute.
2. **novelty** — for tier 1, the visited-node count of the URL's template at push
   time (fewer → explored first, so unseen templates lead). 0 for tier 0.
3. **depth** — shallower first (keeps BFS breadth, avoids diving one branch).
4. **seq** — monotonic counter for stable FIFO tiebreak (and to avoid comparing URLs).

A `queued` set prevents pushing the same URL twice; tier 0 is pushed before tier 1
within a node, so a reached URL wins over the same URL seen only as an href.

### Config (`config.yaml` `run:`, `DEFAULTS`, CLI)

- `mine_hrefs` (default `true`) — master toggle; `false` reproduces the old
  navigated-only behavior.
- `per_template_cap` (default `3`) — max tier-1 nodes admitted per URL template.
- `max_hrefs_per_page` (default `100`) — cap on hrefs mined per page.

CLI flags mirror the repo convention: `--no-mine-hrefs`, `--per-template-cap`,
`--max-hrefs-per-page`. Precedence: CLI > config.yaml > `DEFAULTS`.

## Non-goals

- No change to the mock/deterministic pipeline (this is the WebArena runtime only).
- No semantic/embedding novelty scoring (considered, rejected as heavier and
  non-deterministic for a first cut; template dedup is the cheap deterministic gate).
- Frontier starvation on genuinely small sites is still correct behavior — the fix
  only matters when novel content remains.

## Verification

1. `_url_template` unit test: digit/slug segments wildcarded, type segments kept,
   distinct forums → distinct templates.
2. Frontier priority test: tier 0 pops before tier 1; per-template cap enforced
   lazily; unseen templates lead within tier 1.
3. `browser.page_hrefs()` fail-soft returns `[]` when the page eval throws.
4. `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2` still passes
   (full wiring, mining path exercised via `_FakeBrowser`).
5. Existing tests unaffected: `python -m pytest hsge/tests/ -q`.
