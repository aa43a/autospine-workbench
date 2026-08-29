"""Core tests for exact-package P9 human adoption and publication."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.motion_policy_decision_helpers import approved_review
from tests.motion_policy_preflight_helpers import (
    MotionPolicyFixtureMixin,
    tree_snapshot,
)
from tests.motion_policy_review_package_helpers import write_review_package

from autospine_workbench.motion_policy_adoption import (
    INTENT_VALUE,
    REQUEST_FORMAT,
    MotionPolicyAdoptionError,
    MotionPolicyAdoptionPackageNotFoundError,
    MotionPolicyAdoptionUnavailableError,
    adopt_motion_policy_package,
)
from autospine_workbench.motion_policy_review_packages import (
    list_motion_policy_review_packages,
)


class MotionPolicyAdoptionTests(MotionPolicyFixtureMixin, unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name) / "state"
        self.package_dir = write_review_package(
            self.state, self.policy, self.foot, self.depth,
        )
        self.package_id = list_motion_policy_review_packages(
            self.state,
        )["recommended_package_id"]
        self.request = {
            "format": REQUEST_FORMAT,
            "format_version": 1,
            "intent": INTENT_VALUE,
            "package_id": self.package_id,
            "review_input": {
                "review": approved_review(),
                "decisions": self.chain.accept_all(),
                "root_release_keys": [],
                "draw_order_loop_reset": {
                    "mode": "explicit", "approved": False,
                },
            },
        }

    def _adopt(self, request=None, package_id=None):
        upstream = self.chain.upstream
        with patch(
            "autospine_workbench.motion_policy_adoption."
            "VerifiedMeshBundleReader"
        ) as mesh_reader, patch(
            "autospine_workbench.motion_policy_adoption."
            "VerifiedMotionRetargetBundleReader"
        ) as retarget_reader:
            mesh_reader.return_value.load.return_value = upstream.mesh
            retarget_reader.return_value.load.return_value = upstream.retarget
            result = adopt_motion_policy_package(
                self.state,
                package_id or self.package_id,
                request or self.request,
            )
        return result

    def test_publish_replay_and_idempotent_reuse_are_path_free(self):
        first = self._adopt()
        second = self._adopt()
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        stable_first = {**first, "reused": None}
        stable_second = {**second, "reused": None}
        self.assertEqual(stable_first, stable_second)
        self.assertEqual("passed", first["verification"]["status"])
        self.assertTrue(
            first["verification"]["replayed_from_exact_upstreams"]
        )
        address = first["address"]
        directory = (
            self.state / "builds" / first["project_id"]
            / "reviewed-motion-instances"
            / address["motion_instance_v2_sha256"]
            / address["bundle_sha256"]
        )
        self.assertTrue(directory.is_dir())
        self.assertEqual(6, len(tuple(directory.iterdir())))
        encoded = json.dumps(first)
        self.assertNotIn(str(self.state), encoded)
        self.assertNotIn("input_bundle_paths", encoded)

    def test_invalid_crosswire_and_stale_package_make_zero_writes(self):
        before = tree_snapshot(self.state)
        boolean_version = deepcopy(self.request)
        boolean_version["format_version"] = True
        with self.assertRaises(MotionPolicyAdoptionError):
            self._adopt(boolean_version)
        self.assertEqual(before, tree_snapshot(self.state))

        mismatched = deepcopy(self.request)
        mismatched["package_id"] = "f" * 64
        with self.assertRaises(MotionPolicyAdoptionError):
            self._adopt(mismatched)
        self.assertEqual(before, tree_snapshot(self.state))

        crosswired = deepcopy(self.request)
        crosswired["review_input"]["decisions"][0][
            "candidate_id"
        ] = "foot-" + "f" * 64
        with self.assertRaises(MotionPolicyAdoptionError):
            self._adopt(crosswired)
        self.assertEqual(before, tree_snapshot(self.state))

        policy_path = self.package_dir / "depth-pair-policy.json"
        stale = json.loads(policy_path.read_text(encoding="utf-8"))
        stale["policy_id"] = "changed-policy"
        policy_path.write_text(json.dumps(stale), encoding="utf-8")
        after_mutation = tree_snapshot(self.state)
        with self.assertRaises(MotionPolicyAdoptionPackageNotFoundError):
            self._adopt()
        self.assertEqual(after_mutation, tree_snapshot(self.state))

    def test_exact_upstream_failure_makes_zero_publication(self):
        before = tree_snapshot(self.state)
        with patch(
            "autospine_workbench.motion_policy_adoption."
            "VerifiedMeshBundleReader"
        ) as reader, self.assertRaises(
            MotionPolicyAdoptionUnavailableError
        ):
            reader.return_value.load.side_effect = ValueError("private path")
            adopt_motion_policy_package(
                self.state, self.package_id, self.request,
            )
        self.assertEqual(before, tree_snapshot(self.state))

    def test_concurrent_adoption_has_one_writer_and_one_address(self):
        upstream = self.chain.upstream
        with patch(
            "autospine_workbench.motion_policy_adoption."
            "VerifiedMeshBundleReader"
        ) as mesh_reader, patch(
            "autospine_workbench.motion_policy_adoption."
            "VerifiedMotionRetargetBundleReader"
        ) as retarget_reader:
            mesh_reader.return_value.load.return_value = upstream.mesh
            retarget_reader.return_value.load.return_value = upstream.retarget
            with ThreadPoolExecutor(max_workers=4) as executor:
                receipts = list(executor.map(
                    lambda _index: adopt_motion_policy_package(
                        self.state, self.package_id, self.request,
                    ),
                    range(4),
                ))
        self.assertEqual(1, sum(not row["reused"] for row in receipts))
        self.assertEqual(1, len({
            (row["address"]["motion_instance_v2_sha256"],
             row["address"]["bundle_sha256"])
            for row in receipts
        }))


if __name__ == "__main__":
    unittest.main()
