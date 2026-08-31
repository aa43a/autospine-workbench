"""Detached validation for capture-framed official-runtime sessions v2."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_probe_math_inputs import normalize_timing
from .body_sway_probe_validation import require_body_sway_selection
from .body_sway_runtime_capture_session_validation import (
    require_body_sway_capture_sample_ticks,
)
from .body_sway_runtime_capture_v2_fields import (
    require_runtime_v2_assets,
    require_runtime_v2_world_viewport,
)
from .idle_behavior_decision_validation_fields import (
    digest_value,
    identifier_value,
)
from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION
from .spine42_runtime_contract import RUNTIME_NPM_INTEGRITY
from .spine42_runtime_profile import (
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)
from .temporary_body_sway_preview_fields_v2 import (
    require_preview_capture_plan_v2,
    require_preview_projection_metadata_v2,
)


SESSION_SET_FORMAT = "autospine-body-sway-runtime-capture-session-set"
SESSION_SET_FORMAT_VERSION = 2
SESSION_FORMAT = "autospine-body-sway-runtime-capture-session"
SESSION_FORMAT_VERSION = 2
MAX_SESSION_SET_BYTES = 2 * 1024 * 1024
_TOP_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "runtime",
    "source", "timing", "selection", "sample_ticks", "projection",
    "assets", "capture_plan", "summary",
}
_SOURCE_DIGEST_FIELDS = {
    "temporary_preview_v2_sha256", "preview_artifact_set_sha256",
    "preview_projection_v2_sha256", "capture_plan_v2_sha256",
    "preview_source_sha256", "capture_framing_candidate_sha256",
    "capture_framing_decision_sha256", "body_sway_probe_report_sha256",
}


class BodySwayRuntimeCaptureSessionV2ValidationError(ValueError):
    """Raised when a detached v2 session set is malformed."""


def require_body_sway_runtime_capture_session_set_v2(
    value: Mapping[str, Any],
) -> None:
    """Require one bounded, internally cross-bound Preview v2 session set."""

    try:
        root = _object(value, "session set")
        _exact(root, _TOP_FIELDS, "session set")
        if root.get("format") != SESSION_SET_FORMAT \
                or root.get("format_version") != SESSION_SET_FORMAT_VERSION:
            raise BodySwayRuntimeCaptureSessionV2ValidationError(
                "Runtime capture session-set v2 format is unsupported"
            )
        identifier_value(root.get("project_id"), "project_id")
        identifier_value(root.get("clip_id"), "clip_id")
        _runtime(root.get("runtime"))
        source = _source(root.get("source"))
        duration, _loop = normalize_timing(root.get("timing"))
        selection = _object(root.get("selection"), "selection")
        require_body_sway_selection(selection)
        projection = _object(root.get("projection"), "projection")
        projection_context = {
            "p9": {
                "motion_instance_v2_sha256":
                    projection.get("base_motion_instance_v2_sha256"),
            },
            "capture_framing_candidate_sha256":
                source["capture_framing_candidate_sha256"],
            "capture_framing_decision_sha256":
                source["capture_framing_decision_sha256"],
            "capture_framing_revision": source["capture_framing_revision"],
        }
        metadata = require_preview_projection_metadata_v2(
            projection, source=projection_context, timing=root["timing"],
        )
        sample_ticks = require_body_sway_capture_sample_ticks(
            root.get("sample_ticks"), duration,
        )
        if list(sample_ticks) != metadata["sample_ticks"] \
                or source["preview_projection_v2_sha256"] \
                != projection["projection_sha256"]:
            raise BodySwayRuntimeCaptureSessionV2ValidationError(
                "Runtime session v2 projection binding is inconsistent"
            )
        require_runtime_v2_assets(root.get("assets"))
        count = require_preview_capture_plan_v2(
            root.get("capture_plan"), timing=root["timing"],
            selection=dict(selection), projection=projection,
        )
        plan = root["capture_plan"]
        if source["capture_plan_v2_sha256"] \
                != plan["capture_plan_sha256"] \
                or source["world_viewport"] != metadata["world_viewport"] \
                or source["world_viewport"] != plan["world_viewport"]:
            raise BodySwayRuntimeCaptureSessionV2ValidationError(
                "Runtime session v2 plan or world viewport differs"
            )
        summary = _object(root.get("summary"), "summary")
        if summary != {"case_count": count}:
            raise BodySwayRuntimeCaptureSessionV2ValidationError(
                "Runtime session v2 case count is inconsistent"
            )
        if len(_canonical(root)) > MAX_SESSION_SET_BYTES:
            raise BodySwayRuntimeCaptureSessionV2ValidationError(
                "Runtime capture session set v2 exceeds its byte limit"
            )
    except BodySwayRuntimeCaptureSessionV2ValidationError:
        raise
    except (
        KeyError, OverflowError, RecursionError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureSessionV2ValidationError(
            f"Runtime capture session-set v2 validation failed: {exc}"
        ) from exc


def _runtime(value: Any) -> None:
    row = _object(value, "runtime")
    _exact(row, {
        "package", "version", "npm_integrity", "javascript_sha256",
        "stylesheet_sha256", "package_json_sha256", "license_sha256",
        "license_file_presence_is_authorization",
    }, "runtime")
    expected = {
        "package": SPINE_RUNTIME_PACKAGE,
        "version": SPINE_RUNTIME_VERSION,
        "npm_integrity": RUNTIME_NPM_INTEGRITY,
        "javascript_sha256": SPINE_PLAYER_JAVASCRIPT_SHA256,
        "stylesheet_sha256": SPINE_PLAYER_STYLESHEET_SHA256,
    }
    if any(row.get(field) != expected_value
           for field, expected_value in expected.items()) \
            or row.get("license_file_presence_is_authorization") is not False:
        raise BodySwayRuntimeCaptureSessionV2ValidationError(
            "Runtime session v2 identity or license boundary is invalid"
        )
    digest_value(row.get("package_json_sha256"), "runtime package.json")
    digest_value(row.get("license_sha256"), "runtime LICENSE")


def _source(value: Any) -> Mapping[str, Any]:
    row = _object(value, "source")
    _exact(row, {
        *_SOURCE_DIGEST_FIELDS, "capture_framing_revision",
        "current_p10_1_head", "world_viewport",
    }, "source")
    for field in _SOURCE_DIGEST_FIELDS:
        digest_value(row.get(field), field)
    if row["capture_framing_candidate_sha256"] \
            == row["capture_framing_decision_sha256"]:
        raise BodySwayRuntimeCaptureSessionV2ValidationError(
            "Runtime session v2 framing identities collide"
        )
    revision = row.get("capture_framing_revision")
    if type(revision) is not int or not 1 <= revision <= 64:
        raise BodySwayRuntimeCaptureSessionV2ValidationError(
            "Runtime session v2 framing revision is invalid"
        )
    require_runtime_v2_world_viewport(row.get("world_viewport"))
    head = _object(row.get("current_p10_1_head"), "P10.1 head")
    _exact(head, {"candidate_sha256", "decision_sha256", "revision"},
           "P10.1 head")
    digest_value(head.get("candidate_sha256"), "P10.0 candidate")
    digest_value(head.get("decision_sha256"), "P10.1 decision")
    if type(head.get("revision")) is not int \
            or not 1 <= head["revision"] <= 64:
        raise BodySwayRuntimeCaptureSessionV2ValidationError(
            "Runtime session v2 P10.1 head is invalid"
        )
    return row


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BodySwayRuntimeCaptureSessionV2ValidationError(
            f"Runtime capture v2 {label} must be an object"
        )
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise BodySwayRuntimeCaptureSessionV2ValidationError(
            f"Runtime capture v2 {label} fields are invalid"
        )


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
