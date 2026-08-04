"""Agent-facing wrapper around the ChinaTravel environment.

This module intentionally lives outside the ``chinatravel`` package.  It keeps
the benchmark code unchanged while exposing a stable, JSON-serializable tool
surface for agent runtimes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


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


def _literal(value: Any) -> str:
    return repr(value)


def _predicate(key: str, op: str, value: Any) -> str:
    if op == "eq":
        return f"lambda x: x == {_literal(value)}"
    if op == "ne":
        return f"lambda x: x != {_literal(value)}"
    if op == "contains":
        return f"lambda x: {_literal(value)} in str(x)"
    if op == "lt":
        return f"lambda x: x < {_literal(value)}"
    if op == "le":
        return f"lambda x: x <= {_literal(value)}"
    if op == "gt":
        return f"lambda x: x > {_literal(value)}"
    if op == "ge":
        return f"lambda x: x >= {_literal(value)}"
    raise ValueError(f"Unsupported filter op for {key}: {op}")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    command_builder: Callable[[dict[str, Any]], str] | None = None


def _schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": False,
    }


CITY = {
    "type": "string",
    "description": (
        "City name in the selected sandbox language, e.g. Shanghai for en or 上海 for zh"
    ),
}
POINT = {"type": "string", "description": "POI name; must match ChinaTravel data"}
TIME = {"type": "string", "description": "HH:MM"}
TOPK = {"type": "integer", "default": 10, "minimum": 1}
DIST = {"type": "number", "default": 2}
KEY = {"type": "string"}
OP = {"type": "string", "enum": ["eq", "ne", "contains", "lt", "le", "gt", "ge"]}
VALUE = {"description": "Filter value"}


def _simple_call(api_name: str, arg_names: list[str]) -> Callable[[dict[str, Any]], str]:
    def build(args: dict[str, Any]) -> str:
        return f"{api_name}({', '.join(_literal(args[name]) for name in arg_names)})"

    return build


def _select_call(api_name: str) -> Callable[[dict[str, Any]], str]:
    def build(args: dict[str, Any]) -> str:
        return (
            f"{api_name}("
            f"{_literal(args['city'])}, "
            f"{_literal(args['key'])}, "
            f"{_predicate(args['key'], args['op'], args['value'])})"
        )

    return build


TOOL_SPECS: dict[str, ToolSpec] = {
    "china_travel_world_command": ToolSpec(
        "china_travel_world_command",
        "Call the original ChinaTravel WorldEnv with a Python-call command string. Use only for advanced queries.",
        _schema(["command"], {"command": {"type": "string"}}),
    ),
    "china_travel_list_splits": ToolSpec(
        "china_travel_list_splits",
        "List locally available evaluation split names.",
        _schema([], {}),
    ),
    "china_travel_load_query": ToolSpec(
        "china_travel_load_query",
        "Load a ChinaTravel query by split and optional uid. Uses official loader when dependencies are installed.",
        _schema(
            ["split"],
            {
                "split": {"type": "string"},
                "uid": {"type": "string"},
                "oracle_translation": {"type": "boolean", "default": False},
            },
        ),
    ),
    "attractions_keys": ToolSpec(
        "attractions_keys",
        "Return attraction columns and value types for a city.",
        _schema(["city"], {"city": CITY}),
        _simple_call("attractions_keys", ["city"]),
    ),
    "attractions_select": ToolSpec(
        "attractions_select",
        "Filter city attractions with a structured predicate.",
        _schema(["city", "key", "op", "value"], {"city": CITY, "key": KEY, "op": OP, "value": VALUE}),
        _select_call("attractions_select"),
    ),
    "attractions_id_is_open": ToolSpec(
        "attractions_id_is_open",
        "Check whether an attraction id is open at a given time.",
        _schema(["city", "id", "time"], {"city": CITY, "id": {"type": "integer"}, "time": TIME}),
        _simple_call("attractions_id_is_open", ["city", "id", "time"]),
    ),
    "attractions_nearby": ToolSpec(
        "attractions_nearby",
        "Find nearby attractions around a POI.",
        _schema(["city", "point", "topk", "dist"], {"city": CITY, "point": POINT, "topk": TOPK, "dist": DIST}),
        _simple_call("attractions_nearby", ["city", "point", "topk", "dist"]),
    ),
    "attractions_types": ToolSpec(
        "attractions_types",
        "List attraction types in a city.",
        _schema(["city"], {"city": CITY}),
        _simple_call("attractions_types", ["city"]),
    ),
    "accommodations_keys": ToolSpec(
        "accommodations_keys",
        "Return accommodation columns and value types for a city.",
        _schema(["city"], {"city": CITY}),
        _simple_call("accommodations_keys", ["city"]),
    ),
    "accommodations_select": ToolSpec(
        "accommodations_select",
        "Filter city accommodations with a structured predicate.",
        _schema(["city", "key", "op", "value"], {"city": CITY, "key": KEY, "op": OP, "value": VALUE}),
        _select_call("accommodations_select"),
    ),
    "accommodations_nearby": ToolSpec(
        "accommodations_nearby",
        "Find nearby accommodations around a POI.",
        _schema(["city", "point", "topk", "dist"], {"city": CITY, "point": POINT, "topk": TOPK, "dist": {"type": "number", "default": 5}}),
        _simple_call("accommodations_nearby", ["city", "point", "topk", "dist"]),
    ),
    "restaurants_keys": ToolSpec(
        "restaurants_keys",
        "Return restaurant columns and value types for a city.",
        _schema(["city"], {"city": CITY}),
        _simple_call("restaurants_keys", ["city"]),
    ),
    "restaurants_select": ToolSpec(
        "restaurants_select",
        "Filter city restaurants with a structured predicate.",
        _schema(["city", "key", "op", "value"], {"city": CITY, "key": KEY, "op": OP, "value": VALUE}),
        _select_call("restaurants_select"),
    ),
    "restaurants_id_is_open": ToolSpec(
        "restaurants_id_is_open",
        "Check whether a restaurant id is open at a given time.",
        _schema(["city", "id", "time"], {"city": CITY, "id": {"type": "integer"}, "time": TIME}),
        _simple_call("restaurants_id_is_open", ["city", "id", "time"]),
    ),
    "restaurants_nearby": ToolSpec(
        "restaurants_nearby",
        "Find nearby restaurants around a POI.",
        _schema(["city", "point", "topk", "dist"], {"city": CITY, "point": POINT, "topk": TOPK, "dist": DIST}),
        _simple_call("restaurants_nearby", ["city", "point", "topk", "dist"]),
    ),
    "restaurants_with_recommended_food": ToolSpec(
        "restaurants_with_recommended_food",
        "Find restaurants whose recommended dishes contain a food name.",
        _schema(["city", "food"], {"city": CITY, "food": {"type": "string"}}),
        _simple_call("restaurants_with_recommended_food", ["city", "food"]),
    ),
    "restaurants_cuisine": ToolSpec(
        "restaurants_cuisine",
        "List restaurant cuisines in a city.",
        _schema(["city"], {"city": CITY}),
        _simple_call("restaurants_cuisine", ["city"]),
    ),
    "goto": ToolSpec(
        "goto",
        "Query in-city transportation between two POIs.",
        _schema(
            ["city", "start", "end", "start_time", "transport_type"],
            {
                "city": CITY,
                "start": POINT,
                "end": POINT,
                "start_time": TIME,
                "transport_type": {"type": "string", "enum": ["walk", "taxi", "metro"]},
            },
        ),
        _simple_call("goto", ["city", "start", "end", "start_time", "transport_type"]),
    ),
    "intercity_transport_select": ToolSpec(
        "intercity_transport_select",
        "Query train or airplane options between two cities.",
        _schema(
            ["start_city", "end_city", "intercity_type"],
            {
                "start_city": CITY,
                "end_city": CITY,
                "intercity_type": {"type": "string", "enum": ["train", "airplane"]},
                "earliest_leave_time": {"type": "string", "default": "00:00"},
            },
        ),
        lambda args: (
            "intercity_transport_select("
            f"{_literal(args['start_city'])}, {_literal(args['end_city'])}, "
            f"{_literal(args['intercity_type'])}, {_literal(args.get('earliest_leave_time', '00:00'))})"
        ),
    ),
    "poi_lat_lon_search": ToolSpec(
        "poi_lat_lon_search",
        "Look up a POI coordinate in a city.",
        _schema(["city", "name"], {"city": CITY, "name": POINT}),
        _simple_call("poi_lat_lon_search", ["city", "name"]),
    ),
    "next_page": ToolSpec(
        "next_page",
        "Return the next page for the last WorldEnv dataframe result.",
        _schema([], {}),
        lambda args: "next_page()",
    ),
}


class ChinaTravelEnvAdapter:
    def __init__(self, lang: str | None = None) -> None:
        self.lang = _normalize_adapter_lang(lang)
        self._env: Any | None = None

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "inputSchema": spec.input_schema,
            }
            for spec in TOOL_SPECS.values()
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        if name not in TOOL_SPECS:
            return {"success": False, "error": f"Unknown tool: {name}"}

        if name == "china_travel_list_splits":
            return self.list_splits()
        if name == "china_travel_load_query":
            return self.load_query(**arguments)
        if name == "china_travel_world_command":
            return self.world_command(arguments.get("command", ""))

        spec = TOOL_SPECS[name]
        if spec.command_builder is None:
            return {"success": False, "error": f"Tool is not callable: {name}"}
        try:
            command = spec.command_builder(arguments)
            return self.world_command(command)
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
