"""Protocol helpers for exposing ChinaTravel tools to agent runtimes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agent_env.adapter import ChinaTravelEnvAdapter, dumps_result
from agent_env.tools import validate_tool_specs


def _format_error(exc: Exception) -> dict[str, Any]:
    return {
        "success": False,
        "error_type": exc.__class__.__name__,
        "error": str(exc),
    }


@dataclass
class AgentToolRuntime:
    """Shared protocol adapter for CLI, HTTP, MCP, and OpenAI tool calls."""

    adapter: ChinaTravelEnvAdapter = field(default_factory=ChinaTravelEnvAdapter)

    def list_mcp_tools(self) -> list[dict[str, Any]]:
        return self.adapter.list_tools(format="mcp")

    def list_openai_tools(self) -> list[dict[str, Any]]:
        return self.adapter.list_tools(format="openai")

    def list_openai_responses_tools(self) -> list[dict[str, Any]]:
        return self.adapter.list_tools(format="openai-responses")

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.adapter.call_tool(name, arguments)

    def mcp_tool_result(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.call_tool(name, arguments)
        return {
            "content": [{"type": "text", "text": dumps_result(result)}],
            "isError": not bool(result.get("success")),
        }

    def call_openai_tool(self, tool_call: dict[str, Any] | Any) -> dict[str, Any]:
        try:
            name, arguments = self._parse_openai_tool_call(tool_call)
            result = self.call_tool(name, arguments)
            tool_call_id = self._chat_tool_call_id(tool_call)
            call_id = self._responses_call_id(tool_call)
            if tool_call_id:
                result["tool_call_id"] = tool_call_id
            if call_id:
                result["call_id"] = call_id
            result["tool_name"] = name
            return result
        except Exception as exc:
            result = _format_error(exc)
            tool_call_id = self._chat_tool_call_id(tool_call)
            call_id = self._responses_call_id(tool_call)
            if tool_call_id:
                result["tool_call_id"] = tool_call_id
            if call_id:
                result["call_id"] = call_id
            return result

    def call_openai_tools(self, tool_calls: list[dict[str, Any]] | Any) -> list[dict[str, Any]]:
        if not isinstance(tool_calls, list):
            return [_format_error(ValueError("OpenAI tool_calls must be a list."))]
        return [self.call_openai_tool(tool_call) for tool_call in tool_calls]

    def openai_tool_message(self, tool_call: dict[str, Any] | Any) -> dict[str, Any]:
        result = self.call_openai_tool(tool_call)
        message: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": result.get("tool_call_id")
            or self._chat_tool_call_id(tool_call),
            "content": dumps_result(result),
        }
        return message

    def openai_tool_messages(self, tool_calls: list[dict[str, Any]] | Any) -> list[dict[str, Any]]:
        if not isinstance(tool_calls, list):
            result = _format_error(ValueError("OpenAI tool_calls must be a list."))
            return [
                {
                    "role": "tool",
                    "tool_call_id": "",
                    "content": dumps_result(result),
                }
            ]
        return [self.openai_tool_message(tool_call) for tool_call in tool_calls]

    def responses_tool_output(self, tool_call: dict[str, Any] | Any) -> dict[str, Any]:
        result = self.call_openai_tool(tool_call)
        return {
            "type": "function_call_output",
            "call_id": result.get("call_id") or self._responses_call_id(tool_call),
            "output": dumps_result(result),
        }

    def responses_tool_outputs(self, tool_calls: list[dict[str, Any]] | Any) -> list[dict[str, Any]]:
        if not isinstance(tool_calls, list):
            result = _format_error(ValueError("OpenAI Responses function calls must be a list."))
            return [
                {
                    "type": "function_call_output",
                    "call_id": "",
                    "output": dumps_result(result),
                }
            ]
        return [self.responses_tool_output(tool_call) for tool_call in tool_calls]

    def self_check(self) -> dict[str, Any]:
        tool_names = [tool["name"] for tool in self.list_mcp_tools()]
        required_tools = {
            "china_travel_list_splits",
            "china_travel_world_command",
            "attractions_keys",
            "restaurants_nearby",
            "goto",
        }
        missing_tools = sorted(required_tools - set(tool_names))
        schema_errors = validate_tool_specs()
        tool_call = {
            "id": "self_check_call",
            "type": "function",
            "function": {"name": "china_travel_list_splits", "arguments": "{}"},
        }
        openai_message = self.openai_tool_message(tool_call)
        openai_messages = self.openai_tool_messages([tool_call])
        responses_tools = self.list_openai_responses_tools()
        responses_outputs = self.responses_tool_outputs(
            [
                {
                    "id": "fc_self_check",
                    "call_id": "self_check_call",
                    "type": "function_call",
                    "name": "china_travel_list_splits",
                    "arguments": "{}",
                }
            ]
        )
        mcp_result = self.mcp_tool_result("china_travel_list_splits", {})
        return {
            "success": not missing_tools
            and not schema_errors
            and openai_message.get("role") == "tool"
            and len(openai_messages) == 1
            and openai_messages[0].get("role") == "tool"
            and len(responses_tools) == len(tool_names)
            and all("function" not in tool for tool in responses_tools)
            and len(responses_outputs) == 1
            and responses_outputs[0].get("type") == "function_call_output"
            and bool(openai_message.get("tool_call_id"))
            and not bool(mcp_result.get("isError")),
            "tool_count": len(tool_names),
            "missing_tools": missing_tools,
            "schema_errors": schema_errors,
            "openai_message_role": openai_message.get("role"),
            "openai_message_count": len(openai_messages),
            "responses_tool_count": len(responses_tools),
            "responses_output_count": len(responses_outputs),
            "mcp_is_error": bool(mcp_result.get("isError")),
        }

    def _parse_openai_tool_call(self, tool_call: dict[str, Any] | Any) -> tuple[str, dict[str, Any]]:
        if not isinstance(tool_call, dict):
            raise ValueError("OpenAI tool call must be a JSON object.")
        function = tool_call.get("function") or {}
        if function and not isinstance(function, dict):
            raise ValueError("OpenAI tool call function must be a JSON object.")
        name = function.get("name") if isinstance(function, dict) else None
        name = name or tool_call.get("name")
        if not name:
            raise ValueError("OpenAI tool call is missing function.name or name.")

        raw_arguments = (
            function.get("arguments", tool_call.get("arguments", {}))
            if isinstance(function, dict)
            else tool_call.get("arguments", {})
        )
        if isinstance(raw_arguments, str):
            arguments = json.loads(raw_arguments) if raw_arguments.strip() else {}
        elif isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            raise ValueError("OpenAI tool call arguments must be a JSON object or JSON string.")
        if not isinstance(arguments, dict):
            raise ValueError("OpenAI tool call arguments must decode to a JSON object.")
        return str(name), arguments

    def _chat_tool_call_id(self, tool_call: dict[str, Any] | Any) -> str:
        if not isinstance(tool_call, dict):
            return ""
        return str(tool_call.get("id") or "")

    def _responses_call_id(self, tool_call: dict[str, Any] | Any) -> str:
        if not isinstance(tool_call, dict):
            return ""
        return str(tool_call.get("call_id") or tool_call.get("id") or "")
