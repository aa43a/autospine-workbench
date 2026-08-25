"""Pure in-memory verified IK pipeline tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.ik_pipeline import (  # noqa: E402
    VerifiedIkPipeline,
    VerifiedIkPipelineError,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_ik_target_profile import verified_bundle  # noqa: E402


class VerifiedIkPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name)
        self.base = verified_bundle()

    def build(self):
        with patch(
            "autospine_workbench.ik_pipeline.VerifiedMeshBundleReader"
        ) as reader:
            reader.return_value.load.return_value = self.base
            result = VerifiedIkPipeline(self.state).build(
                self.base.project_id,
                self.base.rig_sha256,
                self.base.bundle_sha256,
            )
            reader.assert_called_once_with(self.state)
            reader.return_value.load.assert_called_once_with(
                self.base.project_id,
                self.base.rig_sha256,
                self.base.bundle_sha256,
            )
            return result

    def test_exact_verified_p3_builds_frozen_profile_and_passed_probes(self) -> None:
        result = self.build()

        self.assertEqual(self.base.project_id, result.project_id)
        self.assertEqual("handles=4", result.summary)
        self.assertEqual("passed", result.probes["status"])
        self.assertEqual(4, len(result.profile["handles"]))
        self.assertEqual(result.profile["source"], result.input_sha256s)
        self.assertEqual({
            "profile_sha256": canonical_sha256(result.profile),
            "probes_sha256": canonical_sha256(result.probes),
        }, result.output_sha256s)
        changed_profile, changed_probes = result.profile, result.probes
        changed_profile.clear()
        changed_probes.clear()
        self.assertTrue(result.profile)
        self.assertTrue(result.probes)
        with self.assertRaises(FrozenInstanceError):
            result.summary = "changed"  # type: ignore[misc]

    def test_same_exact_input_is_deterministic_and_does_not_mutate_base(self) -> None:
        rig_before = deepcopy(self.base.rig)
        first, second = self.build(), self.build()

        self.assertEqual(first, second)
        self.assertEqual(rig_before, self.base.rig)

    def test_invalid_identity_fails_before_reader_access(self) -> None:
        cases = (
            ("../escape", self.base.rig_sha256, self.base.bundle_sha256),
            (self.base.project_id, "latest", self.base.bundle_sha256),
            (self.base.project_id, self.base.rig_sha256, "A" * 64),
        )
        with patch(
            "autospine_workbench.ik_pipeline.VerifiedMeshBundleReader"
        ) as reader:
            for values in cases:
                with self.subTest(values=values), self.assertRaises(
                    VerifiedIkPipelineError
                ):
                    VerifiedIkPipeline(self.state).build(*values)
            reader.assert_not_called()

    def test_reader_result_must_equal_requested_exact_address(self) -> None:
        with patch(
            "autospine_workbench.ik_pipeline.VerifiedMeshBundleReader"
        ) as reader:
            reader.return_value.load.return_value = self.base
            with self.assertRaisesRegex(
                VerifiedIkPipelineError, "differs from the requested"
            ):
                VerifiedIkPipeline(self.state).build(
                    self.base.project_id,
                    "f" * 64,
                    self.base.bundle_sha256,
                )

    def test_profile_or_probe_drift_fails_closed(self) -> None:
        invalid = self.build().profile
        invalid["source"]["bundle_sha256"] = "f" * 64
        with (
            patch(
                "autospine_workbench.ik_pipeline.VerifiedMeshBundleReader"
            ) as reader,
            patch(
                "autospine_workbench.ik_pipeline.compile_ik_target_profile"
            ) as compile_profile,
        ):
            reader.return_value.load.return_value = self.base
            compile_profile.return_value.document = invalid
            with self.assertRaises(VerifiedIkPipelineError):
                VerifiedIkPipeline(self.state).build(
                    self.base.project_id,
                    self.base.rig_sha256,
                    self.base.bundle_sha256,
                )


if __name__ == "__main__":
    unittest.main()
