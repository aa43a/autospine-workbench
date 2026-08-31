"""Exact collector snapshot checks for capture-framed RuntimeCapture v2."""

from __future__ import annotations

import hashlib

from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureSnapshot,
)
from .body_sway_runtime_capture_session_v2 import (
    BodySwayRuntimeCaptureSessionsV2,
)
from .body_sway_runtime_capture_v2_inventory import (
    BodySwayRuntimeCaptureV2InventoryError,
    build_body_sway_runtime_capture_v2_inventory,
)


class BodySwayRuntimeCaptureSnapshotV2Error(ValueError):
    """Raised when browser callbacks do not match every exact v2 session."""


def require_exact_body_sway_runtime_capture_snapshot_v2(
    sessions: BodySwayRuntimeCaptureSessionsV2,
    snapshot: BodySwayRuntimeCaptureSnapshot,
) -> dict:
    """Validate ordered reports, PNG bytes, dimensions, and session seals."""

    try:
        if type(sessions) is not BodySwayRuntimeCaptureSessionsV2 \
                or type(snapshot) is not BodySwayRuntimeCaptureSnapshot:
            raise BodySwayRuntimeCaptureSnapshotV2Error(
                "Runtime capture v2 requires exact sessions and snapshot"
            )
        reports = snapshot.reports
        captures = snapshot.capture_bytes
        if len(reports) != len(sessions.case_ids) \
                or set(captures) != {
                    f"captures/{case_id}.png" for case_id in sessions.case_ids
                }:
            raise BodySwayRuntimeCaptureSnapshotV2Error(
                "Runtime capture v2 snapshot inventory differs from sessions"
            )
        for case_id, report in zip(
            sessions.case_ids, reports, strict=True,
        ):
            _require_report(
                sessions,
                sessions.session(case_id),
                case_id,
                report,
                captures[f"captures/{case_id}.png"],
            )
        return build_body_sway_runtime_capture_v2_inventory(
            list(sessions.case_ids), captures,
        )
    except BodySwayRuntimeCaptureSnapshotV2Error:
        raise
    except (
        AttributeError, BodySwayRuntimeCaptureV2InventoryError,
        KeyError, OverflowError, TypeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureSnapshotV2Error(
            f"Runtime capture v2 snapshot validation failed: {exc}"
        ) from exc


def _require_report(sessions, session, case_id, report, raw):
    expected_fields = {
        "status", "project_id", "clip_id", "session_set_sha256",
        "runtime", "source", "assets", "capture", "case", "image",
    }
    image = report.get("image") if type(report) is dict else None
    expected_path = f"captures/{case_id}.png"
    capture = session["capture"]
    dpr = capture["device_pixel_ratio"]
    viewport = capture["viewport"]
    expected_image = {
        "path": expected_path,
        "png_sha256": hashlib.sha256(raw).hexdigest(),
        "width": viewport["width"] * dpr,
        "height": viewport["height"] * dpr,
        "size_bytes": len(raw),
    }
    if type(report) is not dict or set(report) != expected_fields \
            or report.get("status") != "captured" \
            or report.get("project_id") != session["project_id"] \
            or report.get("clip_id") != session["clip_id"] \
            or report.get("session_set_sha256") != sessions.sha256 \
            or report.get("runtime") != session["runtime"] \
            or report.get("source") != session["source"] \
            or report.get("assets") != session["assets"] \
            or report.get("capture") != capture \
            or report.get("case") != session["case"] \
            or image != expected_image:
        raise BodySwayRuntimeCaptureSnapshotV2Error(
            "Runtime capture v2 report differs from its exact session or PNG"
        )


__all__ = [
    "BodySwayRuntimeCaptureSnapshotV2Error",
    "require_exact_body_sway_runtime_capture_snapshot_v2",
]
