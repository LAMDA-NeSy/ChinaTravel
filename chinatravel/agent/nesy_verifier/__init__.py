__all__ = ["LLMModuloAgent"]


def __getattr__(name):
    if name == "LLMModuloAgent":
        from .llm_modulo import LLMModuloAgent

        return LLMModuloAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
