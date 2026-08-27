"""Parser and dispatch tests for the isolated P8 CLI surface."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)


def parser(default: Path) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="p8-test")
    subparsers = result.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, default)
    return result


def result() -> SimpleNamespace:
    return SimpleNamespace(**{
        "path": Path("state/projected-motions/projected/bundle"),
        "clip_id": "kimodo.walk",
        "camera_id": "front-v1",
        "depth_positive": "away_from_camera",
        "projected_motion_sha256": "1" * 64,
        "camera_sha256": "2" * 64,
        "run_sha256": "3" * 64,
        "legacy_motion_sha256": "4" * 64,
        "bundle_sha256": "5" * 64,
        "p7_motion_sha256": "4" * 64,
        "p7_bundle_sha256": "6" * 64,
        "p7_run_sha256": "7" * 64,
        "collapsed_sample_count": 0,
        "minimum_foreshortening_ratio": 0.5,
        "maximum_foreshortening_ratio": 1.0,
        "reused": False,
    })


class ProjectionStageCliTests(unittest.TestCase):
    def setUp(self):
        self.state = Path("state")
        self.parser = parser(self.state)

    def test_parser_requires_all_exact_addresses(self):
        compiled = self.parser.parse_args([
            "compile-projected-motion", "camera.json",
            "--motion-clip-sha256", "a" * 64,
            "--motion-bundle-sha256", "b" * 64,
        ])
        self.assertEqual(Path("camera.json"), compiled.camera)
        self.assertEqual(self.state, compiled.state_root)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args([
                "verify-projected-motion",
                "--projected-motion-sha256", "c" * 64,
            ])
        probed = self.parser.parse_args([
            "probe-projected-scale", "sample",
            "--projected-motion-sha256", "1" * 64,
            "--projected-bundle-sha256", "2" * 64,
            "--motion-instance-sha256", "3" * 64,
            "--motion-retarget-bundle-sha256", "4" * 64,
        ])
        self.assertEqual("sample", probed.project_id)
        self.assertEqual(self.state, probed.state_root)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args([
                "probe-projected-scale", "sample",
                "--projected-motion-sha256", "1" * 64,
                "--projected-bundle-sha256", "2" * 64,
                "--motion-instance-sha256", "3" * 64,
            ])

    def test_compile_and_verify_dispatch_exact_calls(self):
        cases = (
            (
                [
                    "compile-projected-motion", "camera.json",
                    "--motion-clip-sha256", "a" * 64,
                    "--motion-bundle-sha256", "b" * 64,
                ],
                "compile_projected_motion_bundle",
                (self.state, Path("camera.json")),
                {
                    "motion_clip_sha256": "a" * 64,
                    "motion_bundle_sha256": "b" * 64,
                },
            ),
            (
                [
                    "verify-projected-motion",
                    "--projected-motion-sha256", "1" * 64,
                    "--bundle-sha256", "5" * 64,
                ],
                "verify_projected_motion_bundle",
                (self.state, "1" * 64, "5" * 64),
                {},
            ),
        )
        for argv, service_name, positional, keywords in cases:
            with self.subTest(argv=argv), patch(
                f"autospine_workbench.projection_stage_cli.{service_name}",
                return_value=result(),
            ) as service, redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args(argv)
                )
            self.assertEqual(0, status)
            service.assert_called_once_with(*positional, **keywords)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(str(result().path), payload["path"])
            self.assertEqual(set(vars(result())), set(payload) - {"ok", "status"})

    def test_unrelated_command_is_ignored(self):
        self.assertIsNone(dispatch_projection_stage_command(
            argparse.Namespace(command="other")
        ))

    def test_probe_dispatch_serializes_all_paths_and_complete_report(self):
        argv = [
            "probe-projected-scale", "sample",
            "--projected-motion-sha256", "1" * 64,
            "--projected-bundle-sha256", "2" * 64,
            "--motion-instance-sha256", "3" * 64,
            "--motion-retarget-bundle-sha256", "4" * 64,
        ]
        probe_result = SimpleNamespace(
            projected_bundle_path=Path("state/projected/input"),
            motion_retarget_bundle_path=Path("state/retarget/input"),
            report_sha256="5" * 64,
            report={
                "format": "autospine-projected-scale-probes",
                "policy": {"runtime_timeline_emitted": False},
                "debug": {"nested_path": Path("evidence/input.json")},
            },
        )
        with patch(
            "autospine_workbench.projection_stage_cli.probe_projected_scale",
            return_value=probe_result,
        ) as service, redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args(argv)
            )
        self.assertEqual(0, status)
        service.assert_called_once_with(
            self.state,
            "sample",
            projected_motion_sha256="1" * 64,
            projected_bundle_sha256="2" * 64,
            motion_instance_sha256="3" * 64,
            motion_retarget_bundle_sha256="4" * 64,
        )
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(str(probe_result.projected_bundle_path),
                         payload["projected_bundle_path"])
        self.assertEqual(str(probe_result.motion_retarget_bundle_path),
                         payload["motion_retarget_bundle_path"])
        self.assertEqual(str(Path("evidence/input.json")),
                         payload["report"]["debug"]["nested_path"])
        self.assertFalse(
            payload["report"]["policy"]["runtime_timeline_emitted"]
        )

    def test_seam_candidate_command_is_registered_and_dispatched(self):
        argv = [
            "compile-seam-anchor-candidates", "sample",
            "--layer-manifest-sha256", "1" * 64,
            "--p3-rig-sha256", "2" * 64,
            "--p3-bundle-sha256", "3" * 64,
        ]
        parsed = self.parser.parse_args(argv)
        self.assertEqual(self.state, parsed.state_root)
        with patch(
            "autospine_workbench.projection_stage_cli."
            "dispatch_seam_anchor_candidate_command",
            return_value=0,
        ) as dispatch:
            status = dispatch_projection_stage_command(parsed)
        self.assertEqual(0, status)
        dispatch.assert_called_once_with(parsed)


if __name__ == "__main__":
    unittest.main()
