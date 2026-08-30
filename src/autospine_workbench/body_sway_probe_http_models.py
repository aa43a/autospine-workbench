"""Bounded, path-free response projections for the P10.2 operator page."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .body_sway_probe_packages import classify_body_sway_probe_head


ENTRY_FORMAT = "autospine-body-sway-probe-entry"
FORMAT_VERSION = 2


def body_sway_probe_entry(
    evidence,
    head,
    *,
    report=None,
    preview: dict[str, Any] | None = None,
    canvas_adjustment=None,
) -> dict[str, Any]:
    """Project exact evidence without exposing filesystem paths."""

    candidates = evidence.candidates.document
    feature = next(
        row for row in candidates["features"]
        if row["feature_id"] == "body_sway"
    )
    probeability = classify_body_sway_probe_head(feature, head)
    decision = head.decision.document["decisions"][0] \
        if head.decision is not None else None
    report_document = report.document if report is not None else None
    if report_document is not None:
        status = report_document["status"]
        result = {
            "status": status,
            "release_gate": report_document["release_gate"],
            "schedule": report_document["schedule"],
            "checks": report_document["checks"],
            "summary": report_document["summary"],
        }
    else:
        status, result = probeability, None
    canvas = evidence.mesh_bundle.rig["canvas"]
    if preview is not None:
        preview = {
            **preview,
            "canvas": {
                "width": canvas["width"], "height": canvas["height"],
            },
            "composite_url": (
                f"/api/projects/{quote(evidence.address.project_id, safe='')}"
                "/composite"
            ),
        }
    adjustment_projection = None
    if canvas_adjustment is not None:
        adjustment_projection = {
            "candidate_sha256": canvas_adjustment.sha256,
            "document": canvas_adjustment.document,
        }
    return {
        "format": ENTRY_FORMAT,
        "format_version": FORMAT_VERSION,
        "status": status,
        "probeability": probeability,
        "package": {
            "package_id": evidence.address.package_id,
            **evidence.address.public_document(),
        },
        "candidate_sha256": evidence.candidates.sha256,
        "history": {
            "current_revision": head.current_revision,
            "head_decision_sha256": head.decision_sha256,
            "action": decision["action"] if decision is not None else None,
            "probe_status": (
                decision["probe_status"] if decision is not None else None
            ),
        },
        "report_sha256": report.sha256 if report is not None else None,
        "result": result,
        "preview": preview,
        "canvas_adjustment": adjustment_projection,
        "technical": {
            "report": report_document,
            "semantics": {
                "diagnostic_only": True,
                "release_authority": False,
                "runtime_equivalence_claimed": False,
                "visual_quality_claimed": False,
                "continuous_time_safety_claimed": False,
            },
        },
    }
