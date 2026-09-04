try:
    from json_repair import repair_json as _repair_json
except ImportError:
    def repair_json(text: str, ensure_ascii: bool = False, **kwargs) -> str:
        return text
else:
    def repair_json(text: str, ensure_ascii: bool = False, **kwargs) -> str:
        return _repair_json(text, ensure_ascii=ensure_ascii, **kwargs)
