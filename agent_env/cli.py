"""Interactive command-line wrapper for ChinaTravel agent tools."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from agent_env.adapter import ChinaTravelEnvAdapter, dumps_result
from agent_env.runtime import AgentToolRuntime


HELP_TEXT = """Commands:
  help
  check
  tools
  openai-tools
  responses-tools
  splits
  call <tool_name> <json_arguments>
  openai-call <tool_call_json>
  openai-calls <tool_calls_json_array>
  openai-message <tool_call_json>
  openai-messages <tool_calls_json_array>
  responses-output <function_call_json>
  responses-outputs <function_calls_json_array>
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


def _load_json_array(raw: str) -> list[Any]:
    value = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError("Arguments must be a JSON array.")
    return value


def _handle_repl_line(runtime: AgentToolRuntime, line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped in {"quit", "exit"}:
        return False
    if stripped == "help":
        print(HELP_TEXT, flush=True)
        return True
    if stripped == "check":
        _print_result(runtime.self_check())
        return True
    if stripped == "tools":
        print(dumps_result({"success": True, "tools": runtime.list_mcp_tools()}), flush=True)
        return True
    if stripped == "openai-tools":
        print(dumps_result({"success": True, "tools": runtime.list_openai_tools()}), flush=True)
        return True
    if stripped == "responses-tools":
        print(dumps_result({"success": True, "tools": runtime.list_openai_responses_tools()}), flush=True)
        return True
    if stripped == "splits":
        print(dumps_result(runtime.adapter.list_splits()), flush=True)
        return True
    if stripped.startswith("world "):
        _print_result(runtime.adapter.world_command(stripped[len("world ") :].strip()))
        return True
    if stripped.startswith("call "):
        remainder = stripped[len("call ") :].strip()
        try:
            parts = remainder.split(maxsplit=1)
            if not parts:
                raise ValueError("Missing tool name.")
            name = parts[0]
            raw_args = parts[1] if len(parts) > 1 else "{}"
            _print_result(runtime.call_tool(name, _load_json_object(raw_args)))
        except Exception as exc:
            _print_result(
                {
                    "success": False,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )
        return True
    if stripped.startswith("openai-call "):
        try:
            tool_call = _load_json_object(stripped[len("openai-call ") :].strip())
            _print_result(runtime.call_openai_tool(tool_call))
        except Exception as exc:
            _print_result(
                {
                    "success": False,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )
        return True
    if stripped.startswith("openai-calls "):
        try:
            tool_calls = _load_json_array(stripped[len("openai-calls ") :].strip())
            _print_result({"success": True, "results": runtime.call_openai_tools(tool_calls)})
        except Exception as exc:
            _print_result(
                {
                    "success": False,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )
        return True
    if stripped.startswith("openai-message "):
        try:
            tool_call = _load_json_object(stripped[len("openai-message ") :].strip())
            _print_result({"success": True, "message": runtime.openai_tool_message(tool_call)})
        except Exception as exc:
            _print_result(
                {
                    "success": False,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )
        return True
    if stripped.startswith("openai-messages "):
        try:
            tool_calls = _load_json_array(stripped[len("openai-messages ") :].strip())
            _print_result({"success": True, "messages": runtime.openai_tool_messages(tool_calls)})
        except Exception as exc:
            _print_result(
                {
                    "success": False,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )
        return True
    if stripped.startswith("responses-output "):
        try:
            tool_call = _load_json_object(stripped[len("responses-output ") :].strip())
            _print_result({"success": True, "output": runtime.responses_tool_output(tool_call)})
        except Exception as exc:
            _print_result(
                {
                    "success": False,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                }
            )
        return True
    if stripped.startswith("responses-outputs "):
        try:
            tool_calls = _load_json_array(stripped[len("responses-outputs ") :].strip())
            _print_result({"success": True, "outputs": runtime.responses_tool_outputs(tool_calls)})
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


def run_repl(runtime: AgentToolRuntime) -> int:
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
        if not _handle_repl_line(runtime, line):
            return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Call ChinaTravel agent environment tools.")
    parser.add_argument("--lang", "--locale", choices=["zh", "en"], default=None)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("check", help="Run a lightweight protocol self-check.")
    subparsers.add_parser("tools", help="List available tools.")
    subparsers.add_parser("openai-tools", help="List tools in OpenAI tool-call format.")
    subparsers.add_parser("responses-tools", help="List tools in OpenAI Responses API format.")
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

    openai_call_parser = subparsers.add_parser("openai-call", help="Execute an OpenAI tool call object.")
    openai_call_parser.add_argument("tool_call", help="OpenAI tool call JSON object.")

    openai_calls_parser = subparsers.add_parser("openai-calls", help="Execute an OpenAI tool_calls JSON array.")
    openai_calls_parser.add_argument("tool_calls", help="OpenAI tool_calls JSON array.")

    openai_message_parser = subparsers.add_parser("openai-message", help="Execute a tool call and return an OpenAI tool response message.")
    openai_message_parser.add_argument("tool_call", help="OpenAI tool call JSON object.")

    openai_messages_parser = subparsers.add_parser("openai-messages", help="Execute tool calls and return OpenAI tool response messages.")
    openai_messages_parser.add_argument("tool_calls", help="OpenAI tool_calls JSON array.")

    responses_output_parser = subparsers.add_parser("responses-output", help="Execute a Responses API function_call item.")
    responses_output_parser.add_argument("tool_call", help="Responses API function_call JSON object.")

    responses_outputs_parser = subparsers.add_parser("responses-outputs", help="Execute Responses API function_call items.")
    responses_outputs_parser.add_argument("tool_calls", help="Responses API function_call JSON array.")

    args = parser.parse_args()
    runtime = AgentToolRuntime(ChinaTravelEnvAdapter(lang=args.lang))

    try:
        if args.command is None or args.command == "repl":
            code = run_repl(runtime)
        elif args.command == "check":
            code = _print_result(runtime.self_check())
        elif args.command == "tools":
            code = _print_result({"success": True, "tools": runtime.list_mcp_tools()})
        elif args.command == "openai-tools":
            code = _print_result({"success": True, "tools": runtime.list_openai_tools()})
        elif args.command == "responses-tools":
            code = _print_result({"success": True, "tools": runtime.list_openai_responses_tools()})
        elif args.command == "splits":
            code = _print_result(runtime.adapter.list_splits())
        elif args.command == "call":
            code = _print_result(runtime.call_tool(args.tool, _load_json_object(args.arguments)))
        elif args.command == "openai-call":
            code = _print_result(runtime.call_openai_tool(_load_json_object(args.tool_call)))
        elif args.command == "openai-calls":
            code = _print_result(
                {"success": True, "results": runtime.call_openai_tools(_load_json_array(args.tool_calls))}
            )
        elif args.command == "openai-message":
            code = _print_result(
                {"success": True, "message": runtime.openai_tool_message(_load_json_object(args.tool_call))}
            )
        elif args.command == "openai-messages":
            code = _print_result(
                {"success": True, "messages": runtime.openai_tool_messages(_load_json_array(args.tool_calls))}
            )
        elif args.command == "responses-output":
            code = _print_result(
                {"success": True, "output": runtime.responses_tool_output(_load_json_object(args.tool_call))}
            )
        elif args.command == "responses-outputs":
            code = _print_result(
                {"success": True, "outputs": runtime.responses_tool_outputs(_load_json_array(args.tool_calls))}
            )
        elif args.command == "world":
            code = _print_result(runtime.adapter.world_command(args.world_command))
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
