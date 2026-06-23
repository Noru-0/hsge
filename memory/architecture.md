# Architecture Memory

## Project Shape

HSGE is a research framework for Hierarchical Skill-Graph Exploration. It explores websites, mines successful trajectories into reusable skills, verifies those skills, and composes them into longer-horizon tasks.

The codebase is intentionally backend-pluggable:

- `hsge/llm.py`: abstract `LLM` and `Embedder` interfaces, plus deterministic `MockLLM` and `HashingEmbedder`.
- `hsge/env.py`: abstract/simple web environment model used by verification and tests.
- `hsge/schema.py`: shared data structures: `Step`, `SubTrajectory`, `SkillCard`, `ParamSlot`, `Task`.
- `hsge/segmentation.py`: converts successful trajectories into candidate sub-trajectories.
- `hsge/clustering.py`: online clustering of sub-trajectories.
- `hsge/abstraction.py`: converts mature clusters into domain-neutral `SkillCard`s.
- `hsge/verification.py`: grounds and executes SkillCards before admission.
- `hsge/library.py`: observes segments, clusters them, abstracts, verifies, admits, and prunes skills.
- `hsge/graph.py`, `hsge/operators.py`, `hsge/curriculum.py`: skill graph, operators, composition, and curriculum tasks.
- `hsge/webarena/`: real WebArena integration, browser/runtime, PageExplorer, scoring, action validation, prefix replay, and diagnostics.

## WebArena Prefix Traces

Prefix-derived frontier nodes use a runtime-local, versioned prefix trace schema
inside `hsge/webarena/runtime.py`, not the shared `Step` schema. The trace records
source URL, target URL, discovery action, replayable actions, stateful hints, and
created time. Checkpoints still store traces under `discovered_urls`, but entries
are now explicit and backward-compatible with older `{source_url, action,
prefix_steps}` records.

## WebArena Frontier Recovery

Frontier expansion prefers callback-discovered URLs from actual solver
navigation because those URLs have replayable prefix traces. If a processed page
produces no callback-discovered children, the runtime falls back to visible
same-origin DOM links, filtered by allow/deny/depth/visited/queued checks and
`filter_frontier`.

Empty direct-load reset observations are recoverable. The runtime records the
reset diagnostic, requeues the URL for bounded retry, and only releases it after
the retry limit. These failures must not be marked visited or processed.

## SFT Action Formats

`build_sft_dataset.py` supports two assistant target formats:

- `hsge_json`: default format for `hsge/webarena/agents.py`. The assistant target
  is JSON shaped like `{"thought": "...", "action": "click('123')"}` and actions
  use the compact HSGE function-call dialect.
- `webarena_id`: upstream WebArena-compatible format for `webarena-main`
  `PromptAgent`. The assistant target is rationale text ending with one fenced
  bracket action such as `click [123]`, `type [123] [text] [0]`, or
  `stop [answer]`.

Dataset validation remains grounded in the HSGE action validator first, then the
optional WebArena export converts already-valid HSGE actions into WebArena
`id_accessibility_tree` actions. This keeps training data aligned with collected
HSGE trajectories while allowing export for upstream WebArena fine-tuning.

## Core Pipeline

1. PageExplorer proposes grounded local tasks from current visible UI evidence.
2. Solver executes tasks and records episodes.
3. Successful episodes are segmented into candidate skill examples.
4. OnlineClusterer groups similar sub-trajectories.
5. Mature clusters are abstracted into SkillCards.
6. Verification grounds slots against held-out contexts and executes canonical actions.
7. Verified skills enter the library and may become operators for composed goals.

## Important Architectural Constraint

Domain-specific tasks are allowed and desirable as training data. Core logic must remain domain-general. Shopping words may appear in source tasks and visible labels, but reusable skills and operator logic should be expressed as generic affordance families such as:

- `open_visible_item`
- `submit_search_query`
- `inspect_feedback_indicator`
- `inspect_menu_options`
- `inspect_filter_sort`
- `activate_state_change_control`
- `fill_visible_field`
- `read_visible_detail`
