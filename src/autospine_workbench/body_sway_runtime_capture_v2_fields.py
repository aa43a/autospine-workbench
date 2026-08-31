"""Reusable strict fields for the RuntimeCapture v2 contract."""

from __future__ import annotations

from collections.abc import Mapping
import math

from .browser_executable_snapshot import MAX_EXECUTABLE_BYTES
from .browser_version_identity import (
    BrowserVersionIdentityError,
    browser_version_identity_sha256,
)
from .idle_behavior_decision_validation_fields import digest_value
from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION
from .spine42_runtime_contract import RUNTIME_NPM_INTEGRITY
from .spine42_runtime_profile import (
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)


class BodySwayRuntimeCaptureV2FieldError(ValueError):
    """Raised when a shared v2 runtime field is invalid."""


def require_runtime_v2_identity(value) -> None:
    row = _object(value, "runtime")
    _exact(row, {
        "package", "version", "npm_integrity", "javascript_sha256",
        "stylesheet_sha256",
    }, "runtime")
    if row != {
        "package": SPINE_RUNTIME_PACKAGE, "version": SPINE_RUNTIME_VERSION,
        "npm_integrity": RUNTIME_NPM_INTEGRITY,
        "javascript_sha256": SPINE_PLAYER_JAVASCRIPT_SHA256,
        "stylesheet_sha256": SPINE_PLAYER_STYLESHEET_SHA256,
    }:
        raise BodySwayRuntimeCaptureV2FieldError(
            "Runtime capture v2 runtime identity is not pinned"
        )


def require_runtime_v2_assets(value) -> None:
    row = _object(value, "assets")
    _exact(row, {
        "skeleton_sha256", "atlas_sha256", "texture_sha256", "texture_size",
    }, "assets")
    for field in ("skeleton_sha256", "atlas_sha256", "texture_sha256"):
        digest_value(row.get(field), field)
    size = row.get("texture_size")
    if not isinstance(size, list) or len(size) != 2 or any(
        type(item) is not int or not 1 <= item <= 4096 for item in size
    ):
        raise BodySwayRuntimeCaptureV2FieldError(
            "Runtime capture v2 texture size is invalid"
        )


def require_runtime_v2_browser(value) -> None:
    row = _object(value, "browser")
    _exact(row, {
        "family", "reported_version", "version_output_sha256",
        "executable_sha256", "executable_size", "identity_scope",
    }, "browser")
    try:
        expected = browser_version_identity_sha256(
            row.get("family"), row.get("reported_version")
        )
    except BrowserVersionIdentityError as exc:
        raise BodySwayRuntimeCaptureV2FieldError(
            "Runtime capture v2 browser identity is invalid"
        ) from exc
    digest_value(row.get("executable_sha256"), "browser executable SHA-256")
    if row.get("version_output_sha256") != expected \
            or row.get("identity_scope") \
            != "launcher-executable-and-reported-version" \
            or type(row.get("executable_size")) is not int \
            or not 1 <= row["executable_size"] <= MAX_EXECUTABLE_BYTES:
        raise BodySwayRuntimeCaptureV2FieldError(
            "Runtime capture v2 browser snapshot is inconsistent"
        )


def require_runtime_v2_world_viewport(value) -> dict[str, float]:
    row = _object(value, "world viewport")
    _exact(row, {"x", "y", "width", "height"}, "world viewport")
    numbers = tuple(row[field] for field in ("x", "y", "width", "height"))
    if any(isinstance(item, bool) or not isinstance(item, (int, float))
           or not math.isfinite(float(item))
           or abs(float(item)) > 1e12 for item in numbers) \
            or row["width"] <= 0 or row["height"] <= 0 \
            or not math.isclose(row["width"], row["height"],
                                rel_tol=0.0, abs_tol=1e-9):
        raise BodySwayRuntimeCaptureV2FieldError(
            "Runtime capture v2 world viewport is invalid"
        )
    return {field: float(row[field]) for field in row}


def _object(value, label) -> Mapping:
    if not isinstance(value, Mapping):
        raise BodySwayRuntimeCaptureV2FieldError(
            f"Runtime capture v2 {label} must be an object"
        )
    return value


def _exact(value, fields, label) -> None:
    if set(value) != set(fields):
        raise BodySwayRuntimeCaptureV2FieldError(
            f"Runtime capture v2 {label} fields are invalid"
        )
