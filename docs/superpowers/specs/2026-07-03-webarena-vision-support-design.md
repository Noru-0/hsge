# Design: vision support for PageExplorer/Solver

Date: 2026-07-03

## Purpose

Let `PageExplorer` and `Solver` (the two WebArena helper agents that reason
about a *live* page, as opposed to `trajectory_segmenter`/`skill_abstractor`/
`skill_verifier`/`operator_inducer`, which only re-process already-collected
text) optionally see a screenshot alongside the axtree, using OpenAI vision
models (GPT-4o family). Screenshots that get sent to the LLM are also saved
under `out_dir` so a run can be inspected visually after the fact, mirroring
the existing per-step axtree persistence.

Vision is **opt-in per role via config.yaml**, defaulting to off everywhere,
so existing non-vision runs (mock, DeepSeek, dry-run) are unaffected.

## Confirmed decisions

- Scope: only `page_explorer` and `solver` get real code paths that capture
  and attach a screenshot. The config schema exposes `vision`/`som`/
  `image_detail` uniformly on every role for consistency, but the other
  four roles ignore it (no live page at their point in the pipeline).
- Model split: `page_explorer` -> `gpt-4o` (called once per node, worth the
  quality), `solver` -> `gpt-4o-mini` (called up to `max_steps` times per
  episode, needs to stay cheap).
- `image_detail: low` by default (fixed ~85 tokens/image regardless of size;
  the axtree text already carries the fine detail, the image is supplementary
  context) — configurable to `high`/`auto` per role if the user wants it.
- Set-of-Marks (SoM) bbox+bid annotation is folded into this spec (was
  originally pitched as a follow-up): BrowserGym already ships
  `browsergym.utils.obs.overlay_som(screenshot, extra_properties)`, which
  draws a dashed bounding box + bid tag per interactive element using
  `obs["extra_element_properties"]` (already extracted today, just not kept
  around) — no custom drawing code needed. `som: bool = True` per role,
  only meaningful when `vision: true`.
- Retry/backoff for `OpenAILLM` transient errors is also folded in (was
  pitched as a follow-up): a completed OpenAI API call can fail transiently
  (rate limit, connection blip, 5xx) and today that crashes the whole run.

## Changes by file

### `hsge/webarena/browser.py` (`WebArenaBrowser`)

BrowserGym's `_get_obs()` already populates `obs["screenshot"]` (a numpy
RGB array) on every observation, unconditionally — no env kwarg needed.
`observation()` currently reads `obs.get("extra_element_properties")` only
to pass through to `flatten_axtree_to_str` and then discards it; keep a
reference (`self._last_extra_props`) so `overlay_som` can use the same data.

Add two methods:

```python
def screenshot_bytes(self, som: bool = False) -> bytes | None:
    """JPEG-encode the last observation's screenshot. If som, overlay
    bid-tagged bounding boxes first via browsergym.utils.obs.overlay_som
    (using self._last_extra_props). None on any failure (mirrors the
    try/except-to-empty-string pattern already used for axtree)."""

def screenshot_b64(self, som: bool = False) -> str | None:
    """base64 of screenshot_bytes(som), for embedding in an API request."""
```
JPEG quality 80 (keeps per-file size reasonable across many steps/episodes;
OpenAI accepts JPEG same as PNG). Requires Pillow — already a transitive
BrowserGym dependency (`overlay_som` itself uses `PIL.Image`/`ImageDraw`/
`ImageFont`), but add it explicitly to `requirements.txt`'s swap-in section
since we now import it directly too.

`_FakeBrowser` in `run_webarena.py` (dry-run stub) gets a `screenshot_b64(som=False)`
returning a tiny embedded 2x2 JPEG constant (ignoring `som`), so `--dry-run`
can exercise the full vision code path (capture -> attach -> save) without a
real browser or API key.

### `hsge/llm.py` (`LLM` ABC, `MockLLM`) and `hsge/backends.py` (`OpenAILLM`)

Extend the abstract signature (backward compatible via defaults):

```python
def complete_json(self, system: str, prompt: str,
                   image_b64: str | None = None, image_detail: str = "low") -> dict:
```

- `MockLLM.complete_json` gains the two params, ignores them (unchanged
  behavior).
- `OpenAILLM.complete_json`: if `image_b64` is None, build the message
  exactly as today (plain string content — stays maximally compatible with
  non-OpenAI-vision endpoints like DeepSeek). If `image_b64` is set, build:
  ```python
  content = [{"type": "text", "text": prompt},
             {"type": "image_url",
              "image_url": {"url": f"data:image/jpeg;base64,{image_b64}",
                             "detail": image_detail}}]
  ```
  and use that as the user message content instead of the plain string.

**Retry/backoff for transient errors** (`OpenAILLM.complete_json` and
`complete_text`): wrap the `self.client.chat.completions.create(...)` call
in a small retry loop. Retry only on `openai.RateLimitError`,
`openai.APIConnectionError`, `openai.APITimeoutError`,
`openai.InternalServerError` (all verified present in the installed
`openai==1.109.1`); do NOT retry `AuthenticationError`/`BadRequestError`
(non-transient, retrying wastes time before failing anyway). Policy: up to
3 retries (4 attempts total), exponential backoff `1s, 2s, 4s` plus small
random jitter, printing one line per retry (e.g. `[OpenAILLM] retry 1/3
after RateLimitError, sleeping 1.2s`). After exhausting retries, re-raise
the last exception (run still crashes on a persistent outage — this only
smooths over blips, matching "don't add handling for unrecoverable
scenarios").

### `hsge/webarena/agents.py` (`PageExplorer`, `Solver`)

Both gain `vision: bool = False, som: bool = True, image_detail: str =
"low"` constructor params, stored as attributes. Screenshot capture only
happens when `self.vision` is true (so non-vision roles pay zero extra
cost — no encode, no extra bytes over the wire); `som` only matters when
`vision` is also true.

- `PageExplorer.propose(self, obs, screenshot_b64: str | None = None)`:
  caller (runtime.py) passes the screenshot; `propose` forwards it to
  `complete_json` iff `self.vision`.
- `Solver.solve(...)`: inside the per-step loop, when `self.vision`, call
  `browser.screenshot_b64(som=self.som)` and pass it to `complete_json`;
  track it in a new parallel list `obs_screenshots` (mirrors `obs_texts`).
  **Return-value shape changes**: `solve()` now returns
  `(steps, obs_texts, obs_screenshots, final_obs, success)` — every call
  site in `runtime.py` updates its unpacking accordingly.

### `hsge/webarena/runtime.py`

- `_record(self, goal, steps, obs_texts, obs_screenshots, success, difficulty, tag)`:
  for step `k`, if `obs_screenshots[k]` is truthy, base64-decode and write
  `page_state/step_{k:03d}_screenshot.jpg` alongside the existing
  `step_{k:03d}_axtree.txt`, and add `"screenshot": {"path": ...}` next to
  `"axtree_txt"` in the step record. No screenshot -> no file, no new key
  (identical output to today).
- Per-node screenshot (for `PageExplorer`): right after computing
  `content_hash` (same `obs` already in hand), if
  `self.explorer.vision`, capture once via
  `browser.screenshot_b64(som=self.explorer.som)`, reuse it both for
  `self.explorer.propose(obs, screenshot_b64=...)` and for saving to
  `node_state/node_{index:04d}_screenshot.jpg`; record that path in
  `node_rec["screenshot"]` (new key in `nodes.json`, `None` when vision is
  off or capture failed).
- Both callers of `self.solver.solve(...)` (local-task loop and
  goal-conditioned task) update their unpacking to include
  `obs_screenshots` and pass it into `_record`.

### `run_webarena.py`

- `_effective_llm_config` gains three resolved fields using the same
  `_first_not_none` role > shared > default precedence already used for
  `temperature`: `"vision": _first_not_none(role_cfg.get("vision"), llm_cfg.get("vision"), False)`,
  `"som": _first_not_none(role_cfg.get("som"), llm_cfg.get("som"), True)`,
  and `"image_detail": _first_not_none(role_cfg.get("image_detail"), llm_cfg.get("image_detail"), "low")`.
- New `_resolve_agent_vision(llm_cfg) -> dict[str, dict]` (one `{"vision":
  bool, "som": bool, "image_detail": str}` per role in `AGENT_ROLES`), built
  the same way `_resolve_agent_llms` is.
- `WebArenaExplorer.__init__` gains `agent_vision: dict[str, dict] | None =
  None`; constructs `PageExplorer(..., vision=..., som=..., image_detail=...)`
  and `Solver(..., vision=..., som=..., image_detail=...)` from
  `agent_vision["page_explorer"]` / `agent_vision["solver"]`.
- Dry-run path (`args.dry_run`) passes an `agent_vision` dict with
  `vision=True` for `page_explorer`/`solver` so `--dry-run` exercises the
  full wiring against `_FakeBrowser`'s stub screenshot.

### `config.yaml`

```yaml
llm:
  agents:
    page_explorer:
      provider: openai
      model: gpt-4o
      vision: true
      som: true
      image_detail: low
    solver:
      provider: openai
      model: gpt-4o-mini
      vision: true
      som: true
      image_detail: low
    trajectory_segmenter:
      model: deepseek-v4-flash        # unchanged; vision fields omitted (default false)
    skill_abstractor:
      model: deepseek-v4-flash
    skill_verifier:
      model: deepseek-v4-flash
    operator_inducer:
      model: deepseek-v4-flash
```
Requires `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL`) in `.env` for
the roles now on `provider: openai`, per the existing per-role provider
fallback chain — no new secret-handling mechanism.

### `requirements.txt`

Add `Pillow` to the swap-in section (JPEG encode of the BrowserGym
screenshot array).

## Output layout after this change

```
out_dir/
  episodes/ep_XXXX/
    page_state/
      step_000_axtree.txt
      step_000_screenshot.jpg   # NEW, only when vision on for that role
  node_state/                   # NEW directory
    node_0001_screenshot.jpg
  nodes.json                    # NEW "screenshot" key per node record
  ...(skills.json/operators.json/graph.json/predicates.json/summary.json/run_log.jsonl unchanged)
```

## Testing plan

- Existing suite (`hsge/tests/`) must stay green unchanged (all new params
  default to off/None).
- Extend `hsge/tests/test_multi_llm.py` with one test asserting
  `_effective_llm_config`'s vision/som/image_detail precedence (role >
  shared > default), matching the existing style of that test file.
- Unit-test `OpenAILLM`'s retry loop with a fake client whose
  `create()` raises a retryable error N times then succeeds, asserting the
  final result is returned and the right number of attempts were made;
  and a second case asserting a non-retryable error (e.g.
  `AuthenticationError`) raises immediately without sleeping.
- Manual: `python run_webarena.py --dry-run --out <scratch>` exercises the
  full capture -> attach -> persist path end-to-end against the `_FakeBrowser`
  stub screenshot, with no API key required, before spending real GPT-4o
  cost.

## Out of scope (this spec)

- Task-level dedup against already-admitted skills — separate follow-up.
- Any change to `trajectory_segmenter`/`skill_abstractor`/`skill_verifier`/
  `operator_inducer` — they stay text-only.
