"""Fail-closed validation for a version-neutral orthographic camera model."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import re
from typing import Any

from .kimodo_npz_map_validation import (
    KimodoNpzMapError,
    require_kimodo_npz_map,
)


FORMAT = "autospine-camera-model"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 16 * 1024
MAX_REFERENCE_METERS = 1_000_000.0
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_AXES = frozenset(("+X", "-X", "+Y", "-Y", "+Z", "-Z"))
_TOP = {
    "format", "format_version", "camera_id", "projection", "basis",
    "depth_positive", "origin", "normalization", "reference_length_meters",
}
_BASIS = {"screen_x", "screen_y", "depth"}


class CameraModelError(ValueError):
    """Raised when camera semantics are invalid or require guessing."""


def require_camera_model(document: Mapping[str, Any]) -> None:
    """Validate one explicit, static orthographic camera model."""

    try:
        root = _object(document, "Camera model")
        _exact(root, _TOP, "Camera model")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise CameraModelError("Camera model format is unsupported")
        _safe_id(root.get("camera_id"))
        if root.get("projection") != "static_orthographic":
            raise CameraModelError("Camera projection is unsupported")
        _basis(root.get("basis"))
        if root.get("depth_positive") not in {
            "toward_camera", "away_from_camera",
        }:
            raise CameraModelError("Camera depth direction is unsupported")
        if root.get("origin") != "source_root_frame0":
            raise CameraModelError("Camera origin is unsupported")
        if root.get("normalization") != "map_reference_length":
            raise CameraModelError("Camera normalization is unsupported")
        _reference(root.get("reference_length_meters"))
        if len(_canonical(root)) > MAX_DOCUMENT_BYTES:
            raise CameraModelError("Camera model byte limit exceeded")
    except CameraModelError:
        raise
    except (OverflowError, TypeError, ValueError) as exc:
        raise CameraModelError(f"Camera model validation failed: {exc}") from exc


def camera_model_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical identity of one validated camera model."""

    require_camera_model(document)
    return hashlib.sha256(_canonical(document)).hexdigest()


def require_camera_matches_kimodo_map(
    camera: Mapping[str, Any], kimodo_map: Mapping[str, Any]
) -> None:
    """Require camera axes and normalization to match one validated map."""

    require_camera_model(camera)
    try:
        require_kimodo_npz_map(kimodo_map)
    except KimodoNpzMapError as exc:
        raise CameraModelError("Kimodo NPZ map is invalid") from exc
    map_basis = kimodo_map["basis"]
    if any(
        camera["basis"][field] != map_basis[field]
        for field in ("screen_x", "screen_y", "depth")
    ):
        raise CameraModelError("Camera basis differs from Kimodo NPZ map")
    if float(camera["reference_length_meters"]) != float(
        kimodo_map["root"]["reference_length_meters"]
    ):
        raise CameraModelError(
            "Camera reference length differs from Kimodo NPZ map"
        )


def _basis(value: Any) -> None:
    basis = _object(value, "Camera basis")
    _exact(basis, _BASIS, "Camera basis")
    axes = [basis.get(field) for field in ("screen_x", "screen_y", "depth")]
    if any(axis not in _AXES for axis in axes) \
            or len({str(axis)[1] for axis in axes}) != 3:
        raise CameraModelError("Camera basis axes must be signed and orthogonal")


def _reference(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) \
            or not 0 < float(value) <= MAX_REFERENCE_METERS:
        raise CameraModelError("Camera reference length is invalid")


def _safe_id(value: Any) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise CameraModelError("Camera id is invalid")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CameraModelError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise CameraModelError(f"{label} fields are incomplete or unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
