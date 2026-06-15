# 10 — Changelog: all modifications from baseline

This document records every change applied to the HSGE codebase during the
setup & hardening session (2026-06-10).

---

## 1. Multi-provider LLM support

### 1.1 `run_webarena.py` — rewritten CLI
- Added `--provider {deepseek,openai,custom}` flag
- Added `--explorer-model` and `--solver-model` flags (separate models per role)
- Added `--model` shorthand (sets both)
- Added `--screenshot` flag
- Auto-loads `.env` file (custom `_load_dotenv()`, no extra dependency)
- `_resolve_models()`: priority chain CLI > `EXPLORER_MODEL`/`SOLVER_MODEL` env > provider preset
- `_resolve_api_config()`: maps provider name → api_key, base_url, default model
- Prints `[config]` block on startup showing resolved provider/model/base URL

### 1.2 `.env.example` — created
- Template with presets for DeepSeek, OpenAI, and custom providers
- WebArena URLs (`WA_SHOPPING`, etc.)
- Optional `EXPLORER_MODEL` / `SOLVER_MODEL` overrides

### 1.3 `.env` — updated
- Added `LLM_PROVIDER`, `DEEPSEEK_MODEL`, `OPENAI_MODEL`
- Added WebArena test accounts (`WA_ACCOUNT_*`)
- Fixed `DEEPSEEK_BASE_URL` to include `/v1`

### 1.4 `hsge/webarena/runtime.py` — separate explorer/solver LLMs
- `WebArenaExplorer.__init__` now accepts `explorer_llm` and `solver_llm` (backward-compat with old `llm=` kwarg)
- `PageExplorer` uses `_explorer_llm`; `Solver` uses `_solver_llm`; `SkillLibrary` uses `_explorer_llm`

### 1.5 `run_webarena.ps1` — created
- PowerShell helper for quick runs with different providers on Windows

---

## 2. Browser fixes

### 2.1 `hsge/webarena/browser.py` — `links()` extracted real DOM links
- **Before:** `links()` returned only `open_pages_urls` (≈ 1 URL = current tab), causing frontier to die after 1-2 nodes
- **After:** `links()` uses Playwright `page.evaluate()` to extract all `<a href>` from the live DOM, filters same-origin, deduplicates. Returns 10-200 real links per page.

### 2.2 `hsge/webarena/browser.py` — `screenshot` support
- Added `screenshot: bool` parameter to `__init__`
- `observation()` now always includes `"screenshot_base64"` key (None if disabled)
- When enabled, captures PNG screenshot via `self.env.page.screenshot()`

---

## 3. Vision / Screenshot support

### 3.1 `hsge/llm.py` — `complete_vision_json()`
- Added default `complete_vision_json()` method on `LLM` base class
- Falls back to `complete_json()` when backend doesn't support vision

### 3.2 `hsge/backends.py` — `OpenAILLM.complete_vision_json()`
- Sends multimodal message `[text, image_url]` via OpenAI Vision API format
- Refactored JSON parsing into shared `_parse_json()` helper

### 3.3 `hsge/webarena/agents.py` — Solver uses vision when available
- `Solver.solve()` checks `obs.get("screenshot_base64")` and routes to `complete_vision_json()` or `complete_json()`
- Returns 5-tuple: `(steps, obs_texts, final_obs, success, screenshots)`
- `screenshots` is `list[bytes|None]` parallel to steps

### 3.4 `hsge/webarena/runtime.py` — screenshot persistence
- `_record()` accepts optional `screenshots` list
- Saves PNG files to `screenshots/step_XXX.png` (separate folder from `page_state/`)
- `episode.jsonl` observation includes `"screenshot_png": {"path": "screenshots/step_XXX.png"}`

### 3.5 `run_webarena.py` — `_DryLLM` updated
- Added `complete_vision_json()` stub for dry-run compatibility

---

## 4. WebArena test accounts

### 4.1 `hsge/webarena/agents.py` — account hints injected into solver prompt
- `_accounts_hint()` reads `WA_ACCOUNT_SHOPPING_USERNAME/PASSWORD` etc. from env
- Prepends `KNOWN ACCOUNTS:` block to solver system prompt
- Agent can use credentials for login tasks without guessing

### 4.2 `.env` — accounts added
```
WA_ACCOUNT_SHOPPING_USERNAME=emma.lopez@gmail.com
WA_ACCOUNT_SHOPPING_PASSWORD=Password.123
WA_ACCOUNT_REDDIT_USERNAME=MarvelsGrantMan136
WA_ACCOUNT_REDDIT_PASSWORD=test1234
WA_ACCOUNT_GITLAB_USERNAME=byteblaze
WA_ACCOUNT_GITLAB_PASSWORD=hello1234
```

---

## 5. Bug fixes (from full-flow audit)

### 5.1 `hsge/webarena/runtime.py` — `max_depth` now enforced
- Frontier changed from `[url]` to `[(url, depth)]`
- Each expansion increments depth; nodes beyond `max_depth` are skipped
- Log shows `[node N depth=D]`

### 5.2 `hsge/webarena/runtime.py` — `_mine_operator()` guards
- Added `hasattr(steps[0], 'url')` check
- Uses `.get("url", "")` on `final_obs` dict instead of `["url"]`

### 5.3 `hsge/library.py` — abstract retry on failure
- `_try_admit()` only calls `self._abstracted.add(cid)` AFTER successful abstraction
- Previously: abstraction failure → cluster permanently marked → never retried

### 5.4 `hsge/segmentation.py` — robust LLM response validation
- Validates `seg["span"]` type (`list`/`tuple`), length (2), bounds (`[0, len(steps)]`)
- Wraps in try/except to skip malformed segments gracefully

### 5.5 `hsge/abstraction.py` — defensive LLM response
- Returns `None` instead of raising `KeyError` when LLM omits `name` field
- Prompt improved with explicit JSON schema

### 5.6 `hsge/webarena/runtime.py` — `_record()` fixes
- Added `encoding="utf-8"` to file writes
- `obs_text` extracted to variable (no repeated index access)

### 5.7 `hsge/webarena/agents.py` — docstring fix
- `Solver.solve()` docstring corrected to show actual 5-tuple return type

---

## 6. Repository setup

### 6.1 `.gitignore` — created
Excludes: `.env`, `__pycache__/`, `outputs/`, `*.jsonl`, IDE/OS files, `venv/`

### 6.2 Git initialized & pushed
- `git init` → commit 43 files → push to `https://github.com/Noru-0/hsge.git`
- Branch: `master`
- **API keys in `.env` are NOT in the repository**

### 6.3 `docs/09_run_on_webarena.md` — updated
- Added provider/model selection instructions
- Added screenshot usage docs
- Added PowerShell helper reference

---

## 7. Runtime hardening (round 2)

### 7.1 `hsge/webarena/browser.py` — `unwrapped.page` fix
- **Before:** `self.env.page` failed because BrowserGym wraps the env in
  `OrderEnforcing` + `PassiveEnvChecker` gym wrappers; `.page` only exists
  on the innermost `BrowserEnv`
- **After:** `self.env.unwrapped.page` reaches through wrappers
- Fixes both screenshot capture AND `links()` DOM extraction

### 7.2 `hsge/backends.py` — null-safe content extraction
- Added `_get_content()` helper that safely extracts text from OpenAI response
- Handles `msg.choices[0].message.content = None` (content filter refusal)
- Handles content returned as list-of-blocks (some model variants)
- `complete_json`, `complete_vision_json`, `complete_text` all use `_get_content()`

### 7.3 `hsge/webarena/runtime.py` — URL normalization
- Added `_norm()` helper: `rstrip("/")` to prevent trailing-slash mismatches
- Root URL normalized on entry; all child links normalized before comparison
- Prevents the same page being visited twice (e.g. `/page` vs `/page/`)

### 7.4 `hsge/webarena/runtime.py` — frontier dedup fix
- **Before:** links were added to `visited` set immediately on discovery,
  causing `len(visited)` to explode with unprocessed URLs → loop stopped
  after 1 real node
- **After:** separate `queued` set tracks URLs added to frontier;
  `visited` only contains actually-processed nodes; `nodes_processed`
  counter respects `--max-nodes` correctly

### 7.5 `hsge/webarena/runtime.py` — duplicate code removed
- Removed duplicate `eff = end - start; if not eff: return` block in `_mine_operator()`

### 7.6 `hsge/webarena/runtime.py` — `browser.close()` on every node
- Added `browser.close()` at end of each node iteration to free Playwright resources

---

## 8. File logging

### 8.1 `hsge/webarena/runtime.py` — `run.log`
- `WebArenaExplorer.__init__` opens `outputs/<run>/run.log`
- All `print()` output also written to log file with `flush()` for real-time tailing
- Mirror of console output; survives terminal closure


## 9. Frontier URL filter — template clustering

### 9.1 `hsge/webarena/frontier_filter.py` — ✨ Created
Domain-agnostic URL deduplication via automatic template clustering:

**Pass 1 — `extract_templates(urls)`**: Position-based variable detection.
Compares values at each path depth across ALL candidate URLs. If >15% of URLs
(or ≥3 absolute) differ at a depth → that position is a variable placeholder
(`{slug}`, `{id}`, `{hash}`, `{uuid}`). Otherwise it's kept as a static segment.

**Pass 1b — `template_priority(template, size)`**: Scores each template cluster
by generic heuristics (placeholder count, depth, keywords, cluster size, query
params). No domain-specific rules.

**Pass 2 — `_sample_diverse(urls, k)`**: Picks k URLs maximising path-depth
diversity within each cluster (evenly-spaced index sampling).

**`filter_frontier(frontier, max_output)`**: Stateless batch API — clusters,
scores, samples within budget. Used by `clean_frontier.py` for post-hoc analysis.

### 9.2 `hsge/webarena/runtime.py` — Global template quota
`WebArenaExplorer._filter_links()` wraps the extraction pipeline with a
**global quota** (`_template_quota: dict[str, int]`, `_template_max = 2`).
Each URL template is allowed at most 2 URLs across ALL nodes combined,
preventing the frontier from accumulating many similar URLs over multiple
pages. Logs `[filter] N links → M (global quotas: T templates)` at each node.

### 9.3 Variable detection thresholds
| Parameter | Value | Meaning |
|-----------|-------|---------|
| `_VARIABLE_RATIO` | 0.15 | Fraction of distinct values → variable position |
| `_VARIABLE_ABSOLUTE_MIN` | 3 | OR: if ≥3 distinct non-numeric values → variable |

Previous value `_VARIABLE_THRESHOLD = 0.25` was too high for small batches
(60 URLs) where 12 distinct values / 60 = 20% < 25% → positions incorrectly
treated as static → each category became its own template → filter ineffective.

### 9.4 `clean_frontier.py` — ✨ Created
Standalone script: reads `outputs/wa_run/frontier.jsonl`, applies
`filter_frontier()`, writes `frontier_clean.jsonl` with per-node
reduction statistics. Also `analyze_frontier.py` for diagnostic breakdowns.

### 9.5 Results (Magento benchmark)
- Root node: 334 URLs → ≤60 per node (−82%)
- After global quota fix + variable threshold fix: node 2 frontier 119 → 12 (−90%)
- Total across nodes: ~2000 → ~100 (−95%)
- Domain-agnostic: same algorithm works on Wikipedia, GitLab, any website

---

## Summary of files touched

| File | Status |
|------|--------|
| `run_webarena.py` | ✏️ Rewritten |
| `run_webarena.ps1` | ✨ Created |
| `.env.example` | ✨ Created |
| `.env` | ✏️ Updated (accounts, model names, provider) |
| `.gitignore` | ✨ Created |
| `hsge/webarena/runtime.py` | ✏️ separate LLMs, max_depth, guards, screenshot persist, URL norm, frontier fix, file logging |
| `hsge/webarena/browser.py` | ✏️ real DOM links, screenshot capture, unwrapped.page fix |
| `hsge/webarena/agents.py` | ✏️ accounts hint, vision routing, screenshot list |
| `hsge/backends.py` | ✏️ `complete_vision_json()`, `_get_content()` null-safe, `_parse_json()` |
| `hsge/llm.py` | ✏️ `complete_vision_json()` base method |
| `hsge/library.py` | ✏️ abstract retry fix |
| `hsge/abstraction.py` | ✏️ defensive JSON, better prompt |
| `hsge/segmentation.py` | ✏️ robust span validation |
| `build_sft_dataset.py` | ✏️ (no functional change) |
| `hsge/webarena/frontier_filter.py` | ✨ Created — template clustering engine |
| `clean_frontier.py` | ✨ Created — standalone frontier cleaning script |
| `analyze_frontier.py` | ✨ Created — diagnostic breakdown tool |
| `docs/05_frontier_filter.md` | ✨ Created — full design document |
| `docs/06_code_reference.md` | ✨ Created — file-by-file walkthrough |
| `docs/09_run_on_webarena.md` | ✏️ Updated |
| `docs/10_changelog.md` | ✨ This file |
