"""Canonical CLI and end-to-end publish/verify tests for P9 bundles."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
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

from autospine_workbench.cli import main  # noqa: E402
from autospine_workbench.p9_bundle_commands import (  # noqa: E402
    P9BundleCommandError,
    P9BundleCommandResult,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)
from tests.p9_v2_helpers import tree  # noqa: E402
from tests.reviewed_motion_bundle_helpers import (  # noqa: E402
    ReviewedMotionStorageFixture,
)


SHA = {str(index): str(index) * 64 for index in range(1, 7)}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("state"))
    return value


def publish_argv(*extra: str) -> list[str]:
    return [
        "publish-reviewed-motion-bundle", "sample",
        "--foot-candidates", "foot.json",
        "--depth-candidates", "depth.json",
        "--decision", "decision.json",
        "--reviewed-policy", "policy.json",
        "--p3-rig-sha256", SHA["1"],
        "--p3-bundle-sha256", SHA["2"],
        "--motion-instance-sha256", SHA["3"],
        "--motion-retarget-bundle-sha256", SHA["4"],
        *extra,
    ]


def verify_argv(*extra: str) -> list[str]:
    return [
        "verify-reviewed-motion-bundle", "sample",
        "--motion-instance-v2-sha256", SHA["5"],
        "--reviewed-motion-bundle-sha256", SHA["6"],
        *extra,
    ]


def result() -> P9BundleCommandResult:
    report = {
        "format": "autospine-reviewed-motion-test",
        "format_version": 1,
        "address": {"bundle_sha256": SHA["6"]},
    }
    return P9BundleCommandResult(
        input_paths=(Path("input.json"),),
        output_path=Path("bundle") / SHA["6"],
        reused=False,
        report_sha256="f" * 64,
        report=report,
    )


class P9BundleCliDispatchTests(unittest.TestCase):
    def test_both_commands_dispatch_exact_addresses(self):
        cases = (
            (
                publish_argv(), "publish_reviewed_motion_bundle_command",
                (
                    Path("state"), "sample", Path("foot.json"),
                    Path("depth.json"), Path("decision.json"),
                    Path("policy.json"),
                ),
                {
                    "p3_rig_sha256": SHA["1"],
                    "p3_bundle_sha256": SHA["2"],
                    "motion_instance_sha256": SHA["3"],
                    "motion_retarget_bundle_sha256": SHA["4"],
                },
            ),
            (
                verify_argv(), "verify_reviewed_motion_bundle_command",
                (Path("state"), "sample"),
                {
                    "motion_instance_v2_sha256": SHA["5"],
                    "reviewed_motion_bundle_sha256": SHA["6"],
                },
            ),
        )
        for argv, service_name, positional, keywords in cases:
            with self.subTest(command=argv[0]), patch(
                f"autospine_workbench.p9_bundle_cli.{service_name}",
                return_value=result(),
            ) as service, redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    parser().parse_args(argv)
                )
            self.assertEqual(0, status)
            service.assert_called_once_with(*positional, **keywords)
            line = output.getvalue().strip()
            self.assertEqual(
                json.dumps(
                    json.loads(line), ensure_ascii=False, allow_nan=False,
                    sort_keys=True, separators=(",", ":"),
                ),
                line,
            )
            self.assertTrue(json.loads(line)["ok"])

    def test_document_only_has_report_address_and_no_paths(self):
        for argv, service_name in (
            (publish_argv("--document-only"),
             "publish_reviewed_motion_bundle_command"),
            (verify_argv("--document-only"),
             "verify_reviewed_motion_bundle_command"),
        ):
            with self.subTest(command=argv[0]), patch(
                f"autospine_workbench.p9_bundle_cli.{service_name}",
                return_value=result(),
            ), redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    parser().parse_args(argv)
                )
            line = output.getvalue().strip()
            self.assertEqual(0, status)
            self.assertEqual(result().report, json.loads(line))
            self.assertNotIn("input", line)
            self.assertNotIn("bundle/", line)

    def test_domain_error_is_canonical_and_returns_two(self):
        with patch(
            "autospine_workbench.p9_bundle_cli."
            "publish_reviewed_motion_bundle_command",
            side_effect=P9BundleCommandError("broken"),
        ), redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                parser().parse_args(publish_argv())
            )
        self.assertEqual(2, status)
        self.assertEqual(
            {"error": "broken", "ok": False, "status": "error"},
            json.loads(output.getvalue()),
        )


class P9BundleIntegratedCliTests(unittest.TestCase):
    def test_publish_then_verify_document_only_is_canonical_and_zero_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = ReviewedMotionStorageFixture(root)
            names = ("foot", "depth", "decision", "policy")
            paths = []
            for name, document in zip(names, fixture.documents[:4], strict=True):
                path = root / f"{name}.json"
                path.write_text(json.dumps(
                    document, ensure_ascii=False, allow_nan=False,
                    sort_keys=True, separators=(",", ":"),
                ), encoding="utf-8")
                paths.append(path)
            publish = [
                "publish-reviewed-motion-bundle", fixture.mesh.project_id,
                "--foot-candidates", str(paths[0]),
                "--depth-candidates", str(paths[1]),
                "--decision", str(paths[2]),
                "--reviewed-policy", str(paths[3]),
                "--p3-rig-sha256", fixture.mesh.rig_sha256,
                "--p3-bundle-sha256", fixture.mesh.bundle_sha256,
                "--motion-instance-sha256", fixture.retarget.instance_sha256,
                "--motion-retarget-bundle-sha256",
                fixture.retarget.bundle_sha256,
                "--state-root", str(fixture.state_root), "--document-only",
            ]
            with patch(
                "autospine_workbench.p9_bundle_commands."
                "VerifiedMeshBundleReader"
            ) as mesh_reader, patch(
                "autospine_workbench.p9_bundle_commands."
                "VerifiedMotionRetargetBundleReader"
            ) as p5_reader, redirect_stdout(io.StringIO()) as output:
                mesh_reader.return_value.load.return_value = fixture.mesh
                p5_reader.return_value.load.return_value = fixture.retarget
                self.assertEqual(0, main(publish))
            publication = json.loads(output.getvalue())
            line = output.getvalue().strip()
            self.assertEqual(
                json.dumps(publication, sort_keys=True, separators=(",", ":")),
                line,
            )
            before = tree(fixture.state_root)
            address = publication["address"]
            verify = [
                "verify-reviewed-motion-bundle", fixture.mesh.project_id,
                "--motion-instance-v2-sha256",
                address["motion_instance_v2_sha256"],
                "--reviewed-motion-bundle-sha256", address["bundle_sha256"],
                "--state-root", str(fixture.state_root), "--document-only",
            ]
            with patch(
                "autospine_workbench.reviewed_motion_bundle_reader."
                "VerifiedMeshBundleReader"
            ) as mesh_reader, patch(
                "autospine_workbench.reviewed_motion_bundle_reader."
                "VerifiedMotionRetargetBundleReader"
            ) as p5_reader, redirect_stdout(io.StringIO()) as output:
                mesh_reader.return_value.load.return_value = fixture.mesh
                p5_reader.return_value.load.return_value = fixture.retarget
                self.assertEqual(0, main(verify))
            self.assertEqual(before, tree(fixture.state_root))
            verification = json.loads(output.getvalue())
            self.assertEqual(address, verification["address"])
            self.assertNotIn("path", output.getvalue())


if __name__ == "__main__":
    unittest.main()
