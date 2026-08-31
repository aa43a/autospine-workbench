"""Exact 640x640 PNG payload inventory awaiting official runtime execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import re
from typing import Any

from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
)
from .body_sway_runtime_capture_v2_profile import (
    ARTIFACT_SET_DIGEST_DOMAIN,
    CAPTURE_VIEWPORT,
    MAX_CAPTURE_ARTIFACTS,
)
from .idle_behavior_decision_validation_fields import digest_value
from .png_rgba import RgbaPngError, decode_rgba_png
from .resolved_project import canonical_sha256


class BodySwayRuntimeCaptureV2InventoryError(ValueError):
    """Raised when the v2 PNG inventory differs from its exact bytes."""


def build_body_sway_runtime_capture_v2_inventory(
    ordered_case_ids: Sequence[str], capture_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    """Build a domain-separated inventory in capture-plan order."""

    try:
        identifiers = tuple(ordered_case_ids)
        if not 3 <= len(identifiers) <= MAX_CAPTURE_ARTIFACTS \
                or len(set(identifiers)) != len(identifiers):
            raise BodySwayRuntimeCaptureV2InventoryError(
                "Runtime capture v2 case inventory is invalid"
            )
        files = tuple(_file(case_id, capture_bytes) for case_id in identifiers)
        if set(capture_bytes) != {item["path"] for item in files}:
            raise BodySwayRuntimeCaptureV2InventoryError(
                "Runtime capture v2 PNG inventory is not exact"
            )
        total = sum(item["size_bytes"] for item in files)
        if total > MAX_CAPTURE_TOTAL_BYTES:
            raise BodySwayRuntimeCaptureV2InventoryError(
                "Runtime capture v2 PNG inventory is too large"
            )
        return {
            "artifact_set_sha256": _artifact_set_sha256(files),
            "total_bytes": total,
            "files": list(files),
        }
    except BodySwayRuntimeCaptureV2InventoryError:
        raise
    except (KeyError, RgbaPngError, TypeError, ValueError) as exc:
        raise BodySwayRuntimeCaptureV2InventoryError(
            f"Runtime capture v2 inventory compilation failed: {exc}"
        ) from exc


def require_body_sway_runtime_capture_v2_inventory(
    value: Mapping[str, Any], capture_bytes: Mapping[str, bytes],
) -> tuple[dict[str, Any], ...]:
    """Validate a detached inventory and every declared PNG byte."""

    try:
        if not isinstance(value, Mapping) or set(value) != {
            "artifact_set_sha256", "total_bytes", "files",
        } or not isinstance(capture_bytes, Mapping):
            raise BodySwayRuntimeCaptureV2InventoryError(
                "Runtime capture v2 inventory fields are invalid"
            )
        rows = value.get("files")
        if not isinstance(rows, list) \
                or not 3 <= len(rows) <= MAX_CAPTURE_ARTIFACTS:
            raise BodySwayRuntimeCaptureV2InventoryError(
                "Runtime capture v2 artifact count is invalid"
            )
        normalized = tuple(_declared_file(row, capture_bytes) for row in rows)
        if len({row["case_id"] for row in normalized}) != len(normalized) \
                or set(capture_bytes) != {row["path"] for row in normalized}:
            raise BodySwayRuntimeCaptureV2InventoryError(
                "Runtime capture v2 artifact inventory is not exact"
            )
        total = sum(row["size_bytes"] for row in normalized)
        if type(value.get("total_bytes")) is not int \
                or value["total_bytes"] != total \
                or total > MAX_CAPTURE_TOTAL_BYTES:
            raise BodySwayRuntimeCaptureV2InventoryError(
                "Runtime capture v2 total bytes are inconsistent"
            )
        digest_value(value.get("artifact_set_sha256"), "artifact set SHA-256")
        if value["artifact_set_sha256"] != _artifact_set_sha256(normalized):
            raise BodySwayRuntimeCaptureV2InventoryError(
                "Runtime capture v2 artifact-set digest is inconsistent"
            )
        return normalized
    except BodySwayRuntimeCaptureV2InventoryError:
        raise
    except (
        KeyError, OverflowError, RgbaPngError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureV2InventoryError(
            f"Runtime capture v2 inventory validation failed: {exc}"
        ) from exc


def _file(case_id: str, captures: Mapping[str, bytes]) -> dict[str, Any]:
    if type(case_id) is not str or _CASE_ID.fullmatch(case_id) is None:
        raise BodySwayRuntimeCaptureV2InventoryError(
            "Runtime capture v2 case id is unsafe"
        )
    path = f"captures/{case_id}.png"
    raw = captures.get(path)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_CAPTURE_BYTES:
        raise BodySwayRuntimeCaptureV2InventoryError(
            "Runtime capture v2 PNG bytes are missing or unbounded"
        )
    image = decode_rgba_png(raw, source_name=path)
    if (image.width, image.height) != (
        CAPTURE_VIEWPORT["width"], CAPTURE_VIEWPORT["height"],
    ):
        raise BodySwayRuntimeCaptureV2InventoryError(
            "Runtime capture v2 PNG must be exactly 640x640"
        )
    return {
        "path": path,
        "role": "validated-runtime-capture-payload-v2",
        "case_id": case_id,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "width": image.width,
        "height": image.height,
    }


def _declared_file(value: Any, captures: Mapping[str, bytes]) -> dict[str, Any]:
    fields = {
        "path", "role", "case_id", "sha256", "size_bytes", "width", "height",
    }
    if not isinstance(value, Mapping) or set(value) != fields \
            or value.get("role") != "validated-runtime-capture-payload-v2":
        raise BodySwayRuntimeCaptureV2InventoryError(
            "Runtime capture v2 file fields are invalid"
        )
    expected = _file(value.get("case_id"), captures)
    if dict(value) != expected:
        raise BodySwayRuntimeCaptureV2InventoryError(
            "Runtime capture v2 metadata differs from PNG bytes"
        )
    return expected


def _artifact_set_sha256(files: Sequence[Mapping[str, Any]]) -> str:
    return canonical_sha256({
        "domain": ARTIFACT_SET_DIGEST_DOMAIN,
        "files": list(files),
    })


_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{0,95}$")
