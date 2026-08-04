"""Interactive command-line wrapper for ChinaTravel agent tools."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from agent_env.adapter import ChinaTravelEnvAdapter, dumps_result


HELP_TEXT = """Commands:
  help
  tools
  splits
  call <tool_name> <json_arguments>
  world <WorldEnv command>
  quit

Examples:
  call attractions_keys {"city":"上海"}
  call attractions_nearby {"city":"上海","point":"上海迪士尼度假区","topk":5,"dist":5}
  world attractions_keys('上海')
"""


def _print_result(result: dict[str, Any]) -> int:
    print(dumps_result(result), flush=True)
    return 0 if result.get("success", True) else 1


def _load_json_object(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Arguments must be a JSON object.")
    return value


def _handle_repl_line(adapter: ChinaTravelEnvAdapter, line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped in {"quit", "exit"}:
        return False
    if stripped == "help":
        print(HELP_TEXT, flush=True)
        return True
    if stripped == "tools":
        print(dumps_result({"success": True, "tools": adapter.list_tools()}), flush=True)
        return True
    if stripped == "splits":
        print(dumps_result(adapter.list_splits()), flush=True)
        return True
    if stripped.startswith("world "):
        _print_result(adapter.world_command(stripped[len("world ") :].strip()))
        return True
    if stripped.startswith("call "):
        remainder = stripped[len("call ") :].strip()
        try:
            parts = remainder.split(maxsplit=1)
            if not parts:
                raise ValueError("Missing tool name.")
            name = parts[0]
            raw_args = parts[1] if len(parts) > 1 else "{}"
            _print_result(adapter.call_tool(name, _load_json_object(raw_args)))
        except Exception as exc:
            _print_result(
                {
                    "success": False,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )
        return True

    _print_result({"success": False, "error": f"Unknown command: {stripped}"})
    return True


def run_repl(adapter: ChinaTravelEnvAdapter) -> int:
    print("ChinaTravel agent CLI. Type 'help' for commands, 'quit' to exit.", flush=True)
    while True:
        try:
            line = input("chinatravel> ")
        except EOFError:
            print("", flush=True)
            return 0
        except KeyboardInterrupt:
            print("", flush=True)
            return 130
        if not _handle_repl_line(adapter, line):
            return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Call ChinaTravel agent environment tools.")
    parser.add_argument(
        "--lang",
        choices=["zh", "en"],
        default=os.environ.get("CHINATRAVEL_LANG", "zh"),
        help="Sandbox/query language. Defaults to CHINATRAVEL_LANG or zh.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("tools", help="List available tools.")
    subparsers.add_parser("splits", help="List locally available evaluation splits.")
    subparsers.add_parser("repl", help="Start an interactive prompt.")

    call_parser = subparsers.add_parser("call", help="Call a structured tool.")
    call_parser.add_argument("tool", help="Tool name, e.g. attractions_keys.")
    call_parser.add_argument(
        "arguments",
        nargs="?",
        default="{}",
        help='JSON object arguments, e.g. \'{"city":"上海"}\'.',
    )

    world_parser = subparsers.add_parser("world", help="Call the raw WorldEnv command surface.")
    world_parser.add_argument("world_command", help="WorldEnv command string.")

    args = parser.parse_args()
    adapter = ChinaTravelEnvAdapter(lang=args.lang)

    try:
        if args.command is None or args.command == "repl":
            code = run_repl(adapter)
        elif args.command == "tools":
            code = _print_result({"success": True, "tools": adapter.list_tools()})
        elif args.command == "splits":
            code = _print_result(adapter.list_splits())
        elif args.command == "call":
            code = _print_result(adapter.call_tool(args.tool, _load_json_object(args.arguments)))
        elif args.command == "world":
            code = _print_result(adapter.world_command(args.world_command))
        else:
            parser.error(f"Unknown command: {args.command}")
            code = 2
    except Exception as exc:
        code = _print_result(
            {
                "success": False,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
