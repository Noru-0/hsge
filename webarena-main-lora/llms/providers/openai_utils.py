"""Tools to generate from OpenAI prompts.
Adopted from https://github.com/zeno-ml/zeno-build/
Rewritten for openai >= 1.0 (supports custom base_url via OPENAI_BASE_URL).
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from typing import Any

import aiolimiter
import openai
from tqdm.asyncio import tqdm_asyncio


# ---- Client factory (supports custom base_url for vLLM etc.) ----
def _get_client() -> openai.OpenAI:
    return openai.OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", "not-needed"),
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        organization=os.environ.get("OPENAI_ORGANIZATION", None),
    )


def _get_async_client() -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", "not-needed"),
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        organization=os.environ.get("OPENAI_ORGANIZATION", None),
    )


def retry_with_exponential_backoff(  # type: ignore
    func,
    initial_delay: float = 1,
    exponential_base: float = 2,
    jitter: bool = True,
    max_retries: int = 3,
    errors: tuple[Any] = (openai.RateLimitError,),
):
    """Retry a function with exponential backoff."""

    def wrapper(*args, **kwargs):  # type: ignore
        num_retries = 0
        delay = initial_delay

        while True:
            try:
                return func(*args, **kwargs)
            except errors as e:
                num_retries += 1
                if num_retries > max_retries:
                    raise Exception(
                        f"Maximum number of retries ({max_retries}) exceeded."
                    )
                delay *= exponential_base * (1 + jitter * random.random())
                print(f"Retrying in {delay} seconds.")
                time.sleep(delay)
            except Exception as e:
                raise e

    return wrapper


# ---------------------------------------------------------------------------
# Completion API (legacy, rarely used by WebArena chat agent)
# ---------------------------------------------------------------------------

async def _throttled_openai_completion_acreate(
    engine: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    top_p: float,
    limiter: aiolimiter.AsyncLimiter,
) -> dict[str, Any]:
    client = _get_async_client()
    async with limiter:
        for _ in range(3):
            try:
                resp = await client.completions.create(
                    model=engine,
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                )
                return {"choices": [{"text": resp.choices[0].text}]}
            except openai.RateLimitError:
                logging.warning("OpenAI API rate limit exceeded. Sleeping for 10 seconds.")
                await asyncio.sleep(10)
            except openai.APIError as e:
                logging.warning(f"OpenAI API error: {e}")
                break
        return {"choices": [{"text": ""}]}


async def agenerate_from_openai_completion(
    prompts: list[str],
    engine: str,
    temperature: float,
    max_tokens: int,
    top_p: float,
    context_length: int,
    requests_per_minute: int = 300,
) -> list[str]:
    """Generate from OpenAI Completion API (async batch)."""
    limiter = aiolimiter.AsyncLimiter(requests_per_minute)
    async_responses = [
        _throttled_openai_completion_acreate(
            engine=engine, prompt=prompt, temperature=temperature,
            max_tokens=max_tokens, top_p=top_p, limiter=limiter,
        )
        for prompt in prompts
    ]
    responses = await tqdm_asyncio.gather(*async_responses)
    return [x["choices"][0]["text"] for x in responses]


@retry_with_exponential_backoff
def generate_from_openai_completion(
    prompt: str,
    engine: str,
    temperature: float,
    max_tokens: int,
    top_p: float,
    context_length: int,
    stop_token: str | None = None,
) -> str:
    client = _get_client()
    resp = client.completions.create(
        model=engine,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stop=[stop_token] if stop_token else None,
    )
    return resp.choices[0].text


# ---------------------------------------------------------------------------
# Chat Completion API (primary path for WebArena)
# ---------------------------------------------------------------------------

async def _throttled_openai_chat_completion_acreate(
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    top_p: float,
    limiter: aiolimiter.AsyncLimiter,
) -> dict[str, Any]:
    client = _get_async_client()
    async with limiter:
        for _ in range(3):
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                )
                return {"choices": [{"message": {"content": resp.choices[0].message.content}}]}
            except openai.RateLimitError:
                logging.warning("OpenAI API rate limit exceeded. Sleeping for 10 seconds.")
                await asyncio.sleep(10)
            except asyncio.exceptions.TimeoutError:
                logging.warning("OpenAI API timeout. Sleeping for 10 seconds.")
                await asyncio.sleep(10)
            except openai.APIError as e:
                logging.warning(f"OpenAI API error: {e}")
                break
        return {"choices": [{"message": {"content": ""}}]}


async def agenerate_from_openai_chat_completion(
    messages_list: list[list[dict[str, str]]],
    engine: str,
    temperature: float,
    max_tokens: int,
    top_p: float,
    context_length: int,
    requests_per_minute: int = 300,
) -> list[str]:
    """Generate from OpenAI Chat Completion API (async batch)."""
    limiter = aiolimiter.AsyncLimiter(requests_per_minute)
    async_responses = [
        _throttled_openai_chat_completion_acreate(
            model=engine, messages=message, temperature=temperature,
            max_tokens=max_tokens, top_p=top_p, limiter=limiter,
        )
        for message in messages_list
    ]
    responses = await tqdm_asyncio.gather(*async_responses)
    return [x["choices"][0]["message"]["content"] for x in responses]


@retry_with_exponential_backoff
def generate_from_openai_chat_completion(
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    top_p: float,
    context_length: int,
    stop_token: str | None = None,
) -> str:
    client = _get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stop=[stop_token] if stop_token else None,
    )
    return resp.choices[0].message.content


@retry_with_exponential_backoff
# debug only
def fake_generate_from_openai_chat_completion(
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    top_p: float,
    context_length: int,
    stop_token: str | None = None,
) -> str:
    answer = "Let's think step-by-step. This page shows a search box with ID [164]. I can type the query into it. In summary, the next action I will perform is ```type [164] [N/A] [1]```"
    return answer
