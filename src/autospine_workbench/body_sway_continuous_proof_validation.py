"""Strict semantic validation for P10.4b2 continuous proof evidence."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_continuous_proof_analysis import (
    BodySwayContinuousProofAnalysisError,
    analyze_body_sway_continuous_source,
)
from .body_sway_continuous_proof_profile import (
    MAX_DOCUMENT_BYTES,
    body_sway_continuous_proof_analyzer_profile,
    body_sway_continuous_proof_release_gate,
)
from .body_sway_continuous_proof_source import (
    BodySwayContinuousSourceError,
    require_body_sway_continuous_source,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-continuous-preview-proof"
FORMAT_VERSION = 1
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "problem", "segments", "analyzer", "claims", "status",
    "release_gate", "summary",
}
_ANALYSIS_FIELDS = {"problem", "segments", "claims", "status", "summary"}


class BodySwayContinuousProofValidationError(ValueError):
    """Raised when continuous evidence is detached, forged, or overclaims."""


def require_body_sway_continuous_proof(
    document: Mapping[str, Any],
) -> None:
    """Recompute the complete source problem and every interval result."""

    try:
        root = _bounded_object_copy(document, "continuous proof")
        if set(root) != _TOP:
            raise BodySwayContinuousProofValidationError(
                "Continuous proof fields are unsupported"
            )
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise BodySwayContinuousProofValidationError(
                "Continuous proof format is unsupported"
            )
        source = require_body_sway_continuous_source(root.get("source"))
        candidate = source["amplitude_envelope_candidate"]
        if root.get("project_id") != candidate["project_id"] \
                or root.get("clip_id") != candidate["clip_id"]:
            raise BodySwayContinuousProofValidationError(
                "Continuous proof project or clip differs from exact source"
            )
        expected = analyze_body_sway_continuous_source(source).document
        actual = {field: root.get(field) for field in _ANALYSIS_FIELDS}
        if _canonical(actual) != _canonical(expected):
            raise BodySwayContinuousProofValidationError(
                "Continuous proof evidence differs from exact recomputation"
            )
        if _canonical(root.get("analyzer")) != _canonical(
            body_sway_continuous_proof_analyzer_profile()
        ):
            raise BodySwayContinuousProofValidationError(
                "Continuous proof analyzer profile is unsupported"
            )
        certified = (
            root["status"]
            == "continuous_preview_model_structural_certified"
        )
        if _canonical(root.get("release_gate")) != _canonical(
            body_sway_continuous_proof_release_gate(certified)
        ):
            raise BodySwayContinuousProofValidationError(
                "Continuous proof release gate must remain blocked"
            )
    except BodySwayContinuousProofValidationError:
        raise
    except (
        BodySwayContinuousProofAnalysisError, BodySwayContinuousSourceError,
        KeyError, OverflowError, RecursionError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise BodySwayContinuousProofValidationError(
            f"Continuous proof validation failed: {exc}"
        ) from exc


def body_sway_continuous_proof_sha256(
    document: Mapping[str, Any],
) -> str:
    """Return a canonical identity only after full proof recomputation."""

    require_body_sway_continuous_proof(document)
    return canonical_sha256(document)


def _bounded_object_copy(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BodySwayContinuousProofValidationError(
            f"{label} must be a JSON object"
        )
    encoded = bytearray()
    _encode_bounded_json(value, encoded, depth=0)
    copied = json.loads(encoded)
    if not isinstance(copied, dict):
        raise BodySwayContinuousProofValidationError(
            f"{label} must be a JSON object"
        )
    return copied


def _encode_bounded_json(value: Any, output: bytearray, *, depth: int) -> None:
    if depth > 128:
        raise BodySwayContinuousProofValidationError(
            "Continuous proof JSON nesting is too deep"
        )
    if isinstance(value, Mapping):
        if len(value) > 100_000 \
                or any(type(key) is not str for key in value):
            raise BodySwayContinuousProofValidationError(
                "Continuous proof JSON object keys are invalid"
            )
        _append(output, b"{")
        for index, key in enumerate(sorted(value)):
            if index:
                _append(output, b",")
            _encode_string(key, output)
            _append(output, b":")
            _encode_bounded_json(value[key], output, depth=depth + 1)
        _append(output, b"}")
    elif type(value) is list:
        if len(value) > 100_000:
            raise BodySwayContinuousProofValidationError(
                "Continuous proof JSON array is too large"
            )
        _append(output, b"[")
        for index, item in enumerate(value):
            if index:
                _append(output, b",")
            _encode_bounded_json(item, output, depth=depth + 1)
        _append(output, b"]")
    elif type(value) is str:
        _encode_string(value, output)
    elif value is None:
        _append(output, b"null")
    elif type(value) is bool:
        _append(output, b"true" if value else b"false")
    elif type(value) is int:
        _append(output, str(value).encode("ascii"))
    elif type(value) is float:
        if value != value or value in (float("inf"), -float("inf")):
            raise BodySwayContinuousProofValidationError(
                "Continuous proof JSON number must be finite"
            )
        _append(output, json.dumps(value, allow_nan=False).encode("ascii"))
    else:
        raise BodySwayContinuousProofValidationError(
            "Continuous proof contains a non-JSON value"
        )


def _encode_string(value: str, output: bytearray) -> None:
    escapes = {
        '"': b'\\"', "\\": b"\\\\", "\b": b"\\b", "\f": b"\\f",
        "\n": b"\\n", "\r": b"\\r", "\t": b"\\t",
    }
    _append(output, b'"')
    for character in value:
        if character in escapes:
            _append(output, escapes[character])
        elif ord(character) < 0x20:
            _append(output, f"\\u{ord(character):04x}".encode("ascii"))
        else:
            try:
                _append(output, character.encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise BodySwayContinuousProofValidationError(
                    "Continuous proof contains invalid Unicode"
                ) from exc
    _append(output, b'"')


def _append(output: bytearray, value: bytes) -> None:
    if len(output) + len(value) > MAX_DOCUMENT_BYTES:
        raise BodySwayContinuousProofValidationError(
            "Continuous proof exceeds its byte limit"
        )
    output.extend(value)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
