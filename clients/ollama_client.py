"""Ollama LLM client — async singleton with retries and structured output."""
import asyncio
import json
import os
from typing import Any

import httpx

from config import logger

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))

# Model shortcuts from env
MODEL_SMALL = os.getenv("OLLAMA_MODEL_SMALL", "gemma3:4b")
MODEL_MEDIUM = os.getenv("OLLAMA_MODEL_MEDIUM", "gemma3:12b")
MODEL_LARGE = os.getenv("OLLAMA_MODEL_LARGE", "gemma3:27b")


async def ollama_chat(
    model: str,
    messages: list[dict],
    schema: dict | None = None,
    temperature: float = 0.0,
) -> dict:
    """
    Call Ollama chat API. If schema is provided, uses structured output (format field).
    Returns parsed dict from content.
    Retries MAX_RETRIES times on timeout or invalid schema.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if schema:
        payload["format"] = schema

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                r = await client.post(f"{OLLAMA_BASE}/api/chat", json=payload)
                r.raise_for_status()
                content = r.json()["message"]["content"]
                if schema:
                    return json.loads(content)
                return {"text": content}
        except Exception as e:
            last_error = e
            logger.warning(f"Ollama attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)

    raise RuntimeError(f"Ollama failed after {MAX_RETRIES} attempts: {last_error}")


async def ollama_generate(
    model: str,
    prompt: str,
    schema: dict | None = None,
    temperature: float = 0.0,
) -> dict:
    """
    Call Ollama generate API (non-chat). Simpler interface for single-prompt tasks.
    """
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if schema:
        payload["format"] = schema

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                r = await client.post(f"{OLLAMA_BASE}/api/generate", json=payload)
                r.raise_for_status()
                content = r.json().get("response", "{}")
                if schema:
                    return json.loads(content)
                return {"text": content}
        except Exception as e:
            last_error = e
            logger.warning(f"Ollama generate attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)

    raise RuntimeError(f"Ollama generate failed after {MAX_RETRIES} attempts: {last_error}")
