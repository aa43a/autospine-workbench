"""Filesystem boundary tests for automatic motion-policy review packages."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from tests.motion_policy_preflight_helpers import MotionPolicyFixtureMixin
from tests.motion_policy_review_package_helpers import write_review_package

from autospine_workbench.current_project_chain import CurrentProjectChain
from autospine_workbench.motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    MotionPolicyReviewPackageHistoricalError,
    _is_linklike,
    _read_text,
    get_motion_policy_review_package,
    list_motion_policy_review_packages,
    require_current_motion_policy_review_package,
)


class MotionPolicyReviewPackageTests(
    MotionPolicyFixtureMixin,
    unittest.TestCase,
):
    def setUp(self) -> None:
        self.state_temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.state_temporary.name)

    def tearDown(self) -> None:
        self.state_temporary.cleanup()

    def _current(self, *, resolved=None, manifest=None):
        project_id = self.policy["project_id"]
        p3 = self.policy["source"]["p3"]
        return {
            project_id: CurrentProjectChain(
                project_id,
                resolved or p3["resolved_project_sha256"],
                manifest or p3["layer_manifest_sha256"],
            ),
        }

    def test_list_and_exact_detail_are_deterministic_and_path_free(self):
        write_review_package(
            self.state, self.policy, self.foot, self.depth,
            motion_id="motion-b",
        )
        write_review_package(
            self.state, self.policy, self.foot, self.depth,
            motion_id="motion-a",
        )

        first = list_motion_policy_review_packages(self.state)
        second = list_motion_policy_review_packages(self.state)
        self.assertEqual(first, second)
        self.assertEqual(2, first["count"])
        self.assertEqual(0, first["skipped_count"])
        self.assertEqual(
            ["motion-a", "motion-b"],
            [row["motion_id"] for row in first["packages"]],
        )
        self.assertEqual(
            first["packages"][0]["package_id"],
            first["recommended_package_id"],
        )
        self.assertNotEqual(
            first["packages"][0]["package_id"],
            first["packages"][1]["package_id"],
        )
        self.assertNotIn("policy_json", first["packages"][0])
        self.assertNotIn("authoring_alignment", first["packages"][0])

        detail = get_motion_policy_review_package(
            self.state, first["recommended_package_id"],
        )
        self.assertEqual(self.policy, json.loads(detail["policy_json"]))
        self.assertNotIn("authoring_alignment", detail)
        self.assertEqual(self.foot, json.loads(detail["foot_candidates_json"]))
        self.assertEqual(
            self.depth, json.loads(detail["depth_candidates_json"]),
        )
        encoded = json.dumps(detail)
        self.assertNotIn("private-package-root", encoded)
        self.assertNotIn("input_bundle_paths", encoded)

    def test_explicit_current_inventory_aligns_and_recommends_only_unique(self):
        write_review_package(self.state, self.policy, self.foot, self.depth)
        current = self._current()

        listing = list_motion_policy_review_packages(
            self.state, current_project_chains=current,
        )
        row = listing["packages"][0]
        self.assertEqual(2, listing["format_version"])
        self.assertEqual(2, row["format_version"])
        self.assertEqual("current", row["authoring_alignment"])
        self.assertEqual(row["package_id"], listing["recommended_package_id"])
        detail = get_motion_policy_review_package(
            self.state,
            row["package_id"],
            current_project_chains=current,
        )
        self.assertEqual("current", detail["authoring_alignment"])
        self.assertEqual(2, detail["format_version"])
        self.assertEqual(
            row["package_id"],
            require_current_motion_policy_review_package(
                self.state,
                row["package_id"],
                current_project_chains=current,
            )["package_id"],
        )

        historical = self._current(manifest="f" * 64)
        stale = list_motion_policy_review_packages(
            self.state, current_project_chains=historical,
        )
        self.assertIsNone(stale["recommended_package_id"])
        self.assertEqual(
            "historical", stale["packages"][0]["authoring_alignment"],
        )
        with self.assertRaises(MotionPolicyReviewPackageHistoricalError):
            require_current_motion_policy_review_package(
                self.state,
                row["package_id"],
                current_project_chains=historical,
            )
        for stale_current in (
            self._current(resolved="e" * 64),
            {},
        ):
            with self.subTest(stale_current=stale_current):
                stale = list_motion_policy_review_packages(
                    self.state, current_project_chains=stale_current,
                )
                self.assertIsNone(stale["recommended_package_id"])
                self.assertEqual(
                    "historical",
                    stale["packages"][0]["authoring_alignment"],
                )

    def test_two_current_packages_are_not_ambiguously_recommended(self):
        write_review_package(
            self.state, self.policy, self.foot, self.depth,
            motion_id="motion-a",
        )
        write_review_package(
            self.state, self.policy, self.foot, self.depth,
            motion_id="motion-b",
        )
        listing = list_motion_policy_review_packages(
            self.state, current_project_chains=self._current(),
        )
        self.assertEqual(2, listing["count"])
        self.assertIsNone(listing["recommended_package_id"])
        self.assertEqual(
            {"current"},
            {row["authoring_alignment"] for row in listing["packages"]},
        )

    def test_invalid_and_crosswired_packages_are_skipped(self):
        write_review_package(self.state, self.policy, self.foot, self.depth)
        invalid = self.state / "reviews" / "motion-b" / "sample-a"
        invalid.mkdir(parents=True)
        (invalid / "depth-pair-policy.json").write_text(
            '{"secret":"C:/private/should-not-leak"}', encoding="utf-8",
        )
        for name in (
            "foot-lock-candidates.json", "depth-order-candidates.json",
        ):
            (invalid / name).write_text("{}", encoding="utf-8")

        mismatched_policy = deepcopy(self.policy)
        mismatched_policy["project_id"] = "another-project"
        write_review_package(
            self.state, mismatched_policy, self.foot, self.depth,
            motion_id="motion-c",
        )
        malformed = write_review_package(
            self.state, self.policy, self.foot, self.depth,
            motion_id="motion-d",
        )
        (malformed / "depth-pair-policy.json").write_text(
            '{"format":"autospine-depth-pair-policy"}', encoding="utf-8",
        )
        result = list_motion_policy_review_packages(self.state)
        self.assertEqual(1, result["count"])
        self.assertEqual(3, result["skipped_count"])
        with self.assertRaises(MotionPolicyReviewPackageError) as caught:
            get_motion_policy_review_package(self.state, "f" * 64)
        self.assertNotIn("private", str(caught.exception))

    def test_bounded_read_rejects_escape_and_oversize(self):
        package = write_review_package(
            self.state, self.policy, self.foot, self.depth,
        )
        oversized = package / "oversized.json"
        oversized.write_bytes(b"12345")
        with self.assertRaises(MotionPolicyReviewPackageError):
            _read_text(oversized, 4, package)

        outside = self.state / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        with self.assertRaises(MotionPolicyReviewPackageError):
            _read_text(outside, 1024, package)

    def test_linklike_inventory_is_rejected(self):
        class JunctionLike:
            @staticmethod
            def is_symlink() -> bool:
                return False

            @staticmethod
            def is_junction() -> bool:
                return True

        self.assertTrue(_is_linklike(JunctionLike()))  # type: ignore[arg-type]

        external = self.state / "external-motion"
        project = external / "sample-a"
        project.mkdir(parents=True)
        reviews = self.state / "reviews"
        reviews.mkdir()
        link = reviews / "motion-link"
        try:
            link.symlink_to(external, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlinks unavailable: {type(exc).__name__}")
        with self.assertRaises(MotionPolicyReviewPackageError):
            list_motion_policy_review_packages(self.state)


if __name__ == "__main__":
    unittest.main()
