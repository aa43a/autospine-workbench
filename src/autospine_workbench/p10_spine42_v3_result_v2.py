"""Exact historical, path-free result projection for P10.7a v2 jobs."""

from __future__ import annotations

from .p10_spine42_v3_commands_v2 import (
    P10Spine42V3CommandV2Error,
    verify_body_sway_spine42_v3_v2_command,
)
from .spine42_v3_export_evidence_v2 import AUTHORITY, RELEASE_GATE


class P10Spine42V3ResultV2Error(RuntimeError):
    pass


def read_p10_spine42_v3_result_v2(state_root, row):
    """Re-verify immutable five-file bytes before projecting a result."""

    sealed = row.events[-1]["result"]
    try:
        verified = verify_body_sway_spine42_v3_v2_command(
            state_root, row.request["project_id"],
            skeleton_json_sha256=sealed["skeleton_json_sha256"],
            bundle_sha256=sealed["bundle_sha256"],
        )
        payload = verified.document
    except P10Spine42V3CommandV2Error as exc:
        raise P10Spine42V3ResultV2Error(
            "P10.7a v2 historical exact readback failed"
        ) from exc
    if verified.mode != "verified" \
            or verified.project_id != row.request["project_id"] \
            or verified.clip_id != sealed["clip_id"] \
            or verified.skeleton_json_sha256 \
                != sealed["skeleton_json_sha256"] \
            or verified.bundle_sha256 != sealed["bundle_sha256"] \
            or verified.run_document_sha256 \
                != sealed["run_document_sha256"] \
            or verified.report_sha256 != sealed["report_sha256"] \
            or list(verified.inventory) != sealed["inventory"] \
            or payload.get("inventory") != sealed["inventory"] \
            or payload.get("verification") != {
                "status": "passed", "exact_readback": True,
            } or payload.get("authority") != dict(AUTHORITY) \
            or payload.get("release_gate") != {
                "status": RELEASE_GATE["status"],
                "reason_codes": list(RELEASE_GATE["reason_codes"]),
            } or _contains_path(payload):
        raise P10Spine42V3ResultV2Error(
            "P10.7a v2 historical result differs from its journal"
        )
    return {
        "ok": True, "status": "completed",
        **{key: row.request[key] for key in (
            "job_id", "safety_run_id", "dynamic_run_id", "motion_run_id",
            "project_id",
        )},
        "clip_id": sealed["clip_id"], "run": row.public_document(),
        "address": {key: sealed[key] for key in (
            "skeleton_json_sha256", "bundle_sha256",
        )},
        "inventory": list(sealed["inventory"]), "reused": sealed["reused"],
        "authority": dict(AUTHORITY),
        "release_gate": {
            "status": RELEASE_GATE["status"],
            "reason_codes": list(RELEASE_GATE["reason_codes"]),
        },
        "verification": {"status": "passed", "exact_readback": True},
        "permanent_current_authority_claimed": False,
        "release_authority_granted": False,
    }


def _contains_path(value):
    if isinstance(value, dict):
        return any(key == "path" or key.endswith("_path")
                   or _contains_path(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_path(item) for item in value)
    return False


__all__ = [
    "P10Spine42V3ResultV2Error", "read_p10_spine42_v3_result_v2",
]
