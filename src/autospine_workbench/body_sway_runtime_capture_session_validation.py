"""Detached structural validation for a complete P10 runtime session set."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_probe_math_inputs import normalize_timing
from .body_sway_probe_validation import require_body_sway_selection
from .idle_behavior_decision_validation_fields import (
    digest_value,
    identifier_value,
)
from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION
from .spine42_runtime_contract import (
    RUNTIME_NPM_INTEGRITY,
)
from .spine42_runtime_profile import (
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)
from .temporary_body_sway_preview_fields import require_preview_capture_plan


SESSION_SET_FORMAT = "autospine-body-sway-runtime-capture-session-set"
SESSION_SET_FORMAT_VERSION = 1
SESSION_FORMAT = "autospine-body-sway-runtime-capture-session"
SESSION_FORMAT_VERSION = 1
MAX_SESSION_SET_BYTES = 512 * 1024
MAX_SAMPLE_TICKS = 4096
_TOP_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "runtime",
    "source", "timing", "selection", "sample_ticks", "assets",
    "capture_plan", "summary",
}


class BodySwayRuntimeCaptureSessionValidationError(ValueError):
    """Raised when a detached complete runtime session set is malformed."""


def require_body_sway_runtime_capture_session_set(
    value: Mapping[str, Any],
) -> None:
    """Require one bounded profile and its complete ordered capture plan."""

    try:
        root = _object(value, "runtime capture session set")
        _exact(root, _TOP_FIELDS, "runtime capture session set")
        if root.get("format") != SESSION_SET_FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != SESSION_SET_FORMAT_VERSION:
            raise BodySwayRuntimeCaptureSessionValidationError(
                "Runtime capture session-set format is unsupported"
            )
        identifier_value(root.get("project_id"), "project_id")
        identifier_value(root.get("clip_id"), "clip_id")
        require_body_sway_runtime_identity(root.get("runtime"))
        source = _source(root.get("source"))
        duration, _loop = normalize_timing(root.get("timing"))
        selection = _object(root.get("selection"), "selection")
        require_body_sway_selection(selection)
        sample_ticks = require_body_sway_capture_sample_ticks(
            root.get("sample_ticks"), duration
        )
        require_body_sway_runtime_capture_assets(root.get("assets"))
        count = require_preview_capture_plan(
            root.get("capture_plan"),
            duration=duration,
            ticks_per_second=root["timing"]["ticks_per_second"],
            selection=dict(selection),
            sample_ticks=list(sample_ticks),
        )
        if source["capture_plan_sha256"] \
                != root["capture_plan"]["capture_plan_sha256"]:
            raise BodySwayRuntimeCaptureSessionValidationError(
                "Runtime session source differs from its capture plan"
            )
        summary = _object(root.get("summary"), "summary")
        if set(summary) != {"case_count"} \
                or type(summary.get("case_count")) is not int \
                or summary["case_count"] != count:
            raise BodySwayRuntimeCaptureSessionValidationError(
                "Runtime session case count is inconsistent"
            )
        encoded = json.dumps(
            root, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_SESSION_SET_BYTES:
            raise BodySwayRuntimeCaptureSessionValidationError(
                "Runtime capture session set exceeds its byte limit"
            )
    except BodySwayRuntimeCaptureSessionValidationError:
        raise
    except (
        KeyError, OverflowError, RecursionError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureSessionValidationError(
            f"Runtime capture session-set validation failed: {exc}"
        ) from exc


def require_body_sway_runtime_identity(value: Any) -> None:
    """Require the pinned package identity and two exact digest fields."""

    row = _object(value, "runtime")
    _exact(row, {
        "package", "version", "npm_integrity", "javascript_sha256",
        "stylesheet_sha256",
    }, "runtime")
    if row.get("package") != SPINE_RUNTIME_PACKAGE \
            or row.get("version") != SPINE_RUNTIME_VERSION \
            or row.get("npm_integrity") != RUNTIME_NPM_INTEGRITY:
        raise BodySwayRuntimeCaptureSessionValidationError(
            "Runtime identity is not the pinned Spine 4.2 profile"
        )
    digest_value(row.get("javascript_sha256"), "runtime JavaScript SHA-256")
    digest_value(row.get("stylesheet_sha256"), "runtime stylesheet SHA-256")
    if row["javascript_sha256"] != SPINE_PLAYER_JAVASCRIPT_SHA256 \
            or row["stylesheet_sha256"] != SPINE_PLAYER_STYLESHEET_SHA256:
        raise BodySwayRuntimeCaptureSessionValidationError(
            "Runtime dist hashes are not the pinned Spine 4.2 snapshot"
        )


def _source(value: Any) -> Mapping[str, Any]:
    row = _object(value, "source")
    _exact(row, {
        "temporary_preview_sha256", "artifact_set_sha256",
        "preview_projection_sha256", "capture_plan_sha256",
    }, "source")
    for field in row:
        digest_value(row[field], field)
    return row


def require_body_sway_runtime_capture_assets(value: Any) -> None:
    """Require exact skeleton/atlas/texture identities and texture bounds."""

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
        raise BodySwayRuntimeCaptureSessionValidationError(
            "Runtime capture texture size is invalid"
        )


def require_body_sway_capture_sample_ticks(
    value: Any, duration: int,
) -> tuple[int, ...]:
    """Require a bounded, endpoint-complete ordered probe schedule."""

    if not isinstance(value, list) or not 2 <= len(value) <= MAX_SAMPLE_TICKS \
            or any(type(item) is not int for item in value):
        raise BodySwayRuntimeCaptureSessionValidationError(
            "Runtime capture sample ticks are invalid"
        )
    result = tuple(value)
    if result[0] != 0 or result[-1] != duration \
            or any(left >= right for left, right in zip(result, result[1:])):
        raise BodySwayRuntimeCaptureSessionValidationError(
            "Runtime capture sample ticks must be complete and ordered"
        )
    return result


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BodySwayRuntimeCaptureSessionValidationError(
            f"Runtime capture {label} must be an object"
        )
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise BodySwayRuntimeCaptureSessionValidationError(
            f"Runtime capture {label} fields are invalid"
        )
