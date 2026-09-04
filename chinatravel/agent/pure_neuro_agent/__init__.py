__all__ = ["ActAgent", "ReActAgent"]


def __getattr__(name):
    if name in __all__:
        from .pure_neuro_agent import ActAgent, ReActAgent

        return {"ActAgent": ActAgent, "ReActAgent": ReActAgent}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
