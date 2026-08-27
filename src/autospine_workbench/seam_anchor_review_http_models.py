"""Path-free HTTP projections for P10.5b seam-anchor review."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote


def candidate_response(prepared, attachment_refs) -> dict[str, Any]:
    return {
        "candidate_sha256": prepared.candidate_sha256,
        "candidate": prepared.candidate_document,
        "attachment_images": [
            {
                "option_id": row.option_id,
                "attachment_role": row.attachment_role,
                "attachment_id": row.attachment_id,
                "attachment_type": row.attachment_type,
                "image_sha256": row.image_sha256,
                "width": row.width,
                "height": row.height,
                "url": _attachment_url(prepared, row),
            }
            for row in attachment_refs
        ],
    }


def history_response(prepared) -> dict[str, Any]:
    history = prepared.history
    return {
        "candidate_sha256": prepared.candidate_sha256,
        "current_revision": history.current_revision,
        "head_decision_sha256": history.head_decision_sha256,
        "items": [
            {
                "revision": row.revision,
                "decision_sha256": row.decision_sha256,
                "status": row.status,
            }
            for row in history.rows
        ],
    }


def exact_decision_response(exact) -> dict[str, Any]:
    return {
        "candidate_sha256": exact.candidate_sha256,
        "decision_sha256": exact.decision_sha256,
        "revision": exact.revision,
        "decision": exact.decision_document,
    }


def submitted_response(result) -> dict[str, Any]:
    return {
        "candidate_sha256": result.candidate_sha256,
        "decision_sha256": result.decision_sha256,
        "revision": result.revision,
        "status": result.status,
        "release_gate": {
            "status": result.release_gate_status,
            "reason_codes": list(result.release_gate_reason_codes),
        },
        "summary": {
            "relationship_count": result.relationship_count,
            "accept_count": result.accept_count,
            "adjust_count": result.adjust_count,
            "reject_count": result.reject_count,
            "unobservable_count": result.unobservable_count,
            "anchor_pair_count": result.anchor_pair_count,
        },
        "reused": result.reused,
    }


def _attachment_url(prepared, row) -> str:
    address = prepared.address
    parts = (
        "api", "projects", address.project_id, "seam-anchor-reviews",
        address.layer_manifest_sha256, address.p3_rig_sha256,
        address.p3_bundle_sha256, "candidates", prepared.candidate_sha256,
        "options", row.option_id, "attachments", row.attachment_id,
        "images", row.image_sha256,
    )
    return "/" + "/".join(quote(value, safe="") for value in parts)
