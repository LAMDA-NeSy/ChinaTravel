"""Declarative tool definitions for ChinaTravel agent runtimes."""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable


_MISSING = object()


def _predicate(key: str, op: str, value: Any) -> Callable[[Any], bool]:
    if op == "eq":
        return lambda x: x == value
    if op == "ne":
        return lambda x: x != value
    if op == "contains":
        needle = str(value)
        return lambda x: needle in str(x)
    if op == "lt":
        return lambda x: x < value
    if op == "le":
        return lambda x: x <= value
    if op == "gt":
        return lambda x: x > value
    if op == "ge":
        return lambda x: x >= value
    raise ValueError(f"Unsupported filter op for {key}: {op}")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    executor: Callable[[Any, dict[str, Any]], Any] | None = None

    def to_mcp_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    def to_openai_tool(self) -> dict[str, Any]:
        function = {
            "name": self.name,
            "description": self.description,
            "parameters": self._openai_parameters(),
        }
        if self._openai_strict():
            function["strict"] = True
        return {
            "type": "function",
            "function": function,
        }

    def to_openai_responses_tool(self) -> dict[str, Any]:
        tool = {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self._openai_parameters(),
            "strict": self._openai_strict(),
        }
        return tool

    def _openai_parameters(self) -> dict[str, Any]:
        return _strict_schema(self.input_schema) if self._openai_strict() else self.input_schema

    def _openai_strict(self) -> bool:
        return _truthy_env("CHINATRAVEL_OPENAI_STRICT_TOOLS")


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes", "on"}


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    strict_schema = deepcopy(schema)
    properties = strict_schema.get("properties", {})
    original_required = set(schema.get("required", []))
    strict_schema["required"] = list(properties)
    _drop_defaults(strict_schema)
    for field, field_schema in properties.items():
        if field in original_required or not isinstance(field_schema, dict):
            continue
        if "anyOf" in field_schema:
            any_of = list(field_schema["anyOf"])
            if not any(item.get("type") == "null" for item in any_of if isinstance(item, dict)):
                any_of.append({"type": "null"})
            field_schema["anyOf"] = any_of
        elif "type" in field_schema:
            field_type = field_schema["type"]
            if isinstance(field_type, list):
                if "null" not in field_type:
                    field_schema["type"] = [*field_type, "null"]
            else:
                field_schema["type"] = [field_type, "null"]
        else:
            field_schema["anyOf"] = [{"type": "string"}, {"type": "number"}, {"type": "boolean"}, {"type": "null"}]
    return strict_schema


def _drop_defaults(schema: dict[str, Any]) -> None:
    schema.pop("default", None)
    for value in schema.values():
        if isinstance(value, dict):
            _drop_defaults(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _drop_defaults(item)


def _schema_has_key(schema: Any, key: str) -> bool:
    if isinstance(schema, dict):
        return key in schema or any(_schema_has_key(value, key) for value in schema.values())
    if isinstance(schema, list):
        return any(_schema_has_key(item, key) for item in schema)
    return False


def _json_type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "null":
        return value is None
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    return True


def normalize_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop strict-tool nulls for optional fields so local defaults still apply."""

    required = set(spec.input_schema.get("required", []))
    return {
        key: value
        for key, value in arguments.items()
        if value is not None or key in required
    }


def validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> list[str]:
    """Validate tool arguments against the declared JSON schema subset."""

    errors: list[str] = []
    schema = spec.input_schema
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for field in required:
        if field not in arguments:
            errors.append(f"Missing required argument: {field}")

    if schema.get("additionalProperties") is False:
        for field in arguments:
            if field not in properties:
                errors.append(f"Unexpected argument: {field}")

    for field, value in arguments.items():
        field_schema = properties.get(field)
        if not isinstance(field_schema, dict):
            continue
        expected_type = field_schema.get("type")
        if expected_type is None and isinstance(field_schema.get("anyOf"), list):
            allowed_types = [
                item.get("type")
                for item in field_schema["anyOf"]
                if isinstance(item, dict) and isinstance(item.get("type"), str)
            ]
            if allowed_types and not any(_json_type_matches(value, item) for item in allowed_types):
                errors.append(f"Invalid type for {field}: expected one of {allowed_types}")
                continue
        if isinstance(expected_type, str) and not _json_type_matches(value, expected_type):
            errors.append(f"Invalid type for {field}: expected {expected_type}")
            continue
        enum = field_schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            errors.append(f"Invalid value for {field}: expected one of {enum}")
        minimum = field_schema.get("minimum")
        if minimum is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
            if value < minimum:
                errors.append(f"Invalid value for {field}: must be >= {minimum}")
    return errors


def _schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": False,
    }


CITY = {"type": "string", "description": "City name matching the selected ChinaTravel language, e.g. 上海 or Shanghai"}
POINT = {"type": "string", "description": "POI name; must match ChinaTravel data"}
TIME = {"type": "string", "description": "HH:MM"}
TOPK = {"type": "integer", "default": 10, "minimum": 1}
DIST = {"type": "number", "default": 2}
KEY = {"type": "string"}
OP = {"type": "string", "enum": ["eq", "ne", "contains", "lt", "le", "gt", "ge"]}
VALUE = {
    "description": "Filter value",
    "anyOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "integer"},
        {"type": "boolean"},
    ],
}


def _argument(args: dict[str, Any], name: str, default: Any = _MISSING) -> Any:
    if name in args:
        return args[name]
    if default is not _MISSING:
        return default
    raise KeyError(f"Missing required argument: {name}")


def _component_call(
    component_name: str,
    method_name: str,
    arg_names: list[str],
    *,
    defaults: dict[str, Any] | None = None,
) -> Callable[[Any, dict[str, Any]], Any]:
    defaults = defaults or {}

    def run(env: Any, args: dict[str, Any]) -> Any:
        method = getattr(getattr(env, component_name), method_name)
        return method(
            *[
                _argument(args, name, defaults.get(name, _MISSING))
                for name in arg_names
            ]
        )

    return run


def _select_call(component_name: str) -> Callable[[Any, dict[str, Any]], Any]:
    def run(env: Any, args: dict[str, Any]) -> Any:
        component = getattr(env, component_name)
        return component.select(
            args["city"],
            args["key"],
            _predicate(args["key"], args["op"], args["value"]),
        )

    return run


TOOL_SPECS: dict[str, ToolSpec] = {
    "china_travel_world_command": ToolSpec(
        "china_travel_world_command",
        "Call the original ChinaTravel WorldEnv with a restricted function-call command string. Use only for advanced queries.",
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
        _component_call("attractions", "keys", ["city"]),
    ),
    "attractions_select": ToolSpec(
        "attractions_select",
        "Filter city attractions with a structured predicate.",
        _schema(["city", "key", "op", "value"], {"city": CITY, "key": KEY, "op": OP, "value": VALUE}),
        _select_call("attractions"),
    ),
    "attractions_id_is_open": ToolSpec(
        "attractions_id_is_open",
        "Check whether an attraction id is open at a given time.",
        _schema(["city", "id", "time"], {"city": CITY, "id": {"type": "integer"}, "time": TIME}),
        _component_call("attractions", "id_is_open", ["city", "id", "time"]),
    ),
    "attractions_nearby": ToolSpec(
        "attractions_nearby",
        "Find nearby attractions around a POI.",
        _schema(["city", "point"], {"city": CITY, "point": POINT, "topk": TOPK, "dist": DIST}),
        _component_call("attractions", "nearby", ["city", "point", "topk", "dist"], defaults={"topk": 10, "dist": 2}),
    ),
    "attractions_types": ToolSpec(
        "attractions_types",
        "List attraction types in a city.",
        _schema(["city"], {"city": CITY}),
        _component_call("attractions", "get_type_list", ["city"]),
    ),
    "accommodations_keys": ToolSpec(
        "accommodations_keys",
        "Return accommodation columns and value types for a city.",
        _schema(["city"], {"city": CITY}),
        _component_call("accommodations", "keys", ["city"]),
    ),
    "accommodations_select": ToolSpec(
        "accommodations_select",
        "Filter city accommodations with a structured predicate.",
        _schema(["city", "key", "op", "value"], {"city": CITY, "key": KEY, "op": OP, "value": VALUE}),
        _select_call("accommodations"),
    ),
    "accommodations_nearby": ToolSpec(
        "accommodations_nearby",
        "Find nearby accommodations around a POI.",
        _schema(
            ["city", "point"],
            {"city": CITY, "point": POINT, "topk": TOPK, "dist": {"type": "number", "default": 5}},
        ),
        _component_call("accommodations", "nearby", ["city", "point", "topk", "dist"], defaults={"topk": 10, "dist": 5}),
    ),
    "restaurants_keys": ToolSpec(
        "restaurants_keys",
        "Return restaurant columns and value types for a city.",
        _schema(["city"], {"city": CITY}),
        _component_call("restaurants", "keys", ["city"]),
    ),
    "restaurants_select": ToolSpec(
        "restaurants_select",
        "Filter city restaurants with a structured predicate.",
        _schema(["city", "key", "op", "value"], {"city": CITY, "key": KEY, "op": OP, "value": VALUE}),
        _select_call("restaurants"),
    ),
    "restaurants_id_is_open": ToolSpec(
        "restaurants_id_is_open",
        "Check whether a restaurant id is open at a given time.",
        _schema(["city", "id", "time"], {"city": CITY, "id": {"type": "integer"}, "time": TIME}),
        _component_call("restaurants", "id_is_open", ["city", "id", "time"]),
    ),
    "restaurants_nearby": ToolSpec(
        "restaurants_nearby",
        "Find nearby restaurants around a POI.",
        _schema(["city", "point"], {"city": CITY, "point": POINT, "topk": TOPK, "dist": DIST}),
        _component_call("restaurants", "nearby", ["city", "point", "topk", "dist"], defaults={"topk": 10, "dist": 2}),
    ),
    "restaurants_with_recommended_food": ToolSpec(
        "restaurants_with_recommended_food",
        "Find restaurants whose recommended dishes contain a food name.",
        _schema(["city", "food"], {"city": CITY, "food": {"type": "string"}}),
        _component_call("restaurants", "restaurants_with_recommended_food", ["city", "food"]),
    ),
    "restaurants_cuisine": ToolSpec(
        "restaurants_cuisine",
        "List restaurant cuisines in a city.",
        _schema(["city"], {"city": CITY}),
        _component_call("restaurants", "get_cuisine_list", ["city"]),
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
        _component_call("transportation", "goto", ["city", "start", "end", "start_time", "transport_type"]),
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
        lambda env, args: env.intercitytransport.select(
            args["start_city"],
            args["end_city"],
            args["intercity_type"],
            args.get("earliest_leave_time", "00:00"),
        ),
    ),
    "poi_lat_lon_search": ToolSpec(
        "poi_lat_lon_search",
        "Look up a POI coordinate in a city.",
        _schema(["city", "name"], {"city": CITY, "name": POINT}),
        _component_call("poi", "search", ["city", "name"]),
    ),
    "next_page": ToolSpec(
        "next_page",
        "Return the next page for the last WorldEnv dataframe result.",
        _schema([], {}),
        lambda env, args: env.next_page(),
    ),
}


def validate_tool_specs(tool_specs: dict[str, ToolSpec] | None = None) -> list[str]:
    tool_specs = tool_specs or TOOL_SPECS
    errors: list[str] = []
    for key, spec in tool_specs.items():
        if key != spec.name:
            errors.append(f"{key}: registry key does not match tool name {spec.name!r}")
        schema = spec.input_schema
        if schema.get("type") != "object":
            errors.append(f"{spec.name}: input schema must be an object")
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            errors.append(f"{spec.name}: input schema properties must be an object")
            properties = {}
        required = schema.get("required", [])
        if not isinstance(required, list):
            errors.append(f"{spec.name}: input schema required must be a list")
            required = []
        for field in required:
            if field not in properties:
                errors.append(f"{spec.name}: required field {field!r} is missing from properties")

        openai_tool = spec.to_openai_tool()
        function = openai_tool.get("function")
        if openai_tool.get("type") != "function" or not isinstance(function, dict):
            errors.append(f"{spec.name}: OpenAI tool schema must wrap a function")
            continue
        if function.get("name") != spec.name:
            errors.append(f"{spec.name}: OpenAI function name mismatch")
        if function.get("strict") is True:
            parameters = function.get("parameters")
            strict_required = set(parameters.get("required", [])) if isinstance(parameters, dict) else set()
            if strict_required != set(properties):
                errors.append(f"{spec.name}: strict OpenAI schema must require every property")
            if not isinstance(parameters, dict) or parameters.get("additionalProperties") is not False:
                errors.append(f"{spec.name}: strict OpenAI schema requires additionalProperties=false")
            if _schema_has_key(parameters, "default"):
                errors.append(f"{spec.name}: strict OpenAI schema must not include defaults")
        elif function.get("parameters") is not schema:
            errors.append(f"{spec.name}: OpenAI function parameters must reuse input_schema")

        responses_tool = spec.to_openai_responses_tool()
        if responses_tool.get("type") != "function" or "function" in responses_tool:
            errors.append(f"{spec.name}: OpenAI Responses tool schema must be a top-level function tool")
            continue
        if responses_tool.get("name") != spec.name:
            errors.append(f"{spec.name}: OpenAI Responses function name mismatch")
        if responses_tool.get("strict") is True:
            parameters = responses_tool.get("parameters")
            strict_required = set(parameters.get("required", [])) if isinstance(parameters, dict) else set()
            if strict_required != set(properties):
                errors.append(f"{spec.name}: strict Responses schema must require every property")
            if not isinstance(parameters, dict) or parameters.get("additionalProperties") is not False:
                errors.append(f"{spec.name}: strict Responses schema requires additionalProperties=false")
            if _schema_has_key(parameters, "default"):
                errors.append(f"{spec.name}: strict Responses schema must not include defaults")
        elif responses_tool.get("parameters") is not schema:
            errors.append(f"{spec.name}: OpenAI Responses parameters must reuse input_schema")
    return errors
