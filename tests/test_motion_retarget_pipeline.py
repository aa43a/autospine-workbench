"""Exact-address P5 motion retarget pipeline tests."""

from __future__ import annotations

from contextlib import contextmanager, ExitStack
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
)
from autospine_workbench.motion_bundle_store import MotionBundleStore  # noqa: E402
from autospine_workbench.motion_retarget_compiler import (  # noqa: E402
    compile_motion_instance,
)
from autospine_workbench.motion_retarget_report import (  # noqa: E402
    build_motion_retarget_report,
)
from autospine_workbench.motion_retarget_pipeline import (  # noqa: E402
    VerifiedMotionRetargetPipeline,
    VerifiedMotionRetargetPipelineError,
)
from autospine_workbench.motion_target_profile import (  # noqa: E402
    compile_motion_target_profile,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_motion_bundle_contract import payload  # noqa: E402
from tests.test_motion_mesh_regression import exact_mesh_and_target  # noqa: E402
from tests.test_motion_target_profile import ik_fixture  # noqa: E402


def tree(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


class PipelineFixture:
    def __init__(self, root: Path):
        self.state = root / "state"
        self.mesh, _target = exact_mesh_and_target(converted=False)
        self.ik = ik_fixture(self.mesh)
        published_motion = MotionBundleStore(self.state).publish(*payload("idle"))
        self.motion = VerifiedMotionBundleReader(self.state).load(
            published_motion.clip_sha256, published_motion.bundle_sha256
        )
        self.args = (
            self.mesh.project_id, self.mesh.rig_sha256, self.mesh.bundle_sha256,
            self.ik.profile_sha256, self.ik.bundle_sha256,
            self.motion.clip_sha256, self.motion.bundle_sha256,
        )

    def build(self):
        with self.patched_readers():
            return self.build_unpatched()

    def build_unpatched(self):
        return VerifiedMotionRetargetPipeline(self.state).build(*self.args)

    @contextmanager
    def patched_readers(self, *, mesh=None, ik=None, motion=None):
        values = (
            ("VerifiedMeshBundleReader", mesh or self.mesh),
            ("VerifiedIkBundleReader", ik or self.ik),
            ("VerifiedMotionBundleReader", motion or self.motion),
        )
        with ExitStack() as stack:
            readers = []
            for name, value in values:
                reader = stack.enter_context(patch(
                    f"autospine_workbench.motion_retarget_pipeline.{name}"
                ))
                reader.return_value.load.return_value = value
                readers.append(reader)
            yield tuple(readers)


class VerifiedMotionRetargetPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = PipelineFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_exact_pipeline_is_deterministic_read_only_and_complete(self):
        before = tree(self.fixture.state)
        first = self.fixture.build()
        second = self.fixture.build()
        self.assertEqual(first, second)
        self.assertEqual(before, tree(self.fixture.state))
        self.assertEqual("idle", first.clip_id)
        self.assertEqual("passed", first.retarget_report["status"])
        self.assertEqual("passed", first.mesh_regression["status"])
        self.assertIn("mesh=reviewed-noop", first.summary)
        documents = {
            "target_profile_sha256": first.target_profile,
            "motion_instance_sha256": first.motion_instance,
            "retarget_run_document_sha256": first.retarget_run,
            "retarget_report_sha256": first.retarget_report,
            "mesh_regression_sha256": first.mesh_regression,
        }
        for key, document in documents.items():
            self.assertEqual(canonical_sha256(document), first.output_sha256s[key])
        self.assertEqual(15, len(first.input_sha256s))
        self.assertEqual(self.fixture.mesh.rig_sha256,
                         first.input_sha256s["p3_rig_sha256"])
        self.assertEqual(self.fixture.motion.run_sha256,
                         first.input_sha256s["motion_run_sha256"])

    def test_result_documents_are_frozen_and_isolated(self):
        result = self.fixture.build()
        copies = (
            result.target_profile, result.motion_instance, result.retarget_run,
            result.retarget_report, result.mesh_regression,
            result.input_sha256s, result.output_sha256s,
        )
        for value in copies:
            value.clear()
        self.assertTrue(result.target_profile)
        self.assertTrue(result.motion_instance)
        self.assertTrue(result.retarget_run)
        self.assertTrue(result.retarget_report)
        self.assertTrue(result.mesh_regression)
        self.assertTrue(result.input_sha256s)
        self.assertTrue(result.output_sha256s)
        with self.assertRaises(FrozenInstanceError):
            result.summary = "changed"  # type: ignore[misc]

    def test_readers_receive_only_the_seven_explicit_address_parts(self):
        with self.fixture.patched_readers() as readers:
            result = self.fixture.build_unpatched()
            mesh_reader, ik_reader, motion_reader = readers
            for reader in readers:
                reader.assert_called_once_with(self.fixture.state)
            mesh_reader.return_value.load.assert_called_once_with(
                *self.fixture.args[:3]
            )
            ik_reader.return_value.load.assert_called_once_with(
                self.fixture.args[0], *self.fixture.args[3:5]
            )
            motion_reader.return_value.load.assert_called_once_with(
                *self.fixture.args[5:]
            )
        self.assertEqual("idle", result.clip_id)
        for forbidden in ("latest", "latest.json", "alias"):
            changed = list(self.fixture.args)
            changed[1] = forbidden
            with self.subTest(forbidden=forbidden), self.assertRaises(
                VerifiedMotionRetargetPipelineError
            ), self.fixture.patched_readers():
                VerifiedMotionRetargetPipeline(self.fixture.state).build(*changed)

    def test_reader_address_and_p3_p4_chain_tamper_fail_closed(self):
        cases = (
            {"mesh": replace(self.fixture.mesh, bundle_sha256="f" * 64)},
            {"ik": replace(self.fixture.ik, p3_bundle_sha256="f" * 64)},
            {"motion": replace(self.fixture.motion, clip_sha256="f" * 64)},
        )
        for values in cases:
            with self.subTest(values=values), self.fixture.patched_readers(
                **values
            ), self.assertRaises(VerifiedMotionRetargetPipelineError):
                self.fixture.build_unpatched()

    def test_rejected_mesh_and_reader_failure_never_return_documents(self):
        rejected = SimpleNamespace(
            document={"status": "rejected", "summary": "attachments=1"},
            sha256="f" * 64,
        )
        with patch(
            "autospine_workbench.motion_retarget_pipeline."
            "build_motion_mesh_regression", return_value=rejected,
        ), self.assertRaisesRegex(
            VerifiedMotionRetargetPipelineError, "mesh regression rejected"
        ):
            self.fixture.build()
        with patch(
            "autospine_workbench.motion_retarget_pipeline."
            "VerifiedMeshBundleReader"
        ) as reader, self.assertRaisesRegex(
            VerifiedMotionRetargetPipelineError, "reader tamper"
        ):
            reader.return_value.load.side_effect = RuntimeError("reader tamper")
            self.fixture.build_unpatched()

    def test_compiler_and_report_tamper_are_revalidated(self):
        target = compile_motion_target_profile(self.fixture.ik, self.fixture.mesh)
        retargeted = compile_motion_instance(self.fixture.motion, target)
        run = deepcopy(retargeted.run)
        run["output"]["instance_sha256"] = "f" * 64
        changed = replace(retargeted, _run_json=json.dumps(
            run, sort_keys=True, separators=(",", ":")
        ))
        with patch(
            "autospine_workbench.motion_retarget_pipeline."
            "compile_motion_instance", return_value=changed,
        ), self.assertRaises(VerifiedMotionRetargetPipelineError):
            self.fixture.build()

        report = build_motion_retarget_report(
            self.fixture.motion, target, retargeted
        )
        document = report.document
        document["contacts"]["preserved_count"] -= 1
        changed_report = replace(report, _canonical_json=json.dumps(
            document, sort_keys=True, separators=(",", ":")
        ))
        with patch(
            "autospine_workbench.motion_retarget_pipeline."
            "build_motion_retarget_report", return_value=changed_report,
        ), self.assertRaises(VerifiedMotionRetargetPipelineError):
            self.fixture.build()


if __name__ == "__main__":
    unittest.main()
