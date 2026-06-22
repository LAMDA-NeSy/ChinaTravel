"""Restricted evaluators for ChinaTravel symbolic verification DSL."""

from __future__ import annotations

import ast
import operator
from typing import Any


DEFAULT_DSL_BUILTINS = {
    "abs": abs,
    "bool": bool,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "set": set,
    "str": str,
    "sum": sum,
}

_ALLOWED_MUTATING_METHODS = {"add", "append", "extend", "update"}
_ALLOWED_NODES = (
    ast.Module,
    ast.Expr,
    ast.Assign,
    ast.AugAssign,
    ast.For,
    ast.If,
    ast.Pass,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.Call,
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
    ast.BinOp,
    ast.IfExp,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Dict,
    ast.Subscript,
    ast.Slice,
    ast.Attribute,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.BitAnd,
    ast.BitOr,
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)


class DslValidationError(ValueError):
    pass


def _target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for item in node.elts:
            names.update(_target_names(item))
        return names
    return set()


def _bound_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(_target_names(target))
        elif isinstance(node, ast.AugAssign):
            names.update(_target_names(node.target))
        elif isinstance(node, ast.For):
            names.update(_target_names(node.target))
    return names


def validate_dsl_code(
    code: str,
    *,
    allowed_names: set[str],
    allowed_builtins: set[str] | None = None,
) -> ast.Module:
    allowed_builtins = set(DEFAULT_DSL_BUILTINS if allowed_builtins is None else allowed_builtins)
    tree = ast.parse(code, mode="exec")
    names = set(allowed_names) | _bound_names(tree)

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise DslValidationError(f"Unsupported DSL syntax: {node.__class__.__name__}")
        if isinstance(node, ast.Name):
            if (
                isinstance(node.ctx, ast.Load)
                and node.id not in names
                and node.id not in allowed_builtins
            ):
                raise DslValidationError(f"Unknown DSL name: {node.id}")
        elif isinstance(node, ast.Call):
            _validate_call(node, names, allowed_builtins)
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                raise DslValidationError("Dunder attributes are not allowed in DSL code.")
    return tree


def _validate_call(node: ast.Call, allowed_names: set[str], allowed_builtins: set[str]) -> None:
    if isinstance(node.func, ast.Name):
        if node.func.id not in allowed_names and node.func.id not in allowed_builtins:
            raise DslValidationError(f"Unknown DSL callable: {node.func.id}")
        return
    if isinstance(node.func, ast.Attribute):
        if node.func.attr not in _ALLOWED_MUTATING_METHODS:
            raise DslValidationError(f"Unsupported DSL method call: {node.func.attr}")
        if not isinstance(node.func.value, ast.Name) or node.func.value.id not in allowed_names:
            raise DslValidationError("DSL method calls are limited to local containers.")
        return
    raise DslValidationError("Unsupported DSL callable expression.")


def execute_dsl_code(
    code: str,
    variables: dict[str, Any],
    *,
    allowed_builtins: dict[str, Any] | None = None,
) -> dict[str, Any]:
    builtins = dict(DEFAULT_DSL_BUILTINS)
    if allowed_builtins is not None:
        builtins.update(allowed_builtins)
    allowed_names = set(variables)
    tree = validate_dsl_code(
        code,
        allowed_names=allowed_names,
        allowed_builtins=set(builtins),
    )
    bound_names = _bound_names(tree)
    sandbox = dict(variables)
    exec(
        compile(tree, "<chinatravel-dsl>", "exec"),
        {"__builtins__": builtins},
        sandbox,
    )
    keep_names = allowed_names | bound_names
    for key, value in sandbox.items():
        if key.startswith("__"):
            continue
        if key in keep_names:
            variables[key] = value
    return variables


def evaluate_expression(expression: str, variables: dict[str, Any]) -> Any:
    tree = ast.parse(expression, mode="eval")
    return _eval_expr(tree.body, variables)


def _eval_expr(node: ast.AST, variables: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        raise DslValidationError(f"Unknown expression name: {node.id}")
    if isinstance(node, ast.List):
        return [_eval_expr(item, variables) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_expr(item, variables) for item in node.elts)
    if isinstance(node, ast.Set):
        return {_eval_expr(item, variables) for item in node.elts}
    if isinstance(node, ast.Dict):
        return {
            _eval_expr(key, variables): _eval_expr(value, variables)
            for key, value in zip(node.keys, node.values)
        }
    if isinstance(node, ast.UnaryOp):
        value = _eval_expr(node.operand, variables)
        if isinstance(node.op, ast.Not):
            return not value
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return +value
        raise DslValidationError("Unsupported unary expression.")
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = True
            for value_node in node.values:
                result = _eval_expr(value_node, variables)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for value_node in node.values:
                result = _eval_expr(value_node, variables)
                if result:
                    return result
            return result
        raise DslValidationError("Unsupported boolean expression.")
    if isinstance(node, ast.BinOp):
        return _eval_binary(node, variables)
    if isinstance(node, ast.Compare):
        return _eval_compare(node, variables)
    if isinstance(node, ast.Subscript):
        return _eval_expr(node.value, variables)[_eval_slice(node.slice, variables)]
    raise DslValidationError(f"Unsupported expression syntax: {node.__class__.__name__}")


def _eval_slice(node: ast.AST, variables: dict[str, Any]) -> Any:
    if isinstance(node, ast.Slice):
        lower = _eval_expr(node.lower, variables) if node.lower else None
        upper = _eval_expr(node.upper, variables) if node.upper else None
        step = _eval_expr(node.step, variables) if node.step else None
        return slice(lower, upper, step)
    return _eval_expr(node, variables)


def _eval_binary(node: ast.BinOp, variables: dict[str, Any]) -> Any:
    operations = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.BitAnd: operator.and_,
        ast.BitOr: operator.or_,
    }
    for op_type, op_func in operations.items():
        if isinstance(node.op, op_type):
            return op_func(_eval_expr(node.left, variables), _eval_expr(node.right, variables))
    raise DslValidationError("Unsupported binary expression.")


def _eval_compare(node: ast.Compare, variables: dict[str, Any]) -> bool:
    left = _eval_expr(node.left, variables)
    for op, comparator in zip(node.ops, node.comparators):
        right = _eval_expr(comparator, variables)
        if not _compare(left, op, right):
            return False
        left = right
    return True


def _compare(left: Any, op: ast.cmpop, right: Any) -> bool:
    comparisons = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
    }
    if isinstance(op, ast.In):
        return left in right
    if isinstance(op, ast.NotIn):
        return left not in right
    for op_type, op_func in comparisons.items():
        if isinstance(op, op_type):
            return op_func(left, right)
    raise DslValidationError("Unsupported comparison expression.")
