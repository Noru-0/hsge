# Progress Report

## Summary

During this period, I started from a Go-Browse + U/V baseline. However, this direction was not selected as the main direction -> build a new agent based on my supervisor's ideas (**HSGE agent**): a pipeline that runs exploration/evaluation on the **WebArena Shopping domain**, uses frontier selection, recovers state with prefix traces, discovers skills, verifies skills, generates SFT data, and evaluates with **SR (success rate)**.

## General Timeline

| Date | Work |
| --- | --- |
| **1/6** | Tested a Go-Browse-like baseline with U/V frontier scoring. The result improved slightly. However, this direction was not selected as the main direction -> build a new agent based on my supervisor's ideas (HSGE agent). |
| **4/6** | Designed and started implementing the HSGE agent: online skill discovery, verification-gated admission, hierarchical skill graph, curriculum/transfer idea. |
| **10/6** | Completed an offline baseline to validate the basic pipeline before WebArena runs. |
| **16/6** | Integrated the WebArena runtime: online exploration, multi-provider LLM, screenshots, prefix traces, frontier filtering, and login/account handling. |
| **23-24/6** | Fixed exploration and data-quality issues: prefix replay, stale frontier handling, action validation, and SFT export format. |
| **25/6** | Fine-tuned LoRA and evaluated HSGE-18 on the **WebArena Shopping domain**, using **SR (success rate)** as the main metric. |

## Main Results

- **Go-Browse + U/V baseline:** added node selection using Uncertainty and Value scores. Compared with the baseline, SR improved from **22.4%** to **25.5%** with U and **26.0%** with U+V. However, this direction was not selected as the main direction -> build a new agent based on my supervisor's ideas (HSGE agent).
- **WebArena runtime:** added online exploration, multi-provider LLM support, screenshot observations, logging, login/account handling, URL-template frontier filtering, and checkpoint/resume.
- **State restoration:** added prefix traces to replay the action sequence leading to a URL, helping recover pages that cannot be restored well by direct URL navigation.
- **Skill discovery:** improved segmentation, abstraction, canonical skill families, verification diagnostics, and quality gates to avoid over-specific or non-executable skills.
- **Training pipeline:** standardized the action space, filtered invalid/hallucinated BID actions, and supported `hsge_json` and WebArena bracket-action export.
- **Latest LoRA eval:** fine-tuned `Qwen2.5-7B-Instruct` using single-turn + multi-turn HSGE data, evaluated on the **WebArena Shopping domain**, reaching **SR = 26/184 scored tasks = 14.13%**.
- **Latest runtime:** exploration took **3h50m**, training took **1h15m**, and evaluation took **4h**.

## Key Metrics

| Experiment | Result |
| --- | ---: |
| Baseline eval | 43/192, 22.4% |
| Only U eval | 49/192, 25.5% |
| U + V eval | 50/192, 26.0% |
| HSGE first exploration | 20 nodes, 109 tasks, 92/109 positive trajectories; early-stopped due to runtime/action errors |
| `train-single-18.jsonl` | 750 samples, ~3.5M tokens |
| Latest WebArena Shopping eval | SR = 26 pass / 184 scored = 14.13% |
| Latest run time | Exploration 3h50m, training 1h15m, eval 4h |

## Data / Training / Evaluation

- **Data:** the current main dataset is `train-single-18.jsonl` with **750 samples**, about **14.2 MB / 3.5M tokens**, covering **85 page titles**, **109 products**, and **15 categories**. There is also a multi-turn version for continuing training after single-turn training.
- **Training:** fine-tuned `Qwen2.5-7B-Instruct` with LoRA in two stages: first on single-turn data, then continued on multi-turn data. Latest training time: **1h15m**.
- **Evaluation:** ran on the **WebArena Shopping domain** using an HSGE JSON action adapter to WebArena action format. The main metric is **SR (success rate)**. Latest result: **187 tasks**, **184 scored**, **26 pass**, **158 fail**, **3 unhandled errors**, **SR = 14.13%**. Evaluation time: **4h**.
- **Exploration data collection:** latest exploration run was on the **WebArena Shopping domain** and took **3h50m**. The collected data is still skewed toward easy tasks such as search, wishlist, compare, product detail, and add-to-cart; checkout, order/account workflow, read-and-answer, filter/sort, and hover/scroll are still underrepresented.
- **Note:** HSGE first exploration was an initial test run and stopped early due to runtime/action-format/grounding errors, so those numbers show that the basic pipeline worked but should not be treated as a complete run.

## Fixed Issues

- Fixed HSGE/WebArena action-format mapping, especially `fill`, `type`, `scroll`, `hover`, `press`, and `send_msg_to_user`.
- Blocked invalid training examples: unsupported actions, missing BIDs, clicks on disabled/static elements, and truncated thoughts.
- Fixed prefix-derived nodes being reset back to the root page before task execution.
- Stale-prefix and empty-reset nodes are no longer counted as successfully processed.
- Added DOM-link fallback when the solver does not discover new URLs, reducing early stopping from empty frontier.

## Current Limitations

- Exploration can still stop early when a prefix trace becomes stale or cannot be re-grounded.
- Grounding is still weak for combobox/select controls, changing BIDs, and repeated labels.
- Skill reuse is not strong yet; admitted skills have not produced many long-horizon compositions.
- Training data is still skewed toward simple tasks such as search, wishlist, compare, product detail, and add-to-cart; checkout, order/account workflow, read-and-answer, filter/sort, and hover/scroll are still missing.
- Login state and WebArena action format remain important evaluation failure sources.

## Next Steps

1. Improve prefix recovery by re-grounding actions using label, role, and context.
2. Add no-op/loop detection for repeated clicks and combobox/select controls.
3. Run new exploration to increase coverage of missing task families.
4. Clean the dataset: deduplicate, flag login redirects, and balance task types.
5. Fine-tune again and re-evaluate on the **WebArena Shopping domain**, comparing with the current **SR = 14.13%**.
