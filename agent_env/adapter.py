"""Agent-facing wrapper around the ChinaTravel environment.

This module intentionally lives outside the ``chinatravel`` package.  It keeps
the benchmark code unchanged while exposing a stable, JSON-serializable tool
surface for agent runtimes.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from agent_env.tools import TOOL_SPECS, normalize_arguments, validate_arguments


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAGE_SIZE = 10


def _jsonable(value: Any, *, max_rows: int = DEFAULT_PAGE_SIZE) -> Any:
    """Convert common ChinaTravel return values to JSON-safe structures."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): _jsonable(v, max_rows=max_rows) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v, max_rows=max_rows) for v in value]

    if hasattr(value, "head") and hasattr(value, "to_dict"):
        page = value.head(max_rows)
        return {
            "type": "dataframe",
            "columns": [str(c) for c in page.columns],
            "rows": _jsonable(page.to_dict(orient="records"), max_rows=max_rows),
            "row_count": int(len(value)),
            "returned_rows": int(len(page)),
        }

    if hasattr(value, "tolist"):
        try:
            return _jsonable(value.tolist(), max_rows=max_rows)
        except Exception:
            pass

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return str(value)


def _format_error(exc: Exception) -> dict[str, Any]:
    return {
        "success": False,
        "error_type": exc.__class__.__name__,
        "error": str(exc),
    }


class _AdapterOutput:
    def __init__(self, success: bool, data: Any, *, page_size: int = DEFAULT_PAGE_SIZE) -> None:
        self._success = success
        self._data = data
        self._page_size = page_size
        self._page_idx = 0
        self._original_data = data
        if hasattr(data, "head") and hasattr(data, "iloc"):
            self._data = data.head(page_size)

    def __getitem__(self, key: str) -> Any:
        if key == "success":
            return self._success
        if key == "data":
            return self._data
        if key == "whole_data":
            return self._original_data
        if key == "str":
            return str(self)
        raise KeyError(f"Invalid output key: {key}")

    def __str__(self) -> str:
        return str(self._data)

    def next_page(self) -> Any:
        if not hasattr(self._original_data, "iloc"):
            return "next_page() is not supported for this data type."
        self._page_idx += 1
        start = self._page_idx * self._page_size
        end = start + self._page_size
        if start >= len(self._original_data):
            self._data = "No more data."
        else:
            self._data = self._original_data.iloc[start:end]
        return self


def _is_env_output(value: Any) -> bool:
    if not hasattr(value, "__getitem__"):
        return False
    try:
        value["success"]
        value["data"]
        return True
    except Exception:
        return False


class ChinaTravelEnvAdapter:
    def __init__(self, lang: str | None = None) -> None:
        self.lang = lang or os.getenv("CHINATRAVEL_ENV_LANG")
        self._env: Any | None = None

    def list_tools(self, *, format: str = "mcp") -> list[dict[str, Any]]:
        if format == "mcp":
            return [spec.to_mcp_tool() for spec in TOOL_SPECS.values()]
        if format in {"openai", "openai-chat"}:
            return self.list_openai_tools()
        if format in {"openai-responses", "responses"}:
            return self.list_openai_responses_tools()
        raise ValueError(f"Unsupported tool schema format: {format}")

    def list_openai_tools(self) -> list[dict[str, Any]]:
        return [spec.to_openai_tool() for spec in TOOL_SPECS.values()]

    def list_openai_responses_tools(self) -> list[dict[str, Any]]:
        return [spec.to_openai_responses_tool() for spec in TOOL_SPECS.values()]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return {
                "success": False,
                "error": "Tool arguments must be a JSON object.",
                "tool": name,
            }
        if name not in TOOL_SPECS:
            return {"success": False, "error": f"Unknown tool: {name}"}

        spec = TOOL_SPECS[name]
        arguments = normalize_arguments(spec, arguments)
        validation_errors = validate_arguments(spec, arguments)
        if validation_errors:
            return {
                "success": False,
                "error_type": "ValidationError",
                "error": "; ".join(validation_errors),
                "tool": name,
            }

        if name == "china_travel_list_splits":
            return self.list_splits()
        if name == "china_travel_load_query":
            try:
                return self.load_query(**arguments)
            except Exception as exc:
                return _format_error(exc)
        if name == "china_travel_world_command":
            return self.world_command(arguments.get("command", ""))

        if spec.executor is None:
            return {"success": False, "error": f"Tool is not callable: {name}"}
        try:
            env = self._get_env()
            output = self._wrap_env_output(spec.executor(env, arguments))
            env.results.append(output)
            return self._env_output_to_dict(output, command=name)
        except Exception as exc:
            return _format_error(exc)

    def world_command(self, command: str) -> dict[str, Any]:
        if not command:
            return {"success": False, "error": "Empty command."}
        try:
            env = self._get_env()
            output = env(command)
            return self._env_output_to_dict(output, command=command)
        except Exception as exc:
            result = _format_error(exc)
            result["command"] = command
            result["hint"] = (
                "Install requirements and download the ChinaTravel database into "
                "chinatravel/environment/database if this is an initialization error."
            )
            return result

    def list_splits(self) -> dict[str, Any]:
        split_dir = PROJECT_ROOT / "chinatravel" / "evaluation" / "default_splits"
        try:
            splits = sorted(path.stem for path in split_dir.glob("*.txt"))
            return {"success": True, "splits": splits}
        except Exception as exc:
            return _format_error(exc)

    def load_query(
        self,
        split: str,
        uid: str | None = None,
        oracle_translation: bool = False,
    ) -> dict[str, Any]:
        try:
            from chinatravel.data.load_datasets import load_query

            args = argparse.Namespace(splits=split, oracle_translation=oracle_translation, lang=self.lang)
            query_ids, query_data = load_query(args)
            if uid is not None:
                if uid not in query_data:
                    return {"success": False, "error": f"Query uid not found: {uid}"}
                return {
                    "success": True,
                    "split": split,
                    "query_ids": [uid],
                    "query": _jsonable(query_data[uid]),
                }
            return {
                "success": True,
                "split": split,
                "query_ids": query_ids,
                "query_count": len(query_ids),
            }
        except Exception as exc:
            return _format_error(exc)

    def _get_env(self) -> Any:
        if self._env is None:
            from chinatravel.environment.world_env import WorldEnv

            self._env = WorldEnv(lang=self.lang)
        return self._env

    def _wrap_env_output(self, value: Any) -> Any:
        if _is_env_output(value):
            return value
        return _AdapterOutput(True, value)

    def _env_output_to_dict(self, output: Any, *, command: str) -> dict[str, Any]:
        if hasattr(output, "__getitem__"):
            try:
                success = bool(output["success"])
                data = output["data"]
                return {
                    "success": success,
                    "command": command,
                    "text": str(output),
                    "data": _jsonable(data),
                }
            except Exception:
                pass
        return {"success": True, "command": command, "text": str(output), "data": _jsonable(output)}


def dumps_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
