"""PNG artifact inventory for one complete P10 runtime capture set."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
    BodySwayRuntimeCaptureSnapshot,
)
from .body_sway_runtime_capture_profile import (
    ARTIFACT_SET_DIGEST_DOMAIN,
    MAX_CAPTURE_ARTIFACTS,
)
from .idle_behavior_decision_validation_fields import digest_value
from .png_rgba import RgbaPngError, decode_rgba_png
from .resolved_project import canonical_sha256


class BodySwayRuntimeCaptureInventoryError(ValueError):
    """Raised when capture PNG bytes and their inventory disagree."""


def build_body_sway_runtime_capture_inventory(
    snapshot: BodySwayRuntimeCaptureSnapshot,
) -> dict[str, Any]:
    """Build an ordered, content-addressed inventory from a complete snapshot."""

    if type(snapshot) is not BodySwayRuntimeCaptureSnapshot:
        raise BodySwayRuntimeCaptureInventoryError(
            "Capture inventory requires an exact immutable snapshot"
        )
    reports, captures = snapshot.reports, snapshot.capture_bytes
    if not 3 <= len(reports) <= MAX_CAPTURE_ARTIFACTS \
            or len(reports) != len(captures):
        raise BodySwayRuntimeCaptureInventoryError(
            "Capture inventory count is invalid"
        )
    files = []
    for report in reports:
        try:
            if report.get("status") != "captured":
                raise BodySwayRuntimeCaptureInventoryError(
                    "Capture inventory contains a non-capture report"
                )
            case_id, image = report["case"]["id"], report["image"]
            path = f"captures/{case_id}.png"
            raw = captures.get(path)
            if type(raw) is not bytes \
                    or not 0 < len(raw) <= MAX_CAPTURE_BYTES:
                raise BodySwayRuntimeCaptureInventoryError(
                    "Capture inventory PNG bytes are missing or unbounded"
                )
            decoded = decode_rgba_png(raw, source_name=path)
            row = {
                "path": path,
                "role": "official-runtime-capture",
                "case_id": case_id,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "width": decoded.width,
                "height": decoded.height,
            }
            if image != {
                "path": path, "png_sha256": row["sha256"],
                "width": row["width"], "height": row["height"],
                "size_bytes": row["size_bytes"],
            }:
                raise BodySwayRuntimeCaptureInventoryError(
                    "Capture report image differs from its PNG bytes"
                )
            files.append(row)
        except BodySwayRuntimeCaptureInventoryError:
            raise
        except (KeyError, RgbaPngError, TypeError, ValueError) as exc:
            raise BodySwayRuntimeCaptureInventoryError(
                f"Capture inventory item is invalid: {exc}"
            ) from exc
    if len({row["case_id"] for row in files}) != len(files) \
            or set(captures) != {row["path"] for row in files}:
        raise BodySwayRuntimeCaptureInventoryError(
            "Capture inventory paths or case ids are not exact"
        )
    total = sum(row["size_bytes"] for row in files)
    if total > MAX_CAPTURE_TOTAL_BYTES:
        raise BodySwayRuntimeCaptureInventoryError(
            "Capture inventory exceeds its total byte limit"
        )
    return {
        "artifact_set_sha256": _artifact_set_sha256(files),
        "total_bytes": total,
        "files": files,
    }


def require_body_sway_runtime_capture_inventory(
    value: Mapping[str, Any], capture_bytes: Mapping[str, bytes],
) -> tuple[dict[str, Any], ...]:
    """Validate detached inventory shape, aggregate and every exact PNG byte."""

    try:
        if not isinstance(value, Mapping) or set(value) != {
            "artifact_set_sha256", "total_bytes", "files",
        } or not isinstance(capture_bytes, Mapping):
            raise BodySwayRuntimeCaptureInventoryError(
                "Runtime capture inventory fields are invalid"
            )
        files = value.get("files")
        if not isinstance(files, list) \
                or not 3 <= len(files) <= MAX_CAPTURE_ARTIFACTS:
            raise BodySwayRuntimeCaptureInventoryError(
                "Runtime capture file count is invalid"
            )
        normalized = tuple(_file(row, capture_bytes) for row in files)
        if len({row["case_id"] for row in normalized}) != len(normalized) \
                or len({row["path"] for row in normalized}) != len(normalized) \
                or set(capture_bytes) != {row["path"] for row in normalized}:
            raise BodySwayRuntimeCaptureInventoryError(
                "Runtime capture file inventory is not exact"
            )
        total = sum(row["size_bytes"] for row in normalized)
        if type(value.get("total_bytes")) is not int \
                or value["total_bytes"] != total \
                or total > MAX_CAPTURE_TOTAL_BYTES:
            raise BodySwayRuntimeCaptureInventoryError(
                "Runtime capture total bytes are inconsistent"
            )
        digest_value(value.get("artifact_set_sha256"), "artifact set SHA-256")
        if value["artifact_set_sha256"] != _artifact_set_sha256(normalized):
            raise BodySwayRuntimeCaptureInventoryError(
                "Runtime capture artifact-set digest is inconsistent"
            )
        return normalized
    except BodySwayRuntimeCaptureInventoryError:
        raise
    except (
        KeyError, OverflowError, RgbaPngError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureInventoryError(
            f"Runtime capture inventory validation failed: {exc}"
        ) from exc


def _file(value: Any, captures: Mapping[str, bytes]) -> dict[str, Any]:
    fields = {"path", "role", "case_id", "sha256", "size_bytes", "width", "height"}
    if not isinstance(value, Mapping) or set(value) != fields \
            or value.get("role") != "official-runtime-capture":
        raise BodySwayRuntimeCaptureInventoryError(
            "Runtime capture file fields are invalid"
        )
    case_id, path = value.get("case_id"), value.get("path")
    if type(case_id) is not str or path != f"captures/{case_id}.png":
        raise BodySwayRuntimeCaptureInventoryError(
            "Runtime capture file path is invalid"
        )
    raw = captures.get(path)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_CAPTURE_BYTES:
        raise BodySwayRuntimeCaptureInventoryError(
            "Runtime capture file bytes are missing or unbounded"
        )
    image = decode_rgba_png(raw, source_name=path)
    expected = {
        "path": path, "role": "official-runtime-capture", "case_id": case_id,
        "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
        "width": image.width, "height": image.height,
    }
    if dict(value) != expected:
        raise BodySwayRuntimeCaptureInventoryError(
            "Runtime capture file metadata differs from its bytes"
        )
    return expected


def _artifact_set_sha256(files) -> str:
    return canonical_sha256({
        "domain": ARTIFACT_SET_DIGEST_DOMAIN,
        "files": list(files),
    })
