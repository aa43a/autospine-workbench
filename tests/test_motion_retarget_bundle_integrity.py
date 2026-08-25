"""Full rebuild tests for immutable P5 retarget bundle snapshots."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_retarget_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
    MAX_RUN_BYTES,
    build_motion_retarget_bundle_contract,
)
from autospine_workbench.motion_retarget_bundle_integrity import (  # noqa: E402
    MotionRetargetBundleIntegrityError,
    MotionRetargetBundleSnapshot,
    verify_motion_retarget_bundle_snapshot,
)
from tests.test_motion_retarget_pipeline import PipelineFixture  # noqa: E402


class RetargetBundleFixture:
    def __init__(self, root: Path):
        self.pipeline = PipelineFixture(root)
        self.result = self.pipeline.build()
        self.contract = build_motion_retarget_bundle_contract(
            self.result.project_id,
            self.result.target_profile,
            self.result.motion_instance,
            self.result.retarget_run,
            self.result.retarget_report,
            self.result.mesh_regression,
        )
        self.directory = (
            self.pipeline.state / "builds" / self.contract.project_id
            / "motion-instances" / self.contract.instance_sha256
            / self.contract.bundle_sha256
        )
        self.directory.mkdir(parents=True)
        for name, data in self.contract.document_bytes.items():
            (self.directory / name).write_bytes(data)

    def snapshot(self, items=None, directory=None):
        values = items or tuple(
            (name, self.contract.document_bytes[name]) for name in DOCUMENT_NAMES
        )
        return MotionRetargetBundleSnapshot(directory or self.directory, values)

    def verify(self, snapshot=None):
        return verify_motion_retarget_bundle_snapshot(
            snapshot or self.snapshot(),
            state_root=self.pipeline.state,
            expected_project_id=self.contract.project_id,
            expected_instance_sha256=self.contract.instance_sha256,
            expected_bundle_sha256=self.contract.bundle_sha256,
        )

    @contextmanager
    def patched_pipeline(self, result=None):
        with patch(
            "autospine_workbench.motion_retarget_bundle_integrity."
            "VerifiedMotionRetargetPipeline"
        ) as pipeline:
            pipeline.return_value.build.return_value = result or self.result
            yield pipeline


class MotionRetargetBundleIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = RetargetBundleFixture(Path(self.temporary.name))

    def test_full_success_is_exact_frozen_and_isolated(self):
        with self.fixture.patched_pipeline() as pipeline:
            verified = self.fixture.verify()
        contract = self.fixture.contract
        self.assertEqual(DOCUMENT_NAMES, verified.inventory)
        self.assertEqual(contract.instance_sha256, verified.instance_sha256)
        self.assertEqual(contract.bundle_sha256, verified.bundle_sha256)
        self.assertEqual(contract.run_document_sha256,
                         verified.run_document_sha256)
        self.assertEqual(contract.report_sha256,
                         verified.retarget_report_sha256)
        self.assertEqual(contract.mesh_report_sha256,
                         verified.mesh_regression_sha256)
        expected_sources = {
            "p3_rig_sha256": self.fixture.pipeline.args[1],
            "p3_bundle_sha256": self.fixture.pipeline.args[2],
            "p4_profile_sha256": self.fixture.pipeline.args[3],
            "p4_bundle_sha256": self.fixture.pipeline.args[4],
            "motion_clip_sha256": self.fixture.pipeline.args[5],
            "motion_bundle_sha256": self.fixture.pipeline.args[6],
        }
        self.assertEqual(expected_sources, verified.source_addresses)
        pipeline.return_value.build.assert_called_once_with(
            self.fixture.pipeline.args[0], *expected_sources.values()
        )
        verified.target_profile.clear()
        verified.source_addresses.clear()
        verified.document_bytes.clear()
        self.assertTrue(verified.target_profile)
        self.assertEqual(expected_sources, verified.source_addresses)
        self.assertEqual(DOCUMENT_NAMES, verified.inventory)
        with self.assertRaises(FrozenInstanceError):
            verified.clip_id = "changed"  # type: ignore[misc]

    def test_each_stored_document_tamper_fails_before_pipeline(self):
        baseline = self.fixture.snapshot().document_items
        for index, name in enumerate(DOCUMENT_NAMES):
            changed = list(baseline)
            changed[index] = (name, changed[index][1] + b"\n")
            with self.subTest(name=name), self.fixture.patched_pipeline() as pipe:
                with self.assertRaises(MotionRetargetBundleIntegrityError):
                    self.fixture.verify(self.fixture.snapshot(tuple(changed)))
                pipe.return_value.build.assert_not_called()

    def test_requested_and_physical_address_drift_fail_closed(self):
        with self.fixture.patched_pipeline(), self.assertRaises(
            MotionRetargetBundleIntegrityError
        ):
            verify_motion_retarget_bundle_snapshot(
                self.fixture.snapshot(),
                state_root=self.fixture.pipeline.state,
                expected_project_id=self.fixture.contract.project_id,
                expected_instance_sha256="f" * 64,
                expected_bundle_sha256=self.fixture.contract.bundle_sha256,
            )
        wrong = self.fixture.directory.parent.parent / self.fixture.contract.bundle_sha256
        with self.fixture.patched_pipeline(), self.assertRaisesRegex(
            MotionRetargetBundleIntegrityError, "content-address path"
        ):
            self.fixture.verify(self.fixture.snapshot(directory=wrong))

        outside = (
            Path(self.temporary.name) / "outside" / "builds"
            / self.fixture.contract.project_id / "motion-instances"
            / self.fixture.contract.instance_sha256
            / self.fixture.contract.bundle_sha256
        )
        outside.mkdir(parents=True)
        with self.fixture.patched_pipeline(), self.assertRaisesRegex(
            MotionRetargetBundleIntegrityError, "content-address path"
        ):
            self.fixture.verify(self.fixture.snapshot(directory=outside))

    def test_pipeline_document_or_identity_drift_fails(self):
        document = self.fixture.result.target_profile
        document["project_id"] = "other"
        changed = replace(
            self.fixture.result,
            project_id="other",
            _target_json=json.dumps(document, sort_keys=True, separators=(",", ":")),
        )
        with self.fixture.patched_pipeline(changed), self.assertRaises(
            MotionRetargetBundleIntegrityError
        ):
            self.fixture.verify()

        outputs = self.fixture.result.output_sha256s
        outputs["retarget_report_sha256"] = "f" * 64
        changed = replace(
            self.fixture.result,
            _output_sha_json=json.dumps(outputs, sort_keys=True, separators=(",", ":")),
        )
        with self.fixture.patched_pipeline(changed), self.assertRaisesRegex(
            MotionRetargetBundleIntegrityError, "identity inventory"
        ):
            self.fixture.verify()

    def test_actual_upstream_motion_bundle_tamper_is_rejected(self):
        motion_path = (
            self.fixture.pipeline.state / "motions"
            / self.fixture.pipeline.args[5] / self.fixture.pipeline.args[6]
            / "motion.json"
        )
        motion_path.write_bytes(motion_path.read_bytes() + b"\n")
        targets = (
            ("VerifiedMeshBundleReader", self.fixture.pipeline.mesh),
            ("VerifiedIkBundleReader", self.fixture.pipeline.ik),
        )
        with ExitStack() as stack:
            for name, value in targets:
                reader = stack.enter_context(patch(
                    f"autospine_workbench.motion_retarget_pipeline.{name}"
                ))
                reader.return_value.load.return_value = value
            with self.assertRaises(MotionRetargetBundleIntegrityError):
                self.fixture.verify()

    def test_strict_json_inventory_and_budget_fail_closed(self):
        items = list(self.fixture.snapshot().document_items)
        items[0] = (items[0][0], b'{"x":1,"x":2}')
        with self.fixture.patched_pipeline(), self.assertRaisesRegex(
            MotionRetargetBundleIntegrityError, "duplicate key"
        ):
            self.fixture.verify(self.fixture.snapshot(tuple(items)))
        items = list(self.fixture.snapshot().document_items)
        items[2] = (items[2][0], b"x" * (MAX_RUN_BYTES + 1))
        with self.fixture.patched_pipeline(), self.assertRaisesRegex(
            MotionRetargetBundleIntegrityError, "byte budget"
        ):
            self.fixture.verify(self.fixture.snapshot(tuple(items)))
        swapped = list(self.fixture.snapshot().document_items)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        with self.fixture.patched_pipeline(), self.assertRaisesRegex(
            MotionRetargetBundleIntegrityError, "inventory"
        ):
            self.fixture.verify(self.fixture.snapshot(tuple(swapped)))


if __name__ == "__main__":
    unittest.main()
