"""OpenAI-compatible LLM adapters used by ChinaTravel agents.

The agent code expects a small callable protocol:

    llm(messages, one_line=True, json_mode=False) -> str

This module keeps that protocol while routing all model calls through the
OpenAI-compatible APIs. Direct in-process model inference has been intentionally
removed; point ``--llm`` at an OpenAI-compatible model name and configure the
endpoint with environment variables instead.
"""

from __future__ import annotations

import json
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from chinatravel.json_utils import repair_json


DEFAULT_MAX_TOKENS = 4096
REQUEST_ERROR_RESPONSE = '{"error": "Request failed, please try again."}'
CHAT_WIRE_API = "chat"
RESPONSES_WIRE_API = "responses"
SUPPORTED_WIRE_APIS = {CHAT_WIRE_API, RESPONSES_WIRE_API}


def _first_env(*names: str | None) -> str | None:
    for name in names:
        if not name:
            continue
        value = os.getenv(name)
        if value:
            return value
    return None


def _drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _truthy_env(name: str) -> bool:
    value = os.getenv(name, "")
    return value.lower() in {"1", "true", "yes", "on"}


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            elif isinstance(part, str):
                text_parts.append(part)
        return "\n".join(text_parts)
    return str(content)


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return {key: _model_dump(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    return value


def _message_to_dict(message: Any) -> dict[str, Any]:
    dumped = _model_dump(message)
    if isinstance(dumped, dict):
        return dumped
    result = {
        "role": getattr(message, "role", "assistant"),
        "content": getattr(message, "content", None),
    }
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls is not None:
        result["tool_calls"] = _model_dump(tool_calls)
    return result


def _responses_to_message(response: Any) -> dict[str, Any]:
    dumped = _model_dump(response)
    if not isinstance(dumped, dict):
        dumped = {}

    content_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for item in dumped.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "message":
            for content in item.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                if isinstance(content.get("text"), str):
                    content_parts.append(content["text"])
        elif item_type == "function_call":
            call_id = item.get("call_id") or item.get("id") or ""
            tool_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}"),
                    },
                    "call_id": call_id,
                }
            )

    if not content_parts and isinstance(dumped.get("output_text"), str):
        content_parts.append(dumped["output_text"])

    message: dict[str, Any] = {
        "role": "assistant",
        "content": "\n".join(part for part in content_parts if part),
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _to_chat_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chat_tools = []
    for tool in tools:
        if isinstance(tool.get("function"), dict):
            chat_tools.append(tool)
        elif tool.get("type") == "function":
            function = {
                "name": tool.get("name"),
                "description": tool.get("description"),
                "parameters": tool.get("parameters"),
            }
            if "strict" in tool:
                function["strict"] = tool["strict"]
            chat_tools.append({"type": "function", "function": _drop_none(function)})
        else:
            chat_tools.append(tool)
    return chat_tools


def _to_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    responses_tools = []
    for tool in tools:
        function = tool.get("function")
        if isinstance(function, dict):
            responses_tool = {
                "type": tool.get("type", "function"),
                "name": function.get("name"),
                "description": function.get("description"),
                "parameters": function.get("parameters"),
            }
            if "strict" in function:
                responses_tool["strict"] = function["strict"]
            responses_tools.append(_drop_none(responses_tool))
        else:
            responses_tools.append(tool)
    return responses_tools


@dataclass(frozen=True)
class ModelAlias:
    name: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    default_request_args: dict[str, Any] = field(default_factory=dict)


MODEL_ALIASES: dict[str, ModelAlias] = {
    "deepseek": ModelAlias(
        name="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        default_request_args={"temperature": 0, "top_p": 0.00000001},
    ),
    "gpt-4o": ModelAlias(
        name="gpt-4o",
        model="chatgpt-4o-latest",
        api_key_env="OPENAI_API_KEY",
        default_request_args={"temperature": 0, "top_p": 0.01},
    ),
    "glm4-plus": ModelAlias(
        name="glm4-plus",
        model="glm-4-plus",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPUAI_API_KEY",
        default_request_args={"temperature": 0, "top_p": 0.01},
    ),
}


PROVIDER_ALIASES: dict[str, ModelAlias] = {
    "deepseek": MODEL_ALIASES["deepseek"],
    "openai": ModelAlias(name="OpenAI", model="", api_key_env="OPENAI_API_KEY"),
    "zhipu": MODEL_ALIASES["glm4-plus"],
    "glm": MODEL_ALIASES["glm4-plus"],
}


class AbstractLLM(ABC):
    class ModeError(Exception):
        pass

    def __init__(self) -> None:
        self.input_token_count = 0
        self.output_token_count = 0
        self.input_token_maxx = 0

    def __call__(
        self,
        messages: list[dict[str, Any]],
        one_line: bool = True,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> str:
        if one_line and json_mode:
            raise self.ModeError("one_line and json_mode cannot be True at the same time")
        if kwargs:
            return self._get_response(messages, one_line, json_mode, **kwargs)
        return self._get_response(messages, one_line, json_mode)

    @abstractmethod
    def _get_response(
        self,
        messages: list[dict[str, Any]],
        one_line: bool,
        json_mode: bool,
        **kwargs: Any,
    ) -> str:
        pass


class OpenAICompatibleLLM(AbstractLLM):
    """LLM adapter for OpenAI-compatible Chat Completions or Responses endpoints."""

    def __init__(
        self,
        model: str,
        *,
        name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
        organization: str | None = None,
        project: str | None = None,
        default_request_args: dict[str, Any] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        token_limit_arg: str | None = None,
        wire_api: str | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.name = name or model
        self.max_tokens = max_tokens
        self.wire_api = (
            wire_api
            or os.getenv("CHINATRAVEL_OPENAI_WIRE_API")
            or os.getenv("OPENAI_WIRE_API")
            or CHAT_WIRE_API
        ).strip().lower()
        if self.wire_api not in SUPPORTED_WIRE_APIS:
            raise ValueError(
                f"Unsupported OpenAI wire API: {self.wire_api}. "
                f"Expected one of {sorted(SUPPORTED_WIRE_APIS)}."
            )
        default_token_limit_arg = (
            "max_output_tokens" if self.wire_api == RESPONSES_WIRE_API else "max_tokens"
        )
        self.token_limit_arg = (
            token_limit_arg
            if token_limit_arg is not None
            else os.getenv("CHINATRAVEL_OPENAI_TOKEN_LIMIT_ARG", default_token_limit_arg)
        )
        self.default_request_args = dict(default_request_args or {})

        resolved_base_url = (
            os.getenv("CHINATRAVEL_OPENAI_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or base_url
        )
        resolved_api_key = api_key or _first_env(
            "CHINATRAVEL_OPENAI_API_KEY",
            api_key_env,
            "OPENAI_API_KEY",
        )

        client_kwargs = _drop_none(
            {
                "base_url": resolved_base_url,
                "api_key": resolved_api_key,
                "organization": organization or os.getenv("OPENAI_ORG_ID"),
                "project": project or os.getenv("OPENAI_PROJECT"),
            }
        )
        if resolved_base_url and "api_key" not in client_kwargs:
            client_kwargs["api_key"] = "EMPTY"
        self._client_kwargs = client_kwargs
        self._llm: Any | None = None

    @property
    def model_name(self) -> str:
        return self.name

    @property
    def llm(self) -> Any:
        if self._llm is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ImportError(
                    "The openai package is required for OpenAI-compatible model calls. "
                    "Install project requirements or use the rule placeholder."
                ) from exc
            self._llm = OpenAI(**self._client_kwargs)
        return self._llm

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any | None = None,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return the full assistant message, including OpenAI tool calls."""

        request_args = self._request_args(
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            **kwargs,
        )
        return self._send_request(messages, request_args)

    def _get_response(
        self,
        messages: list[dict[str, Any]],
        one_line: bool,
        json_mode: bool,
        **kwargs: Any,
    ) -> str:
        tools = kwargs.pop("tools", None)
        tool_choice = kwargs.pop("tool_choice", None)
        response_format = kwargs.pop("response_format", None)
        if json_mode and response_format is None:
            response_format = {"type": "json_object"}
        request_args = self._request_args(
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            **kwargs,
        )
        if one_line and "stop" not in request_args:
            request_args["stop"] = ["\n"]

        try:
            message = self._send_request(messages, request_args)
            res_str = _content_to_text(message.get("content")).strip()
            if not res_str and message.get("tool_calls"):
                res_str = json.dumps(
                    {"tool_calls": message["tool_calls"]},
                    ensure_ascii=False,
                )
            if json_mode:
                return repair_json(res_str, ensure_ascii=False)
            if one_line:
                return res_str.split("\n")[0]
            return res_str
        except Exception as exc:
            if _truthy_env("CHINATRAVEL_OPENAI_RAISE_ERRORS"):
                raise
            print(exc, file=sys.stderr)
            return REQUEST_ERROR_RESPONSE

    def _request_args(
        self,
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any | None = None,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        request_args = {**self.default_request_args, **kwargs}
        if self.token_limit_arg:
            request_args.setdefault(self.token_limit_arg, self.max_tokens)
        if tools is not None:
            request_args["tools"] = (
                _to_responses_tools(tools)
                if self.wire_api == RESPONSES_WIRE_API
                else _to_chat_tools(tools)
            )
        if tool_choice is not None:
            request_args["tool_choice"] = tool_choice
        if response_format is not None:
            if self.wire_api == RESPONSES_WIRE_API:
                request_args.setdefault("text", {"format": response_format})
            else:
                request_args["response_format"] = response_format
        return request_args

    def _send_request(
        self,
        messages: list[dict[str, Any]],
        request_args: dict[str, Any],
    ) -> dict[str, Any]:
        if self.wire_api == RESPONSES_WIRE_API:
            if not hasattr(self.llm, "responses"):
                raise RuntimeError(
                    "The installed openai client does not expose the Responses API. "
                    "Upgrade the openai package or set CHINATRAVEL_OPENAI_WIRE_API=chat."
                )
            response = self.llm.responses.create(
                model=self.model,
                input=messages,
                **request_args,
            )
            self._record_usage(response)
            return _responses_to_message(response)

        completion = self.llm.chat.completions.create(
            model=self.model,
            messages=messages,
            **request_args,
        )
        self._record_usage(completion)
        return _message_to_dict(completion.choices[0].message)

    def _record_usage(self, completion: Any) -> None:
        usage = getattr(completion, "usage", None)
        if usage is None:
            return
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        if prompt_tokens is None:
            prompt_tokens = getattr(usage, "input_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        if completion_tokens is None:
            completion_tokens = getattr(usage, "output_tokens", None)
        if prompt_tokens is not None:
            self.input_token_count += int(prompt_tokens)
            self.input_token_maxx = max(self.input_token_maxx, int(prompt_tokens))
        if completion_tokens is not None:
            self.output_token_count += int(completion_tokens)


def create_llm(llm_name: str | None, **overrides: Any) -> AbstractLLM:
    """Create an LLM from an alias or arbitrary OpenAI-compatible model name."""

    model_name = llm_name or os.getenv("CHINATRAVEL_OPENAI_MODEL") or os.getenv("OPENAI_MODEL")
    if not model_name:
        raise ValueError(
            "No LLM model was provided. Pass --llm <model> or set CHINATRAVEL_OPENAI_MODEL."
        )
    model_name = model_name.strip()
    if not model_name:
        raise ValueError(
            "No LLM model was provided. Pass --llm <model> or set CHINATRAVEL_OPENAI_MODEL."
        )
    model_key = model_name.lower()
    if model_key == "rule":
        return EmptyLLM()

    alias = MODEL_ALIASES.get(model_key)
    provider_alias = None
    if alias is None and "/" in model_name:
        provider, provider_model = model_name.split("/", 1)
        provider_alias = PROVIDER_ALIASES.get(provider.lower())
        if provider_alias is not None:
            alias = ModelAlias(
                name=model_name,
                model=provider_model,
                base_url=provider_alias.base_url,
                api_key_env=provider_alias.api_key_env,
                default_request_args=provider_alias.default_request_args,
            )

    if alias is not None:
        config = {
            "model": alias.model,
            "name": alias.name,
            "base_url": alias.base_url,
            "api_key_env": alias.api_key_env,
            "default_request_args": alias.default_request_args,
        }
    else:
        config = {"model": model_name, "name": model_name}

    config.update({key: value for key, value in overrides.items() if value is not None})
    return OpenAICompatibleLLM(**config)


class EmptyLLM(AbstractLLM):
    def __init__(self) -> None:
        super().__init__()
        self.name = "EmptyLLM"

    @property
    def model_name(self) -> str:
        return self.name

    def _get_response(
        self,
        messages: list[dict[str, Any]],
        one_line: bool,
        json_mode: bool,
        **kwargs: Any,
    ) -> str:
        return "Empty LLM response"


if __name__ == "__main__":
    model = create_llm(None)
    print(model([{"role": "user", "content": "hello!"}], one_line=False))
