# HSGE — Hierarchical Skill-Graph Exploration

HSGE is a framework for web agents that discover **reusable, verified skills**
during exploration and **compose** them into long-horizon tasks. It maintains a
two-level graph — concrete page states/actions at the low level, abstract skills
with precondition/effect edges at the high level — discovers skills online, admits
only those that execute successfully, transfers them to unseen sites, and generates
an easy→hard curriculum whose deepest chains are full transactions (e.g. a purchase).

This repository is a **runnable skeleton with deterministic mock backends**: the
whole pipeline runs with no API keys, GPU, or live browser. Swap the mocks for real
backends (LLM, embedder, WebArena) to scale up.

## Quickstart

```bash
pip install numpy
python explore.py             # run the exploration loop (frontier -> discover -> compose -> verify)
python demo_shopping.py       # shopping domain: plan -> execute -> verify a purchase
python demo.py                # login/search domain: discover -> verify -> transfer
python compare_three_way.py   # Flat baseline vs AWM vs HSGE on identical input
PYTHONPATH=. python hsge/tests/test_clustering.py
```

Run everything from this directory (the one containing `hsge/`).

## Scripts

| Script | What it does |
| --- | --- |
| `explore.py` | The exploration loop: frontier expansion, skill discovery, goal-conditioned composed episode, terminal verification |
| `demo.py` | Full discover→cluster→abstract→verify→transfer on mock login/search sites |
| `demo_shopping.py` | End-to-end shopping: plan a purchase, execute it, verify at order-confirmation |
| `demo_purchase.py` | Planning + curriculum only (operator/precondition model) |
| `compare.py`, `compare_three_way.py` | Baseline comparisons (Flat / AWM / HSGE) |
| `run_webarena.py` | Standalone WebArena exploration (real run + `--dry-run`) |
| `build_sft_dataset.py` | Converts collected trajectories into curriculum-ordered SFT data |

## Documentation (`docs/`)

| Doc | Read it for |
| --- | --- |
| `01_overview.md` | The method, contributions, and what makes it different |
| `02_architecture.md` | Module map, data flow, the hierarchical-graph model |
| `03_running_locally.md` | Running every script + interpreting the output |
| `04_webarena_runbook.md` | Hosting WebArena and running real exploration |
| `06_training.md` | The collect → SFT → fine-tune → evaluate → loop pipeline |
| `09_run_on_webarena.md` | Running the standalone WebArena exploration runtime |
| `15_lora_finetune_eval_webarena_shopping.md` | LoRA fine-tune Qwen and evaluate on WebArena Shopping |
| `00_package_readme.md` | The original package-level README |

## The pipeline at a glance

```
explore (collect verified, composed trajectories)
   -> build_sft_dataset.py (curriculum-ordered SFT data)
      -> fine-tune a model
         -> evaluate on WebArena
            -> re-collect with the improved agent   (iterated bootstrap)
```

## SFT dataset formats

`build_sft_dataset.py` can export training data in three formats. The default
`hsge_json` format uses Go-Browse style prompt structure with full action space
documentation in each user message.

```bash
# Recommended: HSGE solver format (Go-Browse style, full action docs)
PYTHONPATH=. python build_sft_dataset.py outputs/wa_run_17/episodes train_hsge.jsonl

# Multi-turn (one sample per trajectory)
PYTHONPATH=. python build_sft_dataset.py outputs/wa_run_17/episodes train_hsge.jsonl --multiturn

# WebArena bracket format (upstream compatibility)
PYTHONPATH=. python build_sft_dataset.py outputs/wa_run_17/episodes train_webarena.jsonl \
  --action-format webarena_json
PYTHONPATH=. python build_sft_dataset.py outputs/wa_run_17/episodes train_webarena.jsonl \
  --action-format webarena_json --multiturn
```

| Flag | Output | Action syntax |
|------|--------|---------------|
| `hsge_json` (default, **recommended**) | `{"thought": "...", "action": "click('337')"}` | `click('bid')`, `fill('bid','text')`, `send_msg_to_user('text')` |
| `webarena_json` | `{"thought": "...", "action": "click [337]"}` | `click [id]`, `type [id] [text] [0]`, `stop [answer]` |
| `webarena_id` | prose + `` ```click [337]``` `` | `click [id]`, `type [id] [text] [0]`, `stop [answer]` |

`hsge_json` training samples follow the Go-Browse prompt structure:
system is a short role instruction; the user message includes `# Goal`,
`# Current page Accessibility Tree`, `# Action Space` (full documentation with
signatures, descriptions, and examples for all 8 actions), `# History of past
actions`, and `# Next action`.

- `--multiturn` groups all steps of an episode into one chat conversation.
- `goto` examples are dropped by default; add `--allow-goto-training` only
  when direct URL actions are part of the intended deployment policy.
