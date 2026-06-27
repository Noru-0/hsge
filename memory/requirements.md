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

## Fine-Tune and Eval Artifact Handling

- Do not commit generated LoRA adapters, evaluation traces, browser logs, or
  downloaded WebArena copies.
- Keep generated artifacts under ignored locations such as `outputs/`, `logs/`,
  and `webarena-main-lora/`.
- Preserve small run documentation in `docs/` and operational memory in
  `memory/`.
- When reporting WebArena eval results, distinguish:
  - scored tasks from `[Result]` log lines,
  - unhandled errors from `error.txt`,
  - render HTML count from attempted/rendered tasks.

## HSGE-18 Eval Repro Requirements

For the HSGE-18 LoRA eval, use vLLM with the LoRA served as
`hsge-qwen-hsge18` and set:

```bash
export OPENAI_API_BASE="http://127.0.0.1:8000/v1"
export OPENAI_API_KEY="EMPTY"
export EVAL_MODEL="hsge-qwen-hsge18"
```

Use the HSGE JSON WebArena prompt:

```text
webarena-main/agent/prompts/jsons/p_hsge_json_id_actree.json
```
