"""Strict standalone validation for DynamicViewportFit v1 candidates."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from .dynamic_viewport_fit import (
    FORMAT,
    FORMAT_VERSION,
    RELEASE_GATE,
    SEMANTICS,
    derive_dynamic_viewport_fit,
    dynamic_viewport_fit_profile,
)
from .dynamic_viewport_fit_inputs import (
    DynamicViewportFitInputError,
    MAX_GEOMETRY_ITEM_COUNT,
    MAX_POINT_COUNT,
    MAX_SAMPLE_COUNT,
    envelope_value,
    mapping_value,
    margin_value,
    point_value,
    viewport_value,
)
from .resolved_project import canonical_sha256


MAX_DOCUMENT_BYTES = 64 * 1024
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOP_FIELDS = {
    "format", "format_version", "source", "viewport", "margin_px",
    "motion_envelope", "transform", "fitted_envelope", "fit_status",
    "profile", "semantics", "status", "release_gate",
}


class DynamicViewportFitValidationError(ValueError):
    """Raised when a viewport candidate is malformed or overclaims authority."""


def require_dynamic_viewport_fit(document: Mapping[str, Any]) -> None:
    """Validate all fields and independently replay the transform derivation."""

    try:
        root = mapping_value(document, "Dynamic viewport fit")
        _exact_fields(root, _TOP_FIELDS, "Dynamic viewport fit")
        if root.get("format") != FORMAT \
                or root.get("format_version") != FORMAT_VERSION:
            raise DynamicViewportFitValidationError(
                "Dynamic viewport fit format is unsupported"
            )
        _source(root.get("source"))
        viewport = viewport_value(root.get("viewport"))
        margin = margin_value(root.get("margin_px"), viewport)
        envelope = _envelope(root.get("motion_envelope"), "motion envelope")
        expected = derive_dynamic_viewport_fit(envelope, viewport, margin)
        if root.get("transform") != expected["transform"] \
                or root.get("fitted_envelope") != expected["fitted_envelope"] \
                or root.get("fit_status") != expected["fit_status"]:
            raise DynamicViewportFitValidationError(
                "Dynamic viewport transform differs from its envelope"
            )
        if root.get("profile") != dynamic_viewport_fit_profile():
            raise DynamicViewportFitValidationError(
                "Dynamic viewport profile differs from v1"
            )
        if root.get("semantics") != SEMANTICS:
            raise DynamicViewportFitValidationError(
                "Dynamic viewport semantics differ from v1"
            )
        if root.get("status") != "candidate_only" \
                or root.get("release_gate") != RELEASE_GATE:
            raise DynamicViewportFitValidationError(
                "Dynamic viewport fit must remain authority-free and blocked"
            )
        if len(_canonical(root)) > MAX_DOCUMENT_BYTES:
            raise DynamicViewportFitValidationError(
                "Dynamic viewport fit document exceeds its resource limit"
            )
    except DynamicViewportFitValidationError:
        raise
    except (DynamicViewportFitInputError, KeyError, OverflowError,
            TypeError, UnicodeError, ValueError) as exc:
        raise DynamicViewportFitValidationError(
            f"Dynamic viewport fit validation failed: {exc}"
        ) from exc


def dynamic_viewport_fit_sha256(document: Mapping[str, Any]) -> str:
    """Return a canonical identity only after strict standalone validation."""

    require_dynamic_viewport_fit(document)
    return canonical_sha256(document)


def _source(value) -> None:
    source = mapping_value(value, "Dynamic viewport source")
    _exact_fields(source, {
        "kind", "evidence_sha256", "sample_count",
        "geometry_item_count", "point_count",
    }, "Dynamic viewport source")
    if not isinstance(source.get("evidence_sha256"), str) \
            or not _SHA.fullmatch(source["evidence_sha256"]):
        raise DynamicViewportFitValidationError(
            "Dynamic viewport source identity is invalid"
        )
    counts = [source.get(field) for field in (
        "sample_count", "geometry_item_count", "point_count",
    )]
    if any(type(item) is not int or item < 0 for item in counts):
        raise DynamicViewportFitValidationError(
            "Dynamic viewport source counts are invalid"
        )
    samples, items, points = counts
    if source.get("kind") == "sampled_attachment_geometry":
        valid = 1 <= samples <= MAX_SAMPLE_COUNT \
            and samples <= items <= MAX_GEOMETRY_ITEM_COUNT \
            and 1 <= points <= MAX_POINT_COUNT
    elif source.get("kind") == "point_bounds":
        valid = samples == 0 and points == 0 \
            and 1 <= items <= MAX_GEOMETRY_ITEM_COUNT
    else:
        valid = False
    if not valid:
        raise DynamicViewportFitValidationError(
            "Dynamic viewport source cardinality is inconsistent"
        )


def _envelope(value, label):
    row = mapping_value(value, label)
    _exact_fields(row, {"min_xy", "max_xy", "size", "center_xy"}, label)
    minimum, maximum = point_value(row.get("min_xy")), point_value(row.get("max_xy"))
    if minimum[0] > maximum[0] or minimum[1] > maximum[1]:
        raise DynamicViewportFitValidationError(f"{label} minimum exceeds maximum")
    expected = envelope_value([minimum, maximum])
    if dict(row) != expected:
        raise DynamicViewportFitValidationError(f"{label} derivation is inconsistent")
    return expected


def _exact_fields(value, fields, label):
    if set(value) != fields:
        raise DynamicViewportFitValidationError(f"{label} fields are unsupported")


def _canonical(value) -> bytes:
    return json.dumps(
        dict(value) if isinstance(value, Mapping) else value,
        ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
