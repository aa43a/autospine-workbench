"""Pure compiler for the inner capture-framed RuntimeCapture v2 payload."""

from __future__ import annotations

import json
from typing import Any

from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureSnapshot,
)
from .body_sway_runtime_capture_session_v2 import (
    BodySwayRuntimeCaptureSessionV2Error,
    BodySwayRuntimeCaptureSessionsV2,
    require_exact_body_sway_runtime_capture_sessions_v2,
)
from .body_sway_runtime_capture_snapshot_v2 import (
    BodySwayRuntimeCaptureSnapshotV2Error,
    require_exact_body_sway_runtime_capture_snapshot_v2,
)
from .body_sway_runtime_capture_v2 import (
    BodySwayRuntimeCaptureV2,
    BodySwayRuntimeCaptureV2Error,
    require_body_sway_runtime_capture_v2_preview_binding,
)
from .body_sway_runtime_capture_v2_profile import (
    RELEASE_GATE,
    SEMANTICS,
    body_sway_runtime_capture_v2_compiler_profile,
)
from .body_sway_runtime_capture_v2_validation import (
    body_sway_runtime_capture_v2_case_stream_sha256,
)
from .browser_executable_snapshot import BrowserExecutableSnapshot
from .browser_version_identity import browser_version_identity_sha256
from .resolved_project import canonical_sha256
from .spine42_runtime_inputs import Spine42RuntimePackage
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


class BodySwayRuntimeCaptureV2CompilerError(ValueError):
    """Raised when completed collector bytes cannot form the v2 payload."""


def compile_body_sway_runtime_capture_v2(
    preview: TemporaryBodySwayPreviewV2,
    runtime: Spine42RuntimePackage,
    sessions: BodySwayRuntimeCaptureSessionsV2,
    snapshot: BodySwayRuntimeCaptureSnapshot,
    browser: BrowserExecutableSnapshot,
) -> BodySwayRuntimeCaptureV2:
    """Compile validated PNG bytes; execution authority remains external."""

    try:
        _require_types(preview, runtime, sessions, snapshot, browser)
        sessions = require_exact_body_sway_runtime_capture_sessions_v2(
            preview, runtime, sessions,
        )
        inventory = require_exact_body_sway_runtime_capture_snapshot_v2(
            sessions, snapshot,
        )
        preview_document = preview.document
        source = preview_document["source"]
        projection = preview_document["projection"]
        plan = preview_document["capture_plan"]
        reports = snapshot.reports
        files = {row["case_id"]: row for row in inventory["files"]}
        cases = [
            {
                "case_id": report["case"]["id"],
                "animation": report["case"]["animation"],
                "tick": report["case"]["tick"],
                "time_seconds": report["case"]["time_seconds"],
                "image_path": report["image"]["path"],
                "png_sha256": report["image"]["png_sha256"],
            }
            for report in reports
        ]
        if any(files[row["case_id"]]["path"] != row["image_path"]
               for row in cases):
            raise BodySwayRuntimeCaptureV2CompilerError(
                "Runtime capture v2 cases differ from the PNG inventory"
            )
        pair_count = (len(cases) - 1) // 2
        roles = {
            row["role"]: row for row in preview_document["artifacts"]["files"]
        }
        document = {
            "format": "autospine-body-sway-runtime-capture",
            "format_version": 2,
            "project_id": preview_document["project_id"],
            "clip_id": preview_document["clip_id"],
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
                "body_sway_probe_report_sha256":
                    source["body_sway_probe_report_sha256"],
                "current_p10_1_head": source["current_p10_1_head"],
                "world_viewport": plan["world_viewport"],
            },
            "timing": preview_document["timing"],
            "selection": preview_document["selection"],
            "compiler": body_sway_runtime_capture_v2_compiler_profile(),
            "semantics": _copy(SEMANTICS),
            "runtime": _runtime(sessions.document["runtime"]),
            "assets": {
                "skeleton_sha256": roles["spine-skeleton-v2"]["sha256"],
                "atlas_sha256": roles["spine-atlas"]["sha256"],
                "texture_sha256": roles["spine-texture"]["sha256"],
                "texture_size": [
                    preview_document["summary"]["atlas_width"],
                    preview_document["summary"]["atlas_height"],
                ],
            },
            "browser": _browser(browser),
            "capture": {
                "viewport": plan["viewport"],
                "device_pixel_ratio": plan["device_pixel_ratio"],
                "background": plan["background"],
                "preserve_drawing_buffer": plan["preserve_drawing_buffer"],
                "world_viewport": plan["world_viewport"],
                "capture_plan_sha256": plan["capture_plan_sha256"],
                "case_stream_sha256":
                    body_sway_runtime_capture_v2_case_stream_sha256(cases),
                "cases": plan["cases"],
            },
            "cases": cases,
            "artifacts": inventory,
            "status":
                "validated_capture_payload_ready_for_official_runtime_execution",
            "release_gate": _copy(RELEASE_GATE),
            "summary": {
                "case_count": len(cases), "setup_case_count": 1,
                "base_case_count": pair_count,
                "combined_case_count": pair_count,
                "runtime_error_count": 0,
                "png_total_bytes": inventory["total_bytes"],
            },
        }
        result = BodySwayRuntimeCaptureV2.from_detached(
            document, snapshot.capture_bytes,
        )
        require_body_sway_runtime_capture_v2_preview_binding(result, preview)
        return result
    except BodySwayRuntimeCaptureV2CompilerError:
        raise
    except _ERRORS as exc:
        raise BodySwayRuntimeCaptureV2CompilerError(
            f"Runtime capture v2 compilation failed: {exc}"
        ) from exc


def require_exact_body_sway_runtime_capture_v2(
    preview, runtime, sessions, snapshot, browser, capture,
) -> str:
    """Recompile all trusted runner inputs and require byte identity."""

    if type(capture) is not BodySwayRuntimeCaptureV2:
        raise BodySwayRuntimeCaptureV2CompilerError(
            "Runtime capture v2 value is invalid"
        )
    expected = compile_body_sway_runtime_capture_v2(
        preview, runtime, sessions, snapshot, browser,
    )
    if expected.canonical_bytes != capture.canonical_bytes \
            or expected.capture_bytes != capture.capture_bytes:
        raise BodySwayRuntimeCaptureV2CompilerError(
            "Runtime capture v2 differs from exact runner replay"
        )
    return expected.sha256


def _require_types(preview, runtime, sessions, snapshot, browser):
    if type(preview) is not TemporaryBodySwayPreviewV2 \
            or type(runtime) is not Spine42RuntimePackage \
            or type(sessions) is not BodySwayRuntimeCaptureSessionsV2 \
            or type(snapshot) is not BodySwayRuntimeCaptureSnapshot \
            or type(browser) is not BrowserExecutableSnapshot:
        raise BodySwayRuntimeCaptureV2CompilerError(
            "Runtime capture v2 compiler inputs are invalid"
        )


def _runtime(value):
    return {key: value[key] for key in (
        "package", "version", "npm_integrity",
        "javascript_sha256", "stylesheet_sha256",
    )}


def _browser(value):
    return {
        "family": value.family,
        "reported_version": value.reported_version,
        "version_output_sha256": browser_version_identity_sha256(
            value.family, value.reported_version,
        ),
        "executable_sha256": value.executable_sha256,
        "executable_size": value.size_bytes,
        "identity_scope": "launcher-executable-and-reported-version",
    }


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_ERRORS = (
    AttributeError, BodySwayRuntimeCaptureSessionV2Error,
    BodySwayRuntimeCaptureSnapshotV2Error,
    BodySwayRuntimeCaptureV2Error, KeyError, OverflowError,
    TypeError, UnicodeError, ValueError,
)

__all__ = [
    "BodySwayRuntimeCaptureV2CompilerError",
    "compile_body_sway_runtime_capture_v2",
    "require_exact_body_sway_runtime_capture_v2",
]
