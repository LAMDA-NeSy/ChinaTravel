#!/usr/bin/env python3
"""Small helpers for OpenAI-compatible Chat Completions HTTP requests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def resolve_chat_completions_url(api_config: Mapping[str, Any]) -> str:
    """Resolve either a complete URL or base_url + chat_completions_path."""
    explicit_url = str(api_config.get("url") or "").strip()
    if explicit_url:
        return explicit_url

    base_url = str(api_config.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        raise ValueError("API config must define either url or base_url")

    endpoint_path = str(
        api_config.get("chat_completions_path") or "/chat/completions"
    ).strip()
    if not endpoint_path:
        return base_url
    normalized_path = "/" + endpoint_path.lstrip("/")
    if base_url.endswith(normalized_path):
        return base_url
    return base_url + normalized_path


def build_chat_completion_payload(
    api_config: Mapping[str, Any],
    *,
    model: str,
    messages: Sequence[Mapping[str, Any]],
    default_temperature: float,
    default_max_tokens: int = 1024,
) -> dict[str, Any]:
    """Build a Chat Completions body and merge provider-specific extra fields."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": list(messages),
    }

    temperature = api_config.get("temperature", default_temperature)
    if temperature is not None:
        payload["temperature"] = float(temperature)

    max_tokens = api_config.get("max_tokens", default_max_tokens)
    if max_tokens is not None:
        max_tokens_field = str(
            api_config.get("max_tokens_field") or "max_tokens"
        ).strip()
        if not max_tokens_field:
            raise ValueError("max_tokens_field cannot be empty when max_tokens is set")
        payload[max_tokens_field] = int(max_tokens)

    extra_body = api_config.get("extra_body", {})
    if extra_body is None:
        extra_body = {}
    if not isinstance(extra_body, Mapping):
        raise ValueError("extra_body must be a JSON object")
    payload.update(extra_body)
    return payload


def build_api_headers(
    api_config: Mapping[str, Any], api_key: str | None
) -> dict[str, str]:
    """Build configurable authentication and provider-specific request headers."""
    extra_headers = api_config.get("extra_headers", {})
    if extra_headers is None:
        extra_headers = {}
    if not isinstance(extra_headers, Mapping):
        raise ValueError("extra_headers must be a JSON object")

    headers = {"Content-Type": "application/json"}
    headers.update(
        {
            str(key): str(value)
            for key, value in extra_headers.items()
            if value is not None
        }
    )

    if api_key:
        auth_header = str(api_config.get("auth_header") or "Authorization").strip()
        if not auth_header:
            raise ValueError("auth_header cannot be empty when an API key is used")
        auth_scheme = str(api_config.get("auth_scheme", "Bearer") or "").strip()
        headers[auth_header] = f"{auth_scheme} {api_key}".strip()
    elif bool(api_config.get("api_key_required", True)):
        api_key_env = str(api_config.get("api_key_env") or "API_KEY")
        raise ValueError(f"{api_key_env} is required but not set")

    return headers
