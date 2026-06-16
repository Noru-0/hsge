#!/usr/bin/env python3
"""
SFT fine-tune Qwen2.5-7B-Instruct on HSGE web-agent trajectory data.

Usage:
    python train_qwen_sft.py --data train.jsonl [--lora] [--no-wandb]

Data format (from build_sft_dataset.py):
    {"messages": [{"role":"system","content":...}, {"role":"user","content":...},
                  {"role":"assistant","content":...}], "difficulty": int, ...}

Approach:
    - LoRA (default): fits on single 24 GB GPU (RTX 3090/4090, A5000)
    - Full SFT (--full): needs 48+ GB GPU (A6000, 2x3090)
    - DataCollatorForCompletionOnlyLM: train only on assistant tokens
"""
from __future__ import annotations

import argparse
import os
import sys
import math

import torch
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from transformers.utils.import_utils import is_torch_bf16_gpu_available
from trl import SFTConfig, SFTTrainer
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
RESPONSE_TEMPLATE = "<|im_start|>assistant\n"       # Qwen2.5 chat template marker
MAX_SEQ_LENGTH = 24000                               # ~24K tokens (fits long AXTree pages, matching Go-Browse)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Fine-tune Qwen2.5-7B for web agent")
    p.add_argument("--data", required=True, help="Path to train.jsonl (messages format)")
    p.add_argument("--output", default="outputs/qwen_7b_hsge_agent", help="Output dir")
    p.add_argument("--lora", action="store_true", default=True,
                   help="Use LoRA (default: True, fits 24 GB GPU)")
    p.add_argument("--full", dest="lora", action="store_false",
                   help="Full SFT (needs 48+ GB GPU)")
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--batch-size", type=int, default=1,
                   help="Per-device batch size")
    p.add_argument("--grad-accum", type=int, default=4,
                   help="Gradient accumulation steps")
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--no-wandb", action="store_true", help="Disable W&B logging")
    p.add_argument("--wandb-project", default="hsge-agent")
    p.add_argument("--val-split", type=float, default=0.05,
                   help="Validation split fraction (0 = no split)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Data loading & formatting
# ---------------------------------------------------------------------------
def load_and_format_dataset(data_path: str, tokenizer, val_split: float = 0.05):
    """Load messages-format jsonl and apply Qwen2.5 chat template to produce 'text'."""
    ds = load_dataset("json", data_files=data_path, split="train")

    # If val_split > 0, split off a validation set
    if val_split > 0:
        ds = ds.train_test_split(test_size=val_split, seed=42)
        train_ds, val_ds = ds["train"], ds["test"]
    else:
        train_ds = ds
        val_ds = None

    def _apply_template(examples):
        texts = [
            tokenizer.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=False
            )
            for msgs in examples["messages"]
        ]
        return {"text": texts}

    train_ds = train_ds.map(
        _apply_template, batched=True, remove_columns=train_ds.column_names
    )
    if val_ds is not None:
        val_ds = val_ds.map(
            _apply_template, batched=True, remove_columns=val_ds.column_names
        )

    return train_ds, val_ds


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()

    # ---- W&B ----
    if not args.no_wandb:
        os.environ.setdefault("WANDB_PROJECT", args.wandb_project)
    else:
        os.environ["WANDB_DISABLED"] = "true"

    use_bf16 = is_torch_bf16_gpu_available()
    dtype = torch.bfloat16 if use_bf16 else torch.float16

    print(f"Model: {MODEL_ID}")
    print(f"Data: {args.data}")
    print(f"LoRA: {args.lora}  |  Epochs: {args.epochs}  |  "
          f"Batch: {args.batch_size} x {args.grad_accum}  |  LR: {args.lr}")
    print(f"Precision: {'bf16' if use_bf16 else 'fp16'}  |  "
          f"Max seq len: {MAX_SEQ_LENGTH}  |  GPU count: {torch.cuda.device_count()}")
    for i in range(torch.cuda.device_count()):
        mem = torch.cuda.get_device_properties(i).total_mem / 1024**3
        print(f"  GPU {i}: {torch.cuda.get_device_name(i)} ({mem:.1f} GB)")

    # ---- Tokenizer ----
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    # Qwen2.5 uses <|im_start|> and <|im_end|>; ensure pad token is set
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # ---- Data collator (train only assistant completions) ----
    collator = DataCollatorForCompletionOnlyLM(
        response_template=RESPONSE_TEMPLATE,
        tokenizer=tokenizer,
    )

    # ---- Load & format dataset ----
    train_ds, val_ds = load_and_format_dataset(args.data, tokenizer, args.val_split)
    print(f"Train examples: {len(train_ds)}")
    if val_ds is not None:
        print(f"Val examples: {len(val_ds)}")

    # ---- SFTConfig ----
    effective_batch = args.batch_size * args.grad_accum * max(torch.cuda.device_count(), 1)
    sft_config = SFTConfig(
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        warmup_steps=100,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        fp16=not use_bf16,
        bf16=use_bf16,
        logging_steps=5,
        optim="paged_adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        seed=3407,
        output_dir=args.output,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=2,
        max_seq_length=MAX_SEQ_LENGTH,
        packing=False,                       # keep examples separate
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        dataset_num_proc=4,
        report_to=[] if args.no_wandb else ["wandb"],
        dataloader_num_workers=2,
        eval_strategy="steps" if val_ds is not None else "no",
        eval_steps=200 if val_ds is not None else None,
    )

    # ---- Model loading ----
    if args.lora:
        # 4-bit quantized base + LoRA adapters → fits 24 GB GPU
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=dtype,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
            attn_implementation="flash_attention_2",
            torch_dtype=dtype,
        )
        # Prepare for k-bit training
        from peft import prepare_model_for_kbit_training
        model = prepare_model_for_kbit_training(model)

        lora_config = LoraConfig(
            r=16,
            lora_alpha=32,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
            lora_dropout=0.05,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()
    else:
        # Full SFT — needs 48+ GB
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            device_map="auto",
            trust_remote_code=True,
            attn_implementation="flash_attention_2",
            torch_dtype=dtype,
        )

    # ---- Trainer ----
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=collator,
        args=sft_config,
    )

    # ---- Train ----
    print(f"\nEffective batch size: {effective_batch}")
    print(f"Total steps: ~{len(train_ds) * args.epochs // effective_batch}")
    print("Starting training...\n")
    trainer.train()

    # ---- Save ----
    final_path = os.path.join(args.output, "final_checkpoint")
    trainer.save_model(final_path)
    tokenizer.save_pretrained(final_path)
    print(f"\nModel saved to {final_path}")


if __name__ == "__main__":
    main()
