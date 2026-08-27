"""Small strict-value helpers for the resolved snapshot contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re
from typing import Any, NoReturn


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ROLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


class ResolvedSnapshotValidationError(ValueError):
    """Raised when a resolved snapshot is ambiguous or internally invalid."""

    def __init__(self, path: str, message: str, code: str = "invalid") -> None:
        self.path = path
        self.message = message
        self.code = code
        super().__init__(f"{path}: {message}")


def fail(path: str, message: str, code: str = "invalid") -> NoReturn:
    raise ResolvedSnapshotValidationError(path, message, code)


def object_exact(
    value: Any,
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    path: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        fail(path, "must be a JSON object", "type")
    keys = set(value)
    non_strings = [key for key in keys if not isinstance(key, str)]
    if non_strings:
        fail(path, "all object keys must be strings", "type")
    missing = sorted(required - keys)
    if missing:
        fail(f"{path}.{missing[0]}", "field is required", "required")
    unknown = sorted(keys - required - optional)
    if unknown:
        fail(f"{path}.{unknown[0]}", "authority field is unsupported", "unknown_field")
    return value


def array(value: Any, path: str, *, maximum: int | None = None) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        fail(path, "must be a JSON array", "type")
    values = list(value)
    if maximum is not None and len(values) > maximum:
        fail(path, f"must contain at most {maximum} items", "length")
    return values


def safe_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        fail(path, "must be a safe identifier", "id")
    return value


def role(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _ROLE.fullmatch(value):
        fail(path, "must be a canonical role token", "role")
    return value


def sha256(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        fail(path, "must be a lowercase SHA-256", "hash")
    return value


def version(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        fail(path, "must be a safe version token", "version")
    return value


def text(
    value: Any,
    path: str,
    *,
    maximum: int,
    nonblank: bool = False,
) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        fail(path, f"must be a string of at most {maximum} characters", "type")
    if nonblank and not value.strip():
        fail(path, "must not be blank", "length")
    return value


def integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        fail(path, f"must be an integer >= {minimum}", "type")
    return value


def finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(path, "must be a finite number", "type")
    number = float(value)
    if not math.isfinite(number):
        fail(path, "must be a finite number", "finite")
    return number


def bounded_number(value: Any, path: str, minimum: float, maximum: float) -> float:
    number = finite(value, path)
    if not minimum <= number <= maximum:
        fail(path, f"must be between {minimum} and {maximum}", "bounds")
    return number


def point(value: Any, path: str, width: int, height: int) -> tuple[float, float]:
    values = array(value, path)
    if len(values) != 2:
        fail(path, "must contain exactly two coordinates", "shape")
    x, y = finite(values[0], f"{path}[0]"), finite(values[1], f"{path}[1]")
    if not 0 <= x <= width or not 0 <= y <= height:
        fail(path, "must lie inside the canvas", "bounds")
    return x, y


def exact_string_list(
    value: Any,
    path: str,
    *,
    allowed: set[str] | None = None,
    sorted_values: bool = False,
    maximum: int | None = None,
) -> list[str]:
    values = array(value, path, maximum=maximum)
    for index, item in enumerate(values):
        if not isinstance(item, str):
            fail(f"{path}[{index}]", "must be a string", "type")
        if allowed is not None and item not in allowed:
            fail(f"{path}[{index}]", "contains an unsupported value", "enum")
    if len(values) != len(set(values)):
        fail(path, "must contain unique values", "duplicate")
    if sorted_values and values != sorted(values):
        fail(path, "must be sorted", "order")
    return values


def contract(value: Any, path: str, name: str) -> None:
    item = object_exact(value, required={"name", "version"}, path=path)
    if item.get("name") != name or item.get("version") != 1:
        fail(path, "contract descriptor is unsupported", "version")
