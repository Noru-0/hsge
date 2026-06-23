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

