import os

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer


MODEL = os.environ.get("MODEL", "Qwen/Qwen2.5-7B-Instruct")
TRAIN_FILE = os.environ.get("TRAIN_FILE", "data/sft/webarena_train.jsonl")
DEV_FILE = os.environ.get("DEV_FILE", "data/sft/webarena_dev.jsonl")
OUTPUT_DIR = os.environ.get(
    "OUTPUT_DIR", "outputs/lora/qwen25_7b_webarena_shopping"
)


tokenizer = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"


def render_chat(example):
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}


train = load_dataset("json", data_files=TRAIN_FILE, split="train").map(render_chat)
dev = load_dataset("json", data_files=DEV_FILE, split="train").map(render_chat)

use_qlora = os.environ.get("USE_QLORA", "1") != "0"
quantization_config = None
if use_qlora:
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

model = AutoModelForCausalLM.from_pretrained(
    MODEL,
    quantization_config=quantization_config,
    device_map="auto",
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
)
model.config.use_cache = False

lora = LoraConfig(
    r=int(os.environ.get("LORA_R", "32")),
    lora_alpha=int(os.environ.get("LORA_ALPHA", "64")),
    lora_dropout=float(os.environ.get("LORA_DROPOUT", "0.05")),
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ],
    task_type="CAUSAL_LM",
)

args = SFTConfig(
    output_dir=OUTPUT_DIR,
    dataset_text_field="text",
    max_seq_length=int(os.environ.get("MAX_SEQ_LENGTH", "8192")),
    num_train_epochs=float(os.environ.get("NUM_TRAIN_EPOCHS", "3")),
    per_device_train_batch_size=int(os.environ.get("TRAIN_BATCH_SIZE", "1")),
    per_device_eval_batch_size=int(os.environ.get("EVAL_BATCH_SIZE", "1")),
    gradient_accumulation_steps=int(os.environ.get("GRAD_ACCUM_STEPS", "8")),
    learning_rate=float(os.environ.get("LEARNING_RATE", "2e-4")),
    lr_scheduler_type="cosine",
    warmup_ratio=float(os.environ.get("WARMUP_RATIO", "0.05")),
    logging_steps=int(os.environ.get("LOGGING_STEPS", "5")),
    eval_strategy="steps",
    eval_steps=int(os.environ.get("EVAL_STEPS", "25")),
    save_steps=int(os.environ.get("SAVE_STEPS", "50")),
    save_total_limit=int(os.environ.get("SAVE_TOTAL_LIMIT", "2")),
    bf16=True,
    packing=False,
    gradient_checkpointing=True,
    report_to=[],
    max_steps=int(os.environ.get("MAX_STEPS", "-1")),
)

trainer = SFTTrainer(
    model=model,
    processing_class=tokenizer,
    args=args,
    train_dataset=train,
    eval_dataset=dev,
    peft_config=lora,
)
trainer.train()
trainer.save_model()
tokenizer.save_pretrained(OUTPUT_DIR)
