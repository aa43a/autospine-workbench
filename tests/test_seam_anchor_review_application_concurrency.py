"""Application-level linearization tests for P10.5b seam review."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import tempfile
from threading import Barrier
import unittest

from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_application import (
    SeamAnchorReviewApplication,
)
from autospine_workbench.seam_anchor_review_errors import (
    SeamAnchorReviewRevisionConflict,
)
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.seam_anchor_review_helpers import seam_review_rows


class SeamAnchorReviewApplicationConcurrencyTests(unittest.TestCase):
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
        self.prepared = self.service.prepare(self.address)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def payload(self, notes: str) -> dict:
        return {
            "base_revision": 0,
            "candidate_sha256": self.prepared.candidate_sha256,
            "previous_decision_sha256": None,
            "review": {"reviewer_id": "artist-01", "notes": notes},
            "decisions": seam_review_rows(
                self.prepared.candidate_document, "accept"
            ),
        }

    def test_identical_concurrent_submissions_converge(self):
        payload = self.payload("same review")
        barrier = Barrier(2)

        def attempt(_index):
            barrier.wait()
            return self.service.submit(self.address, deepcopy(payload))

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual([False, True], sorted(row.reused for row in results))
        self.assertEqual(1, len({row.decision_sha256 for row in results}))
        self.assertEqual({1}, {row.revision for row in results})

    def test_different_concurrent_submissions_have_one_typed_loser(self):
        payloads = (self.payload("left review"), self.payload("right review"))
        barrier = Barrier(2)

        def attempt(payload):
            barrier.wait()
            try:
                return self.service.submit(self.address, deepcopy(payload))
            except SeamAnchorReviewRevisionConflict as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, payloads))
        winners = [row for row in results if not isinstance(row, Exception)]
        losers = [row for row in results if isinstance(row, Exception)]
        self.assertEqual(1, len(winners), results)
        self.assertEqual(1, len(losers), results)
        self.assertIsInstance(losers[0], SeamAnchorReviewRevisionConflict)
        self.assertEqual((1, 1), (
            losers[0].requested_revision, losers[0].current_revision,
        ))
        self.assertEqual(winners[0].decision_sha256, losers[0].current_head)
        current = self.service.prepare(self.address)
        self.assertEqual(
            winners[0].decision_sha256, current.history.head_decision_sha256
        )


if __name__ == "__main__":
    unittest.main()
