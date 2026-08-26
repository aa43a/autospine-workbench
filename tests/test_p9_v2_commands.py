"""Read-only command service tests for MotionInstance and Spine v2."""

from __future__ import annotations

from copy import deepcopy
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

from autospine_workbench.p9_v2_commands import (  # noqa: E402
    P9V2CommandError,
    compile_motion_instance_v2_command,
    export_spine42_v2_command,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.p9_v2_helpers import P9V2Fixture, tree  # noqa: E402


class P9V2CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = P9V2Fixture(Path(temporary.name))

    def compile(self):
        with patch(
            "autospine_workbench.p9_v2_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as reader:
            reader.return_value.load.return_value = self.fixture.p5
            before = tree(self.fixture.state)
            result = compile_motion_instance_v2_command(
                self.fixture.state,
                self.fixture.project_id,
                self.fixture.policy_path,
                motion_instance_sha256=self.fixture.p5.instance_sha256,
                motion_retarget_bundle_sha256=self.fixture.p5.bundle_sha256,
            )
            self.assertEqual(before, tree(self.fixture.state))
        reader.return_value.load.assert_called_once_with(
            self.fixture.project_id,
            self.fixture.p5.instance_sha256,
            self.fixture.p5.bundle_sha256,
        )
        return result

    def export(self):
        with patch(
            "autospine_workbench.p9_v2_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as p5_reader, patch(
            "autospine_workbench.p9_v2_commands.VerifiedMeshSourceReader"
        ) as p3_reader:
            p5_reader.return_value.load.return_value = self.fixture.p5
            p3_reader.return_value.load.return_value = self.fixture.mesh
            before = tree(self.fixture.state)
            result = export_spine42_v2_command(
                self.fixture.state,
                self.fixture.project_id,
                self.fixture.policy_path,
                p3_rig_sha256=self.fixture.mesh.p3_rig_sha256,
                p3_bundle_sha256=self.fixture.mesh.p3_bundle_sha256,
                motion_instance_sha256=self.fixture.p5.instance_sha256,
                motion_retarget_bundle_sha256=self.fixture.p5.bundle_sha256,
            )
            self.assertEqual(before, tree(self.fixture.state))
        p3_reader.return_value.load.assert_called_once_with(
            self.fixture.project_id,
            self.fixture.mesh.p3_rig_sha256,
            self.fixture.mesh.p3_bundle_sha256,
        )
        return result

    def test_compile_returns_canonical_v2_without_writing_state(self) -> None:
        result = self.compile()
        self.assertEqual("autospine-motion-instance", result.report["format"])
        self.assertEqual(2, result.report["format_version"])
        self.assertEqual(result.report_sha256, canonical_sha256(result.report))
        self.assertEqual(2, len(result.input_paths))

    def test_export_contains_text_and_hashes_but_no_binary_png(self) -> None:
        result = self.export()
        report = result.report
        self.assertEqual(
            "autospine-spine42-v2-readonly-export", report["format"]
        )
        self.assertEqual("2.0.0", report["adapter_profile"]["adapter"]["version"])
        self.assertIn("drawOrder", next(iter(
            report["skeleton_json"]["animations"].values()
        )))
        self.assertTrue(report["atlas_text"].startswith("skeleton.png\n"))
        self.assertEqual(64, len(report["png_sha256"]))
        self.assertEqual(64, len(report["atlas_sha256"]))
        self.assertEqual(result.report_sha256, canonical_sha256(report))
        encoded = json.dumps(report, allow_nan=False)
        self.assertNotIn("png_bytes", encoded)
        self.assertFalse(_contains_bytes(report))

    def test_duplicate_nonfinite_and_stale_policy_fail_closed(self) -> None:
        for name, raw in (
            ("duplicate.json", b'{"format":"a","format":"b"}'),
            ("nonfinite.json", b'{"value":NaN}'),
        ):
            path = self.fixture.root / name
            path.write_bytes(raw)
            with self.subTest(name=name), patch(
                "autospine_workbench.p9_v2_commands."
                "VerifiedMotionRetargetBundleReader"
            ) as reader, self.assertRaises(P9V2CommandError):
                compile_motion_instance_v2_command(
                    self.fixture.state,
                    self.fixture.project_id,
                    path,
                    motion_instance_sha256=self.fixture.p5.instance_sha256,
                    motion_retarget_bundle_sha256=self.fixture.p5.bundle_sha256,
                )
            reader.assert_not_called()

        changed = deepcopy(self.fixture.policy)
        changed["source"]["p5"]["bundle_sha256"] = "f" * 64
        path = self.fixture.root / "stale.json"
        path.write_text(json.dumps(changed), encoding="utf-8")
        with patch(
            "autospine_workbench.p9_v2_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as reader, self.assertRaisesRegex(P9V2CommandError, "source chain"):
            reader.return_value.load.return_value = self.fixture.p5
            compile_motion_instance_v2_command(
                self.fixture.state,
                self.fixture.project_id,
                path,
                motion_instance_sha256=self.fixture.p5.instance_sha256,
                motion_retarget_bundle_sha256=self.fixture.p5.bundle_sha256,
            )

    def test_explicit_p3_must_match_reviewed_policy(self) -> None:
        changed = deepcopy(self.fixture.mesh)
        changed.p3_bundle_sha256 = "f" * 64
        with patch(
            "autospine_workbench.p9_v2_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as p5_reader, patch(
            "autospine_workbench.p9_v2_commands.VerifiedMeshSourceReader"
        ) as p3_reader, self.assertRaisesRegex(P9V2CommandError, "P3 bundle"):
            p5_reader.return_value.load.return_value = self.fixture.p5
            p3_reader.return_value.load.return_value = changed
            export_spine42_v2_command(
                self.fixture.state,
                self.fixture.project_id,
                self.fixture.policy_path,
                p3_rig_sha256="1" * 64,
                p3_bundle_sha256="2" * 64,
                motion_instance_sha256=self.fixture.p5.instance_sha256,
                motion_retarget_bundle_sha256=self.fixture.p5.bundle_sha256,
            )


def _contains_bytes(value) -> bool:
    if isinstance(value, bytes):
        return True
    if isinstance(value, dict):
        return any(_contains_bytes(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_bytes(item) for item in value)
    return False


if __name__ == "__main__":
    unittest.main()
