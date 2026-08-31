"""Package-centric publication command for official Preview v2 execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable

from .body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecutionReader,
    VerifiedBodySwayRuntimeExecutionReaderError,
)
from .body_sway_runtime_execution_store import (
    BodySwayRuntimeExecutionStore,
    BodySwayRuntimeExecutionStoreError,
)
from .p10_preview_v2_commands import (
    P10PreviewV2CommandError,
    P10PreviewV2CommandResult,
    compile_body_sway_preview_v2_for_package,
    require_exact_preview_v2_for_mount,
)
from .p10_runtime_capture_v2_runner import (
    P10RuntimeCaptureV2Progress,
    P10RuntimeCaptureV2RunnerError,
    run_p10_body_sway_runtime_capture_v2,
)
from .p10_runtime_environment import P10RuntimeEnvironment
from .project_store import ProjectStore


class P10RuntimeCaptureV2CommandError(RuntimeError):
    """Raised unless one current package publishes exact execution evidence."""


@dataclass(frozen=True, slots=True)
class P10RuntimeCaptureV2CommandResult:
    package_id: str
    project_id: str
    clip_id: str
    temporary_preview_v2_sha256: str
    runtime_execution_sha256: str
    runtime_capture_v2_sha256: str
    artifact_set_sha256: str
    bundle_sha256: str
    browser_family: str
    browser_reported_version: str
    case_count: int
    reused: bool

    def public_document(self) -> dict:
        return {
            "format": "autospine-p10-runtime-capture-v2-command-result",
            "format_version": 1,
            "package_id": self.package_id,
            "project_id": self.project_id,
            "clip_id": self.clip_id,
            "addresses": {
                "project_id": self.project_id,
                "temporary_preview_v2_sha256":
                    self.temporary_preview_v2_sha256,
                "bundle_sha256": self.bundle_sha256,
                "artifact_set_sha256": self.artifact_set_sha256,
            },
            "runtime_execution_sha256": self.runtime_execution_sha256,
            "runtime_capture_v2_sha256": self.runtime_capture_v2_sha256,
            "browser": {
                "family": self.browser_family,
                "reported_version": self.browser_reported_version,
            },
            "summary": {"case_count": self.case_count},
            "reused": self.reused,
            "status": "captured_unreviewed",
        }


def execute_p10_runtime_capture_v2_for_package(
    store: ProjectStore,
    package_id: str,
    *,
    environment: P10RuntimeEnvironment,
    expected_p10_1: Mapping,
    expected_framing: Mapping,
    license_acknowledged: bool,
    run_confirmed: bool,
    on_progress: Callable[[P10RuntimeCaptureV2Progress], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> P10RuntimeCaptureV2CommandResult:
    """Compile current Preview v2, execute, publish, and exact-read it back."""

    if type(store) is not ProjectStore:
        raise P10RuntimeCaptureV2CommandError(
            "Runtime capture v2 command requires a ProjectStore"
        )
    try:
        preview = compile_body_sway_preview_v2_for_package(store, package_id)
        _require_expected_heads(
            preview, expected_p10_1, expected_framing,
        )
        capture = run_p10_body_sway_runtime_capture_v2(
            preview,
            environment=environment,
            license_acknowledged=license_acknowledged,
            run_confirmed=run_confirmed,
            on_progress=on_progress,
            is_cancelled=is_cancelled,
        )
        published = BodySwayRuntimeExecutionStore(store.state_root).publish(
            capture.execution,
        )
        verified = VerifiedBodySwayRuntimeExecutionReader(
            store.state_root,
        ).load(
            published.project_id,
            published.temporary_preview_v2_sha256,
            published.bundle_sha256,
            published.artifact_set_sha256,
        )
        _require_addresses(capture, published, verified)
        current = require_exact_preview_v2_for_mount(preview)
        if current.sha256 != published.temporary_preview_v2_sha256:
            raise P10RuntimeCaptureV2CommandError(
                "Preview v2 changed before execution publication completed"
            )
        return P10RuntimeCaptureV2CommandResult(
            package_id,
            published.project_id,
            capture.clip_id,
            published.temporary_preview_v2_sha256,
            published.execution_sha256,
            published.runtime_capture_v2_sha256,
            published.artifact_set_sha256,
            published.bundle_sha256,
            capture.browser_family,
            capture.browser_reported_version,
            capture.case_count,
            published.reused,
        )
    except P10RuntimeCaptureV2CommandError:
        raise
    except _ERRORS as exc:
        raise P10RuntimeCaptureV2CommandError(
            f"Package-centric runtime capture v2 failed: {exc}"
        ) from exc


def _require_addresses(capture, published, verified):
    execution = verified.execution
    source = execution.document["source"]
    actual = (
        verified.project_id,
        verified.temporary_preview_v2_sha256,
        verified.bundle_sha256,
        verified.artifact_set_sha256,
        execution.sha256,
        source["runtime_capture_v2_sha256"],
    )
    expected = (
        capture.project_id,
        capture.temporary_preview_v2_sha256,
        published.bundle_sha256,
        capture.artifact_set_sha256,
        capture.runtime_execution_sha256,
        capture.runtime_capture_v2_sha256,
    )
    if actual != expected:
        raise P10RuntimeCaptureV2CommandError(
            "Published runtime execution differs from its exact readback"
        )


def _require_expected_heads(preview, expected_p10_1, expected_framing):
    p10 = _head(expected_p10_1, "P10.1")
    framing = _head(expected_framing, "capture framing")
    actual_p10 = preview.document["source"]["current_p10_1_head"]
    actual_framing = {
        "candidate_sha256": preview.capture_framing_candidate_sha256,
        "decision_sha256": preview.capture_framing_decision_sha256,
        "revision": preview.capture_framing_revision,
    }
    if p10 != actual_p10 or framing != actual_framing:
        raise P10RuntimeCaptureV2CommandError(
            "The confirmed P10.1 or capture-framing head is stale"
        )


def _head(value, label):
    fields = {"candidate_sha256", "decision_sha256", "revision"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise P10RuntimeCaptureV2CommandError(
            f"Expected {label} identity is invalid"
        )
    row = dict(value)
    for name in ("candidate_sha256", "decision_sha256"):
        digest = row[name]
        if type(digest) is not str or len(digest) != 64 \
                or any(character not in "0123456789abcdef" for character in digest):
            raise P10RuntimeCaptureV2CommandError(
                f"Expected {label} identity is invalid"
            )
    revision = row["revision"]
    if type(revision) is not int or not 1 <= revision <= 1_000_000_000:
        raise P10RuntimeCaptureV2CommandError(
            f"Expected {label} identity is invalid"
        )
    return row


_ERRORS = (
    BodySwayRuntimeExecutionStoreError,
    P10PreviewV2CommandError,
    P10RuntimeCaptureV2RunnerError,
    VerifiedBodySwayRuntimeExecutionReaderError,
    KeyError, OSError, TypeError, ValueError,
)


__all__ = [
    "P10RuntimeCaptureV2CommandError", "P10RuntimeCaptureV2CommandResult",
    "execute_p10_runtime_capture_v2_for_package",
]
