"""Filesystem boundary tests for automatic motion-policy review packages."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from tests.motion_policy_preflight_helpers import MotionPolicyFixtureMixin
from tests.motion_policy_review_package_helpers import write_review_package

from autospine_workbench.motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    _is_linklike,
    _read_text,
    get_motion_policy_review_package,
    list_motion_policy_review_packages,
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

        detail = get_motion_policy_review_package(
            self.state, first["recommended_package_id"],
        )
        self.assertEqual(self.policy, json.loads(detail["policy_json"]))
        self.assertEqual(self.foot, json.loads(detail["foot_candidates_json"]))
        self.assertEqual(
            self.depth, json.loads(detail["depth_candidates_json"]),
        )
        encoded = json.dumps(detail)
        self.assertNotIn("private-package-root", encoded)
        self.assertNotIn("input_bundle_paths", encoded)

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
