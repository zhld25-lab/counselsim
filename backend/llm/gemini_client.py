"""The app's single door to whatever LLM is configured.

Despite the historical file name this is provider-agnostic: `_raw_call`
dispatches to the google-genai SDK for Gemini, or to `openai_compat` for any
vendor speaking the OpenAI /chat/completions dialect (Groq, OpenRouter, ...).

Responsibilities:
  * build a call from (system prompt, perspective-converted transcript)
  * enforce a hard timeout
  * parse JSON, retrying once, then degrade gracefully
  * fall back to the offline mock engine when no API key is configured
"""
import concurrent.futures
import json
import logging
import re
from typing import Callable, Dict, List, Optional

import config

log = logging.getLogger("counselsim.llm")

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=8)
_client = None


class LLMError(RuntimeError):
    pass


def _get_client():
    global _client
    if _client is None:
        from google import genai  # imported lazily so mock mode needs no SDK

        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _raw_call(model: str, system_prompt: str, contents: List[Dict], json_mode: bool):
    """Dispatch to whichever vendor config selected."""
    if config.LLM_PROVIDER != "gemini":
        from llm import openai_compat

        return openai_compat.raw_call(model, system_prompt, contents, json_mode)
    return _gemini_call(model, system_prompt, contents, json_mode)


def _gemini_call(model: str, system_prompt: str, contents: List[Dict], json_mode: bool):
    from google.genai import types

    client = _get_client()
    parts = [
        types.Content(
            role="model" if c["role"] == "model" else "user",
            parts=[types.Part.from_text(text=c["text"])],
        )
        for c in contents
        if c.get("text")
    ]
    if not parts:
        parts = [types.Content(role="user", parts=[types.Part.from_text(text="Begin.")])]

    cfg = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.9 if json_mode else 0.7,
    )
    if json_mode:
        cfg.response_mime_type = "application/json"

    resp = client.models.generate_content(model=model, contents=parts, config=cfg)
    return (resp.text or "").strip()


def call_text(
    model: str,
    system_prompt: str,
    contents: List[Dict],
    json_mode: bool = True,
) -> str:
    """One Gemini call with a hard timeout. Raises LLMError on failure."""
    future = _EXECUTOR.submit(_raw_call, model, system_prompt, contents, json_mode)
    try:
        return future.result(timeout=config.LLM_TIMEOUT)
    except concurrent.futures.TimeoutError:
        raise LLMError(f"LLM call timed out after {config.LLM_TIMEOUT:.0f}s")
    except Exception as exc:  # noqa: BLE001 - surfaced to the frontend
        raise LLMError(f"LLM call failed: {exc}") from exc


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    candidate = text.strip()
    match = _FENCE.search(candidate)
    if match:
        candidate = match.group(1).strip()
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    # last resort: grab the outermost {...}
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        try:
            value = json.loads(candidate[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def call_json(
    model: str,
    system_prompt: str,
    contents: List[Dict],
    mock: Optional[Callable[[], dict]] = None,
    fallback: Optional[Callable[[str], dict]] = None,
) -> dict:
    """Call the model and return parsed JSON.

    * mock mode -> `mock()` is used instead of the network
    * a bad parse is retried once with a stricter nudge
    * if it still fails, `fallback(raw_text)` decides what to do
    """
    if config.USE_MOCK:
        if mock is None:
            raise LLMError("Mock mode is on but this call has no mock implementation")
        return mock()

    raw = call_text(model, system_prompt, contents)
    parsed = extract_json(raw)
    if parsed is not None:
        return parsed

    log.warning("JSON parse failed, retrying once. Raw: %.200s", raw)
    retry_contents = contents + [
        {
            "role": "user",
            "text": "Your previous reply was not valid JSON. Reply again with "
            "ONLY the JSON object, no prose and no code fences.",
        }
    ]
    raw2 = call_text(model, system_prompt, retry_contents)
    parsed = extract_json(raw2)
    if parsed is not None:
        return parsed

    if fallback is not None:
        return fallback(raw2 or raw)
    raise LLMError("Model did not return valid JSON")
