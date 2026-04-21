"""
Shared LLM client utilities for DebateTrader.

This module provides a small provider-agnostic wrapper so agent modules can
request structured generations without duplicating provider setup logic.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional convenience dependency
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_project_env() -> None:
    """Load `.env` from the project root, even if python-dotenv is unavailable."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    if load_dotenv is not None:
        load_dotenv(dotenv_path=env_path, override=False)
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_project_env()

DEFAULT_PROVIDER_ENV = "DEBATETRADER_LLM_PROVIDER"
DEFAULT_MODEL_ENV = "DEBATETRADER_LLM_MODEL"
DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-latest"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
DEFAULT_GROQ_MIN_INTERVAL_SEC = 2.0
DEFAULT_GROQ_MAX_RETRIES = 3

_LAST_GROQ_CALL_TS = 0.0


def call_llm(
    messages: list[dict[str, str]],
    system_prompt: str,
    model: str | None = None,
    provider: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> str:
    """
    Call the configured LLM provider and return plain text content.

    Provider selection order:
    1. explicit `provider` argument
    2. `DEBATETRADER_LLM_PROVIDER` environment variable
    3. available API keys (`ANTHROPIC_API_KEY`, then `GROQ_API_KEY`)
    """

    selected_provider = _resolve_provider(provider=provider)
    selected_model = model or os.getenv(DEFAULT_MODEL_ENV) or _default_model(selected_provider)

    if selected_provider == "anthropic":
        return _call_anthropic(
            messages=messages,
            system_prompt=system_prompt,
            model=selected_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    if selected_provider == "groq":
        return _call_groq(
            messages=messages,
            system_prompt=system_prompt,
            model=selected_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    raise ValueError(f"Unsupported LLM provider: {selected_provider}")


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """
    Parse a JSON object from raw model output.

    Models sometimes wrap JSON in code fences or prepend explanatory text.
    This helper strips common wrappers before loading the object.
    """

    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise
        parsed = json.loads(cleaned[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("LLM output must decode to a JSON object.")

    return parsed


def _resolve_provider(provider: str | None) -> str:
    explicit = (provider or os.getenv(DEFAULT_PROVIDER_ENV) or "").strip().lower()
    anthropic_available = bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    groq_available = bool(os.getenv("GROQ_API_KEY", "").strip())

    if explicit:
        if explicit == "anthropic":
            if anthropic_available:
                return "anthropic"
            if groq_available:
                return "groq"
        elif explicit == "groq":
            if groq_available:
                return "groq"
            if anthropic_available:
                return "anthropic"
        else:
            raise ValueError(f"Unsupported LLM provider: {explicit}")

    if anthropic_available:
        return "anthropic"
    if groq_available:
        return "groq"

    raise RuntimeError(
        "No usable LLM provider configured. Set ANTHROPIC_API_KEY or GROQ_API_KEY. "
        "If DEBATETRADER_LLM_PROVIDER is set, the client will fall back to the other "
        "provider when the preferred provider's API key is missing."
    )


def _default_model(provider: str) -> str:
    if provider == "anthropic":
        return DEFAULT_ANTHROPIC_MODEL
    if provider == "groq":
        return DEFAULT_GROQ_MODEL
    raise ValueError(f"Unsupported LLM provider: {provider}")


def _call_anthropic(
    messages: list[dict[str, str]],
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for provider='anthropic'.")

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        system=system_prompt,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()


def _call_groq(
    messages: list[dict[str, str]],
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for provider='groq'.")

    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, *messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        return (content or "").strip()
    except ImportError:
        return _call_groq_via_http(
            api_key=api_key,
            messages=messages,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )


def _call_groq_via_http(
    api_key: str,
    messages: list[dict[str, str]],
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    import requests

    global _LAST_GROQ_CALL_TS

    min_interval = float(
        os.getenv("DEBATETRADER_GROQ_MIN_INTERVAL_SEC", DEFAULT_GROQ_MIN_INTERVAL_SEC)
    )
    max_retries = int(
        os.getenv("DEBATETRADER_GROQ_MAX_RETRIES", DEFAULT_GROQ_MAX_RETRIES)
    )

    for attempt in range(max_retries + 1):
        now = time.time()
        elapsed = now - _LAST_GROQ_CALL_TS
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "system", "content": system_prompt}, *messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        _LAST_GROQ_CALL_TS = time.time()

        if response.status_code != 429:
            response.raise_for_status()
            payload = response.json()
            choices = payload.get("choices") or []
            if not choices:
                raise RuntimeError("Groq HTTP response did not contain any choices.")
            content = choices[0].get("message", {}).get("content")
            return (content or "").strip()

        if attempt >= max_retries:
            response.raise_for_status()

        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                sleep_seconds = max(float(retry_after), min_interval)
            except ValueError:
                sleep_seconds = max(min_interval, 5.0 * (attempt + 1))
        else:
            sleep_seconds = max(min_interval, 5.0 * (attempt + 1))

        print(
            f"[llm_client] Groq rate-limited (attempt {attempt + 1}/{max_retries + 1}); "
            f"retrying in {sleep_seconds:.1f}s"
        )
        time.sleep(sleep_seconds)

    raise RuntimeError("Groq HTTP retry loop exited unexpectedly.")
