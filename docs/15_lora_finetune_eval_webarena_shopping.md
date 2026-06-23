# 15 — LoRA Fine-tuning and WebArena Shopping Evaluation

This guide is for fine-tuning `Qwen/Qwen2.5-7B-Instruct` with LoRA/QLoRA and
evaluating it on the upstream WebArena **Shopping** test set.

Use this path when the final evaluator is `webarena-main/run.py`. If the model
will instead replace the HSGE solver inside `run_webarena.py`, use
`hsge_json` data instead of the WebArena format below.

## 1. Choose the Right Dataset Format

For upstream WebArena evaluation, train on WebArena `id_accessibility_tree`
actions:

```bash
PYTHONPATH=. python build_sft_dataset.py outputs/wa_run_17 train_webarena.jsonl \
  --action-format webarena_id \
  --report outputs/wa_run_17/sft_report_webarena.json
```

Expected run-17 first-pass output:

```text
examples valid: 199
action format : webarena_id
```

Do not mix formats:

| Evaluator | Dataset format | Example action |
| --- | --- | --- |
| `webarena-main/run.py` | `webarena_id` | `click [123]` |
| HSGE `run_webarena.py` solver | `hsge_json` | `{"action": "click('123')"}` |

Run 17 is clean enough for a first LoRA smoke test, but it is small. Expect the
model to learn output syntax better than full benchmark behavior until more
shopping task families are collected.

## 2. Prepare a Train/Dev Split

Keep the raw generated file unchanged, then create split files:

```bash
mkdir -p data/sft
python - <<'PY'
import json, random
from pathlib import Path

src = Path("train_webarena.jsonl")
rows = src.read_text(encoding="utf-8").splitlines()
random.Random(7).shuffle(rows)

n_dev = max(20, int(len(rows) * 0.1))
Path("data/sft").mkdir(parents=True, exist_ok=True)
Path("data/sft/webarena_train.jsonl").write_text("\n".join(rows[n_dev:]) + "\n", encoding="utf-8")
Path("data/sft/webarena_dev.jsonl").write_text("\n".join(rows[:n_dev]) + "\n", encoding="utf-8")
print({"train": len(rows[n_dev:]), "dev": len(rows[:n_dev])})
PY
```

With only ~200 examples, treat dev loss as a syntax/overfit signal, not a
reliable benchmark predictor.

## 3. Fine-tune Qwen with QLoRA

Any trainer that accepts chat `messages` JSONL works. LLaMA-Factory, Axolotl,
and TRL are all reasonable. A minimal TRL-style setup is:

```bash
pip install -U "transformers>=4.45" datasets accelerate peft trl bitsandbytes
```

Create `scripts/train_qwen_webarena_lora.py`:

```python
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig
from trl import SFTConfig, SFTTrainer

MODEL = "Qwen/Qwen2.5-7B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

def render_chat(example):
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}

train = load_dataset("json", data_files="data/sft/webarena_train.jsonl", split="train").map(render_chat)
dev = load_dataset("json", data_files="data/sft/webarena_dev.jsonl", split="train").map(render_chat)

bnb = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype="bfloat16",
    bnb_4bit_use_double_quant=True,
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL,
    quantization_config=bnb,
    device_map="auto",
    trust_remote_code=True,
)

lora = LoraConfig(
    r=32,
    lora_alpha=64,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    task_type="CAUSAL_LM",
)

args = SFTConfig(
    output_dir="outputs/lora/qwen25_7b_webarena_shopping",
    dataset_text_field="text",
    max_seq_length=8192,
    num_train_epochs=3,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.05,
    logging_steps=5,
    eval_strategy="steps",
    eval_steps=25,
    save_steps=50,
    bf16=True,
    packing=False,
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    args=args,
    train_dataset=train,
    eval_dataset=dev,
    peft_config=lora,
)
trainer.train()
trainer.save_model()
```

Run:

```bash
PYTHONPATH=. accelerate launch scripts/train_qwen_webarena_lora.py
```

If the GPU cannot handle `8192`, lower `max_seq_length` to `4096`, but expect
some AXTree context loss.

## 4. Serve the LoRA Model

Serve the adapter with an OpenAI-compatible chat endpoint. With vLLM:

```bash
pip install -U vllm

vllm serve Qwen/Qwen2.5-7B-Instruct \
  --enable-lora \
  --lora-modules hsge-qwen-webarena=outputs/lora/qwen25_7b_webarena_shopping \
  --served-model-name hsge-qwen-webarena \
  --max-model-len 8192 \
  --port 8000
```

Smoke test:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{
    "model": "hsge-qwen-webarena",
    "messages": [
      {"role": "system", "content": "End with one WebArena action in backticks."},
      {"role": "user", "content": "OBSERVATION: [1] button '\''Search'\''\nOBJECTIVE: click search"}
    ],
    "temperature": 0,
    "max_tokens": 128
  }'
```

The output should contain a parseable action such as `click [1]`.

## 5. Build Shopping-only WebArena Configs

The upstream manifest contains 187 pure shopping tasks plus a few mixed-domain
tasks. For a clean shopping-only evaluation, keep only `sites == ["shopping"]`.
`webarena-main/run.py` expects dense filenames like `config_files/0.json`,
`config_files/1.json`, and so on, so create a temporary shopping-only config
directory with dense filenames while preserving each original `task_id` inside
the JSON.

```bash
python - <<'PY'
import json
from pathlib import Path
import shutil

root = Path("webarena-main")
src = root / "config_files" / "test.raw.json"
backup = root / "config_files_all"
active = root / "config_files"

if not backup.exists():
    shutil.copytree(active, backup)

out = root / "config_files_shopping"
out.mkdir(parents=True, exist_ok=True)

tasks = json.loads(src.read_text(encoding="utf-8"))
kept = []
for dense_id, item in enumerate([t for t in tasks if t.get("sites") == ["shopping"]]):
    original_task_id = int(item["task_id"])
    (out / f"{dense_id}.json").write_text(json.dumps(item, indent=2), encoding="utf-8")
    kept.append((dense_id, original_task_id))

# Replace active config_files with the dense shopping-only set for run.py.
for p in active.glob("*.json"):
    p.unlink()
for dense_id, _ in kept:
    shutil.copy2(out / f"{dense_id}.json", active / f"{dense_id}.json")

(out / "ids.tsv").write_text(
    "\n".join(f"{dense}\t{orig}" for dense, orig in kept) + "\n",
    encoding="utf-8",
)
print({"shopping_tasks": len(kept), "run_range": f"0..{len(kept)}"})
PY
```

After evaluation, restore the original config directory if needed:

```bash
rm -rf webarena-main/config_files
cp -R webarena-main/config_files_all webarena-main/config_files
```

If you do not want to modify `webarena-main/config_files`, patch `run.py` later
to accept a config directory or explicit config list.

## 6. Configure WebArena

Follow `docs/04_webarena_runbook.md` to host the shopping site. At minimum:

```bash
export SHOPPING="http://<host>:7770"
export SHOPPING_ADMIN="http://<host>:7780/admin"
export REDDIT="todo"
export GITLAB="todo"
export MAP="todo"
export WIKIPEDIA="todo"
export HOMEPAGE="todo"
```

The exact variable names depend on upstream WebArena vs BrowserGym. For
`webarena-main`, follow its environment/config expectations; for HSGE
BrowserGym runs, use the `WA_` variables from `docs/04_webarena_runbook.md`.

Reset the shopping site before each full benchmark run. WebArena shopping is
stateful, and cart/account/order state can contaminate scores.

## 7. Run Upstream WebArena Evaluation

From `webarena-main/`, use the id-accessibility-tree prompt and point OpenAI
calls at the local server.

```bash
cd webarena-main

export OPENAI_API_KEY=dummy
export OPENAI_API_BASE=http://localhost:8000/v1

python run.py \
  --provider openai \
  --model hsge-qwen-webarena \
  --mode chat \
  --instruction_path agent/prompts/jsons/p_cot_id_actree_2s_no_na.json \
  --action_set_tag id_accessibility_tree \
  --observation_type accessibility_tree \
  --current_viewport_only \
  --temperature 0 \
  --top_p 1 \
  --max_tokens 256 \
  --max_obs_length 6000 \
  --max_steps 30 \
  --test_start_idx 0 \
  --test_end_idx 187 \
  --result_dir ../outputs/eval_qwen_webarena_shopping
```

Important compatibility note: this local `webarena-main` uses the older OpenAI
Python client style. If `OPENAI_API_BASE` is ignored, set `openai.api_base` in
`webarena-main/llms/providers/openai_utils.py` or run with an OpenAI package
version compatible with that code.

## 8. Report Results

The runner writes logs, HTML renders, traces, and `config.json` into the result
directory. Report:

- number of shopping tasks evaluated;
- average score;
- pass count and fail count;
- parsing early stops;
- repeated-action early stops;
- common failure task families.

A quick score summary can be recovered from the run log:

```bash
rg "PASS|FAIL|Average score|Early stop|Failed to parse|Same action" \
  outputs/eval_qwen_webarena_shopping -S
```

Compare at least three conditions:

1. Base `Qwen/Qwen2.5-7B-Instruct` without LoRA.
2. Qwen LoRA trained on `train_webarena.jsonl`.
3. A stronger reference model, if available, with the same prompt and task set.

## 9. Expected First-pass Limitations

Run 17 currently provides only about 199 WebArena-format examples. It has useful
search, click, fill, hover, and answer examples, but weak or missing coverage for:

- scroll-heavy product/review tasks;
- order history and account tasks;
- checkout and purchase tasks;
- refund/reorder tasks;
- price/rating/market-analysis tasks.

Use the first LoRA run to validate the full training/evaluation plumbing. For a
meaningful benchmark push, collect more successful HSGE trajectories for the
missing shopping task families, rebuild `train_webarena.jsonl`, and fine-tune
again.
