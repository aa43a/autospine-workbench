"""Small pure candidate/P3 fixtures for P10.5b decision tests."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.seam_anchor_candidates import (
    compile_seam_anchor_candidates,
)
from tests.seam_anchor_candidate_helpers import seam_inputs


def review_candidate_and_rig(*, mesh_id: str | None = None):
    inputs = seam_inputs(mesh_id=mesh_id)
    with patch(
        "autospine_workbench.seam_anchor_candidates."
        "require_seam_anchor_inputs",
        return_value=inputs,
    ):
        candidate = compile_seam_anchor_candidates({}, object()).document
    rig = inputs.rig
    candidate["source"]["rig_sha256"] = canonical_sha256(rig)
    return candidate, rig


def seam_review_rows(candidate, action="accept"):
    rows = []
    for relationship in candidate["relationships"]:
        effective = action if relationship["status"] == "review_required" \
            else "unobservable"
        option = next((
            row for row in relationship["options"]
            if row["status"] == "candidate"
        ), None)
        row = {
            "relationship_id": relationship["relationship_id"],
            "relationship_evidence_sha256": relationship["evidence_sha256"],
            "action": effective,
            "option_id": None if option is None else option["option_id"],
            "option_evidence_sha256": (
                None if option is None else option["evidence_sha256"]
            ),
            "notes": "reviewed seam",
        }
        if effective == "adjust":
            row["final_anchors"] = deepcopy(option["anchors"])
        rows.append(row)
    return rows


def seam_review_payload(candidate, *, action="accept"):
    from autospine_workbench.seam_anchor_candidate_validation import (
        seam_anchor_candidates_sha256,
    )

    return {
        "base_revision": 0,
        "candidate_sha256": seam_anchor_candidates_sha256(candidate),
        "previous_decision_sha256": None,
        "review": {"reviewer_id": "artist-01", "notes": "all six"},
        "decisions": seam_review_rows(candidate, action),
    }
