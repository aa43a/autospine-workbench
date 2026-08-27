"""Exact replay and tamper tests for reviewed seam-anchor set bundles."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.reviewed_seam_anchor_set_bundle_contract import (
    DOCUMENT_NAMES,
    reviewed_seam_anchor_set_bundle_address_sha256,
)
from autospine_workbench.immutable_bundle_fs import ImmutableBundleSnapshot
from autospine_workbench.reviewed_seam_anchor_set_bundle_fs import (
    reviewed_seam_anchor_set_bundle_fs,
)
from autospine_workbench.reviewed_seam_anchor_set_bundle_reader import (
    VerifiedReviewedSeamAnchorSetBundleReader,
    VerifiedReviewedSeamAnchorSetBundleReaderError,
)
from autospine_workbench.reviewed_seam_anchor_set_bundle_store import (
    ReviewedSeamAnchorSetBundleStore,
)
from autospine_workbench.reviewed_seam_anchor_set_bundle_integrity import (
    ReviewedSeamAnchorSetBundleIntegrityError,
    verify_reviewed_seam_anchor_set_bundle_snapshot,
)
from tests.reviewed_seam_anchor_set_bundle_helpers import (
    PersistedReviewedSeamAnchorSetFixture,
    bound_value,
    exact_bundle_values,
)


_READER_MODULE = (
    "autospine_workbench.reviewed_seam_anchor_set_bundle_reader"
)


class ReviewedSeamAnchorSetBundleReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name) / "state"
        self.candidates, self.decision, self.rig, self.reviewed_set = (
            exact_bundle_values()
        )
        self.published = ReviewedSeamAnchorSetBundleStore(
            self.state
        ).publish(
            self.candidates, self.decision, self.rig, self.reviewed_set
        )
        self.reader = VerifiedReviewedSeamAnchorSetBundleReader(self.state)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def load(self):
        return self.reader.load(
            self.published.project_id,
            self.published.set_sha256,
            self.published.bundle_sha256,
        )

    def test_exact_reader_replays_candidate_history_and_set(self):
        bound = bound_value(self.candidates, self.rig)
        with patch(
            f"{_READER_MODULE}.load_bound_seam_anchor_review_candidate",
            return_value=bound,
        ) as candidate_loader, patch(
            f"{_READER_MODULE}.load_seam_anchor_review_decision",
            return_value=self.decision,
        ) as decision_loader:
            verified = self.load()
        candidate_loader.assert_called_once()
        loaded_address = candidate_loader.call_args.args[1]
        self.assertEqual(
            self.candidates.document["source"]["bundle_sha256"],
            loaded_address.p3_bundle_sha256,
        )
        self.assertEqual(
            self.published.decision_sha256,
            decision_loader.call_args.args[3],
        )
        self.assertEqual(DOCUMENT_NAMES, verified.inventory)
        self.assertEqual(self.published.review_revision,
                         verified.review_revision)
        isolated = verified.reviewed_set
        isolated.clear()
        self.assertEqual(self.reviewed_set.document, verified.reviewed_set)

    def test_wrong_set_or_bundle_sha_is_rejected_without_scanning(self):
        for set_sha, bundle_sha in (
            ("f" * 64, self.published.bundle_sha256),
            (self.published.set_sha256, "f" * 64),
        ):
            with self.subTest(set_sha=set_sha, bundle_sha=bundle_sha), \
                    self.assertRaises(
                        VerifiedReviewedSeamAnchorSetBundleReaderError
                    ):
                self.reader.load(
                    self.published.project_id, set_sha, bundle_sha
                )

    def test_tampered_bytes_are_rejected_before_upstream_replay(self):
        for name in DOCUMENT_NAMES:
            target = self.published.path / name
            original = target.read_bytes()
            with self.subTest(name=name), patch(
                f"{_READER_MODULE}.load_bound_seam_anchor_review_candidate"
            ) as loader, self.assertRaises(
                VerifiedReviewedSeamAnchorSetBundleReaderError
            ):
                target.write_bytes(b"{}")
                try:
                    self.load()
                finally:
                    target.write_bytes(original)
            loader.assert_not_called()

    def test_extra_inventory_is_rejected_before_upstream_replay(self):
        (self.published.path / "latest.json").write_text(
            "{}", encoding="utf-8"
        )
        with patch(
            f"{_READER_MODULE}.load_bound_seam_anchor_review_candidate"
        ) as loader, self.assertRaises(
            VerifiedReviewedSeamAnchorSetBundleReaderError
        ):
            self.load()
        loader.assert_not_called()

    def test_noncanonical_addressed_json_is_rejected_before_replay(self):
        files = {
            name: (self.published.path / name).read_bytes()
            for name in DOCUMENT_NAMES
        }
        files[DOCUMENT_NAMES[0]] = json.dumps(
            self.candidates.document, indent=1
        ).encode("utf-8")
        bundle_sha = reviewed_seam_anchor_set_bundle_address_sha256(files)
        reviewed_seam_anchor_set_bundle_fs(
            self.state, self.published.project_id
        ).publish(self.published.set_sha256, bundle_sha, files)
        with patch(
            f"{_READER_MODULE}.load_bound_seam_anchor_review_candidate"
        ) as loader, self.assertRaises(
            VerifiedReviewedSeamAnchorSetBundleReaderError
        ):
            self.reader.load(
                self.published.project_id,
                self.published.set_sha256,
                bundle_sha,
            )
        loader.assert_not_called()

    def test_wrong_project_suffix_is_rejected_without_upstream_replay(self):
        with patch(
            f"{_READER_MODULE}.load_bound_seam_anchor_review_candidate"
        ) as loader, self.assertRaises(
            VerifiedReviewedSeamAnchorSetBundleReaderError
        ):
            self.reader.load(
                "other-project",
                self.published.set_sha256,
                self.published.bundle_sha256,
            )
        loader.assert_not_called()

    def test_non_path_snapshot_is_normalized_by_integrity_boundary(self):
        snapshot = reviewed_seam_anchor_set_bundle_fs(
            self.state, self.published.project_id
        ).read(self.published.set_sha256, self.published.bundle_sha256)
        malformed = ImmutableBundleSnapshot(
            "not-a-path",  # type: ignore[arg-type]
            snapshot.primary_sha256,
            snapshot.bundle_sha256,
            snapshot.ordered_names,
            snapshot.payloads,
        )
        with self.assertRaises(ReviewedSeamAnchorSetBundleIntegrityError):
            verify_reviewed_seam_anchor_set_bundle_snapshot(
                malformed,
                expected_project_id=self.published.project_id,
                expected_set_sha256=self.published.set_sha256,
                expected_bundle_sha256=self.published.bundle_sha256,
                candidates=self.candidates.document,
                decision=self.decision.document,
                rig=self.rig,
            )

    def test_wrong_project_path_suffix_fails_integrity(self):
        snapshot = reviewed_seam_anchor_set_bundle_fs(
            self.state, self.published.project_id
        ).read(self.published.set_sha256, self.published.bundle_sha256)
        wrong_path = snapshot.path.parent.parent.parent.parent \
            / "other-project" / snapshot.path.parent.parent.name \
            / snapshot.primary_sha256 / snapshot.bundle_sha256
        malformed = ImmutableBundleSnapshot(
            wrong_path,
            snapshot.primary_sha256,
            snapshot.bundle_sha256,
            snapshot.ordered_names,
            snapshot.payloads,
        )
        with self.assertRaises(ReviewedSeamAnchorSetBundleIntegrityError):
            verify_reviewed_seam_anchor_set_bundle_snapshot(
                malformed,
                expected_project_id=self.published.project_id,
                expected_set_sha256=self.published.set_sha256,
                expected_bundle_sha256=self.published.bundle_sha256,
                candidates=self.candidates.document,
                decision=self.decision.document,
                rig=self.rig,
            )


class ReviewedSeamAnchorSetHistoricalReaderTests(unittest.TestCase):
    def test_revision_one_bundle_remains_readable_after_revision_two(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PersistedReviewedSeamAnchorSetFixture(Path(temporary))
            self.assertEqual(1, fixture.published.review_revision)
            self.assertEqual(2, fixture.current_revision)
            self.assertNotEqual(
                fixture.published.decision_sha256,
                fixture.current_head_sha256,
            )
            verified = VerifiedReviewedSeamAnchorSetBundleReader(
                fixture.state
            ).load(
                fixture.published.project_id,
                fixture.published.set_sha256,
                fixture.published.bundle_sha256,
            )
        self.assertEqual(1, verified.review_revision)
        self.assertEqual(
            fixture.published.decision_sha256, verified.decision_sha256
        )
        self.assertEqual(1, verified.decision["review"]["revision"])


if __name__ == "__main__":
    unittest.main()
