"""Agent-facing wrapper around the ChinaTravel environment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from agent_env.tools import TOOL_SPECS, normalize_arguments, validate_arguments


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAGE_SIZE = 10


def _normalize_adapter_lang(lang: str | None = None) -> str:
    value = str(lang or os.environ.get("CHINATRAVEL_LANG") or "zh").lower()
    if value not in {"zh", "en"}:
        raise ValueError("ChinaTravel language must be 'zh' or 'en'.")
    return value


def _ensure_project_on_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


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


class ChinaTravelEnvAdapter:
    def __init__(self, lang: str | None = None) -> None:
        self.lang = _normalize_adapter_lang(lang)
        self._env: Any | None = None

    def list_tools(self, format: str = "mcp") -> list[dict[str, Any]]:
        formatters = {
            "mcp": "to_mcp_tool",
            "openai": "to_openai_tool",
            "openai-responses": "to_openai_responses_tool",
            "responses": "to_openai_responses_tool",
        }
        normalized_format = str(format).strip().lower()
        formatter_name = formatters.get(normalized_format)
        if formatter_name is None:
            raise ValueError(
                "Unsupported tool format: {}. Expected one of {}.".format(
                    format,
                    sorted(formatters),
                )
            )
        return [
            getattr(spec, formatter_name)()
            for spec in TOOL_SPECS.values()
        ]

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _format_error(ValueError("Tool arguments must be a JSON object."))
        spec = TOOL_SPECS.get(name)
        if spec is None:
            return {"success": False, "error": f"Unknown tool: {name}"}

        arguments = normalize_arguments(spec, arguments)
        validation_errors = validate_arguments(spec, arguments)
        if validation_errors:
            result = _format_error(ValueError("; ".join(validation_errors)))
            result["validation_errors"] = validation_errors
            return result

        if name == "china_travel_list_splits":
            return self.list_splits()
        if name == "china_travel_load_query":
            return self.load_query(**arguments)
        if name == "china_travel_world_command":
            return self.world_command(arguments.get("command", ""))
        if spec.executor is None:
            return {"success": False, "error": f"Tool is not callable: {name}"}

        command = "{}({})".format(
            name,
            json.dumps(arguments, ensure_ascii=False, sort_keys=True),
        )
        try:
            env = self._get_env()
            output = spec.executor(env, arguments)
            output = self._record_env_output(env, output)
            return self._env_output_to_dict(output, command=command)
        except Exception as exc:
            result = _format_error(exc)
            result["command"] = command
            return result

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
            _ensure_project_on_path()
            from chinatravel.data.load_datasets import load_query

            args = argparse.Namespace(
                splits=split,
                oracle_translation=oracle_translation,
                lang=self.lang,
            )
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
            _ensure_project_on_path()
            from chinatravel.environment.world_env import WorldEnv

            self._env = WorldEnv(lang=self.lang)
        return self._env

    @staticmethod
    def _record_env_output(env: Any, output: Any) -> Any:
        if not hasattr(env, "results"):
            return output
        from chinatravel.environment.world_env import EnvOutput

        if not isinstance(output, EnvOutput):
            output = EnvOutput(True, output)
        env.results.append(output)
        return output

    def _env_output_to_dict(
        self,
        output: Any,
        *,
        command: str,
    ) -> dict[str, Any]:
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
        return {
            "success": True,
            "command": command,
            "text": str(output),
            "data": _jsonable(output),
        }


def dumps_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
