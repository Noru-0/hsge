#!/usr/bin/env python3
"""Merge the Qwen2.5-7B-Instruct LoRA adapter into a standalone checkpoint
using peft directly, for a box that only serves/evaluates (no LLaMA-Factory
needed). Adapted from merge_lora_peft.py, which handles Qwen3.5-9B's
vision-tower wrapper -- Qwen2.5-7B-Instruct is a plain text-only
Qwen2ForCausalLM, so this is the standard peft merge path with no
AutoModelForImageTextToText workaround needed.

    python training/merge_lora_peft_qwen25.py \
        /workspace/models/Qwen2.5-7B-Instruct \
        /workspace/saves/qwen25-7b-lora-merged-v1 \
        /workspace/models/Qwen2.5-7B-Instruct-merged-v1

Runs on CPU: 7B in bf16 is ~15 GB of RAM and leaves the GPU free for vLLM.
"""
import json
import shutil
import sys
from pathlib import Path

import torch
from peft import PeftModel
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = sys.argv[1] if len(sys.argv) > 1 else "/workspace/models/Qwen2.5-7B-Instruct"
ADAPTER = sys.argv[2] if len(sys.argv) > 2 else "/workspace/saves/qwen25-7b-lora-merged-v1"
OUT = sys.argv[3] if len(sys.argv) > 3 else "/workspace/models/Qwen2.5-7B-Instruct-merged-v1"

print(f"base={BASE}\nadapter={ADAPTER}\nout={OUT}", flush=True)

model = AutoModelForCausalLM.from_pretrained(
    BASE, dtype=torch.bfloat16, device_map="cpu", trust_remote_code=True)
print(f"base loaded: {type(model).__name__}", flush=True)

model = PeftModel.from_pretrained(model, ADAPTER, device_map="cpu")

# Same sanity check as merge_lora_peft.py: assert every attached LoRA site is
# one the adapter file actually carries weights for (target_modules are bare
# suffixes, so a mismatch would silently randomly-initialize a site instead
# of erroring).
saved = {k.split(".lora_")[0].removeprefix("base_model.model.")
         for k in load_file(str(Path(ADAPTER) / "adapter_model.safetensors"))}
attached = {name.removeprefix("base_model.model.")
            for name, mod in model.named_modules() if hasattr(mod, "lora_A")}
unbacked = attached - saved
assert not unbacked, f"{len(unbacked)} LoRA sites have no saved weights: {sorted(unbacked)[:5]}"
print(f"lora sites: {len(attached)} attached, all backed by saved weights", flush=True)

model = model.merge_and_unload()
model.save_pretrained(OUT, max_shard_size="5GB", safe_serialization=True)

# Tokenizer/chat template from the adapter dir (the exact files training used).
AutoTokenizer.from_pretrained(ADAPTER, trust_remote_code=True).save_pretrained(OUT)
for extra in ("chat_template.jinja",):
    src = Path(ADAPTER) / extra
    if src.exists():
        shutil.copy(src, Path(OUT) / extra)

# Fail here rather than 10 minutes into a vLLM startup.
cfg = json.loads((Path(OUT) / "config.json").read_text())
assert cfg.get("architectures") == ["Qwen2ForCausalLM"], cfg.get("architectures")
weights = lambda d: set(json.loads(  # noqa: E731
    (Path(d) / "model.safetensors.index.json").read_text())["weight_map"])
lost = weights(BASE) - weights(OUT)
assert not lost, f"{len(lost)} tensors lost in merge: {sorted(lost)[:5]}"
print(f"config OK, {len(weights(OUT))} tensors, none lost", flush=True)
print("DONE", flush=True)
