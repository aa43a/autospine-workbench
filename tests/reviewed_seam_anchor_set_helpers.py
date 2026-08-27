"""Pure fixtures for P10.5c reviewed seam-anchor set tests."""

from __future__ import annotations

from autospine_workbench.seam_anchor_review_decision import (
    build_seam_anchor_review_decision,
)
from tests.seam_anchor_review_helpers import (
    review_candidate_and_rig,
    seam_review_rows,
)


def reviewed_set_inputs(
    *, action: str = "accept", previous=None, mesh_id: str | None = None,
):
    candidate, rig = review_candidate_and_rig(mesh_id=mesh_id)
    decision = build_seam_anchor_review_decision(
        candidate,
        rig,
        review={"reviewer_id": "artist-01", "notes": "six seams"},
        decisions=seam_review_rows(candidate, action),
        previous_decision=previous,
    ).document
    return candidate, decision, rig
