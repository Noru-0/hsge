import os

import torch
from datasets import load_dataset
from peft import LoraConfig, PeftModel, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer


BASE_MODEL = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-7B-Instruct")
PEFT_MODEL_PATH = os.environ.get("PEFT_MODEL_PATH", "")
TRAIN_FILE = os.environ["TRAIN_FILE"]
DEV_FILE = os.environ["DEV_FILE"]
OUTPUT_DIR = os.environ["OUTPUT_DIR"]

tokenizer_source = PEFT_MODEL_PATH or BASE_MODEL
tokenizer = AutoTokenizer.from_pretrained(tokenizer_source, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"


def render_chat(example):
    return {
        "text": tokenizer.apply_chat_template(
            example["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )
    }


train = load_dataset("json", data_files=TRAIN_FILE, split="train").map(render_chat)
dev = load_dataset("json", data_files=DEV_FILE, split="train").map(render_chat)

bnb = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

peft_config = None
if PEFT_MODEL_PATH:
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    base_model = prepare_model_for_kbit_training(
        base_model, use_gradient_checkpointing=True
    )
    model = PeftModel.from_pretrained(
        base_model,
        PEFT_MODEL_PATH,
        is_trainable=True,
    )
else:
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    peft_config = LoraConfig(
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

model.config.use_cache = False

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
    peft_config=peft_config,
)
trainer.train()
trainer.save_model()
tokenizer.save_pretrained(OUTPUT_DIR)
