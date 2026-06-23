# Task Log Memory

## Recent Work

### Run 06-09 Analysis

Evaluated earlier WebArena runs for task proposal quality, pass/fail rate, skill creation, domain overfitting, prefix replay, node metrics, and exploration behavior. Main findings:

- Task proposals were often useful but sometimes too shallow.
- Early skill creation produced weak or overfit names.
- Node metrics needed explicit task-level accounting.
- Prefix replay needed stricter grounding and safer direct-goto fallback behavior.
- Domain-specific tasks should not be suppressed; only reusable agent logic should remain domain-general.

### Skill Abstraction Quality Improvements

Implemented stricter abstraction and validation:

- Stronger domain-neutral abstraction prompt.
- Canonical action-template validation.
- Slot-type validation for selectors and values.
- Duplicate/canonical skill handling.
- Rejection of natural-language templates and domain-overfit final SkillCards.

Commit: `d2e69e2 Improve skill abstraction quality gates`

### Exploration, Checkout, Metrics, and Diagnostics Improvements

Implemented broader exploration and diagnostics:

- Skill diagnostics logging.
- Action-level segmentation for reusable primitives.
- Deterministic fallback SkillCard generation.
- Safe checkout/order exploration knobs.
- Transactional-flow detection.
- Task-level node metrics.
- Prefix replay validation improvements.
- Useful-skill diversity tracking.

Commit: `817a749 Improve skill discovery and checkout exploration`

### Run 10 Analysis and Follow-up Fixes

Run 10 was stopped early. It showed:

- 32 episodes: 17 success, 15 failed.
- 43 segment observations.
- 22 cluster maturity events.
- 13 abstractions attempted.
- 0 admitted skills.
- All verification rejections reported `insufficient_successes`.

Core diagnosis: discovery was no longer starved for examples. The bottleneck had moved to verification and grounding. The LLM produced plausible but noncanonical skills like `activate_visible_control` and `click_visible_item_image`, and verifier diagnostics were too coarse.

Implemented follow-up fixes:

- Canonicalized almost-generic skill names to approved families.
- Filtered `send_msg_to_user` and `goto` from skill candidate segments.
- Added deterministic slot grounding fallback in verification.
- Added verification failure reasons to diagnostics.
- Increased browser verification contexts from 3 to 10.
- Allowed deterministic bootstrap skills to verify with `k=1`.
- Prevented `Page Next` pagination from being treated as deep progression.
- Added regression tests for these cases.

Validation:

- `PYTHONPATH=. python hsge/tests/test_clustering.py` passed.
- `PYTHONPATH=. python hsge/tests/test_action_validation.py` passed.
- `PYTHONPATH=. python -m compileall hsge` passed.
- Full pytest could not run because `pytest` was not installed.

## 2026-06-23: Run 11 Early Stop and Easy-Task Failure Fix

Run 11 stopped early because the frontier was exhausted after only a few usable nodes. Several candidate URLs were marked visited/processed before `_process_node()` proved they could be loaded and explored. When stale stateful prefix replay skipped those nodes, the frontier still lost them.

The run also showed easy search-result tasks failing from the wrong page. Node 2 reached `/catalogsearch/result` through prefix replay, but each local task called `browser.reset()`, which reset back to the original browser start URL instead of the prefix-arrived search-result state. As a result, tasks like sorting by price, opening a result item, and clicking result-page compare controls were attempted against the root page AXTree.

Implemented fixes:

- Preserve prefix traces after successful prefix navigation so they can be replayed for each task at a prefix-derived node.
- Add a correctness-first task reset helper that replays the prefix before each local/composed task when a prefix is available.
- Move node processed/visited accounting until after `_process_node()` returns a processed URL.
- Keep stale skipped nodes from inflating processed metrics.
- Avoid re-adding the currently processed URL during callback frontier expansion.
- Treat product/gallery `Next` controls as pagination/progression noise unless checkout/order-flow cues are present.

Validation:

- Added regression coverage for prefix-based task reset and the `Next` progression filter.
- Run the direct fallback test sweep when pytest is unavailable.

## 2026-06-23: Run 12 Evaluation

Run 12 showed that the main wrong-page reset bug was fixed, but early stopping is only partially fixed.

What improved:

- Node 2 tasks now start from the correct search-results URL:
  `http://192.168.1.31:7770/catalogsearch/result/?q=Gingerbread+House`.
- Result-page tasks no longer accidentally run from root `/`.
- Easy result-page tasks improved:
  - opening `Sort By` succeeded,
  - clicking a product detail link succeeded,
  - clicking `Add to Compare` succeeded,
  - My Cart status/report tasks from the result page succeeded.
- No empty/invalid episodes were recorded: `invalid_or_empty_episodes: 0`.
- Skill creation improved: one real skill was admitted, `activate_state_change_control`.
- Node metrics became more honest: checkpoint showed only two truly processed/visited nodes, not the skipped stale-prefix nodes.

Still unresolved:

- The run still stopped early with only `nodes_processed: 2`.
- Stale prefix nodes are no longer falsely counted as processed, but they are still removed from frontier and not retried.
- Several queued/discovered URLs remain unreachable because prefix BIDs went stale:
  - product detail URLs,
  - wishlist,
  - category pages,
  - login-derived URLs.
- Some task proposals remain poorly grounded:
  - category labels can become address/checkout-field tasks,
  - product titles can become feedback-control tasks.
- Some simple actions still loop:
  - sort-by-price clicked the `Sort By` combobox repeatedly instead of selecting the `Price` option,
  - add-to-cart/add-to-wishlist on result items repeatedly clicked controls without reaching a success marker.

Next likely fixes:

- Preserve or retry stale-prefix frontier nodes instead of permanently draining them.
- Add a fallback recovery path for stale prefixes, such as re-discovering a same-label target from the source page AXTree or direct URL fallback only when the prefix is stateless/safe.
- Add task preflight grounding so quoted entities/control categories must match visible AXTree evidence before a task is attempted.
- Improve solver behavior for combobox/select controls by selecting visible options after opening the control.
- Improve no-op click handling: when URL/AXTree do not change after repeated clicks, force an alternative grounded target or terminate with a clearer failure reason.

## 2026-06-23: Prefix Trace Save Logic Cleanup

Implemented a versioned runtime-local prefix trace schema in `hsge/webarena/runtime.py`.

Changes:

- Added `PrefixTrace` and `PrefixTraceStep` for checkpoint-safe prefix replay data.
- Replaced ad hoc raw `Step` storage in `_discovered_urls` with normalized trace construction.
- Preserved backward compatibility for older checkpoint records shaped like `{source_url, action, prefix_steps}`.
- Updated checkpoint save/resume and prefix replay to route through trace coercion helpers.
- Added compact `prefix_trace` metadata to `nodes/node_*/node_info.json`.
- Added regression coverage for checkpoint round-trip and legacy trace migration.

Validation:

- `python -m py_compile hsge/webarena/runtime.py hsge/tests/test_action_validation.py hsge/tests/test_clustering.py` passed.
- Direct prefix regression functions passed.
- Full pytest could not run because `pytest` was not installed in the active Python environment.

Frontier-exhaustion proposal:

- Do not terminate solely because the active frontier is empty while recoverable stale-prefix candidates exist.
- Track stale-prefix candidates in a retry queue with bounded attempts.
- On retry, first re-ground the action on the source page by label/role/BID similarity, then replay.
- Use direct URL fallback only when the prefix trace is stateless.
- If both active frontier and retry queue are empty, refresh from safe current-page discoveries or scorer lookahead before stopping.
