#!/usr/bin/env python3
"""Merge a LoRA adapter into a standalone checkpoint using peft directly.

Same result as `llamafactory-cli export training/merge_lora_all.yaml`, without
needing LLaMA-Factory on the box. Use this when a machine only serves/evaluates
(the eval box has no train venv: setting one up is the slowest and most
fragile part of vast_setup.sh, and merging needs none of it).

    python training/merge_lora_peft.py \
        /workspace/models/Qwen3.5-9B \
        /workspace/saves/qwen35-9b-lora-all \
        /workspace/models/Qwen3.5-9B-all

Runs on CPU: 9B in bf16 is ~19 GB of RAM and leaves the GPU free for vLLM.
"""
import json
import shutil
import sys
from pathlib import Path

import torch
from peft import PeftModel
from safetensors.torch import load_file
from transformers import AutoModelForImageTextToText, AutoTokenizer

# The multi-token-prediction head is a vLLM speculative-decoding draft module
# that transformers does not model, so it never survives a merge. Harmless
# unless MTP speculative decoding is enabled (serve_vllm.sh does not).
_DROPPABLE_PREFIXES = ("mtp.",)

BASE = sys.argv[1] if len(sys.argv) > 1 else "/workspace/models/Qwen3.5-9B"
ADAPTER = sys.argv[2] if len(sys.argv) > 2 else "/workspace/saves/qwen35-9b-lora-all"
OUT = sys.argv[3] if len(sys.argv) > 3 else "/workspace/models/Qwen3.5-9B-all"

print(f"base={BASE}\nadapter={ADAPTER}\nout={OUT}", flush=True)

# Qwen3.5-9B is Qwen3_5ForConditionalGeneration (text tower + vision tower).
# AutoModelForCausalLM would load only the text tower, and saving that back out
# writes a Qwen3_5TextConfig with the 348 vision tensors dropped -- vLLM then
# refuses the checkpoint ("Expected Qwen3_5Config, found Qwen3_5TextConfig").
# The LoRA only touches text-decoder modules, but the wrapper must survive.
model = AutoModelForImageTextToText.from_pretrained(
    BASE, dtype=torch.bfloat16, device_map="cpu", trust_remote_code=True)
print(f"base loaded: {type(model).__name__}", flush=True)

model = PeftModel.from_pretrained(model, ADAPTER, device_map="cpu")

# target_modules are bare suffixes (q_proj, o_proj, ...), so peft could also
# match same-named modules in the vision tower -- those have no saved weights
# and would be silently randomly initialized. Assert every attached LoRA site
# is one the adapter file actually carries weights for.
saved = {k.split(".lora_")[0].removeprefix("base_model.model.")
         for k in load_file(str(Path(ADAPTER) / "adapter_model.safetensors"))}
attached = {name.removeprefix("base_model.model.")
            for name, mod in model.named_modules() if hasattr(mod, "lora_A")}
unbacked = attached - saved
assert not unbacked, f"{len(unbacked)} LoRA sites have no saved weights: {sorted(unbacked)[:5]}"
print(f"lora sites: {len(attached)} attached, all backed by saved weights", flush=True)

model = model.merge_and_unload()
model.save_pretrained(OUT, max_shard_size="5GB", safe_serialization=True)

# The tokenizer/chat template come from the adapter dir, not the base model:
# these are the exact files training used, and the checkpoint's chat_template
# still honours enable_thinking (the eval client sends enable_thinking=False).
AutoTokenizer.from_pretrained(ADAPTER, trust_remote_code=True).save_pretrained(OUT)
for extra in ("chat_template.jinja", "processor_config.json"):
    src = Path(ADAPTER) / extra
    if src.exists():
        shutil.copy(src, Path(OUT) / extra)

# Fail here rather than 10 minutes into a vLLM startup.
cfg = json.loads((Path(OUT) / "config.json").read_text())
assert cfg.get("architectures") == ["Qwen3_5ForConditionalGeneration"], cfg.get("architectures")
assert "vision_config" in cfg and "text_config" in cfg, sorted(cfg)
weights = lambda d: set(json.loads(  # noqa: E731
    (Path(d) / "model.safetensors.index.json").read_text())["weight_map"])
lost = {k for k in weights(BASE) - weights(OUT)
        if not k.startswith(_DROPPABLE_PREFIXES)}
assert not lost, f"{len(lost)} non-MTP tensors lost in merge: {sorted(lost)[:5]}"
print(f"config OK, {len(weights(OUT))} tensors "
      f"({len(weights(BASE)) - len(weights(OUT))} MTP tensors dropped)", flush=True)
print("DONE", flush=True)
