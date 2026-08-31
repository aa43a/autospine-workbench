"""Frozen exact official-runtime session set for Preview v2 cases."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_runtime_capture_session import (
    MAX_RUNTIME_JAVASCRIPT_BYTES,
    MAX_RUNTIME_STYLESHEET_BYTES,
)
from .body_sway_runtime_capture_session_v2_validation import (
    SESSION_FORMAT,
    SESSION_FORMAT_VERSION,
    SESSION_SET_FORMAT,
    SESSION_SET_FORMAT_VERSION,
    require_body_sway_runtime_capture_session_set_v2,
)
from .resolved_project import canonical_sha256
from .spine42_runtime_inputs import Spine42RuntimePackage
from .spine42_runtime_profile import (
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2
from .temporary_body_sway_preview_validation_v2 import (
    require_temporary_body_sway_preview_v2,
)


class BodySwayRuntimeCaptureSessionV2Error(ValueError):
    """Raised when Preview v2 and runtime cannot form exact sessions."""


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeCaptureSessionsV2:
    """Canonical complete v2 plan; public values are detached JSON copies."""

    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(
            row["case_id"]
            for row in self.document["capture_plan"]["cases"]
        )

    def session(self, case_id: str) -> dict[str, Any]:
        document = self.document
        row = next((
            item for item in document["capture_plan"]["cases"]
            if item["case_id"] == case_id
        ), None)
        if row is None:
            raise BodySwayRuntimeCaptureSessionV2Error(
                "Capture case is absent from the exact v2 session set"
            )
        plan = document["capture_plan"]
        return _copy({
            "format": SESSION_FORMAT,
            "format_version": SESSION_FORMAT_VERSION,
            "project_id": document["project_id"],
            "clip_id": document["clip_id"],
            "runtime": document["runtime"],
            "source": document["source"],
            "assets": document["assets"],
            "capture": {
                key: plan[key] for key in (
                    "viewport", "device_pixel_ratio", "background",
                    "preserve_drawing_buffer", "world_viewport",
                )
            },
            "case": {
                "id": row["case_id"], "animation": row["animation"],
                "tick": row["tick"], "time_seconds": row["time_seconds"],
            },
        })


def build_body_sway_runtime_capture_sessions_v2(
    preview: TemporaryBodySwayPreviewV2,
    runtime: Spine42RuntimePackage,
) -> BodySwayRuntimeCaptureSessionsV2:
    """Bind complete Preview v2, framing, asset, and runtime identities."""

    try:
        if type(preview) is not TemporaryBodySwayPreviewV2 \
                or type(runtime) is not Spine42RuntimePackage:
            raise BodySwayRuntimeCaptureSessionV2Error(
                "Runtime capture v2 requires exact preview and runtime snapshots"
            )
        document, artifacts = preview.document, preview.artifact_bytes
        require_temporary_body_sway_preview_v2(document, artifacts)
        _require_runtime(runtime)
        rows = {row["role"]: row for row in document["artifacts"]["files"]}
        source = document["source"]
        projection = document["projection"]
        plan = document["capture_plan"]
        value = {
            "format": SESSION_SET_FORMAT,
            "format_version": SESSION_SET_FORMAT_VERSION,
            "project_id": document["project_id"],
            "clip_id": document["clip_id"],
            "runtime": {
                **document["runtime_target"]["runtime"],
                "javascript_sha256": runtime.javascript_sha256,
                "stylesheet_sha256": runtime.stylesheet_sha256,
                "package_json_sha256": runtime.package_json_sha256,
                "license_sha256": runtime.license_sha256,
                "license_file_presence_is_authorization": False,
            },
            "source": {
                "temporary_preview_v2_sha256": preview.sha256,
                "preview_artifact_set_sha256": preview.artifact_set_sha256,
                "preview_projection_v2_sha256":
                    projection["projection_sha256"],
                "capture_plan_v2_sha256": plan["capture_plan_sha256"],
                "preview_source_sha256": canonical_sha256(source),
                "capture_framing_candidate_sha256":
                    source["capture_framing_candidate_sha256"],
                "capture_framing_decision_sha256":
                    source["capture_framing_decision_sha256"],
                "capture_framing_revision":
                    source["capture_framing_revision"],
                "current_p10_1_head": source["current_p10_1_head"],
                "body_sway_probe_report_sha256":
                    source["body_sway_probe_report_sha256"],
                "world_viewport": projection["world_viewport"],
            },
            "timing": document["timing"],
            "selection": document["selection"],
            "sample_ticks": projection["sample_ticks"],
            "projection": projection,
            "assets": {
                "skeleton_sha256": rows["spine-skeleton-v2"]["sha256"],
                "atlas_sha256": rows["spine-atlas"]["sha256"],
                "texture_sha256": rows["spine-texture"]["sha256"],
                "texture_size": [
                    document["summary"]["atlas_width"],
                    document["summary"]["atlas_height"],
                ],
            },
            "capture_plan": plan,
            "summary": {"case_count": len(plan["cases"])},
        }
        require_body_sway_runtime_capture_session_set_v2(value)
        return BodySwayRuntimeCaptureSessionsV2(_canonical(value))
    except BodySwayRuntimeCaptureSessionV2Error:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureSessionV2Error(
            f"Body-sway runtime capture session v2 failed: {exc}"
        ) from exc


def require_exact_body_sway_runtime_capture_sessions_v2(
    preview: TemporaryBodySwayPreviewV2,
    runtime: Spine42RuntimePackage,
    sessions: BodySwayRuntimeCaptureSessionsV2,
) -> BodySwayRuntimeCaptureSessionsV2:
    """Replay exact inputs and reject a cross-wired v2 session set."""

    if type(sessions) is not BodySwayRuntimeCaptureSessionsV2:
        raise BodySwayRuntimeCaptureSessionV2Error(
            "Runtime capture session set v2 is invalid"
        )
    expected = build_body_sway_runtime_capture_sessions_v2(preview, runtime)
    if sessions.canonical_bytes != expected.canonical_bytes:
        raise BodySwayRuntimeCaptureSessionV2Error(
            "Runtime capture session set v2 differs from exact replay"
        )
    return expected


def _require_runtime(runtime: Spine42RuntimePackage) -> None:
    javascript, stylesheet = runtime.javascript_bytes, runtime.stylesheet_bytes
    if type(javascript) is not bytes \
            or not 0 < len(javascript) <= MAX_RUNTIME_JAVASCRIPT_BYTES \
            or type(stylesheet) is not bytes \
            or not 0 < len(stylesheet) <= MAX_RUNTIME_STYLESHEET_BYTES:
        raise BodySwayRuntimeCaptureSessionV2Error(
            "Official runtime v2 byte snapshots are invalid"
        )
    expected = (
        SPINE_PLAYER_JAVASCRIPT_SHA256,
        SPINE_PLAYER_STYLESHEET_SHA256,
    )
    actual = runtime.javascript_sha256, runtime.stylesheet_sha256
    content = (
        hashlib.sha256(javascript).hexdigest(),
        hashlib.sha256(stylesheet).hexdigest(),
    )
    if actual != expected or content != expected:
        raise BodySwayRuntimeCaptureSessionV2Error(
            "Official runtime v2 bytes differ from the pinned profile"
        )
    for value in (runtime.package_json_sha256, runtime.license_sha256):
        if type(value) is not str or len(value) != 64 \
                or any(character not in "0123456789abcdef"
                       for character in value):
            raise BodySwayRuntimeCaptureSessionV2Error(
                "Runtime package.json and LICENSE identities are required"
            )


def _copy(value: Any) -> dict[str, Any]:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
