"""Synthetic query generation utilities for ChinaTravel."""

__all__ = [
    "DEFAULT_REGISTRY",
    "ConstraintGeneratorRegistry",
    "FromPlansConfig",
    "SeedQueryConfig",
    "generate_from_plans",
    "generate_seed_queries",
]


def __getattr__(name):
    if name in {"FromPlansConfig", "SeedQueryConfig"}:
        from synthetic_query_generation import models

        return getattr(models, name)
    if name in {"DEFAULT_REGISTRY", "ConstraintGeneratorRegistry"}:
        from synthetic_query_generation import constraints

        return getattr(constraints, name)
    if name in {"generate_from_plans", "generate_seed_queries"}:
        from synthetic_query_generation import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
