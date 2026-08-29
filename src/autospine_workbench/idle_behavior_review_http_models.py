"""Path-free response projections for assisted P10.1 review."""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import quote

from .idle_behavior_review_profile import (
    ENTRY_FORMAT,
    FORMAT_VERSION,
    PACKAGE_FORMAT,
    SUGGESTED_AMPLITUDES,
    SUGGESTED_PHASES,
    TARGET_BONE_IDS,
)
from .idle_behavior_review_replay import IdleBehaviorReviewEvidence
from .rig_fk import evaluate_world_setup


def idle_behavior_review_entry(
    evidence: IdleBehaviorReviewEvidence, history,
) -> dict[str, Any]:
    candidate = evidence.candidates.document
    feature = body_sway_feature(candidate)
    status = (
        "reviewed" if history.current_revision
        else "review_required" if feature["availability"] == "candidate"
        else "candidate_unobservable"
    )
    observable = feature["availability"] == "candidate"
    return {
        "format": ENTRY_FORMAT,
        "format_version": FORMAT_VERSION,
        "status": status,
        "package": _package(evidence),
        "candidate_sha256": evidence.candidates.sha256,
        "candidate": candidate,
        "suggestion": _suggestion(candidate) if observable else None,
        "preview": _preview(evidence) if observable else None,
        "history": _history(history),
    }


def body_sway_feature(candidate: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row for row in candidate["features"]
        if row["feature_id"] == "body_sway"
    ]
    if len(rows) != 1:
        raise ValueError("Idle behavior body-sway inventory is invalid")
    return rows[0]


def _package(evidence: IdleBehaviorReviewEvidence) -> dict[str, Any]:
    address, candidate = evidence.address, evidence.candidates.document
    canvas = evidence.mesh_bundle.rig["canvas"]
    composite = f"/api/projects/{quote(address.project_id, safe='')}/composite"
    return {
        "format": PACKAGE_FORMAT,
        "format_version": FORMAT_VERSION,
        "package_id": address.package_id,
        **address.public_document(),
        "status": "ready_for_candidate_replay",
        "source": candidate["source"],
        "project": {
            "project_id": address.project_id,
            "canvas": {
                "width": canvas["width"], "height": canvas["height"],
            },
            "composite_url": composite,
        },
    }


def _suggestion(candidate: dict[str, Any]) -> dict[str, Any]:
    duration = candidate["timing"]["duration_ticks"]
    cycles = max(1, min(4, int(duration / 2_000_000 + 0.5)))
    return {
        "profile": {"id": "body-sway-subtle-draft", "version": "1.0.0"},
        "authority": "none",
        "status": "unvalidated_draft",
        "action": "adjust",
        "reason_code": "human-approved-assisted-draft-v1",
        "payload": {
            "cycles": cycles,
            "per_bone_amplitude_deg": _values(SUGGESTED_AMPLITUDES),
            "per_bone_phase_fraction": _values(SUGGESTED_PHASES),
        },
        "claims": {
            "human_approved": False,
            "structural_safety": False,
            "visual_quality": False,
            "runtime_equivalence": False,
            "safe_range": False,
            "release_authority": False,
        },
    }


def _preview(evidence: IdleBehaviorReviewEvidence) -> dict[str, Any]:
    candidate, rig = evidence.candidates.document, evidence.mesh_bundle.rig
    world = evaluate_world_setup(rig["bones"])
    by_id = {row["id"]: row for row in rig["bones"]}
    bones = []
    for bone_id in TARGET_BONE_IDS:
        frame = world[bone_id]
        start, end = frame["origin_xy"], frame["endpoint_xy"]
        bones.append({
            "bone_id": bone_id,
            "parent_bone_id": by_id[bone_id]["parent"],
            "length_px": math.hypot(
                end[0] - start[0], end[1] - start[1],
            ),
            "setup_world_rotation_deg": frame["rotation_deg"],
            "setup_start_px": {"x": start[0], "y": start[1]},
            "setup_end_px": {"x": end[0], "y": end[1]},
        })
    project = quote(evidence.address.project_id, safe="")
    timing, canvas = candidate["timing"], rig["canvas"]
    return {
        "kind": "setup-local-bone-schematic",
        "evidence_authority": "none",
        "coordinate_space": {
            "origin": "top_left", "x_axis": "right",
            "y_axis": "down", "units": "pixel",
        },
        "canvas": {
            "width": canvas["width"], "height": canvas["height"],
        },
        "composite_url": f"/api/projects/{project}/composite",
        "ticks_per_second": timing["ticks_per_second"],
        "duration_ticks": timing["duration_ticks"],
        "anchor_px": bones[0]["setup_start_px"],
        "bones": bones,
    }


def _history(snapshot) -> dict[str, Any]:
    return {
        "current_revision": snapshot.current_revision,
        "head_decision_sha256": snapshot.head_decision_sha256,
        "revision_count": len(snapshot.rows),
        "items": [
            {
                "revision": row.revision,
                "decision_sha256": row.decision_sha256,
                "action": row.action,
                "probe_status": row.probe_status,
                "parameters": row.parameters,
            }
            for row in snapshot.rows
        ],
    }


def _values(values) -> list[dict[str, Any]]:
    return [
        {"bone_id": bone_id, "value": value}
        for bone_id, value in zip(TARGET_BONE_IDS, values, strict=True)
    ]
