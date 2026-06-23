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
# Go-Browse style: JSON output + narrative thought + webarena bracket actions
python build_sft_dataset.py outputs/<run>/episodes train.jsonl \
  --action-format webarena_json

# Multi-turn (one sample per trajectory, not per step)
python build_sft_dataset.py outputs/<run>/episodes train.jsonl \
  --action-format webarena_json --multiturn
```

Three action formats are supported:

| Flag | Assistant output | Thought style |
|------|-----------------|---------------|
| `webarena_json` | `{"thought": "Looking at the page...", "action": "click [337]"}` | Narrative paragraph (Go-Browse style) |
| `webarena_id` | prose + `` ```click [337]``` `` code block | Narrative paragraph (Go-Browse style) |
| `hsge_json` (default) | `{"thought": "...", "action": "click('337')"}` | Narrative paragraph (Go-Browse style) |

All formats use goal-aware narrative thoughts (no template markers like "Evidence:" or "In summary").
Use `--multiturn` to group all steps of an episode into one chat conversation so the model learns
sequential decision-making. Without it, each step is a separate single-turn sample.

Each example mirrors your solver's action-planner prompt:

- system: action space + output format
- user: goal + current observation (accessibility tree) + recent action history
- assistant: the step's `{"thought":..., "action":...}` (exactly what your solver emits)

Only successful (and, with the terminal evaluator, verified) episodes are kept; each
example carries a `difficulty` for the curriculum. Because the target is the solver's
own output format, a model fine-tuned on this drops straight back into the solver.

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
