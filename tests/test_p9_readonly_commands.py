"""Filesystem boundary tests for P9 read-only commands."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
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

from autospine_workbench.p9_readonly_commands import (  # noqa: E402
    P9ReadOnlyCommandError,
    compile_heading_evidence_command,
    probe_depth_order_command,
    probe_foot_lock_command,
)
from autospine_workbench.cli import main  # noqa: E402
from tests.projected_motion_bundle_helpers import ProjectedBundleFixture  # noqa: E402


def _snapshot(root: Path):
    return tuple(sorted(
        (
            path.relative_to(root).as_posix(),
            path.is_dir(),
            0 if path.is_dir() else path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in root.rglob("*")
    ))


def _compiled(format_name="autospine-test"):
    return SimpleNamespace(
        sha256="f" * 64,
        document={"format": format_name, "runtime_timeline_emitted": False},
    )


class P9ReadOnlyCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"

    def test_real_cli_command_reads_exact_bundles_without_writes(self):
        fixture = ProjectedBundleFixture(self.root)
        published = fixture.publish()
        before = _snapshot(fixture.state)
        with redirect_stdout(io.StringIO()) as output:
            status = main([
                "compile-kimodo-policy-evidence",
                "--motion-sha256", fixture.p7.clip_sha256,
                "--motion-bundle-sha256", fixture.p7.bundle_sha256,
                "--projected-motion-sha256", published.projected_motion_sha256,
                "--projected-bundle-sha256", published.bundle_sha256,
                "--state-root", str(fixture.state),
            ])
        self.assertEqual(0, status)
        self.assertEqual(before, _snapshot(fixture.state))
        line = output.getvalue().strip()
        result = json.loads(line)
        self.assertEqual(
            json.dumps(result, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, separators=(",", ":")),
            line,
        )
        self.assertEqual(
            "autospine-kimodo-policy-evidence", result["report"]["format"]
        )
        self.assertEqual(2, len(result["input_bundle_paths"]))
        self.assertFalse(result["report"]["policy"]["candidate_emitted"])

    def test_policy_files_are_strict_and_rejected_before_bundle_reads(self):
        bad_values = (
            b'{"format":"a","format":"b"}',
            b'{"maximum":NaN}',
            b"[]",
        )
        for index, raw in enumerate(bad_values):
            path = self.root / f"bad-{index}.json"
            path.write_bytes(raw)
            with self.subTest(index=index), patch(
                "autospine_workbench.p9_readonly_commands."
                "VerifiedMotionBundleReader"
            ) as motion_reader, self.assertRaises(P9ReadOnlyCommandError):
                compile_heading_evidence_command(
                    self.state,
                    path,
                    motion_sha256="1" * 64,
                    motion_bundle_sha256="2" * 64,
                    projected_motion_sha256="3" * 64,
                    projected_bundle_sha256="4" * 64,
                )
            motion_reader.assert_not_called()

    def test_foot_probe_loads_exact_p8_p5_and_passes_raw_thresholds(self):
        p8 = SimpleNamespace(path=self.root / "p8")
        p5 = SimpleNamespace(path=self.root / "p5")
        with patch(
            "autospine_workbench.p9_readonly_commands."
            "VerifiedProjectedMotionBundleReader"
        ) as p8_reader, patch(
            "autospine_workbench.p9_readonly_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as p5_reader, patch(
            "autospine_workbench.p9_readonly_commands."
            "compile_foot_lock_candidates", return_value=_compiled()
        ) as compiler:
            p8_reader.return_value.load.return_value = p8
            p5_reader.return_value.load.return_value = p5
            result = probe_foot_lock_command(
                self.state,
                "sample",
                projected_motion_sha256="1" * 64,
                projected_bundle_sha256="2" * 64,
                motion_instance_sha256="3" * 64,
                motion_retarget_bundle_sha256="4" * 64,
                max_correction_reference_ratio=0.25,
                max_residual_px=3.5,
            )
        p8_reader.return_value.load.assert_called_once_with("1" * 64, "2" * 64)
        p5_reader.return_value.load.assert_called_once_with(
            "sample", "3" * 64, "4" * 64
        )
        compiler.assert_called_once_with(
            p8, p5,
            max_correction_reference_ratio=0.25,
            max_residual_px=3.5,
        )
        self.assertEqual((p8.path, p5.path), result.input_bundle_paths)

    def test_depth_probe_reads_policy_once_and_loads_all_exact_addresses(self):
        policy_path = self.root / "depth-policy.json"
        policy_path.write_text("{}", encoding="utf-8")
        p8 = SimpleNamespace(path=self.root / "p8")
        p5 = SimpleNamespace(path=self.root / "p5")
        p3 = SimpleNamespace(path=self.root / "p3")
        policy = {"format": "autospine-depth-pair-policy"}
        with patch(
            "autospine_workbench.p9_readonly_commands.strict_json_object",
            return_value=policy,
        ) as decode, patch(
            "autospine_workbench.p9_readonly_commands."
            "VerifiedProjectedMotionBundleReader"
        ) as p8_reader, patch(
            "autospine_workbench.p9_readonly_commands."
            "VerifiedMotionRetargetBundleReader"
        ) as p5_reader, patch(
            "autospine_workbench.p9_readonly_commands.VerifiedMeshBundleReader"
        ) as p3_reader, patch(
            "autospine_workbench.p9_readonly_commands."
            "compile_depth_order_candidates", return_value=_compiled()
        ) as compiler:
            p8_reader.return_value.load.return_value = p8
            p5_reader.return_value.load.return_value = p5
            p3_reader.return_value.load.return_value = p3
            result = probe_depth_order_command(
                self.state,
                "sample",
                policy_path,
                projected_motion_sha256="1" * 64,
                projected_bundle_sha256="2" * 64,
                motion_instance_sha256="3" * 64,
                motion_retarget_bundle_sha256="4" * 64,
                p3_rig_sha256="5" * 64,
                p3_bundle_sha256="6" * 64,
            )
        decode.assert_called_once()
        p3_reader.return_value.load.assert_called_once_with(
            "sample", "5" * 64, "6" * 64
        )
        compiler.assert_called_once_with(p8, p5, p3, policy)
        self.assertEqual((p8.path, p5.path, p3.path), result.input_bundle_paths)


if __name__ == "__main__":
    unittest.main()
