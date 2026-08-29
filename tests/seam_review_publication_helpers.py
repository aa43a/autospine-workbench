"""Exact package plus ready P10.5b head for P10.5c publication tests."""

from __future__ import annotations

from pathlib import Path

from autospine_workbench.motion_policy_seam_review_entry import (
    build_motion_policy_seam_review_entry,
)
from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_application import (
    SeamAnchorReviewApplication,
)
from autospine_workbench.seam_review_publication import (
    FORMAT_VERSION,
    INTENT_VALUE,
    REQUEST_FORMAT,
)
from tests.motion_policy_seam_review_entry_helpers import (
    MotionPolicySeamReviewEntryFixture,
)
from tests.seam_anchor_review_helpers import seam_review_payload


class SeamReviewPublicationFixture:
    def __init__(self, root: Path) -> None:
        self.exact = MotionPolicySeamReviewEntryFixture(root)
        self.state = self.exact.state
        self.package_a = self.exact.package_ids["motion-a"]
        self.package_b = self.exact.package_ids["motion-b"]
        entry = build_motion_policy_seam_review_entry(
            self.state, self.package_a,
        )
        self.address = ExactSeamAnchorReviewAddress(
            entry["project_id"],
            entry["address"]["layer_manifest_sha256"],
            entry["address"]["p3_rig_sha256"],
            entry["address"]["p3_bundle_sha256"],
        )
        service = SeamAnchorReviewApplication(self.state)
        prepared = service.prepare(self.address)
        submitted = service.submit(
            self.address,
            seam_review_payload(prepared.candidate_document),
        )
        self.candidate_sha256 = submitted.candidate_sha256
        self.decision_sha256 = submitted.decision_sha256
        self.revision = submitted.revision

    def request(self, *, package_id: str | None = None) -> dict:
        package = package_id or self.package_a
        return {
            "format": REQUEST_FORMAT,
            "format_version": FORMAT_VERSION,
            "intent": INTENT_VALUE,
            "package_id": package,
            "candidate_sha256": self.candidate_sha256,
            "review_revision": self.revision,
            "decision_sha256": self.decision_sha256,
        }

    def advance_ready_head(self, note: str = "later ready review"):
        service = SeamAnchorReviewApplication(self.state)
        prepared = service.prepare(self.address)
        payload = seam_review_payload(prepared.candidate_document)
        payload["base_revision"] = prepared.history.current_revision
        payload["previous_decision_sha256"] = \
            prepared.history.head_decision_sha256
        payload["review"]["notes"] = note
        return service.submit(self.address, payload)
