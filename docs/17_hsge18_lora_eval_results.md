# HSGE-18 Qwen LoRA Fine-Tune and Shopping Eval

This note records the latest two-stage LoRA fine-tune and WebArena Shopping evaluation run for the HSGE action-format data.

## Training Data

The model was trained from `Qwen/Qwen2.5-7B-Instruct` using two HSGE JSON action datasets:

- `training/train-single-18.jsonl`
- `training/train-multi-18.jsonl`

Training order:

1. Fine-tune on single-turn examples.
2. Continue the same LoRA adapter on multi-turn examples.

The training data uses HSGE-style JSON assistant messages, for example:

```json
{"thought": "...", "action": "click('1424')"}
```

These actions are not native WebArena bracket actions, so evaluation uses a prompt/action adapter that converts HSGE actions to WebArena actions.

## Local Artifacts

Downloaded LoRA adapter:

```text
outputs/lora/qwen25_7b_hsge18_singleturn_multiturn
```

Key files:

```text
adapter_config.json
adapter_model.safetensors
tokenizer.json
tokenizer_config.json
training_args.bin
```

Downloaded evaluation outputs:

```text
outputs/eval_hsge18_shopping_vllm
logs/eval_hsge18_shopping_vllm.clean.log
```

## Evaluation Setup

The evaluation used vLLM serving the base Qwen model plus the LoRA adapter:

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --host 127.0.0.1 \
  --port 8000 \
  --max-model-len 8192 \
  --enable-lora \
  --max-lora-rank 64 \
  --lora-modules hsge-qwen-hsge18=/workspace/hsge/outputs/lora/qwen25_7b_hsge18_singleturn_multiturn
```

WebArena was run against the Cloudflare-hosted Shopping domain:

```text
https://infectious-plasma-gem-officials.trycloudflare.com
```

The eval prompt was:

```text
webarena-main/agent/prompts/jsons/p_hsge_json_id_actree.json
```

Important patches for this run:

- `JsonActionPromptConstructor` parses JSON model outputs and converts HSGE actions such as `click('1424')` to WebArena actions such as `click [1424]`.
- The HSGE JSON prompt metadata includes `action_splitter` so WebArena can render invalid/none actions without crashing.
- The WebArena fuzzy evaluator uses `EVAL_MODEL=hsge-qwen-hsge18` instead of the hardcoded `gpt-4-1106-preview`.

## Eval Command Shape

```bash
export OPENAI_API_BASE="http://127.0.0.1:8000/v1"
export OPENAI_API_KEY="EMPTY"
export EVAL_MODEL="hsge-qwen-hsge18"

python run.py \
  --provider openai \
  --model hsge-qwen-hsge18 \
  --mode chat \
  --instruction_path agent/prompts/jsons/p_hsge_json_id_actree.json \
  --test_config_base_dir config_files_shopping \
  --test_start_idx 0 \
  --test_end_idx 187 \
  --result_dir ../outputs/eval_hsge18_shopping_vllm \
  --max_steps 30 \
  --temperature 0 \
  --top_p 1.0 \
  --max_tokens 128
```

## Results

Final WebArena Shopping result:

```text
Total tasks:      187
Scored tasks:     184
Pass:              26
Fail:             158
Unhandled errors:   3
Average score:      0.14130434782608695
```

Interpreting the score:

- WebArena average over scored tasks: `26 / 184 = 14.13%`.
- If unhandled errors are counted as failures: `26 / 187 = 13.90%`.

The 3 unhandled-error tasks were:

```text
7.json    page load timeout
124.json  evaluator assertion error
129.json  temporary DNS failure to the Cloudflare Shopping URL
```

## Useful Local Checks

Count pass/fail from the downloaded log:

```bash
grep -c "\[Result\] (PASS)" logs/eval_hsge18_shopping_vllm.clean.log
grep -c "\[Result\] (FAIL)" logs/eval_hsge18_shopping_vllm.clean.log
grep -c "\[Result\]" logs/eval_hsge18_shopping_vllm.clean.log
```

Check downloaded result assets:

```bash
find outputs/eval_hsge18_shopping_vllm -maxdepth 1 -name "render_*.html" | wc -l
find outputs/eval_hsge18_shopping_vllm/traces -maxdepth 1 -name "*.zip" | wc -l
```
