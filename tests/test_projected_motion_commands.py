"""Filesystem command-boundary tests for P8 projected-motion bundles."""

from __future__ import annotations

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

from autospine_workbench.projected_motion_commands import (  # noqa: E402
    ProjectedMotionCommandError,
    compile_projected_motion_bundle,
    verify_projected_motion_bundle,
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


if __name__ == "__main__":
    unittest.main()
