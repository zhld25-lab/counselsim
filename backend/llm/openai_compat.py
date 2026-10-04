"""OpenAI-compatible chat-completions provider.

Covers any vendor that speaks the `/chat/completions` dialect: Groq,
OpenRouter, Together, DeepSeek, Moonshot, 智谱, a local vLLM/Ollama, and
OpenAI itself. Only the base URL, the key and the model id change.

This module exposes a single entry point, `raw_call`, with exactly the same
signature and return type as the Gemini wrapper's `_raw_call`, so the rest of
the app never learns which vendor is behind it.
"""
import json
import logging
from typing import Dict, List

import httpx

import config

log = logging.getLogger("counselsim.llm")


def _to_messages(system_prompt: str, contents: List[Dict]) -> List[Dict]:
    """Perspective-converted transcript -> OpenAI `messages`.

    `common.to_contents` emits roles "model"/"user"; OpenAI calls the former
    "assistant". The system prompt becomes the leading system message.
    """
    messages: List[Dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for c in contents:
        text = c.get("text")
        if not text:
            continue
        role = "assistant" if c.get("role") == "model" else "user"
        messages.append({"role": role, "content": text})
    if len(messages) <= 1:
        messages.append({"role": "user", "content": "Begin."})
    return messages


def _post(payload: dict) -> httpx.Response:
    url = config.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    # Some routers (OpenRouter) want these; harmless everywhere else.
    if "openrouter" in config.LLM_BASE_URL:
        headers["HTTP-Referer"] = "http://localhost:8000"
        headers["X-Title"] = "CounselSim"
    return httpx.post(
        url, headers=headers, json=payload, timeout=config.LLM_TIMEOUT
    )


def raw_call(
    model: str, system_prompt: str, contents: List[Dict], json_mode: bool
) -> str:
    """One chat-completions call. Returns the assistant's text.

    Raises on transport or HTTP errors; the caller wraps them in LLMError.
    """
    payload = {
        "model": model,
        "messages": _to_messages(system_prompt, contents),
        "temperature": 0.9 if json_mode else 0.7,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    resp = _post(payload)

    # Not every model on every vendor supports response_format. Rather than
    # maintain a compatibility matrix, retry once without it - the prompts
    # already ask for bare JSON and `extract_json` copes with prose wrappers.
    if resp.status_code == 400 and json_mode:
        log.warning(
            "%s rejected response_format for %s, retrying without it",
            config.LLM_PROVIDER,
            model,
        )
        payload.pop("response_format", None)
        resp = _post(payload)

    if resp.status_code >= 400:
        detail = resp.text[:300]
        raise RuntimeError(f"HTTP {resp.status_code} from {config.LLM_PROVIDER}: {detail}")

    data = resp.json()
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected response shape: {json.dumps(data)[:300]}"
        ) from exc


def list_models() -> List[str]:
    """Model ids the key can reach. Used by tools/check_key.py."""
    url = config.LLM_BASE_URL.rstrip("/") + "/models"
    resp = httpx.get(
        url,
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
        timeout=config.LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return sorted(m["id"] for m in resp.json().get("data", []))
