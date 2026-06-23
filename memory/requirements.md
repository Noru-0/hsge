# Requirements Memory

## Development Requirements

- Always run commands from the project root: `/Users/Kiet/Documents/Code/WebAgent/Phat/hsge`.
- Use `PYTHONPATH=.` for tests and scripts.
- Use mock backends by default. Do not switch to real LLM/browser services unless explicitly requested.
- Tests are pytest-based:

```bash
PYTHONPATH=. python -m pytest hsge/tests/ -v
```

If pytest is unavailable, use the existing direct fallback test files, for example:

```bash
PYTHONPATH=. python hsge/tests/test_clustering.py
PYTHONPATH=. python hsge/tests/test_action_validation.py
PYTHONPATH=. python -m compileall hsge
```

## Domain Generality

The agent logic, skill abstraction, segmentation, clustering, verification, and planning must transfer across unrelated websites. Avoid hardcoding logic that only works for shopping, forums, docs, or admin tools.

Domain-specific tasks are still useful. For example, on a shopping site it is good to propose cart, wishlist, checkout, product, and order-history tasks when visible UI evidence supports them. The generality requirement applies to core mechanisms and reusable skills, not to the natural-language task data collected from a specific domain.

## Skill Quality Requirements

- SkillCards must use canonical HSGE actions only, such as `click(...)`, `fill(...)`, `type(...)`, `hover(...)`, `scroll(...)`, and `press(...)`.
- Do not admit natural-language action templates.
- Selector targets must use selector slots.
- Input/text values must use value slots.
- Final reusable skill names and descriptions must be domain-neutral.
- Prefer rejecting or canonicalizing weak skills over admitting brittle one-off skills.
- Verification should validate rendered canonical actions against the current AXTree before execution.

## Checkout and Transaction Safety

Checkout/order exploration should use safe mode by default:

- Explore cart, checkout, address, shipping, payment, review, and confirmation cues.
- Do not click final irreversible place-order/pay/submit-order controls unless explicitly allowed.
- Treat these flows as generic transaction/state-change affordances, not shopping-only logic.

