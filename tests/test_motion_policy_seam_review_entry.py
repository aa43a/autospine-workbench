"""Exact service tests for read-only P9-to-seam review handoff."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from autospine_workbench.motion_policy_seam_review_entry import (
    BLOCKED_UNOBSERVABLE,
    MANUAL_REVIEW_REQUIRED,
    MotionPolicySeamReviewEntryError,
    MotionPolicySeamReviewEntryNotFoundError,
    build_motion_policy_seam_review_entry,
)
from tests.motion_policy_preflight_helpers import tree_snapshot
from tests.motion_policy_seam_review_entry_helpers import (
    MotionPolicySeamReviewEntryFixture,
)


BLOCKED_RELATIONSHIPS = (
    "seam.pelvis_leg.left",
    "seam.pelvis_leg.right",
    "seam.leg_foot.left",
    "seam.leg_foot.right",
)


class MotionPolicySeamReviewEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = MotionPolicySeamReviewEntryFixture(
            Path(cls.temporary.name)
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _entry(self, motion_id: str):
        return build_motion_policy_seam_review_entry(
            self.fixture.state, self.fixture.package_ids[motion_id],
        )

    def test_a_is_deterministic_manual_review_entry_and_zero_write(self):
        before = tree_snapshot(self.fixture.state)
        first = self._entry("motion-a")
        second = self._entry("motion-a")
        self.assertEqual(first, second)
        self.assertEqual(MANUAL_REVIEW_REQUIRED, first["status"])
        self.assertEqual({
            "relationship_count": 6,
            "review_required_count": 6,
            "unobservable_count": 0,
        }, first["summary"])
        self.assertEqual([], first["blocking_relationships"])
        self.assertEqual(self.fixture.mesh_a.layer_manifest_sha256,
                         first["address"]["layer_manifest_sha256"])
        self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_b_has_exact_four_blockers_and_cannot_claim_ready(self):
        before = tree_snapshot(self.fixture.state)
        entry = self._entry("motion-b")
        self.assertEqual(BLOCKED_UNOBSERVABLE, entry["status"])
        self.assertEqual(4, entry["summary"]["unobservable_count"])
        self.assertEqual(2, entry["summary"]["review_required_count"])
        self.assertEqual(BLOCKED_RELATIONSHIPS, tuple(
            row["relationship_id"]
            for row in entry["blocking_relationships"]
        ))
        self.assertTrue(all(
            row["reason_codes"] for row in entry["blocking_relationships"]
        ))
        encoded = json.dumps(entry, ensure_ascii=False)
        self.assertNotIn("ready_for_compile", encoded)
        self.assertNotIn("approved", encoded)
        self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_response_is_path_free_and_unknown_package_fails_closed(self):
        entry = self._entry("motion-a")
        encoded = json.dumps(entry, ensure_ascii=False)
        self.assertNotIn(str(self.fixture.root), encoded)
        self.assertNotIn('"path"', encoded)
        with self.assertRaises(MotionPolicySeamReviewEntryNotFoundError):
            build_motion_policy_seam_review_entry(
                self.fixture.state, "f" * 64,
            )

    def test_package_to_verified_p3_crosswire_is_zero_write(self):
        before = tree_snapshot(self.fixture.state)
        with self.assertRaises(MotionPolicySeamReviewEntryError):
            self._entry("motion-crosswired")
        self.assertEqual(before, tree_snapshot(self.fixture.state))


if __name__ == "__main__":
    unittest.main()
