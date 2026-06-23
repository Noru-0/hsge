# Decisions Memory

## Domain-Specific Tasks vs Domain-General Logic

Decision: Keep domain-specific tasks when the page supports them. Do not suppress shopping/cart/wishlist/order/checkout tasks on shopping sites.

Reason: These tasks produce useful training data for later SLM training. The overfitting risk belongs in core agent logic and reusable SkillCards, not in grounded task text.

## Canonical Skill Families

Decision: Reusable SkillCards should collapse to a small canonical family vocabulary.

Current accepted families include:

- `open_visible_item`
- `open_visible_detail`
- `submit_search_query`
- `inspect_feedback_indicator`
- `inspect_menu_options`
- `inspect_filter_sort`
- `activate_state_change_control`
- `activate_named_control`
- `fill_visible_field`
- `read_visible_detail`
- `save_visible_item`

Reason: Run logs showed many weak variations that were generic-looking but not actually reusable, such as `activate_visible_control` and `click_visible_item_image`.

## Strict SkillCard Validation

Decision: Keep final SkillCard gates strict.

Reject or canonicalize:

- natural-language action templates,
- value slots used as click targets,
- domain-overfit final names/descriptions/templates,
- noncanonical skill names,
- templates that cannot render to executable HSGE actions.

Reason: Weak admitted skills poison composition and make later curriculum tasks unreliable.

## Bootstrap Verification

Decision: Deterministic fallback skills may verify with `k=1` during bootstrap, but only after canonicalization and action grounding.

Reason: Early runs may not contain multiple distinct contexts for a useful primitive. Requiring `k=2` immediately blocked all skill creation in run 10. The action must still be canonical and grounded.

## Verification Diagnostics

Decision: Verification failures should record concrete reasons, not only `insufficient_successes`.

Examples:

- `browser_not_groundable`
- `browser_unbound_slot`
- `browser_validation_failed:<reason>`
- `mock_not_groundable`
- `mock_parse_failed:<reason>`

Reason: Run 10 had enough upstream evidence, but diagnostics hid whether failures came from no context, no selector, bad action rendering, invalid AXTree grounding, or browser execution.

## Checkout Safety

Decision: Default checkout behavior is safe exploration, not final committing.

Explore and report:

- cart,
- checkout entry,
- address forms,
- shipping/payment options,
- order summary,
- confirmation cues.

Stop before final irreversible actions unless an explicit flag or terminal goal allows it.

## Prefix Replay and Frontier Handling

Decision: Correctness comes before speed for prefix-derived nodes. If a node was discovered through a prefix trace, local tasks should start by replaying that prefix rather than relying on a generic browser reset.

Reason: Run 11 showed search-result tasks being attempted from the root page because task-level reset lost the prefix-arrived node state.

Run 12 follow-up: The task reset problem was fixed, but stale prefixes still drain the frontier. Future handling should not permanently discard potentially useful URLs just because one prefix replay attempt becomes stale. Prefer retry/recovery strategies:

- re-ground the prefix action by visible label or role on the source page,
- retry the URL later if the source state has changed,
- allow direct URL fallback only for stateless/safe prefixes,
- record stale-prefix skips separately from processed nodes.

Do not mark stale-prefix skipped nodes as processed or visited.
