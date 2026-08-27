"""Exact read/CAS application tests for P10.5b seam review."""

from __future__ import annotations

from copy import deepcopy
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
from autospine_workbench.seam_anchor_review_errors import (
    SeamAnchorReviewRevisionConflict,
)
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.p9_v2_helpers import tree
from tests.seam_anchor_review_helpers import seam_review_rows


class SeamAnchorReviewApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = P10PersistedFixture(Path(self.temporary.name))
        fixture = self.fixture
        self.address = ExactSeamAnchorReviewAddress(
            fixture.mesh.project_id, fixture.layer_manifest_sha256,
            fixture.mesh.rig_sha256, fixture.mesh.bundle_sha256,
        )
        self.service = SeamAnchorReviewApplication(self.fixture.state)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def payload(self, prepared, *, note="reviewed"):
        return {
            "base_revision": prepared.history.current_revision,
            "candidate_sha256": prepared.candidate_sha256,
            "previous_decision_sha256":
                prepared.history.head_decision_sha256,
            "review": {"reviewer_id": "artist-01", "notes": note},
            "decisions": seam_review_rows(
                prepared.candidate_document, "accept"
            ),
        }

    def test_prepare_is_zero_write_and_returns_exact_empty_history(self):
        before = tree(self.fixture.state)
        first = self.service.prepare(self.address)
        second = self.service.prepare(self.address)
        self.assertEqual(before, tree(self.fixture.state))
        self.assertEqual(first.candidate_sha256, second.candidate_sha256)
        self.assertEqual((0, None, ()), (
            first.history.current_revision,
            first.history.head_decision_sha256,
            first.history.rows,
        ))
        self.assertEqual(6, first.candidate_document["summary"][
            "unobservable_count"
        ])

    def test_initial_submit_identical_retry_and_stale_conflict(self):
        prepared = self.service.prepare(self.address)
        payload = self.payload(prepared)
        first = self.service.submit(self.address, payload)
        repeated = self.service.submit(self.address, payload)
        self.assertEqual((1, False, True), (
            first.revision, first.reused, repeated.reused
        ))
        self.assertEqual(first.decision_sha256, repeated.decision_sha256)
        self.assertEqual("reviewed_anchor_set_blocked", first.status)

        stale = deepcopy(payload)
        stale["review"]["notes"] = "different stale decision"
        with self.assertRaises(SeamAnchorReviewRevisionConflict) as raised:
            self.service.submit(self.address, stale)
        self.assertEqual((1, 1), (
            raised.exception.requested_revision,
            raised.exception.current_revision,
        ))

    def test_second_revision_and_exact_historical_read(self):
        prepared = self.service.prepare(self.address)
        first = self.service.submit(self.address, self.payload(prepared))
        current = self.service.prepare(self.address)
        second = self.service.submit(
            self.address, self.payload(current, note="second review")
        )
        self.assertEqual(2, second.revision)
        loaded = self.service.exact_decision(
            self.address, candidate_sha256=current.candidate_sha256,
            revision=1, decision_sha256=first.decision_sha256,
        )
        self.assertEqual(1, loaded.revision)
        self.assertEqual(first.decision_sha256, loaded.decision_sha256)
        with self.assertRaises(SeamAnchorReviewApplicationError):
            self.service.exact_decision(
                self.address, candidate_sha256=current.candidate_sha256,
                revision=2, decision_sha256=first.decision_sha256,
            )

    def test_candidate_address_crosswire_is_rejected(self):
        prepared = self.service.prepare(self.address)
        payload = self.payload(prepared)
        payload["candidate_sha256"] = "f" * 64
        with self.assertRaises(SeamAnchorReviewApplicationError):
            self.service.submit(self.address, payload)


if __name__ == "__main__":
    unittest.main()
