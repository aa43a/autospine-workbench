"""Pure outer evidence proving one official execution of payload v2."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
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
from .body_sway_runtime_capture_v2 import BodySwayRuntimeCaptureV2
from .body_sway_runtime_capture_v2_compiler import (
    BodySwayRuntimeCaptureV2CompilerError,
    require_exact_body_sway_runtime_capture_v2,
)
from .body_sway_runtime_execution_profile import (
    AUTHORITY,
    RELEASE_GATE,
    body_sway_runtime_execution_compiler_profile,
    body_sway_runtime_execution_runner_profile,
)
from .body_sway_runtime_execution_validation import (
    BodySwayRuntimeExecutionValidationError,
    require_body_sway_runtime_execution,
)
from .browser_executable_snapshot import BrowserExecutableSnapshot
from .spine42_runtime_inputs import Spine42RuntimePackage
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


class BodySwayRuntimeExecutionError(ValueError):
    """Raised when exact runner inputs cannot prove official execution."""


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeExecution:
    """Canonical receipt retaining its exact inner capture payload privately."""

    _canonical_json: str = field(repr=False)
    _capture: BodySwayRuntimeCaptureV2 = field(repr=False)

    @classmethod
    def from_detached(
        cls, document: dict[str, Any], capture: BodySwayRuntimeCaptureV2,
    ) -> "BodySwayRuntimeExecution":
        """Validate an immutable stored receipt without claiming currentness."""

        try:
            require_body_sway_runtime_execution(document, capture)
            return cls(_canonical(document), capture)
        except BodySwayRuntimeExecutionValidationError as exc:
            raise BodySwayRuntimeExecutionError(
                "Detached runtime execution evidence is invalid"
            ) from exc

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
    def capture(self) -> BodySwayRuntimeCaptureV2:
        return self._capture

    @property
    def artifact_set_sha256(self) -> str:
        return self._capture.artifact_set_sha256


def compile_body_sway_runtime_execution(
    preview: TemporaryBodySwayPreviewV2,
    runtime: Spine42RuntimePackage,
    sessions: BodySwayRuntimeCaptureSessionsV2,
    snapshot: BodySwayRuntimeCaptureSnapshot,
    browser: BrowserExecutableSnapshot,
    capture: BodySwayRuntimeCaptureV2,
    *,
    license_acknowledged: bool,
) -> BodySwayRuntimeExecution:
    """Bind actual collector callbacks to exact runtime, session, and payload."""

    if license_acknowledged is not True:
        raise BodySwayRuntimeExecutionError(
            "Explicit Spine runtime license acknowledgement is required"
        )
    try:
        _require_types(preview, runtime, sessions, snapshot, browser, capture)
        sessions = require_exact_body_sway_runtime_capture_sessions_v2(
            preview, runtime, sessions,
        )
        require_exact_body_sway_runtime_capture_snapshot_v2(
            sessions, snapshot,
        )
        replay_sha = require_exact_body_sway_runtime_capture_v2(
            preview, runtime, sessions, snapshot, browser, capture,
        )
        if replay_sha != capture.sha256:
            raise BodySwayRuntimeExecutionError(
                "Payload v2 identity changed during execution replay"
            )
        inner = capture.document
        source = inner["source"]
        document = {
            "format": "autospine-body-sway-runtime-execution",
            "format_version": 1,
            "project_id": inner["project_id"],
            "clip_id": inner["clip_id"],
            "source": {
                "temporary_preview_v2_sha256":
                    source["temporary_preview_v2_sha256"],
                "preview_artifact_set_sha256":
                    source["preview_artifact_set_sha256"],
                "runtime_capture_v2_sha256": capture.sha256,
                "capture_artifact_set_sha256":
                    capture.artifact_set_sha256,
                "runtime_session_set_v2_sha256": sessions.sha256,
                "capture_plan_v2_sha256":
                    source["capture_plan_v2_sha256"],
                "capture_framing_candidate_sha256":
                    source["capture_framing_candidate_sha256"],
                "capture_framing_decision_sha256":
                    source["capture_framing_decision_sha256"],
                "capture_framing_revision":
                    source["capture_framing_revision"],
                "body_sway_probe_report_sha256":
                    source["body_sway_probe_report_sha256"],
                "current_p10_1_head": source["current_p10_1_head"],
                "world_viewport": source["world_viewport"],
            },
            "compiler": body_sway_runtime_execution_compiler_profile(),
            "authority": _copy(AUTHORITY),
            "runtime": {
                **inner["runtime"],
                "package_json_sha256": runtime.package_json_sha256,
                "license_sha256": runtime.license_sha256,
                "license_acknowledged": True,
                "license_file_presence_is_authorization": False,
            },
            "browser": inner["browser"],
            "runner": body_sway_runtime_execution_runner_profile(),
            "reports": list(snapshot.reports),
            "status": "captured_unreviewed",
            "release_gate": _copy(RELEASE_GATE),
            "summary": {
                "case_count": len(snapshot.reports),
                "runtime_error_count": 0,
                "png_total_bytes": inner["summary"]["png_total_bytes"],
            },
        }
        require_body_sway_runtime_execution(document, capture)
        return BodySwayRuntimeExecution(_canonical(document), capture)
    except BodySwayRuntimeExecutionError:
        raise
    except _ERRORS as exc:
        raise BodySwayRuntimeExecutionError(
            f"Runtime execution evidence compilation failed: {exc}"
        ) from exc


def require_exact_body_sway_runtime_execution(
    preview, runtime, sessions, snapshot, browser, execution,
) -> str:
    """Recompile exact runner inputs and require the same outer receipt."""

    if type(execution) is not BodySwayRuntimeExecution:
        raise BodySwayRuntimeExecutionError(
            "Runtime execution evidence value is invalid"
        )
    expected = compile_body_sway_runtime_execution(
        preview, runtime, sessions, snapshot, browser, execution.capture,
        license_acknowledged=True,
    )
    if expected.canonical_bytes != execution.canonical_bytes \
            or expected.capture.canonical_bytes \
            != execution.capture.canonical_bytes \
            or expected.capture.capture_bytes \
            != execution.capture.capture_bytes:
        raise BodySwayRuntimeExecutionError(
            "Runtime execution evidence differs from exact replay"
        )
    return expected.sha256


def _require_types(preview, runtime, sessions, snapshot, browser, capture):
    if type(preview) is not TemporaryBodySwayPreviewV2 \
            or type(runtime) is not Spine42RuntimePackage \
            or type(sessions) is not BodySwayRuntimeCaptureSessionsV2 \
            or type(snapshot) is not BodySwayRuntimeCaptureSnapshot \
            or type(browser) is not BrowserExecutableSnapshot \
            or type(capture) is not BodySwayRuntimeCaptureV2:
        raise BodySwayRuntimeExecutionError(
            "Runtime execution compiler inputs are invalid"
        )


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_ERRORS = (
    AttributeError, BodySwayRuntimeCaptureSessionV2Error,
    BodySwayRuntimeCaptureSnapshotV2Error,
    BodySwayRuntimeCaptureV2CompilerError,
    BodySwayRuntimeExecutionValidationError, KeyError,
    OverflowError, TypeError, UnicodeError, ValueError,
)

__all__ = [
    "BodySwayRuntimeExecution", "BodySwayRuntimeExecutionError",
    "compile_body_sway_runtime_execution",
    "require_exact_body_sway_runtime_execution",
]
