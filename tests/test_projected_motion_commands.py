"""Filesystem command-boundary tests for P8 projected-motion bundles."""

from __future__ import annotations

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

from autospine_workbench.projected_motion_commands import (  # noqa: E402
    ProjectedMotionCommandError,
    compile_projected_motion_bundle,
    probe_projected_scale,
    verify_projected_motion_bundle,
)
from autospine_workbench.projected_motion_bundle_reader import (  # noqa: E402
    VerifiedProjectedMotionBundleReaderError,
)
from autospine_workbench.motion_retarget_bundle_reader import (  # noqa: E402
    VerifiedMotionRetargetBundleReaderError,
)
from autospine_workbench.projected_scale_probe import (  # noqa: E402
    ProjectedScaleProbeError,
)
from autospine_workbench.safe_input_files import read_real_file  # noqa: E402
from tests.projected_motion_bundle_helpers import (  # noqa: E402
    ProjectedBundleFixture,
)


class ProjectedMotionCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = ProjectedBundleFixture(self.root)
        self.camera_path = self.root / "camera.json"
        self.camera_path.write_text(
            json.dumps(self.fixture.camera), encoding="utf-8"
        )

    def compile(self):
        return compile_projected_motion_bundle(
            self.fixture.state,
            self.camera_path,
            motion_clip_sha256=self.fixture.p7.clip_sha256,
            motion_bundle_sha256=self.fixture.p7.bundle_sha256,
        )

    def test_compile_reads_camera_once_and_reuses_exact_bundle(self):
        calls = []

        def tracked(path, maximum, label):
            calls.append((Path(path), maximum, label))
            return read_real_file(path, maximum, label)

        with patch(
            "autospine_workbench.projected_motion_commands.read_real_file",
            side_effect=tracked,
        ):
            first = self.compile()
        second = self.compile()
        self.assertEqual(1, len(calls))
        self.assertEqual(self.camera_path, calls[0][0])
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual(self.fixture.p7.clip_sha256,
                         first.p7_motion_sha256)
        self.assertEqual(self.fixture.p7.bundle_sha256,
                         first.p7_bundle_sha256)
        self.assertEqual(0, first.collapsed_sample_count)
        self.assertEqual(1.0, first.minimum_foreshortening_ratio)

    def test_verify_is_read_only_and_requires_two_exact_addresses(self):
        compiled = self.compile()
        before = sorted(
            path.relative_to(self.fixture.state)
            for path in self.fixture.state.rglob("*")
        )
        verified = verify_projected_motion_bundle(
            self.fixture.state,
            compiled.projected_motion_sha256,
            compiled.bundle_sha256,
        )
        after = sorted(
            path.relative_to(self.fixture.state)
            for path in self.fixture.state.rglob("*")
        )
        self.assertEqual(before, after)
        self.assertIsNone(verified.reused)
        self.assertEqual(compiled.bundle_sha256, verified.bundle_sha256)
        with self.assertRaises(ProjectedMotionCommandError):
            verify_projected_motion_bundle(
                self.fixture.state, "A" * 64, compiled.bundle_sha256
            )

    def test_malformed_camera_creates_no_projected_namespace(self):
        namespace = self.fixture.state / "projected-motions"
        for index, data in enumerate((
            b'{"format":"x","format":"y"}',
            b'{"format_version":NaN}',
            b"[]",
            b"\xff",
        )):
            path = self.root / f"bad-{index}.json"
            path.write_bytes(data)
            with self.subTest(index=index), self.assertRaises(
                ProjectedMotionCommandError
            ):
                compile_projected_motion_bundle(
                    self.fixture.state,
                    path,
                    motion_clip_sha256=self.fixture.p7.clip_sha256,
                    motion_bundle_sha256=self.fixture.p7.bundle_sha256,
                )
            self.assertFalse(namespace.exists())

    def test_scale_probe_loads_two_exact_bundles_and_never_publishes(self):
        projected = SimpleNamespace(path=self.root / "projected-input")
        retarget = SimpleNamespace(
            path=self.root / "retarget-input",
            target_profile={"project_id": "sample"},
        )
        report = SimpleNamespace(
            sha256="d" * 64,
            document={
                "format": "autospine-projected-scale-probes",
                "policy": {"runtime_timeline_emitted": False},
            },
        )
        before = sorted(self.fixture.state.rglob("*"))
        with patch(
            "autospine_workbench.projected_motion_commands."
            "VerifiedProjectedMotionBundleReader"
        ) as projected_reader, patch(
            "autospine_workbench.projected_motion_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as retarget_reader, patch(
            "autospine_workbench.projected_motion_commands."
            "compile_projected_scale_probes", return_value=report
        ) as compiler, patch(
            "autospine_workbench.projected_motion_commands."
            "ProjectedMotionBundleStore"
        ) as store:
            projected_reader.return_value.load.return_value = projected
            retarget_reader.return_value.load.return_value = retarget
            result = probe_projected_scale(
                self.fixture.state,
                "sample",
                projected_motion_sha256="1" * 64,
                projected_bundle_sha256="2" * 64,
                motion_instance_sha256="3" * 64,
                motion_retarget_bundle_sha256="4" * 64,
            )
        projected_reader.assert_called_once_with(self.fixture.state)
        projected_reader.return_value.load.assert_called_once_with(
            "1" * 64, "2" * 64
        )
        retarget_reader.assert_called_once_with(self.fixture.state)
        retarget_reader.return_value.load.assert_called_once_with(
            "sample", "3" * 64, "4" * 64
        )
        compiler.assert_called_once_with(projected, retarget.target_profile)
        store.assert_not_called()
        self.assertEqual(before, sorted(self.fixture.state.rglob("*")))
        self.assertEqual(projected.path, result.projected_bundle_path)
        self.assertEqual(retarget.path, result.motion_retarget_bundle_path)
        self.assertEqual(report.sha256, result.report_sha256)
        self.assertEqual(report.document, result.report)

    def test_scale_probe_fails_closed_on_reader_or_compiler_error(self):
        cases = (
            ("projected", VerifiedProjectedMotionBundleReaderError("bad")),
            ("retarget", VerifiedMotionRetargetBundleReaderError("bad")),
            ("compiler", ProjectedScaleProbeError("collapsed")),
        )
        for stage, failure in cases:
            projected = SimpleNamespace(path=self.root / "projected")
            retarget = SimpleNamespace(
                path=self.root / "retarget", target_profile={}
            )
            with self.subTest(stage=stage), patch(
                "autospine_workbench.projected_motion_commands."
                "VerifiedProjectedMotionBundleReader"
            ) as projected_reader, patch(
                "autospine_workbench.projected_motion_commands."
                "VerifiedMotionRetargetBundleReader"
            ) as retarget_reader, patch(
                "autospine_workbench.projected_motion_commands."
                "compile_projected_scale_probes"
            ) as compiler, self.assertRaisesRegex(
                ProjectedMotionCommandError, "Projected scale probe failed"
            ):
                projected_reader.return_value.load.return_value = projected
                retarget_reader.return_value.load.return_value = retarget
                if stage == "projected":
                    projected_reader.return_value.load.side_effect = failure
                elif stage == "retarget":
                    retarget_reader.return_value.load.side_effect = failure
                else:
                    compiler.side_effect = failure
                probe_projected_scale(
                    self.fixture.state,
                    "sample",
                    projected_motion_sha256="1" * 64,
                    projected_bundle_sha256="2" * 64,
                    motion_instance_sha256="3" * 64,
                    motion_retarget_bundle_sha256="4" * 64,
                )


if __name__ == "__main__":
    unittest.main()
