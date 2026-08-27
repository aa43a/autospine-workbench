"""Exact-source binding tests for P10.5b candidates."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_candidate_binding import (
    SeamAnchorReviewCandidateBindingError,
    load_bound_seam_anchor_review_candidate,
)
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.p9_v2_helpers import tree


class SeamAnchorReviewCandidateBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = P10PersistedFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def address(self, **changes):
        fixture = self.fixture
        values = {
            "project_id": fixture.mesh.project_id,
            "layer_manifest_sha256": fixture.layer_manifest_sha256,
            "p3_rig_sha256": fixture.mesh.rig_sha256,
            "p3_bundle_sha256": fixture.mesh.bundle_sha256,
            **changes,
        }
        return ExactSeamAnchorReviewAddress(**values)

    def test_replay_is_deterministic_and_zero_write(self):
        before = tree(self.fixture.state)
        first = load_bound_seam_anchor_review_candidate(
            self.fixture.state, self.address()
        )
        second = load_bound_seam_anchor_review_candidate(
            self.fixture.state, self.address()
        )
        self.assertEqual(before, tree(self.fixture.state))
        self.assertEqual(first.candidates.sha256, second.candidates.sha256)
        self.assertEqual(self.fixture.mesh.rig_sha256,
                         first.mesh_bundle.rig_sha256)

    def test_crosswired_exact_address_fails_without_writes(self):
        before = tree(self.fixture.state)
        with self.assertRaises(SeamAnchorReviewCandidateBindingError):
            load_bound_seam_anchor_review_candidate(
                self.fixture.state,
                self.address(p3_bundle_sha256="f" * 64),
            )
        self.assertEqual(before, tree(self.fixture.state))


if __name__ == "__main__":
    unittest.main()
