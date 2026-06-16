#!/usr/bin/env python3
"""
Simple OpenAI-compatible server for Qwen2.5-7B + LoRA adapter.
Serves /v1/chat/completions and /v1/models endpoints.

Usage:
    python model_server.py --base "Qwen/Qwen2.5-7B-Instruct" \
        --lora /root/training/outputs/qwen_7b_hsge_agent/final_checkpoint \
        --lora-name hsge-agent --port 8000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel


# ---- Globals ----
MODEL = None
TOKENIZER = None
BASE_MODEL = None  # base model without LoRA
LORA_MODELS: dict[str, PeftModel] = {}
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# ---- Pydantic models matching OpenAI API ----
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: float = 0.0
    max_tokens: int = 512
    top_p: float = 1.0
    stop: Optional[list[str]] = None

class ModelData(BaseModel):
    id: str
    object: str = "model"
    owned_by: str = "hsge"

class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelData]


# ---- App ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup."""
    global MODEL, TOKENIZER, BASE_MODEL, LORA_MODELS
    print(f"[server] Loading base model: {app.state.base_model_id}")
    print(f"[server] Device: {DEVICE}")

    TOKENIZER = AutoTokenizer.from_pretrained(
        app.state.base_model_id, trust_remote_code=True
    )
    if TOKENIZER.pad_token is None:
        TOKENIZER.pad_token = TOKENIZER.eos_token

    BASE_MODEL = AutoModelForCausalLM.from_pretrained(
        app.state.base_model_id,
        torch_dtype=torch.bfloat16 if DEVICE == "cuda" else torch.float32,
        device_map="auto",
        trust_remote_code=True,
    )
    MODEL = BASE_MODEL  # default: base model

    # Load LoRA adapters
    if app.state.lora_path and app.state.lora_name:
        print(f"[server] Loading LoRA: {app.state.lora_name} from {app.state.lora_path}")
        lora_model = PeftModel.from_pretrained(
            BASE_MODEL, app.state.lora_path, adapter_name=app.state.lora_name
        )
        LORA_MODELS[app.state.lora_name] = lora_model
        print(f"[server] LoRA loaded: {app.state.lora_name}")

    print(f"[server] Ready. Models: {list_models()}")
    yield
    print("[server] Shutting down")


app = FastAPI(title="HSGE Model Server", lifespan=lifespan)


def list_models() -> list[str]:
    models = [app.state.base_model_id.split("/")[-1]]
    models.extend(LORA_MODELS.keys())
    return models


def get_model(model_name: str):
    """Get the right model based on name."""
    # Strip any path prefix
    short = model_name.split("/")[-1] if "/" in model_name else model_name
    if short in LORA_MODELS:
        return LORA_MODELS[short], short
    return BASE_MODEL, "base"


def generate_response(messages: list[Message], model, tokenizer,
                      temperature: float, max_tokens: int,
                      top_p: float, stop: list[str] | None) -> str:
    """Generate text using the chat template."""
    # Convert to dict format for apply_chat_template
    msgs = [{"role": m.role, "content": m.content} for m in messages]
    prompt = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)

    inputs = tokenizer(prompt, return_tensors="pt").to(DEVICE)

    gen_kwargs = dict(
        max_new_tokens=max_tokens,
        do_sample=temperature > 0,
        temperature=temperature if temperature > 0 else 1.0,
        top_p=top_p,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    if stop:
        gen_kwargs["stop_strings"] = stop

    with torch.no_grad():
        outputs = model.generate(**inputs, **gen_kwargs)

    # Decode only the new tokens
    generated = outputs[0][inputs["input_ids"].shape[1]:]
    response = tokenizer.decode(generated, skip_special_tokens=True)
    return response.strip()


@app.get("/v1/models")
async def get_models():
    data = [ModelData(id=name) for name in list_models()]
    return ModelList(data=data)


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    try:
        model, model_key = get_model(req.model)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Model not found: {req.model}")

    t0 = time.time()
    content = generate_response(
        req.messages, model, TOKENIZER,
        req.temperature, req.max_tokens, req.top_p, req.stop
    )
    elapsed = time.time() - t0
    print(f"[server] {model_key} | {len(req.messages)} msgs | {len(content)} chars | {elapsed:.1f}s")

    return JSONResponse({
        "id": f"chatcmpl-{os.urandom(4).hex()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })


@app.get("/health")
async def health():
    return {"status": "ok", "models": list_models()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--lora", default=None, help="Path to LoRA adapter")
    parser.add_argument("--lora-name", default="hsge-agent")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    app.state.base_model_id = args.base
    app.state.lora_path = args.lora
    app.state.lora_name = args.lora_name

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
