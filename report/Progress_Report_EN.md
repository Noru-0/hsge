# Progress Report - Full Version

## 1. Overview

During this period, I first improved a Go-Browse-style baseline with U/V frontier scoring. However, this direction was not selected as the main direction -> build a new agent based on my supervisor's ideas (**HSGE agent**): a hierarchical exploration agent that can discover skills, verify skills, recover exploration state, generate SFT data, and evaluate on the **WebArena Shopping domain** using **SR (success rate)** as the main metric.

The main goal was not only to increase the number of trajectories, but also to improve trajectory quality, state recovery, action validity, and the usefulness of collected data for fine-tuning a smaller agent.

## 2. General Timeline

| Date | Work | Outcome |
| --- | --- | --- |
| **1/6** | Improved a Go-Browse-like baseline with U/V frontier scoring. | SR improved from **22.4%** to **25.5%** with U and **26.0%** with U+V. However, this direction was not selected as the main direction -> build a new agent based on my supervisor's ideas (HSGE agent). |
| **4/6** | Designed the HSGE agent direction based on my supervisor's ideas. | Shifted focus to online skill discovery, verification-gated skill admission, hierarchical skill graph, curriculum, and transfer. |
| **10/6** | Completed an offline baseline. | Had a mock/offline pipeline to validate the basic logic before WebArena runs. |
| **16/6** | Integrated the WebArena runtime. | Added online exploration, multi-provider LLM support, screenshots, prefix traces, frontier filtering, login/account handling, and logging. |
| **23/6** | Fixed major exploration issues. | Fixed prefix-derived task reset, stale-prefix accounting, early frontier exhaustion, and empty reset observation handling. |
| **24/6** | Standardized SFT data and action formats. | Added action validation, invalid-example filtering, `hsge_json`, and WebArena bracket-action export. |
| **25/6** | Fine-tuned and evaluated HSGE-18 LoRA on the **WebArena Shopping domain**. | Latest run: exploration **3h50m**, training **1h15m**, eval **4h**; main metric is **SR**, reaching **26/184 pass = 14.13%**. |

## 3. Baseline Go-Browse + U/V

The initial problem was that a website can expose a very large number of URLs/nodes. Exhaustively exploring the whole frontier is expensive, while many nodes have similar structure or training value. Therefore, I added two node-prioritization scores:

- **Uncertainty score (U):** measures how uncertain the model is when looking at a node. Nodes with higher confidence variance are prioritized because they may provide more valuable training data.
- **Value score (V):** prioritizes branches with higher parent success rate, but discounts a branch if it has already been explored many times. This balances exploiting promising branches and avoiding repeated sibling URLs.

Exploration results on the **WebArena Shopping domain**:

| Strategy | Time | Nodes | Tasks | Trajectories | Training examples |
| --- | ---: | ---: | ---: | ---: | ---: |
| Only U | 6h18m | 6 | 103 | 491 (309/182) | 946 |
| U + V | 18h | 14 | 233 | 1199 (908/291) | 2649 |

Evaluation results after fine-tuning Qwen2.5-7B-Instruct, run on the **WebArena Shopping domain** with **SR (success rate)** as the metric:

| Strategy | Success/Total | SR | Eval Time |
| --- | ---: | ---: | ---: |
| Baseline | 43/192 | 22.4% | 4h |
| Only U | 49/192 | 25.5% | 4h |
| U + V | 50/192 | 26.0% | 4h |

These results show that U/V improved over the baseline, but the gain was still modest. This suggests that frontier scoring helps, but action quality, grounding, task coverage, and state restoration remain larger bottlenecks.

More importantly, after reporting this direction, the Go-Browse + U/V baseline was not selected as the main direction -> build a new agent based on my supervisor's ideas (HSGE agent). Therefore, the U/V baseline is kept as an initial experiment, while the main focus shifted to HSGE.

## 4. HSGE Agent and WebArena Runtime

After the baseline, I implemented HSGE as a hierarchical exploration agent. The core idea is not only to collect independent trajectories, but also to detect repeated sub-trajectories, cluster them, abstract them into skills, verify those skills, and then use the skills/operators to support future exploration and longer tasks.

Implemented components:

- **Online exploration on WebArena:** the system can run directly on WebArena instead of only offline mocks.
- **Multi-provider LLM support:** supports DeepSeek, OpenAI, and custom providers, separating explorer, solver, and lookahead models.
- **Screenshot observations:** saves screenshots per step for debugging and future vision-based evaluation.
- **Detailed logging and artifacts:** each run exports `coverage.json`, `domain.json`, `frontier.jsonl`, `skills.json`, `skill_diagnostics.json`, `graph.json`, `metrics.json`, `episodes/`, screenshots, and page-state accessibility trees.
- **Checkpoint/resume:** runtime can persist frontier state, visited/queued URLs, prefix traces, skill state, and graph state.
- **Login/account handling:** added account hints and storage state for login-required tasks.

## 5. Frontier, Exploration, and State Restoration

A major issue in WebArena exploration is that many URLs cannot be restored correctly with direct navigation. For example, a URL may depend on session state, login redirects, temporary state, or changed element IDs after a browser reset. To address this, I added **prefix traces**.

A prefix trace stores:

- source URL;
- target URL;
- action that led to the target URL;
- replayable action sequence;
- checkpoint/resume metadata.

When a URL is selected again from the frontier, the runtime prioritizes replaying the prefix instead of only using `goto(url)`. This helps tasks start from the correct page state, especially for search results, product pages, cart/wishlist pages, or pages after login.

Important exploration improvements:

- Frontier selection is no longer pure FIFO. The runtime uses U/V score, parent success rate, sibling penalty, and a top-score band to avoid getting stuck on a stale branch.
- Callback-discovered URLs from actual solver actions are preferred because they have prefix traces.
- If the solver does not discover new URLs, the runtime falls back to filtered same-origin DOM links.
- Stale-prefix and empty-reset nodes are no longer counted as successfully processed/visited.
- Runtime has bounded retry/release for stale prefixes and empty observations.
- Task proposal is more grounded in visible affordances, visible labels, task saturation, and progression controls.

One important bug fixed was that prefix-derived nodes were reset back to the root page before task execution. After the fix, tasks on search-result pages start from the correct search-result state instead of mistakenly running from the homepage.

## 6. Skill Discovery and Quality Gates

After the `Improve skill abstraction quality gates` commit, the skill lifecycle was strengthened. The goal is to avoid admitting skills that are too specific, ungroundable, or non-executable.

Main changes:

- Segment trajectories into reusable candidate sub-trajectories.
- Canonicalize skills into general families such as `open_visible_item`, `submit_search_query`, `inspect_filter_sort`, `activate_state_change_control`, `fill_visible_field`, and `read_visible_detail`.
- Reject skills if the action template is noncanonical, slot type is invalid, a value slot is used as a click target, or the description/template is too domain-specific.
- Add deterministic fallback SkillCards for important primitives.
- Add detailed verification diagnostics instead of only reporting `insufficient_successes`.
- Increase browser verification contexts and allow deterministic bootstrap skills with `k=1` when data is limited but the action is canonical and groundable.

Observed outcome:

- After the fixes, the system is no longer completely starved at the discovery stage.
- Some runs admitted real skills, such as `activate_state_change_control`.
- The current bottleneck has moved from "no skill candidates" to "verification/grounding is not strong enough and skill reuse has not yet produced many long-horizon compositions."

## 7. Action Space and Training Data Pipeline

A major issue in early runs was action-format mismatch between HSGE/BrowserGym and WebArena. Some invalid actions entered the training data, causing the model to learn wrong formats or output actions that could not be executed.

Issues found:

- `select_option()` was mapped incorrectly to `type`;
- `fill()` submitted forms too early;
- missing `scroll`, `press`, and `hover`;
- unsupported actions such as `go_back`, tool calls, and natural-language commands;
- hallucinated BID, such as using product names instead of numeric element IDs;
- clicks on disabled buttons or static text;
- truncated thoughts, weakening grounding.

Improvements made:

- Standardized canonical actions: `click`, `fill`, `type`, `press`, `scroll`, `hover`, `goto`, `send_msg_to_user`.
- Validate that BID must be numeric and present in the current accessibility tree.
- Reject role-incompatible actions, such as filling a non-input element.
- Reject disabled targets and unsupported actions.
- Repair/validate SFT data during dataset construction.
- Support multiple export formats:
  - `hsge_json`: main HSGE solver format with JSON assistant output.
  - WebArena bracket action: used for upstream WebArena evaluation.

Current `train-single-18.jsonl` dataset:

| Metric | Value |
| --- | ---: |
| Samples | 750 |
| Estimated size | ~14.2 MB / ~3.5M tokens |
| Unique page titles | 85 |
| Unique products | 109 |
| Unique categories | 15 |

This dataset is useful for learning action syntax and basic shopping behavior, but it is still imbalanced. Tasks such as wishlist, search, compare, product detail, and add-to-cart dominate; checkout, cart management, order/account workflow, read-and-answer, filter/sort, and hover/scroll are still underrepresented.

## 8. Evaluation and LoRA Fine-tuning

The latest stage used `Qwen/Qwen2.5-7B-Instruct` with two-stage LoRA:

1. Fine-tune on `training/train-single-18.jsonl`.
2. Continue the same adapter on `training/train-multi-18.jsonl`.

Evaluation served the HSGE-18 adapter with vLLM and ran on the **WebArena Shopping domain** with a prompt/action adapter that converts HSGE JSON actions into WebArena actions. The main metric is **SR (success rate)**. Required patches included:

- parse JSON model output;
- convert `click('1424')` to `click [1424]`;
- convert `fill(...)` to `type [id] [text] [0]`;
- convert `send_msg_to_user(...)` to `stop [...]`;
- add `action_splitter` so WebArena does not crash when rendering invalid actions;
- use `EVAL_MODEL` for the fuzzy evaluator instead of the old hardcoded model.

Latest result:

| Metric | Result |
| --- | ---: |
| Exploration time | 3h50m |
| Training time | 1h15m |
| Evaluation time | 4h |
| Total tasks | 187 |
| Scored tasks | 184 |
| Pass | 26 |
| Fail | 158 |
| Unhandled errors | 3 |
| SR over scored tasks | 14.13% |
| SR counting errors as failures | 13.90% |

The three unhandled errors were:

- one page-load timeout;
- one evaluator assertion error;
- one temporary DNS failure to the Cloudflare Shopping URL.

Compared with earlier runs that stopped early or had many runtime/action-parsing errors, this evaluation is more complete on the **WebArena Shopping domain** and covers almost the full Shopping benchmark. However, **SR** is still low, mainly because data coverage is insufficient, grounding is weak, and skill reuse does not yet support long-horizon tasks well.

## 9. Fixed Issues and Current Limitations

Important fixed issues:

- Prefix-derived nodes were incorrectly reset to the root page.
- Stale-prefix/empty-reset nodes were incorrectly counted as processed.
- Frontier became empty too early when the solver did not discover new URLs.
- Training data contained invalid actions, hallucinated BIDs, disabled/static targets, and truncated thoughts.
- Evaluation crashed when model output HSGE JSON or quoted actions could not be parsed.

Current limitations:

- Exploration can still stop early when prefixes become stale and cannot be re-grounded.
- Grounding is weak for combobox/select controls, changing BIDs, and repeated labels.
- The solver still loops on no-op clicks or actions that do not change the URL/AXTree.
- Skill reuse is not strong enough yet to create reliable long-horizon task composition.
- The dataset is skewed toward easy tasks and lacks reading tasks, scroll/hover, checkout, and account/order workflows.
- Login state is noisy; some samples start from login redirects.
- WebArena action format is strict, so validation/adapter remains important.

## 10. Next Steps

1. **Prefix recovery:** re-ground prefix actions using label, role, nearby text, and source-page context before releasing a URL.
2. **Loop/no-op handling:** detect repeated clicks, combobox loops, or actions that do not change URL/AXTree to force retry or terminate more clearly.
3. **Exploration coverage:** run more exploration on missing task families: scroll, hover, read-and-answer, filter/sort, cart management, account/order workflow, safe checkout.
4. **Dataset cleaning:** deduplicate single-turn samples, flag login redirects, balance task families, and create clearer train/dev splits.
5. **Skill reuse:** improve verified skill retrieval and operator composition so admitted skills actually support exploration.
6. **Re-evaluation:** fine-tune again on cleaner data and compare on the **WebArena Shopping domain** using **SR**, with the current baseline at **14.13%**.
