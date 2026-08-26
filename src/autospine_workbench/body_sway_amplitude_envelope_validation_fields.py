"""Small generic field helpers for amplitude-envelope validation."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any


FORBIDDEN_KEYS = {"path", "tracks", "keys", "animations"}


class BodySwayAmplitudeEnvelopeFieldError(ValueError):
    """Raised when one generic envelope field is inconsistent."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def require_fixed(value: Any, expected: Any, label: str) -> None:
    if canonical_bytes(value) != canonical_bytes(expected):
        raise BodySwayAmplitudeEnvelopeFieldError(
            f"Amplitude envelope {label} is unsupported"
        )


def contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            key in FORBIDDEN_KEYS or contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_forbidden_key(item) for item in value)
    return False


def bounded_integer(
    value: Any, minimum: int, maximum: int, label: str,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise BodySwayAmplitudeEnvelopeFieldError(
            f"Amplitude envelope {label} is invalid"
        )
    return value


def require_reviewed_probe(row: Mapping[str, Any], report: Mapping[str, Any]) -> None:
    """Bind reviewed-gain evidence to the embedded exact P10.2 report."""

    schedule = report["schedule"]
    expected = (
        schedule["sample_count"], schedule["tick_schedule_sha256"],
        report["sample_stream"]["sample_stream_sha256"], report["checks"],
        "sampled_structural_passed",
    )
    actual = (
        row["sample_count"], row["tick_schedule_sha256"],
        row["sample_stream_sha256"], row["checks"], row["status"],
    )
    if canonical_bytes(actual) != canonical_bytes(expected):
        raise BodySwayAmplitudeEnvelopeFieldError(
            "Reviewed gain differs from the admitted P10.2 report"
        )
