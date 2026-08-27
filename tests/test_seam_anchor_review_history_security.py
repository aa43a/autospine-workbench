"""Fail-closed history and namespace tests for P10.5b seam review."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_application import (
    SeamAnchorReviewApplication,
    SeamAnchorReviewApplicationError,
)
from autospine_workbench.seam_anchor_review_profile import (
    CANDIDATE_NAMESPACE,
    DECISION_NAMESPACE,
)
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.seam_anchor_review_helpers import seam_review_rows


class SeamAnchorReviewHistorySecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = P10PersistedFixture(Path(self.temporary.name))
        self.address = ExactSeamAnchorReviewAddress(
            self.fixture.mesh.project_id,
            self.fixture.layer_manifest_sha256,
            self.fixture.mesh.rig_sha256,
            self.fixture.mesh.bundle_sha256,
        )
        self.service = SeamAnchorReviewApplication(self.fixture.state)
        prepared = self.service.prepare(self.address)
        self.candidate_sha256 = prepared.candidate_sha256
        payload = {
            "base_revision": 0,
            "candidate_sha256": prepared.candidate_sha256,
            "previous_decision_sha256": None,
            "review": {"reviewer_id": "artist-01", "notes": "reviewed"},
            "decisions": seam_review_rows(
                prepared.candidate_document, "accept"
            ),
        }
        self.submitted = self.service.submit(self.address, payload)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def candidate_path(self) -> Path:
        return (
            self.fixture.state / "builds" / self.address.project_id
            / CANDIDATE_NAMESPACE / self.address.p3_bundle_sha256
            / f"{self.candidate_sha256}.json"
        )

    @property
    def decision_parent(self) -> Path:
        return (
            self.fixture.state / "builds" / self.address.project_id
            / DECISION_NAMESPACE / self.candidate_sha256
        )

    @property
    def decision_path(self) -> Path:
        return self.decision_parent / f"{self.submitted.decision_sha256}.json"

    @property
    def revision_slot(self) -> Path:
        return self.decision_parent / "revisions" / "r000001.json"

    def test_namespaces_are_exact_and_have_no_latest_alias(self):
        self.assertTrue(self.candidate_path.is_file())
        self.assertTrue(self.decision_path.is_file())
        self.assertTrue(self.revision_slot.is_file())
        self.assertFalse((self.candidate_path.parent / "latest.json").exists())
        self.assertFalse((self.decision_parent / "latest.json").exists())

    def test_content_address_tamper_fails_closed(self):
        self.decision_path.write_bytes(self.decision_path.read_bytes() + b" ")
        with self.assertRaises(SeamAnchorReviewApplicationError):
            self.service.prepare(self.address)

    def test_candidate_tamper_fails_closed(self):
        self.candidate_path.write_bytes(self.candidate_path.read_bytes() + b" ")
        with self.assertRaises(SeamAnchorReviewApplicationError):
            self.service.prepare(self.address)

    def test_missing_content_address_fails_closed(self):
        self.decision_path.unlink()
        with self.assertRaises(SeamAnchorReviewApplicationError):
            self.service.prepare(self.address)

    def test_revision_slot_tamper_and_extra_inventory_fail_closed(self):
        original = self.revision_slot.read_bytes()
        self.revision_slot.write_bytes(original + b" ")
        with self.assertRaises(SeamAnchorReviewApplicationError):
            self.service.prepare(self.address)
        self.revision_slot.write_bytes(original)
        foreign = self.revision_slot.parent / "foreign.json"
        foreign.write_bytes(b"{}")
        with self.assertRaises(SeamAnchorReviewApplicationError):
            self.service.prepare(self.address)

    def test_revision_slot_alias_fails_closed_when_supported(self):
        target = self.decision_path
        self.revision_slot.unlink()
        try:
            self.revision_slot.symlink_to(target)
        except OSError:
            self.skipTest("Symlink creation is unavailable on this host")
        with self.assertRaises(SeamAnchorReviewApplicationError):
            self.service.prepare(self.address)


if __name__ == "__main__":
    unittest.main()
