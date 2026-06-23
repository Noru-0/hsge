# Task Log

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

