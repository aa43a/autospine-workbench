"""Exact complete-session binding for immutable browser capture snapshots."""

from __future__ import annotations

from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureSnapshot,
)
from .body_sway_runtime_capture_inventory import (
    build_body_sway_runtime_capture_inventory,
)
from .body_sway_runtime_capture_session import (
    BodySwayRuntimeCaptureSessions,
)
from .body_sway_runtime_capture_session_validation import (
    require_body_sway_runtime_capture_session_set,
)


class BodySwayRuntimeCaptureSnapshotValidationError(ValueError):
    """Raised when callback reports or PNG bytes differ from exact sessions."""


def require_exact_body_sway_runtime_capture_snapshot(
    sessions: BodySwayRuntimeCaptureSessions,
    snapshot: BodySwayRuntimeCaptureSnapshot,
) -> dict:
    """Validate every report against its session and every image against bytes."""

    try:
        if type(sessions) is not BodySwayRuntimeCaptureSessions \
                or type(snapshot) is not BodySwayRuntimeCaptureSnapshot:
            raise BodySwayRuntimeCaptureSnapshotValidationError(
                "Runtime capture snapshot inputs are invalid"
            )
        require_body_sway_runtime_capture_session_set(sessions.document)
        reports = snapshot.reports
        if len(reports) != len(sessions.case_ids):
            raise BodySwayRuntimeCaptureSnapshotValidationError(
                "Runtime capture report count differs from the complete plan"
            )
        for case_id, report in zip(sessions.case_ids, reports, strict=True):
            session = sessions.session(case_id)
            common = {
                "status": "captured", "project_id": session["project_id"],
                "clip_id": session["clip_id"],
                "session_set_sha256": sessions.sha256,
                "runtime": session["runtime"], "source": session["source"],
                "assets": session["assets"], "capture": session["capture"],
                "case": session["case"],
            }
            if not isinstance(report, dict) \
                    or set(report) != {*common, "image"} \
                    or any(
                        report.get(field) != value
                        for field, value in common.items()
                    ):
                raise BodySwayRuntimeCaptureSnapshotValidationError(
                    "Runtime capture report differs from its exact session"
                )
        return build_body_sway_runtime_capture_inventory(snapshot)
    except BodySwayRuntimeCaptureSnapshotValidationError:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureSnapshotValidationError(
            f"Exact runtime capture snapshot validation failed: {exc}"
        ) from exc
