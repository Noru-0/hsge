import os
import time
import uuid

import torch
from flask import Flask, jsonify, request
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer, BitsAndBytesConfig


ADAPTER_DIR = os.environ.get(
    "ADAPTER_DIR", "outputs/lora/qwen25_7b_webarena_shopping"
)
SERVED_MODEL_NAME = os.environ.get("SERVED_MODEL_NAME", "hsge-qwen-webarena")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

app = Flask(__name__)

tokenizer = AutoTokenizer.from_pretrained(ADAPTER_DIR, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

bnb = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

model = AutoPeftModelForCausalLM.from_pretrained(
    ADAPTER_DIR,
    quantization_config=bnb,
    device_map="auto",
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
)
model.eval()


def _apply_stop(text, stop):
    if isinstance(stop, str):
        stop = [stop]
    if not stop:
        return text
    cut = len(text)
    for marker in stop:
        if marker:
            idx = text.find(marker)
            if idx >= 0:
                cut = min(cut, idx)
    return text[:cut]


@app.get("/v1/models")
def models():
    return jsonify(
        {
            "object": "list",
            "data": [
                {
                    "id": SERVED_MODEL_NAME,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "local",
                }
            ],
        }
    )


@app.post("/v1/chat/completions")
def chat_completions():
    payload = request.get_json(force=True)
    messages = payload.get("messages", [])
    max_tokens = int(payload.get("max_tokens", 256))
    temperature = float(payload.get("temperature", 0) or 0)
    top_p = float(payload.get("top_p", 1) or 1)
    stop = payload.get("stop")

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    generate_kwargs = {
        "max_new_tokens": max_tokens,
        "pad_token_id": tokenizer.eos_token_id,
        "eos_token_id": tokenizer.eos_token_id,
    }
    if temperature > 0:
        generate_kwargs.update(
            do_sample=True,
            temperature=temperature,
            top_p=top_p,
        )
    else:
        generate_kwargs["do_sample"] = False

    with torch.inference_mode():
        outputs = model.generate(**inputs, **generate_kwargs)
    new_tokens = outputs[0, inputs["input_ids"].shape[-1] :]
    content = tokenizer.decode(new_tokens, skip_special_tokens=True)
    content = _apply_stop(content, stop)

    return jsonify(
        {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": SERVED_MODEL_NAME,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": int(inputs["input_ids"].shape[-1]),
                "completion_tokens": int(new_tokens.shape[-1]),
                "total_tokens": int(inputs["input_ids"].shape[-1] + new_tokens.shape[-1]),
            },
        }
    )


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, threaded=False)
