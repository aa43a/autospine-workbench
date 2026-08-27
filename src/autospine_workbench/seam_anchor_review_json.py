"""Bounded exact-JSON helpers shared by P10.5b public contracts."""

from __future__ import annotations

import json
import math
from typing import Any


def require_bounded_json_tree(
    value: Any, *, max_nodes: int, max_depth: int,
) -> None:
    """Reject subclasses, nonfinite values, and excessive trees iteratively."""

    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes or depth > max_depth:
            raise ValueError("JSON structure exceeds its limit")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("JSON object keys must be strings")
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("JSON numbers must be finite")
        elif type(item) not in (str, int, float, bool, type(None)):
            raise ValueError("Value is not exact JSON")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_copy(value: Any) -> Any:
    return json.loads(canonical_json_bytes(value).decode("utf-8"))
