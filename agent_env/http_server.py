"""Small stdlib HTTP server for the ChinaTravel agent environment."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from agent_env.adapter import ChinaTravelEnvAdapter
from agent_env.runtime import AgentToolRuntime


class Handler(BaseHTTPRequestHandler):
    server_version = "ChinaTravelAgentEnv/0.1"
    runtime: AgentToolRuntime

    def do_OPTIONS(self) -> None:
        self._send({}, status=204)

    def do_GET(self) -> None:
        path = self._path()
        if path == "/health":
            self._send({"success": True, "service": "chinatravel-agent-env"})
        elif path == "/self-check":
            self._send(self.runtime.self_check())
        elif path == "/tools":
            self._send({"success": True, "tools": self.runtime.list_mcp_tools()})
        elif path == "/openai-tools":
            self._send({"success": True, "tools": self.runtime.list_openai_tools()})
        elif path == "/responses-tools":
            self._send({"success": True, "tools": self.runtime.list_openai_responses_tools()})
        elif path == "/splits":
            self._send(self.runtime.adapter.list_splits())
        else:
            self._send({"success": False, "error": "Not found"}, status=404)

    def do_POST(self) -> None:
        try:
            body = self._read_json()
        except ValueError as exc:
            self._send(
                {
                    "success": False,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                },
                status=400,
            )
            return
        path = self._path()
        if path == "/call":
            self._send(self.runtime.call_tool(body.get("tool", ""), body.get("arguments", {})))
        elif path == "/openai-tool-call":
            self._send(self.runtime.call_openai_tool(body.get("tool_call", body)))
        elif path == "/openai-tool-calls":
            self._send({"success": True, "results": self.runtime.call_openai_tools(body.get("tool_calls", []))})
        elif path == "/openai-tool-message":
            self._send({"success": True, "message": self.runtime.openai_tool_message(body.get("tool_call", body))})
        elif path == "/openai-tool-messages":
            self._send({"success": True, "messages": self.runtime.openai_tool_messages(body.get("tool_calls", []))})
        elif path == "/responses-tool-output":
            self._send({"success": True, "output": self.runtime.responses_tool_output(body.get("tool_call", body))})
        elif path == "/responses-tool-outputs":
            self._send({"success": True, "outputs": self.runtime.responses_tool_outputs(body.get("tool_calls", []))})
        elif path == "/world-command":
            self._send(self.runtime.adapter.world_command(body.get("command", "")))
        else:
            self._send({"success": False, "error": "Not found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _path(self) -> str:
        return urlparse(self.path).path

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length header.") from exc
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object.")
        return value

    def _send(self, payload: dict[str, Any], status: int = 200) -> None:
        raw = b"" if status == 204 else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ChinaTravel agent HTTP environment.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--lang", "--locale", choices=["zh", "en"], default=None)
    args = parser.parse_args()

    Handler.runtime = AgentToolRuntime(ChinaTravelEnvAdapter(lang=args.lang))
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"ChinaTravel agent HTTP env listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
