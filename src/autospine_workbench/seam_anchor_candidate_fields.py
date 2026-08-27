"""Closed structural fields for SeamAnchorCandidates v1 validation."""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any

from .seam_anchor_locators import (
    MAX_ABS_ATTACHMENT_COORDINATE,
    MAX_MESH_TRIANGLES,
    MAX_MESH_VERTICES,
    MESH_QUANTIZATION,
    REGION_QUANTIZATION,
)
from .seam_anchor_profile import MAX_ATTACHMENT_PIXELS
from .resolved_project import canonical_sha256


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_LOCATOR_COMMON = {"attachment_id", "attachment_type", "locator_type"}
CONTACT_FIELDS = {
    "contact_id", "mode", "area", "bbox_xywh", "centroid_xy",
    "variance_xy", "representative_xy", "error_radius_px",
    "overlap_ratios", "gap_distance_px", "endpoints_xy",
}


class SeamAnchorCandidateFieldError(ValueError):
    """Raised when one closed candidate field is malformed."""


def object_value(value: Any, label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise SeamAnchorCandidateFieldError(f"{label} must be an object")
    return value


def array_value(
    value: Any, label: str, *, maximum: int | None = None
) -> list[Any]:
    if type(value) is not list:
        raise SeamAnchorCandidateFieldError(f"{label} must be an array")
    if maximum is not None and len(value) > maximum:
        raise SeamAnchorCandidateFieldError(f"{label} exceeds its item limit")
    return value


def exact_fields(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if len(value) != len(fields) or any(field not in value for field in fields):
        raise SeamAnchorCandidateFieldError(
            f"{label} fields are incomplete or unsupported"
        )


def identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise SeamAnchorCandidateFieldError(f"{label} is invalid")
    return value


def digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise SeamAnchorCandidateFieldError(f"{label} SHA-256 is invalid")
    return value


def reasons(value: Any, label: str, *, required: bool = False) -> tuple[str, ...]:
    rows = array_value(value, label, maximum=64)
    result = tuple(identifier(item, label) for item in rows)
    if result != tuple(sorted(set(result))) or (required and not result):
        raise SeamAnchorCandidateFieldError(
            f"{label} must be sorted, unique, and explicit"
        )
    return result


def fixed_object(
    value: Any, expected: Mapping[str, Any], label: str
) -> None:
    row = object_value(value, f"Seam anchor {label}")
    exact_fields(row, set(expected), f"Seam anchor {label}")
    if not _same_json_shape(row, expected) \
            or canonical_sha256(row) != canonical_sha256(expected):
        raise SeamAnchorCandidateFieldError(
            f"Seam anchor {label} is unsupported"
        )


def _same_json_shape(value: Any, expected: Any) -> bool:
    if isinstance(expected, Mapping):
        return type(value) is dict and len(value) == len(expected) \
            and all(key in value for key in expected) \
            and all(_same_json_shape(value[key], item)
                    for key, item in expected.items())
    if isinstance(expected, list):
        return type(value) is list and len(value) == len(expected) \
            and all(_same_json_shape(left, right)
                    for left, right in zip(value, expected, strict=True))
    return type(value) is type(expected) and value == expected


def evidence_seal(row, field, function, label) -> None:
    actual = digest(row.get(field), f"{label} evidence")
    payload = dict(row)
    payload.pop(field)
    if actual != function(payload):
        raise SeamAnchorCandidateFieldError(
            f"Seam anchor {label} evidence hash differs"
        )


def contact_evidence(value: Any, *, max_gap: float) -> str:
    row = object_value(value, "Seam contact evidence")
    exact_fields(row, CONTACT_FIELDS, "Seam contact evidence")
    contact_id = identifier(row.get("contact_id"), "contact_id")
    mode = row.get("mode")
    if mode not in ("overlap", "gap"):
        raise SeamAnchorCandidateFieldError("Seam contact mode is unsupported")
    area = integer(row.get("area"), "contact area", minimum=0,
                   maximum=MAX_ATTACHMENT_PIXELS)
    bbox = integer_vector(row.get("bbox_xywh"), "contact bbox", 4)
    if bbox[2] < 1 or bbox[3] < 1 or area > bbox[2] * bbox[3]:
        raise SeamAnchorCandidateFieldError("Seam contact bbox is invalid")
    if any(abs(item) > MAX_ABS_ATTACHMENT_COORDINATE for item in (
        bbox[0], bbox[1], bbox[0] + bbox[2] - 1,
        bbox[1] + bbox[3] - 1,
    )):
        raise SeamAnchorCandidateFieldError("Seam contact bbox exceeds limits")
    centroid = number_vector(row.get("centroid_xy"), "contact centroid", 2)
    variance = number_vector(
        row.get("variance_xy"), "contact variance", 2, maximum=1e18
    )
    representative = number_vector(
        row.get("representative_xy"), "contact representative", 2
    )
    radius = number(row.get("error_radius_px"), "contact error radius")
    ratios = number_vector(row.get("overlap_ratios"), "overlap ratios", 2)
    gap = number(row.get("gap_distance_px"), "contact gap")
    endpoints_raw = array_value(row.get("endpoints_xy"), "contact endpoints",
                                maximum=2)
    if len(endpoints_raw) != 2:
        raise SeamAnchorCandidateFieldError("Contact endpoints need two points")
    endpoints = tuple(
        number_vector(item, "contact endpoint", 2) for item in endpoints_raw
    )
    if min(*variance, radius, *ratios, gap) < 0 or max(ratios) > 1 \
            or not _rounded_radius_matches(variance, radius):
        raise SeamAnchorCandidateFieldError("Seam contact statistics are invalid")
    if not _inside(centroid, bbox) or not _inside(representative, bbox) \
            or any(not _inside(point, bbox) for point in endpoints):
        raise SeamAnchorCandidateFieldError("Seam contact point is outside bbox")
    _contact_mode(
        contact_id, mode, area, representative, ratios, gap, endpoints, max_gap
    )
    return mode


def locator(value: Any, attachment_id: str, attachment_type: str) -> str:
    row = object_value(value, "Seam locator")
    if row.get("attachment_id") != attachment_id \
            or row.get("attachment_type") != attachment_type:
        raise SeamAnchorCandidateFieldError(
            "Seam locator attachment identity differs from its option"
        )
    identifier(row.get("attachment_id"), "locator attachment id")
    if attachment_type == "region":
        exact_fields(row, _LOCATOR_COMMON | {"local_xy_q4096"},
                     "Region seam locator")
        if row.get("locator_type") != "region-local-q4096":
            raise SeamAnchorCandidateFieldError("Region locator type is invalid")
        coordinates = integer_vector(
            row.get("local_xy_q4096"), "region locator", 2
        )
        maximum = MAX_ABS_ATTACHMENT_COORDINATE * REGION_QUANTIZATION
        if min(coordinates) < 0 or max(coordinates) > maximum:
            raise SeamAnchorCandidateFieldError("Region locator is out of range")
    elif attachment_type == "mesh":
        _mesh_locator(row)
    else:
        raise SeamAnchorCandidateFieldError("Attachment type is unsupported")
    return attachment_type


def number(
    value: Any, label: str, *, maximum: float = MAX_ABS_ATTACHMENT_COORDINATE
) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) \
            or not math.isfinite(value) \
            or abs(value) > maximum:
        raise SeamAnchorCandidateFieldError(f"{label} must be finite")
    return float(value)


def integer(
    value: Any, label: str, *, minimum: int, maximum: int
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise SeamAnchorCandidateFieldError(f"{label} integer is out of range")
    return value


def integer_vector(value: Any, label: str, length: int) -> tuple[int, ...]:
    rows = array_value(value, label, maximum=length)
    if len(rows) != length or any(type(item) is not int for item in rows):
        raise SeamAnchorCandidateFieldError(f"{label} must contain integers")
    return tuple(rows)


def number_vector(
    value: Any, label: str, length: int, *,
    maximum: float = MAX_ABS_ATTACHMENT_COORDINATE,
) -> tuple[float, ...]:
    rows = array_value(value, label, maximum=length)
    if len(rows) != length:
        raise SeamAnchorCandidateFieldError(f"{label} length is invalid")
    return tuple(number(item, label, maximum=maximum) for item in rows)


def _mesh_locator(row: Mapping[str, Any]) -> None:
    exact_fields(row, _LOCATOR_COMMON | {
        "triangle_index", "vertex_indices", "weights_q65535",
    }, "Mesh seam locator")
    if row.get("locator_type") != "mesh-barycentric-q65535":
        raise SeamAnchorCandidateFieldError("Mesh locator type is invalid")
    integer(row.get("triangle_index"), "triangle index", minimum=0,
            maximum=MAX_MESH_TRIANGLES - 1)
    indices = integer_vector(row.get("vertex_indices"), "vertex indices", 3)
    if len(set(indices)) != 3 or min(indices) < 0 \
            or max(indices) >= MAX_MESH_VERTICES:
        raise SeamAnchorCandidateFieldError("Mesh vertex indices are invalid")
    weights = integer_vector(row.get("weights_q65535"), "mesh weights", 3)
    if min(weights) < 0 or max(weights) > MESH_QUANTIZATION \
            or sum(weights) != MESH_QUANTIZATION:
        raise SeamAnchorCandidateFieldError("Mesh locator weights are invalid")


def _inside(point: tuple[float, ...], bbox: tuple[int, ...]) -> bool:
    return bbox[0] <= point[0] <= bbox[0] + bbox[2] - 1 \
        and bbox[1] <= point[1] <= bbox[1] + bbox[3] - 1


def _rounded_radius_matches(variance, radius) -> bool:
    half = 0.5e-6
    variance_low = sum(max(0.0, item - half) for item in variance)
    variance_high = sum(item + half for item in variance)
    radius_low = max(0.0, radius - half)
    radius_high = radius + half
    return radius_low * radius_low <= variance_high + 1e-12 \
        and radius_high * radius_high >= variance_low - 1e-12


def _contact_mode(contact_id, mode, area, representative, ratios, gap,
                  endpoints, max_gap) -> None:
    if mode == "overlap":
        if re.fullmatch(r"overlap\.[0-9]{3}", contact_id) is None \
                or area < 1 or min(ratios) <= 0 or gap != 0 \
                or endpoints[0] != representative \
                or endpoints[1] != representative:
            raise SeamAnchorCandidateFieldError(
                "Overlap contact evidence is inconsistent"
            )
        return
    distance = math.hypot(
        endpoints[0][0] - endpoints[1][0],
        endpoints[0][1] - endpoints[1][1],
    )
    midpoint = (
        (endpoints[0][0] + endpoints[1][0]) / 2,
        (endpoints[0][1] + endpoints[1][1]) / 2,
    )
    if contact_id != "gap.000" or area != 0 \
            or tuple(ratios) != (0.0, 0.0) \
            or not 0 < gap <= max_gap \
            or abs(round(distance, 6) - gap) > 1e-6 \
            or any(abs(a - b) > 1e-6
                   for a, b in zip(representative, midpoint, strict=True)):
        raise SeamAnchorCandidateFieldError("Gap contact evidence is inconsistent")
