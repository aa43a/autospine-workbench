"""Pure report and snapshot consistency helpers for runtime PNG capture."""

from __future__ import annotations

import hashlib
import json
import struct

from .spine42_v3_runtime_session_core import copy_json


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_dimensions(raw: bytes, *, error_type) -> tuple[int, int]:
    if len(raw) < 24 or raw[:8] != _PNG_SIGNATURE \
            or raw[12:16] != b"IHDR":
        raise error_type("Runtime capture is not a canonical PNG header")
    return struct.unpack(">II", raw[16:24])


def base_report(session, status):
    return {
        "status": status,
        "session_set_sha256": session["session_set_sha256"],
        "plan_sha256": session["plan_sha256"],
        "source": session["source"], "runtime": session["runtime"],
        "assets": session["assets"], "capture": session["capture"],
        "case": session["case"], "artifact": session["artifact"],
        **({"source_admission_sha256": session["source_admission_sha256"]}
           if "source_admission_sha256" in session else {}),
    }


def capture_report(session, raw, width, height, observed):
    report = base_report(session, "captured")
    report["observables"] = copy_json(observed)
    report["image"] = {
        "path": session["artifact"]["path"],
        "png_sha256": hashlib.sha256(raw).hexdigest(),
        "width": width, "height": height, "size_bytes": len(raw),
    }
    return report


def require_capture_snapshot_consistency(
    artifact_ids, session_bytes, captures, reports, *, error_type,
) -> None:
    """Reject private-state drift before emitting an immutable snapshot."""

    if set(captures) != set(artifact_ids) \
            or set(reports) != set(artifact_ids):
        raise error_type("Runtime capture bytes and reports are inconsistent")
    for artifact_id in artifact_ids:
        raw, report = captures[artifact_id], reports[artifact_id]
        if type(raw) is not bytes or type(report) is not dict:
            raise error_type(
                "Runtime capture bytes and reports are inconsistent"
            )
        dimensions = png_dimensions(raw, error_type=error_type)
        expected = capture_report(
            json.loads(session_bytes[artifact_id]), raw, *dimensions,
            report.get("observables"),
        )
        if copy_json(report) != expected:
            raise error_type(
                "Runtime capture bytes and report SHA are inconsistent"
            )


__all__ = [
    "base_report", "capture_report", "png_dimensions",
    "require_capture_snapshot_consistency",
]
