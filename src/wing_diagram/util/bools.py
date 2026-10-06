from typing import Any


def is_non_empty_string(obj: Any) -> bool:  #pyright: ignore [reportAny]
    if isinstance(obj, str):
        return len(obj) > 0
    return False