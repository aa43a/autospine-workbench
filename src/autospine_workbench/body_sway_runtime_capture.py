"""Pure compiler for one unreviewed BodySwayRuntimeCapture v1 package."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureSnapshot,
)
from .body_sway_runtime_capture_inventory import BodySwayRuntimeCaptureInventoryError
from .body_sway_runtime_capture_profile import (
    CAPTURE_RELEASE_GATE,
    CAPTURE_SEMANTICS,
    body_sway_runtime_capture_compiler_profile,
    body_sway_runtime_capture_runner_profile,
)
from .body_sway_runtime_capture_session import (
    BodySwayRuntimeCaptureSessionError,
    BodySwayRuntimeCaptureSessions,
    require_exact_body_sway_runtime_capture_sessions,
)
from .body_sway_runtime_capture_snapshot_validation import (
    BodySwayRuntimeCaptureSnapshotValidationError,
    require_exact_body_sway_runtime_capture_snapshot,
)
from .body_sway_runtime_capture_validation import (
    FORMAT,
    FORMAT_VERSION,
    BodySwayRuntimeCaptureValidationError,
    body_sway_runtime_capture_case_stream_sha256,
    require_body_sway_runtime_capture,
)
from .browser_executable_snapshot import BrowserExecutableSnapshot
from .browser_version_identity import (
    BrowserVersionIdentityError,
    browser_version_identity_sha256,
)
from .spine42_runtime_inputs import Spine42RuntimePackage
from .temporary_body_sway_preview import TemporaryBodySwayPreview
from .temporary_body_sway_preview_validation import (
    TemporaryBodySwayPreviewValidationError,
    require_temporary_body_sway_preview,
)


class BodySwayRuntimeCaptureError(ValueError):
    """Raised when complete runtime evidence cannot form a public package."""


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeCapture:
    """Frozen canonical manifest and its exact detached capture PNG bytes."""

    _canonical_json: str = field(repr=False)
    _capture_items: tuple[tuple[str, bytes], ...] = field(repr=False)

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
    def capture_bytes(self) -> dict[str, bytes]:
        return dict(self._capture_items)

    @property
    def artifact_set_sha256(self) -> str:
        return self.document["artifacts"]["artifact_set_sha256"]


def compile_body_sway_runtime_capture(
    preview: TemporaryBodySwayPreview,
    runtime: Spine42RuntimePackage,
    sessions: BodySwayRuntimeCaptureSessions,
    snapshot: BodySwayRuntimeCaptureSnapshot,
    browser: BrowserExecutableSnapshot,
) -> BodySwayRuntimeCapture:
    """Compile complete collector output without granting visual approval."""

    try:
        if type(preview) is not TemporaryBodySwayPreview \
                or type(runtime) is not Spine42RuntimePackage \
                or type(sessions) is not BodySwayRuntimeCaptureSessions \
                or type(snapshot) is not BodySwayRuntimeCaptureSnapshot \
                or type(browser) is not BrowserExecutableSnapshot:
            raise BodySwayRuntimeCaptureError(
                "Runtime capture compilation requires exact input snapshots"
            )
        require_temporary_body_sway_preview(
            preview.document, preview.artifact_bytes
        )
        sessions = require_exact_body_sway_runtime_capture_sessions(
            preview, runtime, sessions
        )
        reports = snapshot.reports
        inventory = require_exact_body_sway_runtime_capture_snapshot(
            sessions, snapshot
        )
        preview_document = preview.document
        plan = preview_document["capture_plan"]
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
        pair_count = (len(cases) - 1) // 2
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": preview_document["project_id"],
            "clip_id": preview_document["clip_id"],
            "source": {
                "temporary_preview_sha256": preview.sha256,
                "preview_artifact_set_sha256": preview.artifact_set_sha256,
                "preview_projection_sha256":
                    preview_document["projection"]["projection_sha256"],
                "capture_plan_sha256": plan["capture_plan_sha256"],
                "runtime_session_set_sha256": sessions.sha256,
                "upstream": preview_document["source"],
            },
            "timing": preview_document["timing"],
            "selection": preview_document["selection"],
            "compiler": body_sway_runtime_capture_compiler_profile(),
            "semantics": _copy(CAPTURE_SEMANTICS),
            "runtime": sessions.document["runtime"],
            "assets": sessions.document["assets"],
            "browser": _browser(browser),
            "runner": body_sway_runtime_capture_runner_profile(),
            "capture": {
                "plan": plan,
                "sample_ticks": preview_document["projection"]["sample_ticks"],
                "case_stream_sha256":
                    body_sway_runtime_capture_case_stream_sha256(cases),
            },
            "cases": cases,
            "artifacts": inventory,
            "status": "captured_unreviewed",
            "release_gate": _copy(CAPTURE_RELEASE_GATE),
            "summary": {
                "case_count": len(cases), "setup_case_count": 1,
                "base_case_count": pair_count,
                "combined_case_count": pair_count,
                "runtime_error_count": 0,
                "png_total_bytes": inventory["total_bytes"],
            },
        }
        require_body_sway_runtime_capture(document, snapshot.capture_bytes)
        return BodySwayRuntimeCapture(
            _canonical(document),
            tuple(sorted(snapshot.capture_bytes.items())),
        )
    except BodySwayRuntimeCaptureError:
        raise
    except (
        BodySwayRuntimeCaptureInventoryError,
        BodySwayRuntimeCaptureSnapshotValidationError,
        BodySwayRuntimeCaptureSessionError,
        BodySwayRuntimeCaptureValidationError,
        TemporaryBodySwayPreviewValidationError,
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureError(
            f"Body-sway runtime capture compilation failed: {exc}"
        ) from exc


def require_exact_body_sway_runtime_capture(
    preview: TemporaryBodySwayPreview,
    runtime: Spine42RuntimePackage,
    sessions: BodySwayRuntimeCaptureSessions,
    snapshot: BodySwayRuntimeCaptureSnapshot,
    browser: BrowserExecutableSnapshot,
    document: dict[str, Any],
    capture_bytes: dict[str, bytes],
) -> str:
    """Recompile trusted inputs and require byte-identical public evidence."""

    try:
        require_body_sway_runtime_capture(document, capture_bytes)
        expected = compile_body_sway_runtime_capture(
            preview, runtime, sessions, snapshot, browser
        )
        if _canonical(document).encode("utf-8") != expected.canonical_bytes \
                or capture_bytes != expected.capture_bytes:
            raise BodySwayRuntimeCaptureError(
                "Runtime capture differs from exact input replay"
            )
        return expected.sha256
    except BodySwayRuntimeCaptureError:
        raise
    except (
        BodySwayRuntimeCaptureValidationError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureError(
            f"Exact runtime capture replay failed: {exc}"
        ) from exc


def _browser(value: BrowserExecutableSnapshot) -> dict[str, Any]:
    try:
        version_sha256 = browser_version_identity_sha256(
            value.family, value.reported_version
        )
    except BrowserVersionIdentityError as exc:
        raise BodySwayRuntimeCaptureError(
            "Browser snapshot version identity is invalid"
        ) from exc
    if value.version_output_sha256 != version_sha256:
        raise BodySwayRuntimeCaptureError(
            "Browser snapshot version identity SHA-256 is inconsistent"
        )
    return {
        "family": value.family,
        "reported_version": value.reported_version,
        "version_output_sha256": version_sha256,
        "executable_sha256": value.executable_sha256,
        "executable_size": value.size_bytes,
        "identity_scope": "launcher-executable-and-reported-version",
    }


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
