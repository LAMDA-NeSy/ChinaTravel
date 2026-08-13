"""Small stdlib HTTP server for the ChinaTravel agent environment."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from agent_env.adapter import ChinaTravelEnvAdapter


ADAPTER = ChinaTravelEnvAdapter()


class Handler(BaseHTTPRequestHandler):
    server_version = "ChinaTravelAgentEnv/0.1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send({"success": True, "service": "chinatravel-agent-env"})
        elif self.path == "/tools":
            self._send({"success": True, "tools": ADAPTER.list_tools()})
        elif self.path == "/splits":
            self._send(ADAPTER.list_splits())
        else:
            self._send({"success": False, "error": "Not found"}, status=404)

    def do_POST(self) -> None:
        body = self._read_json()
        if self.path == "/call":
            self._send(ADAPTER.call_tool(body.get("tool", ""), body.get("arguments", {})))
        elif self.path == "/world-command":
            self._send(ADAPTER.world_command(body.get("command", "")))
        else:
            self._send({"success": False, "error": "Not found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _send(self, payload: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> None:
    global ADAPTER
    parser = argparse.ArgumentParser(description="Run ChinaTravel agent HTTP environment.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--lang",
        choices=["zh", "en"],
        default=os.environ.get("CHINATRAVEL_LANG", "zh"),
    )
    args = parser.parse_args()

    ADAPTER = ChinaTravelEnvAdapter(lang=args.lang)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"ChinaTravel agent HTTP env listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
