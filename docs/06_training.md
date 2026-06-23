# 06 — Training

HSGE is a data + curriculum generator, not a trainer. Training is a downstream step
that consumes HSGE's output. The loop:

```
collect (explore) -> convert (SFT) -> fine-tune -> evaluate -> re-collect
```

## 1. Collect

Run exploration with the goal-conditioned proposer + terminal verification on
(see `04_webarena_runbook.md`). Do not train until this collects verified multi-step
trajectories — otherwise you train on short search/sort/filter data and the model
learns to stop early. Training quality is capped by collection quality.

## 2. Convert to SFT data

```bash
# Recommended: HSGE solver format with Go-Browse style action documentation
python build_sft_dataset.py outputs/<run>/episodes train.jsonl

# Multi-turn (one sample per trajectory, not per step)
python build_sft_dataset.py outputs/<run>/episodes train.jsonl --multiturn

# WebArena bracket format (for upstream compatibility)
python build_sft_dataset.py outputs/<run>/episodes train.jsonl \
  --action-format webarena_json
python build_sft_dataset.py outputs/<run>/episodes train.jsonl \
  --action-format webarena_json --multiturn
```

Three action formats are supported:

| Flag | Assistant output | Action syntax |
|------|-----------------|---------------|
| `hsge_json` (default, **recommended**) | `{"thought": "I need to...", "action": "click('337')"}` | `click('bid')`, `fill('bid','text')`, `send_msg_to_user('text')` |
| `webarena_json` | `{"thought": "Looking at the page...", "action": "click [337]"}` | `click [id]`, `type [id] [text] [0]`, `stop [answer]` |
| `webarena_id` | prose + `` ```click [337]``` `` code block | `click [id]`, `type [id] [text] [0]`, `stop [answer]` |

### `hsge_json` format (Go-Browse style)

The default and recommended format. Training samples follow the Go-Browse prompt structure:

- **System**: Short role instruction only ("You are a web agent...")
- **User**: Structured with `# Goal`, `# Current page Accessibility Tree`, `# Action Space` (full documentation with signatures, descriptions, and examples for all 8 actions), `# History of past actions`, `# Next action`
- **Assistant**: JSON `{"thought": "...", "action": "click('337')"}`

The action space documentation in each user message includes function signatures
with type hints, plain-English descriptions, and usage examples — exactly as
Go-Browse does. This gives the fine-tuned model in-context knowledge of every
available action and its correct syntax.

Actions use the HSGE function-call dialect: `click('bid')`, `fill('bid','text')`,
`type('bid','text','1_or_0')`, `press('key')`, `scroll('down'|'up')`,
`hover('bid')`, `send_msg_to_user('text')`, and optionally `goto('url')`.

### `webarena_json` and `webarena_id` formats

Legacy formats for upstream WebArena PromptAgent compatibility. Actions use bracket
syntax (`click [337]`, `type [332] [controller] [0]`, `stop [answer]`). The action
space is listed as a one-liner in the system message. These formats are kept for
baseline comparisons but `hsge_json` is preferred for training.

## 3. Fine-tune

Pick an open model (e.g. a 7B instruct model). The `messages` jsonl is directly
consumable by LLaMA-Factory, Axolotl, or TRL. LoRA fits on a single 24–48 GB GPU;
full SFT wants multi-GPU. Minimal TRL sketch:

```python
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset
ds = load_dataset("json", data_files="train.jsonl", split="train")
SFTTrainer(model="<base-7b-instruct>", train_dataset=ds,
           args=SFTConfig(output_dir="hsge-agent", num_train_epochs=2,
                          per_device_train_batch_size=2)).train()
```

For a concrete Qwen LoRA workflow and upstream WebArena Shopping benchmark
evaluation, see `15_lora_finetune_eval_webarena_shopping.md`.

## 4. Use the curriculum

`train.jsonl` is sorted easy→hard by `difficulty`. Either train in difficulty order
with limited shuffling, or run staged epochs (≤1, then ≤3, then all) so the model
masters single skills before composed transactions. Curriculum-ordered vs
random-shuffled is a clean ablation.

## 5. Evaluate + loop

Load the checkpoint into your solver, evaluate on WebArena, then re-collect with the
improved agent: deeper exploration → more verified skills → a better dataset → the
next fine-tune. This iterated bootstrap is where compounding gains come from.

## Extensions (not for the first pass)

- **Preference data:** pair a failed and a successful trajectory for the same goal
  to build DPO/rejection-sampling pairs after the SFT warm start (uses the
  failed trajectories you collected).
- **Verification-gated data:** only execution-verified successes enter `train.jsonl`,
  so self-reported "done" episodes don't poison training — the training-side payoff
  of the verification contribution.
