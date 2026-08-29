"""Type-sensitive comparisons for already validated JSON subcontracts."""

from __future__ import annotations

import json
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Preserve JSON numeric spelling distinctions represented by Python types."""

    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def exact_json_equal(left: Any, right: Any) -> bool:
    """Compare validated JSON values without Python's int/float coercion."""

    return canonical_json_bytes(left) == canonical_json_bytes(right)
