"""Frozen exact official-runtime session set for every P10 capture case."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_runtime_capture_session_validation import (
    SESSION_FORMAT,
    SESSION_FORMAT_VERSION,
    SESSION_SET_FORMAT,
    SESSION_SET_FORMAT_VERSION,
    require_body_sway_runtime_capture_session_set,
)
from .spine42_runtime_inputs import Spine42RuntimePackage
from .spine42_runtime_profile import (
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)
from .temporary_body_sway_preview import TemporaryBodySwayPreview
from .temporary_body_sway_preview_validation import (
    require_temporary_body_sway_preview,
)


MAX_RUNTIME_JAVASCRIPT_BYTES = 2 * 1024 * 1024
MAX_RUNTIME_STYLESHEET_BYTES = 512 * 1024


class BodySwayRuntimeCaptureSessionError(ValueError):
    """Raised when a preview/runtime pair cannot form exact sessions."""


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeCaptureSessions:
    """Canonical complete plan; callers receive only detached JSON copies."""

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
        cases = self.document["capture_plan"]["cases"]
        return tuple(row["case_id"] for row in cases)

    def session(self, case_id: str) -> dict[str, Any]:
        document = self.document
        row = next(
            (item for item in document["capture_plan"]["cases"]
             if item["case_id"] == case_id),
            None,
        )
        if row is None:
            raise BodySwayRuntimeCaptureSessionError(
                "Capture case is absent from the exact session set"
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


def build_body_sway_runtime_capture_sessions(
    preview: TemporaryBodySwayPreview,
    runtime: Spine42RuntimePackage,
) -> BodySwayRuntimeCaptureSessions:
    """Build one frozen set binding the complete ordered capture plan."""

    try:
        if type(preview) is not TemporaryBodySwayPreview \
                or type(runtime) is not Spine42RuntimePackage:
            raise BodySwayRuntimeCaptureSessionError(
                "Runtime capture requires exact preview and runtime snapshots"
            )
        document, artifacts = preview.document, preview.artifact_bytes
        require_temporary_body_sway_preview(document, artifacts)
        _require_runtime(runtime)
        rows = {row["role"]: row for row in document["artifacts"]["files"]}
        capture_plan = document["capture_plan"]
        value = {
            "format": SESSION_SET_FORMAT,
            "format_version": SESSION_SET_FORMAT_VERSION,
            "project_id": document["project_id"],
            "clip_id": document["clip_id"],
            "runtime": {
                **document["runtime_target"]["runtime"],
                "javascript_sha256": runtime.javascript_sha256,
                "stylesheet_sha256": runtime.stylesheet_sha256,
            },
            "source": {
                "temporary_preview_sha256": preview.sha256,
                "artifact_set_sha256": preview.artifact_set_sha256,
                "preview_projection_sha256":
                    document["projection"]["projection_sha256"],
                "capture_plan_sha256": capture_plan["capture_plan_sha256"],
            },
            "timing": document["timing"],
            "selection": document["selection"],
            "sample_ticks": document["projection"]["sample_ticks"],
            "assets": {
                "skeleton_sha256": rows["spine-skeleton"]["sha256"],
                "atlas_sha256": rows["spine-atlas"]["sha256"],
                "texture_sha256": rows["spine-texture"]["sha256"],
                "texture_size": [
                    document["summary"]["atlas_width"],
                    document["summary"]["atlas_height"],
                ],
            },
            "capture_plan": capture_plan,
            "summary": {"case_count": len(capture_plan["cases"])},
        }
        require_body_sway_runtime_capture_session_set(value)
        return BodySwayRuntimeCaptureSessions(_canonical(value))
    except BodySwayRuntimeCaptureSessionError:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureSessionError(
            f"Body-sway runtime capture session failed: {exc}"
        ) from exc


def require_exact_body_sway_runtime_capture_sessions(
    preview: TemporaryBodySwayPreview,
    runtime: Spine42RuntimePackage,
    sessions: BodySwayRuntimeCaptureSessions,
) -> BodySwayRuntimeCaptureSessions:
    """Rebuild the complete plan and reject any cross-wired session set."""

    if type(sessions) is not BodySwayRuntimeCaptureSessions:
        raise BodySwayRuntimeCaptureSessionError(
            "Runtime capture session set is invalid"
        )
    expected = build_body_sway_runtime_capture_sessions(preview, runtime)
    if sessions.canonical_bytes != expected.canonical_bytes:
        raise BodySwayRuntimeCaptureSessionError(
            "Runtime capture session set differs from preview/runtime replay"
        )
    return expected


def _require_runtime(runtime: Spine42RuntimePackage) -> None:
    javascript, stylesheet = runtime.javascript_bytes, runtime.stylesheet_bytes
    if type(javascript) is not bytes \
            or not 0 < len(javascript) <= MAX_RUNTIME_JAVASCRIPT_BYTES \
            or type(stylesheet) is not bytes \
            or not 0 < len(stylesheet) <= MAX_RUNTIME_STYLESHEET_BYTES:
        raise BodySwayRuntimeCaptureSessionError(
            "Official runtime byte snapshots are invalid"
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
        raise BodySwayRuntimeCaptureSessionError(
            "Official runtime bytes differ from the pinned capture profile"
        )


def _copy(value: Any) -> dict[str, Any]:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
