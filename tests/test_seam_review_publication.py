"""Package-bound P10.5c publication service tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from autospine_workbench.motion_policy_seam_review_entry import (
    build_motion_policy_seam_review_entry,
)
from autospine_workbench.reviewed_seam_anchor_set_bundle_contract import (
    DOCUMENT_NAMES,
)
from autospine_workbench.reviewed_seam_anchor_set_bundle_fs import (
    reviewed_seam_anchor_set_bundle_fs,
)
from autospine_workbench.seam_review_publication import (
    SeamReviewPublicationError,
    SeamReviewPublicationUnavailableError,
    publish_seam_review_package,
)
from tests.motion_policy_preflight_helpers import tree_snapshot
from tests.seam_review_publication_helpers import (
    SeamReviewPublicationFixture,
)


class SeamReviewPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = SeamReviewPublicationFixture(
            Path(cls.temporary.name) / "exact"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_ready_head_publishes_and_exact_retry_is_stable(self):
        request = self.fixture.request()
        first = publish_seam_review_package(
            self.fixture.state, self.fixture.package_a, request,
        )
        second = publish_seam_review_package(
            self.fixture.state, self.fixture.package_a, deepcopy(request),
        )
        self.assertEqual(first, second)
        self.assertEqual("passed", first["status"])
        self.assertEqual("passed", first["verification"]["status"])
        self.assertTrue(first["verification"][
            "replayed_from_exact_upstreams"
        ])
        self.assertEqual(6, first["summary"]["relationship_count"])
        self.assertEqual(self.fixture.candidate_sha256, first[
            "source"
        ]["candidate_sha256"])
        encoded = str(first)
        self.assertNotIn(str(Path(self.temporary.name)), encoded)
        self.assertNotIn("path", encoded.lower())

    def test_successful_publication_replays_after_head_advances(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SeamReviewPublicationFixture(Path(temporary) / "exact")
            request = fixture.request()
            first = publish_seam_review_package(
                fixture.state, fixture.package_a, request,
            )
            advanced = fixture.advance_ready_head()
            self.assertEqual(2, advanced.revision)
            before_retry = tree_snapshot(fixture.state)
            repeated = publish_seam_review_package(
                fixture.state, fixture.package_a, deepcopy(request),
            )
            self.assertEqual(first, repeated)
            self.assertEqual(before_retry, tree_snapshot(fixture.state))

    def test_unpublished_old_decision_remains_rejected_after_head_advances(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SeamReviewPublicationFixture(Path(temporary) / "exact")
            request = fixture.request()
            advanced = fixture.advance_ready_head()
            self.assertEqual(2, advanced.revision)
            baseline = tree_snapshot(fixture.state)
            with self.assertRaises(SeamReviewPublicationUnavailableError):
                publish_seam_review_package(
                    fixture.state, fixture.package_a, request,
                )
            self.assertEqual(baseline, tree_snapshot(fixture.state))

    def test_old_receipt_is_not_reused_when_exact_bundle_fails_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SeamReviewPublicationFixture(Path(temporary) / "exact")
            request = fixture.request()
            receipt = publish_seam_review_package(
                fixture.state, fixture.package_a, request,
            )
            fixture.advance_ready_head()
            output = receipt["address"]
            directory = reviewed_seam_anchor_set_bundle_fs(
                fixture.state, output["project_id"],
            ).exact_path(
                output["reviewed_set_sha256"], output["bundle_sha256"],
            )
            (directory / DOCUMENT_NAMES[2]).write_bytes(b"{}")
            with self.assertRaises(SeamReviewPublicationUnavailableError):
                publish_seam_review_package(
                    fixture.state, fixture.package_a, request,
                )

    def test_cross_package_blocked_and_tampered_requests_fail_closed(self):
        baseline = tree_snapshot(self.fixture.state)
        cross = self.fixture.request(package_id=self.fixture.package_b)
        with self.assertRaises(SeamReviewPublicationUnavailableError):
            publish_seam_review_package(
                self.fixture.state, self.fixture.package_b, cross,
            )
        self.assertEqual(baseline, tree_snapshot(self.fixture.state))

        for changed in (
            {"decision_sha256": "f" * 64},
            {"candidate_sha256": "e" * 64},
            {"review_revision": 2},
        ):
            with self.subTest(changed=changed), self.assertRaises(
                SeamReviewPublicationUnavailableError
            ):
                publish_seam_review_package(
                    self.fixture.state, self.fixture.package_a,
                    self.fixture.request() | changed,
                )

    def test_request_contract_is_strict(self):
        request = self.fixture.request()
        attempts = (
            request | {"extra": True},
            request | {"package_id": self.fixture.package_b},
            request | {"format_version": True},
            request | {"intent": "wrong"},
        )
        for payload in attempts:
            with self.subTest(payload=payload), self.assertRaises(
                SeamReviewPublicationError
            ):
                publish_seam_review_package(
                    self.fixture.state, self.fixture.package_a, payload,
                )

    def test_b_entry_remains_explicitly_unobservable(self):
        entry = build_motion_policy_seam_review_entry(
            self.fixture.state, self.fixture.package_b,
        )
        self.assertEqual("blocked_unobservable", entry["status"])
        self.assertEqual(4, entry["summary"]["unobservable_count"])


if __name__ == "__main__":
    unittest.main()
