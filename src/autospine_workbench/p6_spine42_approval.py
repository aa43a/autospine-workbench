"""Strict reader-facing validation for approved historical P6 exports."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)


FORMAT = "autospine-p6-spine42-golden"
FORMAT_VERSION = 1
MAX_CASES = 64
_ROOT_FIELDS = {"format", "format_version", "cases"}
_CASE_FIELDS = {"project_id", "mode", "clip_id", "request", "outputs", "gate"}
_REQUEST_FIELDS = {
    "p3_rig_sha256", "p3_bundle_sha256",
    "motion_instance_sha256", "motion_bundle_sha256",
}
_OUTPUT_FIELDS = {
    "skeleton_json_sha256", "atlas_sha256", "png_sha256",
    "run_identity_sha256", "run_document_sha256", "report_sha256",
    "bundle_sha256",
}
_GATE_FIELDS = {"status", "summary", "checks", "metrics"}
_CHECK_FIELDS = {
    "adapter-profile", "attachment-atlas-binding", "atlas-png-geometry",
    "source-image-binding", "motion-binding",
}
_METRIC_FIELDS = {
    "bones", "slots", "attachments", "animations", "events",
    "atlas_regions", "atlas_width", "atlas_height", "source_images",
}


class P6Spine42ApprovalError(ValueError):
    """Raised when historical P6 approval evidence is not exact."""


def require_p6_spine42_approval(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate every declared approved export case and return a copy."""

    try:
        if type(value) is not dict or set(value) != _ROOT_FIELDS \
                or value.get("format") != FORMAT \
                or type(value.get("format_version")) is not int \
                or value.get("format_version") != FORMAT_VERSION:
            raise P6Spine42ApprovalError(
                "P6 export approval root fields are invalid"
            )
        rows = value.get("cases")
        if type(rows) is not list or not 1 <= len(rows) <= MAX_CASES:
            raise P6Spine42ApprovalError(
                "P6 export approval case count is invalid"
            )
        cases = [_case(row) for row in rows]
        identities = [
            (row["project_id"], row["mode"], row["clip_id"])
            for row in cases
        ]
        if len(identities) != len(set(identities)):
            raise P6Spine42ApprovalError(
                "P6 export approval cases are duplicated"
            )
        return _copy({
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "cases": cases,
        })
    except P6Spine42ApprovalError:
        raise
    except (LayerManifestError, KeyError, TypeError, ValueError) as exc:
        raise P6Spine42ApprovalError(
            "P6 export approval validation failed"
        ) from exc


def approved_p6_setup_case(
    approval: Mapping[str, Any],
    project_id: str,
    skeleton_json_sha256: str,
    bundle_sha256: str,
) -> dict[str, Any]:
    """Select exactly one setup-only approval by project and full address."""

    value = require_p6_spine42_approval(approval)
    project = require_safe_token(project_id, "Project id")
    skeleton = require_sha256(skeleton_json_sha256, "P6 skeleton JSON")
    bundle = require_sha256(bundle_sha256, "P6 bundle")
    rows = [
        row for row in value["cases"]
        if row["project_id"] == project
        and row["mode"] == "setup-only"
        and row["clip_id"] is None
        and row["outputs"]["skeleton_json_sha256"] == skeleton
        and row["outputs"]["bundle_sha256"] == bundle
    ]
    if len(rows) != 1:
        raise P6Spine42ApprovalError(
            "Exact approved P6 setup address is missing or ambiguous"
        )
    return _copy(rows[0])


def _case(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _CASE_FIELDS:
        raise P6Spine42ApprovalError("P6 approval case fields are invalid")
    project = require_safe_token(value["project_id"], "Project id")
    mode, clip = value.get("mode"), value.get("clip_id")
    if mode not in {"setup-only", "motion"} \
            or (mode == "setup-only" and clip is not None) \
            or (mode == "motion" and clip not in {"idle", "wave.left"}):
        raise P6Spine42ApprovalError("P6 approval case mode is invalid")
    request = _object(value.get("request"), _REQUEST_FIELDS, "request")
    outputs = _object(value.get("outputs"), _OUTPUT_FIELDS, "outputs")
    for field in ("p3_rig_sha256", "p3_bundle_sha256"):
        require_sha256(request[field], f"P6 {field}")
    for field in _OUTPUT_FIELDS:
        require_sha256(outputs[field], f"P6 {field}")
    motion = (request["motion_instance_sha256"], request["motion_bundle_sha256"])
    if mode == "setup-only" and motion != (None, None):
        raise P6Spine42ApprovalError("P6 setup approval has motion inputs")
    if mode == "motion":
        for item in motion:
            require_sha256(item, "P6 motion input")
    gate = _gate(value.get("gate"), mode)
    return _copy({
        "project_id": project,
        "mode": mode,
        "clip_id": clip,
        "request": request,
        "outputs": outputs,
        "gate": gate,
    })


def _gate(value: Any, mode: str) -> dict[str, Any]:
    gate = _object(value, _GATE_FIELDS, "gate")
    checks = _object(gate.get("checks"), _CHECK_FIELDS, "checks")
    metrics = _object(gate.get("metrics"), _METRIC_FIELDS, "metrics")
    if gate.get("status") != "passed" or type(gate.get("summary")) is not str \
            or not gate["summary"]:
        raise P6Spine42ApprovalError("P6 approval gate is not passed")
    expected_motion = "not_applicable" if mode == "setup-only" else "passed"
    if checks["motion-binding"] != expected_motion \
            or any(checks[key] != "passed" for key in _CHECK_FIELDS
                   if key != "motion-binding"):
        raise P6Spine42ApprovalError("P6 approval checks are invalid")
    if any(type(metrics[key]) is not int or metrics[key] < 0
           for key in _METRIC_FIELDS):
        raise P6Spine42ApprovalError("P6 approval metrics are invalid")
    return _copy(gate)


def _object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise P6Spine42ApprovalError(
            f"P6 approval {label} fields are invalid"
        )
    return value


def _copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ))
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise P6Spine42ApprovalError(
            "P6 approval is not strict finite JSON"
        ) from exc


__all__ = [
    "FORMAT", "FORMAT_VERSION", "MAX_CASES", "P6Spine42ApprovalError",
    "approved_p6_setup_case", "require_p6_spine42_approval",
]
