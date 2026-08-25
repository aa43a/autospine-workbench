"""Service-level gates for exact P5 motion-retarget bundle commands."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
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
    build_motion_retarget_bundle_contract,
)
from autospine_workbench.motion_retarget_bundle_reader import (  # noqa: E402
    VerifiedMotionRetargetBundleReader,
)
from autospine_workbench.motion_retarget_bundle_store import (  # noqa: E402
    MotionRetargetBundleStore,
)
from autospine_workbench.motion_retarget_commands import (  # noqa: E402
    MotionRetargetCommandError,
    compile_motion_retarget_bundle,
    verify_motion_retarget_bundle,
)
from tests.test_motion_retarget_pipeline import PipelineFixture  # noqa: E402


def canonical(value: dict) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


def tree(root: Path) -> dict[str, bytes]:
    return {
        item.relative_to(root).as_posix(): item.read_bytes()
        for item in root.rglob("*") if item.is_file()
    }


def identity(result) -> tuple:
    return (
        result.project_id, result.clip_id, result.target_profile_sha256,
        result.instance_sha256, result.retarget_run_identity_sha256,
        result.run_sha256, result.report_sha256,
        result.mesh_regression_sha256, result.bundle_sha256,
        result.summary, result.source_addresses,
        result.input_sha256s, result.output_sha256s,
    )


class MotionRetargetCommandFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.pipeline_fixture = PipelineFixture(Path(self.temporary.name))
        self.state = self.pipeline_fixture.state
        self.pipeline = self.pipeline_fixture.build()
        args = self.pipeline_fixture.args
        self.project = args[0]
        self.requested = dict(zip((
            "p3_rig_sha256", "p3_bundle_sha256", "p4_profile_sha256",
            "p4_bundle_sha256", "motion_clip_sha256", "motion_bundle_sha256",
        ), args[1:]))
        self.contract = build_motion_retarget_bundle_contract(
            self.project, self.pipeline.target_profile,
            self.pipeline.motion_instance, self.pipeline.retarget_run,
            self.pipeline.retarget_report, self.pipeline.mesh_regression,
        )

    @contextmanager
    def pipeline_patches(self, result=None):
        with patch(
            "autospine_workbench.motion_retarget_commands."
            "VerifiedMotionRetargetPipeline"
        ) as command, patch(
            "autospine_workbench.motion_retarget_bundle_integrity."
            "VerifiedMotionRetargetPipeline"
        ) as integrity:
            command.return_value.build.return_value = result or self.pipeline
            integrity.return_value.build.return_value = result or self.pipeline
            yield command, integrity

    @contextmanager
    def integrity_patch(self):
        with patch(
            "autospine_workbench.motion_retarget_bundle_integrity."
            "VerifiedMotionRetargetPipeline"
        ) as pipeline:
            pipeline.return_value.build.return_value = self.pipeline
            yield pipeline

    def compile(self):
        with self.pipeline_patches() as patched:
            result = compile_motion_retarget_bundle(
                self.state, self.project, **self.requested
            )
        return result, patched

    def publish(self):
        return MotionRetargetBundleStore(self.state).publish(
            self.project, self.pipeline.target_profile,
            self.pipeline.motion_instance, self.pipeline.retarget_run,
            self.pipeline.retarget_report, self.pipeline.mesh_regression,
        )

    def verified(self, published=None):
        publication = published or self.publish()
        with self.integrity_patch():
            return VerifiedMotionRetargetBundleReader(self.state).load(
                self.project, publication.instance_sha256,
                publication.bundle_sha256,
            )


class MotionRetargetCommandSuccessTests(MotionRetargetCommandFixture):
    def test_compile_exact_args_determinism_reuse_and_no_latest_alias(self):
        first, (command, integrity) = self.compile()
        second, _patched = self.compile()
        command.assert_called_once_with(self.state)
        command.return_value.build.assert_called_once_with(
            self.project, *self.requested.values()
        )
        integrity.assert_called_once_with(self.state)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(identity(first), identity(second))
        self.assertEqual(first.path, second.path)
        self.assertEqual(15, len(first.input_sha256s))
        self.assertEqual(6, len(first.output_sha256s))
        self.assertEqual(self.requested, first.source_addresses)
        self.assertFalse((first.path.parent / "latest").exists())
        self.assertFalse((first.path.parent / "latest.json").exists())

    def test_result_exposes_exact_bytes_summary_and_copy_isolation(self):
        result, _patched = self.compile()
        self.assertEqual(DOCUMENT_NAMES, result.inventory)
        self.assertEqual(self.contract.document_bytes, result.document_bytes)
        for name, data in result.document_bytes.items():
            self.assertEqual(data, (result.path / name).read_bytes())
        self.assertEqual(self.pipeline.summary, result.summary)
        self.assertEqual(
            self.pipeline.output_sha256s["retarget_run_identity_sha256"],
            result.retarget_run_identity_sha256,
        )
        for value in (
            result.source_addresses, result.input_sha256s,
            result.output_sha256s, result.document_bytes,
        ):
            value.clear()
        self.assertTrue(result.source_addresses)
        self.assertTrue(result.input_sha256s)
        self.assertTrue(result.output_sha256s)
        self.assertTrue(result.document_bytes)
        with self.assertRaises(FrozenInstanceError):
            result.summary = "changed"  # type: ignore[misc]

    def test_verify_is_read_only_exact_and_marks_reuse_unknown(self):
        compiled, _patched = self.compile()
        before = tree(self.state)
        with self.integrity_patch() as pipeline:
            verified = verify_motion_retarget_bundle(
                self.state, self.project,
                instance_sha256=compiled.instance_sha256,
                bundle_sha256=compiled.bundle_sha256,
            )
        self.assertEqual(before, tree(self.state))
        self.assertIsNone(verified.reused)
        self.assertEqual(identity(compiled), identity(verified))
        pipeline.return_value.build.assert_called_once_with(
            self.project, *self.requested.values()
        )


class MotionRetargetCommandRejectionTests(MotionRetargetCommandFixture):
    def test_requested_exact_address_drift_fails_before_publication(self):
        changed = dict(self.requested)
        changed["p3_rig_sha256"] = "f" * 64
        before = tree(self.state)
        with self.pipeline_patches(), self.assertRaisesRegex(
            MotionRetargetCommandError, "pipeline identity"
        ):
            compile_motion_retarget_bundle(self.state, self.project, **changed)
        self.assertEqual(before, tree(self.state))
        self.assertFalse((self.state / "builds").exists())

    def test_pipeline_full_input_or_output_identity_drift_fails_closed(self):
        cases = []
        inputs = self.pipeline.input_sha256s
        inputs.pop("motion_run_sha256")
        cases.append(replace(self.pipeline, _input_sha_json=canonical(inputs)))
        outputs = self.pipeline.output_sha256s
        outputs["mesh_regression_sha256"] = "f" * 64
        cases.append(replace(self.pipeline, _output_sha_json=canonical(outputs)))
        for drifted in cases:
            with self.subTest(drift=drifted), self.pipeline_patches(drifted), \
                    self.assertRaises(MotionRetargetCommandError):
                compile_motion_retarget_bundle(
                    self.state, self.project, **self.requested
                )
        self.assertFalse((self.state / "builds").exists())

    def test_rejected_mesh_evidence_never_reaches_store(self):
        rejected = deepcopy(self.pipeline.mesh_regression)
        rejected["status"] = "failed"
        drifted = replace(self.pipeline, _mesh_json=canonical(rejected))
        before = tree(self.state)
        with self.pipeline_patches(drifted), self.assertRaises(
            MotionRetargetCommandError
        ), patch(
            "autospine_workbench.motion_retarget_commands."
            "MotionRetargetBundleStore"
        ) as store:
            compile_motion_retarget_bundle(
                self.state, self.project, **self.requested
            )
        store.assert_not_called()
        self.assertEqual(before, tree(self.state))

    def test_store_identity_drift_is_rejected_before_readback(self):
        published = self.publish()
        drifted = replace(published, bundle_sha256="f" * 64)
        with patch(
            "autospine_workbench.motion_retarget_commands."
            "VerifiedMotionRetargetPipeline"
        ) as pipeline, patch(
            "autospine_workbench.motion_retarget_commands."
            "MotionRetargetBundleStore"
        ) as store, patch(
            "autospine_workbench.motion_retarget_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as reader:
            pipeline.return_value.build.return_value = self.pipeline
            store.return_value.publish.return_value = drifted
            with self.assertRaisesRegex(
                MotionRetargetCommandError, "Published motion retarget identity"
            ):
                compile_motion_retarget_bundle(
                    self.state, self.project, **self.requested
                )
        reader.assert_not_called()

    def test_reader_identity_and_document_byte_drift_are_rejected(self):
        published = self.publish()
        verified = self.verified(published)
        identity_drift = replace(verified, retarget_report_sha256="f" * 64)
        byte_items = list(verified._document_items)
        byte_items[0] = (byte_items[0][0], byte_items[0][1] + b"\n")
        byte_drift = replace(verified, _document_items=tuple(byte_items))
        for drifted in (identity_drift, byte_drift):
            with self.subTest(drift=drifted), patch(
                "autospine_workbench.motion_retarget_commands."
                "VerifiedMotionRetargetPipeline"
            ) as pipeline, patch(
                "autospine_workbench.motion_retarget_commands."
                "VerifiedMotionRetargetBundleReader"
            ) as reader:
                pipeline.return_value.build.return_value = self.pipeline
                reader.return_value.load.return_value = drifted
                with self.assertRaises(MotionRetargetCommandError):
                    compile_motion_retarget_bundle(
                        self.state, self.project, **self.requested
                    )

    def test_physical_tamper_and_invalid_verify_addresses_fail_closed(self):
        compiled, _patched = self.compile()
        target = compiled.path / "retarget-report.json"
        target.write_bytes(target.read_bytes() + b"\n")
        with self.integrity_patch(), self.assertRaises(MotionRetargetCommandError):
            verify_motion_retarget_bundle(
                self.state, self.project,
                instance_sha256=compiled.instance_sha256,
                bundle_sha256=compiled.bundle_sha256,
            )
        with self.assertRaises(MotionRetargetCommandError):
            verify_motion_retarget_bundle(
                self.state, self.project,
                instance_sha256="not-a-sha", bundle_sha256="also-not-a-sha",
            )

    def test_adjacent_runtime_failures_are_unified(self):
        with patch(
            "autospine_workbench.motion_retarget_commands."
            "VerifiedMotionRetargetPipeline"
        ) as pipeline:
            pipeline.return_value.build.side_effect = RuntimeError("pipeline boom")
            with self.assertRaisesRegex(
                MotionRetargetCommandError, "bundle compilation failed"
            ):
                compile_motion_retarget_bundle(
                    self.state, self.project, **self.requested
                )
        with patch(
            "autospine_workbench.motion_retarget_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as reader:
            reader.return_value.load.side_effect = RuntimeError("reader boom")
            with self.assertRaisesRegex(
                MotionRetargetCommandError, "bundle verification failed"
            ):
                verify_motion_retarget_bundle(
                    self.state, self.project,
                    instance_sha256="f" * 64, bundle_sha256="e" * 64,
                )


if __name__ == "__main__":
    unittest.main()
