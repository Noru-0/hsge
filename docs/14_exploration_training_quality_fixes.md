# Exploration and Training Data Quality Fixes

This note summarizes the quality pass added after inspecting WebArena exploration
runs `wa_run_01` through `wa_run_06`.

## Goals

- Keep trainable actions executable and grounded in the current AXTree.
- Improve LLM thoughts so examples explain the next action and visible evidence.
- Make task proposals more page-specific instead of repeating generic templates.
- Preserve domain generality while still allowing deeper workflows when the page
  exposes progression controls.
- Make SFT conversion reject bad steps from older or noisy runs.

## Bugs Fixed

### Invalid and Non-Canonical Actions

The action contract is now restricted to canonical HSGE actions:

- `click`
- `fill`
- `type`
- `press`
- `scroll`
- `hover`
- `goto`
- `send_msg_to_user`

Unsupported actions such as `select_option`, `go_back`, tool calls, and natural
language commands are rejected before training.

### Hallucinated or Bad BIDs

Action validation now checks that targeted actions use numeric BIDs present in
the current AXTree. It also rejects role-incompatible targets, such as filling a
non-input element.

### Disabled Element Clicks

The validator now rejects actions targeting disabled elements, for example:

```text
[445] button 'Search', disabled=True
```

This fixed cases where exploration clicked disabled search buttons and still
recorded the step as trainable.

### Truncated Thoughts

Exploration previously saved thoughts through `obs_summary[:100]`, producing
examples such as:

```text
Evidence: [500
```

Thoughts are now saved in full. Shortened context is still used only where needed
for prompts, not for persisted training data.

### Weak `done message` Targets

Successful examples with generic final answers such as `done message` were
identified as low-quality. The success gate now requires final answers to be
grounded in recent visible page text for read/search/report tasks, and in visible
post-action state for state-changing tasks.

## Exploration Improvements

### Page-Grounded Task Proposal

Task proposal now checks page affordances before accepting a task. For example:

- communication tasks require visible contact/message/email/form affordances;
- history/status tasks require visible record/history/order/ticket affordances;
- sort/filter tasks require visible sort/filter/refine/facet controls;
- search tasks require a visible search control;
- hover tasks require visible menu or popup affordances.

This reduces tasks that appeared on nearly every node regardless of page content.

### Label-Specific Seed Tasks

Seeded tasks now include the visible element label instead of using the same
generic wording everywhere.

Example:

```text
Hover over the visible 'Beauty & Personal Care' menu or expandable control and
report one submenu option that appears.
```

This replaces repeated generic tasks such as:

```text
Hover over one visible menu or expandable control and report one submenu option
that appears.
```

### Duplicate Task Saturation

The runtime now tracks exact task attempts:

- skip an exact task after one success;
- skip an exact task after two failures.

This prevents repeated collection of the same task across nodes when the task text
does not change.

### Deeper Workflow Tasks

The proposer can now emit deeper progression tasks when visible controls support
them, without hardcoding a single domain.

Examples of triggering controls:

- `Continue`
- `Next`
- `Confirm`
- `Checkout`
- `Payment`
- `Place order`

Generated task shape:

```text
Use the visible '<control label>' progression control and report the next required
step or confirmation that appears.
```

## SFT Conversion Improvements

`build_sft_dataset.py` now validates and filters steps by default.

Added interfaces:

- `--validate-only`
- `--repair-thoughts`
- `--report <path>`
- `--allow-goto-training`

The report includes:

- valid example count;
- dropped step reasons;
- action family histogram;
- task family histogram;
- repaired thought count;
- AXTree load coverage.

## Evaluation Improvements

The WebArena HSGE prompt constructor now parses HSGE action arguments with
`ast`-based parsing instead of regex-only parsing. This fixes quoted answers such
as:

```text
send_msg_to_user('No products found for "switch accessories"')
```

Evaluation also records parse failures as normal benchmark failures instead of
crashing the whole task.

## Remaining Issues

- Task proposal can still become domain-specific if the current site exposes only
  one domain's affordances. This is expected, but the core heuristics should stay
  domain-agnostic.
- Some frontier replay paths are unstable and fall back to direct URL navigation.
- OpenAI quota errors (`429 insufficient_quota`) can stop useful progress. The
  runtime should eventually stop early on quota exhaustion instead of continuing
  through all remaining nodes.
- Long-horizon tasks still need stronger verifier support before they should be
  heavily used for SFT.

## Suggested Acceptance Checks

Run focused tests:

```bash
pytest -q hsge/tests/test_action_validation.py hsge/tests/test_build_sft_dataset.py hsge/tests/test_hsge_prompt_constructor.py
```

Validate a run before training:

```bash
python build_sft_dataset.py outputs/wa_run --validate-only --report /tmp/sft_report.json
```

Expected properties:

- no trainable `tool_call(...)`, `functions.*`, `select_option`, or `go_back`;
- no nonnumeric or missing BIDs;
- no clicks on disabled controls;
- no truncated thoughts;
- task proposal logs show repeated/saturated tasks being skipped;
- successful training examples include meaningful `hover`, `scroll`, `fill`, and
  `send_msg_to_user` coverage.
