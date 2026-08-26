"""Licensed application service for publishing P10 runtime captures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .body_sway_runtime_capture import BodySwayRuntimeCapture
from .body_sway_runtime_capture_validation import (
    BodySwayRuntimeCaptureValidationError,
    require_body_sway_runtime_capture,
)
from .body_sway_runtime_capture_store import (
    BodySwayRuntimeCaptureStore,
    BodySwayRuntimeCaptureStoreError,
    PublishedBodySwayRuntimeCapture,
)
from .p10_preview_commands import (
    P10PreviewCommandError,
    compile_body_sway_preview_command,
)
from .p10_runtime_capture_runner import (
    P10RuntimeCaptureResult,
    P10RuntimeCaptureRunnerError,
    run_p10_body_sway_runtime_capture,
)


class P10RuntimeCaptureCommandError(RuntimeError):
    """Raised when licensed runtime evidence cannot be captured and published."""


@dataclass(frozen=True, slots=True)
class P10RuntimeCaptureCommandResult:
    """Bounded public identity for immutable, still-unreviewed evidence."""

    path: Path
    temporary_preview_sha256: str
    runtime_capture_sha256: str
    artifact_set_sha256: str
    bundle_sha256: str
    case_count: int
    browser_family: str
    browser_reported_version: str
    release_gate_status: str
    release_gate_reason_codes: tuple[str, ...]
    reused: bool


def capture_body_sway_runtime_command(
    state_root: Path,
    project_id: str,
    candidates_path: Path,
    decision_path: Path,
    probe_report_path: Path,
    *,
    layer_manifest_sha256: str,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
    motion_instance_v2_sha256: str,
    reviewed_motion_bundle_sha256: str,
    runtime_root: Path,
    browser_executable: Path,
    license_acknowledged: bool,
) -> P10RuntimeCaptureCommandResult:
    """Compile, capture, and publish only after explicit license acknowledgement."""

    if license_acknowledged is not True:
        raise P10RuntimeCaptureCommandError(
            "Spine runtime license acknowledgement is required before capture"
        )
    try:
        preview = compile_body_sway_preview_command(
            state_root,
            project_id,
            candidates_path,
            decision_path,
            probe_report_path,
            layer_manifest_sha256=layer_manifest_sha256,
            p3_rig_sha256=p3_rig_sha256,
            p3_bundle_sha256=p3_bundle_sha256,
            motion_instance_sha256=motion_instance_sha256,
            motion_retarget_bundle_sha256=motion_retarget_bundle_sha256,
            motion_instance_v2_sha256=motion_instance_v2_sha256,
            reviewed_motion_bundle_sha256=reviewed_motion_bundle_sha256,
        )
        captured = run_p10_body_sway_runtime_capture(
            preview,
            runtime_root=runtime_root,
            browser_executable=browser_executable,
            license_acknowledged=True,
        )
        _require_capture_result(project_id, preview, captured)
        published = BodySwayRuntimeCaptureStore(state_root).publish(
            captured._capture
        )
        _require_matching_publication(
            project_id, captured, published
        )
        release_gate = captured._capture.document["release_gate"]
        return P10RuntimeCaptureCommandResult(
            path=published.path,
            temporary_preview_sha256=captured.temporary_preview_sha256,
            runtime_capture_sha256=captured.runtime_capture_sha256,
            artifact_set_sha256=captured.artifact_set_sha256,
            bundle_sha256=published.bundle_sha256,
            case_count=captured.case_count,
            browser_family=captured.browser_family,
            browser_reported_version=captured.browser_reported_version,
            release_gate_status=release_gate["status"],
            release_gate_reason_codes=tuple(release_gate["reason_codes"]),
            reused=published.reused,
        )
    except P10RuntimeCaptureCommandError:
        raise
    except _ERRORS as exc:
        raise P10RuntimeCaptureCommandError(
            f"Body-sway runtime capture command failed: {exc}"
        ) from exc


def _require_capture_result(
    project_id: str, preview, captured: P10RuntimeCaptureResult,
) -> None:
    if type(captured) is not P10RuntimeCaptureResult \
            or type(captured._capture) is not BodySwayRuntimeCapture:
        raise P10RuntimeCaptureCommandError(
            "Runtime capture service returned an invalid result"
        )
    capture = captured._capture
    document = capture.document
    require_body_sway_runtime_capture(document, capture.capture_bytes)
    source = document["source"]
    browser = document["browser"]
    release_gate = document["release_gate"]
    if capture.sha256 != captured.runtime_capture_sha256 \
            or capture.artifact_set_sha256 != captured.artifact_set_sha256 \
            or source["temporary_preview_sha256"] \
                != captured.temporary_preview_sha256 \
            or captured.temporary_preview_sha256 \
                != preview.temporary_preview_sha256 \
            or document["project_id"] != project_id \
            or type(captured.case_count) is not int \
            or captured.case_count != len(document["cases"]) \
            or captured.case_count != document["summary"]["case_count"] \
            or captured.browser_family not in {"google-chrome", "chromium"} \
            or browser["family"] != captured.browser_family \
            or not _is_browser_version(captured.browser_reported_version) \
            or browser["reported_version"] \
                != captured.browser_reported_version \
            or document["status"] != "captured_unreviewed" \
            or release_gate["status"] != "blocked" \
            or type(release_gate["reason_codes"]) is not list \
            or not release_gate["reason_codes"]:
        raise P10RuntimeCaptureCommandError(
            "Runtime capture result differs from its exact preview"
        )


def _require_matching_publication(
    project_id: str,
    captured: P10RuntimeCaptureResult,
    published: PublishedBodySwayRuntimeCapture,
) -> None:
    if type(captured) is not P10RuntimeCaptureResult \
            or type(published) is not PublishedBodySwayRuntimeCapture:
        raise P10RuntimeCaptureCommandError(
            "Runtime capture service returned an invalid result"
        )
    expected = (
        published.project_id == project_id,
        published.temporary_preview_sha256
            == captured.temporary_preview_sha256,
        published.manifest_sha256 == captured.runtime_capture_sha256,
        published.artifact_set_sha256 == captured.artifact_set_sha256,
        _is_sha(published.bundle_sha256),
        isinstance(published.path, Path),
        type(published.reused) is bool,
        type(captured.case_count) is int and captured.case_count > 0,
        type(captured.browser_family) is str and bool(captured.browser_family),
        type(captured.browser_reported_version) is str
            and bool(captured.browser_reported_version),
    )
    if not all(expected):
        raise P10RuntimeCaptureCommandError(
            "Published runtime capture identity differs from captured evidence"
        )


def _is_sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 \
        and all(character in "0123456789abcdef" for character in value)


def _is_browser_version(value: object) -> bool:
    if type(value) is not str:
        return False
    parts = value.split(".")
    return len(parts) == 4 and all(
        1 <= len(part) <= 6
        and all(character in "0123456789" for character in part)
        for part in parts
    )


_ERRORS = (
    AttributeError,
    BodySwayRuntimeCaptureValidationError,
    BodySwayRuntimeCaptureStoreError,
    KeyError,
    OSError,
    OverflowError,
    P10PreviewCommandError,
    P10RuntimeCaptureRunnerError,
    RecursionError,
    TypeError,
    UnicodeError,
    ValueError,
)
