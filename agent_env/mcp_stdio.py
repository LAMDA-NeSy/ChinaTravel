"""Minimal MCP-style stdio bridge for ChinaTravel tools.

The implementation is dependency-free and supports the basic JSON-RPC methods
used by MCP clients: initialize, tools/list, tools/call, and ping.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import argparse

from agent_env.adapter import ChinaTravelEnvAdapter
from agent_env.runtime import AgentToolRuntime


def _response(message_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _handle(runtime: AgentToolRuntime, message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid Request: JSON-RPC message must be an object.")
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params", {})
    if params is None:
        params = {}

    if message_id is None:
        return None
    if not isinstance(method, str):
        return _error(message_id, -32600, "Invalid Request: method must be a string.")
    if not isinstance(params, dict):
        return _error(message_id, -32602, "Invalid params: params must be an object.")

    if method == "initialize":
        return _response(
            message_id,
            {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "serverInfo": {"name": "chinatravel-agent-env", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        )
    if method == "ping":
        return _response(message_id, {})
    if method == "tools/list":
        return _response(message_id, {"tools": runtime.list_mcp_tools()})
    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        return _response(message_id, runtime.mcp_tool_result(name, arguments))
    return _error(message_id, -32601, f"Unsupported method: {method}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ChinaTravel agent MCP stdio bridge.")
    parser.add_argument("--lang", "--locale", choices=["zh", "en"], default=None)
    args = parser.parse_args()
    runtime = AgentToolRuntime(ChinaTravelEnvAdapter(lang=args.lang))

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"Parse error: {exc}")
        else:
            message_id = message.get("id") if isinstance(message, dict) else None
            try:
                response = _handle(runtime, message)
            except Exception as exc:
                response = _error(message_id, -32603, f"{exc.__class__.__name__}: {exc}")
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
