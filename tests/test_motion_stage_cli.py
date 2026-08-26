"""Independent parser and dispatch tests for the P5 command surface."""

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

from autospine_workbench.motion_bvh_commands import (  # noqa: E402
    BvhMotionCommandError,
)
from autospine_workbench.motion_kimodo_commands import (  # noqa: E402
    KimodoMotionCommandError,
)
from autospine_workbench.motion_retarget_commands import (  # noqa: E402
    MotionRetargetCommandError,
)
from autospine_workbench.motion_stage_cli import (  # noqa: E402
    add_motion_stage_subcommands,
    dispatch_motion_stage_command,
)


SHA = {
    name: character * 64
    for name, character in (
        ("p3_rig", "1"), ("p3_bundle", "2"),
        ("p4_profile", "3"), ("p4_bundle", "4"),
        ("motion_clip", "5"), ("motion_bundle", "6"),
        ("instance", "7"), ("bundle", "8"),
    )
}


def parser(default: Path) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="p5-test")
    subparsers = result.add_subparsers(dest="command", required=True)
    add_motion_stage_subcommands(subparsers, default)
    return result


def bvh_result() -> SimpleNamespace:
    return SimpleNamespace(
        path=Path("state/motions/clip/bundle"),
        clip_id="fixture.walk",
        map_id="fixture.map-v1",
        raw_bvh_sha256="a" * 64,
        raw_bvh_byte_length=123,
        bvh_map_sha256="b" * 64,
        motion_ir_sha256="c" * 64,
        clip_sha256="c" * 64,
        run_sha256="d" * 64,
        bundle_sha256="e" * 64,
        source_kind="bvh",
        reused=False,
    )


def kimodo_result() -> SimpleNamespace:
    return SimpleNamespace(
        path=Path("state/motions/clip/bundle"),
        clip_id="kimodo.walk",
        source_id="kimodo.source-v1",
        map_id="kimodo.map-v1",
        raw_npz_sha256="1" * 64,
        raw_npz_byte_length=456,
        source_sha256="2" * 64,
        map_sha256="3" * 64,
        array_inventory_sha256="4" * 64,
        motion_ir_sha256="5" * 64,
        clip_sha256="5" * 64,
        run_sha256="6" * 64,
        bundle_sha256="7" * 64,
        source_kind="kimodo_npz",
        reused=False,
    )


def retarget_result() -> SimpleNamespace:
    return SimpleNamespace(
        path=Path("state/builds/project/motion-instances/instance/bundle"),
        project_id="project",
        clip_id="idle",
        source_addresses={key: value for key, value in SHA.items() if key != "instance"},
        target_profile_sha256="9" * 64,
        instance_sha256=SHA["instance"],
        retarget_run_identity_sha256="a" * 64,
        run_sha256="b" * 64,
        report_sha256="c" * 64,
        mesh_regression_sha256="d" * 64,
        bundle_sha256=SHA["bundle"],
        summary="clip=idle;mesh=passed",
        reused=True,
    )


class MotionStageParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.default = Path("default-state")
        self.parser = parser(self.default)

    def test_bvh_arguments_are_typed_and_exact(self) -> None:
        compiled = self.parser.parse_args([
            "compile-bvh-motion", "walk.bvh", "walk-map.json",
        ])
        self.assertEqual(Path("walk.bvh"), compiled.source)
        self.assertEqual(Path("walk-map.json"), compiled.map)
        self.assertEqual(self.default, compiled.state_root)

        verified = self.parser.parse_args([
            "verify-bvh-motion",
            "--clip-sha256", "a" * 64,
            "--bundle-sha256", "b" * 64,
            "--state-root", "other-state",
        ])
        self.assertEqual(Path("other-state"), verified.state_root)

        kimodo = self.parser.parse_args([
            "compile-kimodo-motion", "walk.npz", "walk.source.json",
            "walk.map.json",
        ])
        self.assertEqual(Path("walk.npz"), kimodo.source)
        self.assertEqual(Path("walk.source.json"), kimodo.sidecar)
        self.assertEqual(Path("walk.map.json"), kimodo.map)

    def test_retarget_requires_all_source_and_output_addresses(self) -> None:
        argv = ["compile-motion-retarget", "project", *_retarget_flags()]
        compiled = self.parser.parse_args(argv)
        self.assertEqual("project", compiled.project_id)
        for name in (
            "p3_rig", "p3_bundle", "p4_profile", "p4_bundle",
            "motion_clip", "motion_bundle",
        ):
            self.assertEqual(SHA[name], getattr(compiled, f"{name}_sha256"))

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(["compile-motion-retarget", "project"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args([
                "verify-motion-retarget", "project",
                "--bundle-sha256", SHA["bundle"],
            ])

    def test_verify_commands_have_no_implicit_address_fallback(self) -> None:
        incomplete = (
            ["verify-bvh-motion", "--clip-sha256", "a" * 64],
            ["verify-kimodo-motion", "--clip-sha256", "a" * 64],
            [
                "verify-motion-retarget", "project",
                "--instance-sha256", SHA["instance"],
            ],
        )
        for argv in incomplete:
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit):
                self.parser.parse_args(argv)


class MotionStageDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path("state")
        self.parser = parser(self.state)

    def test_bvh_dispatches_exact_calls_and_prints_every_identity(self) -> None:
        cases = (
            (
                ["compile-bvh-motion", "source.bvh", "map.json"],
                "compile_bvh_motion_bundle",
                (self.state, Path("source.bvh"), Path("map.json")),
            ),
            (
                ["verify-bvh-motion", "--clip-sha256", "c" * 64,
                 "--bundle-sha256", "e" * 64],
                "verify_bvh_motion_bundle",
                (self.state, "c" * 64, "e" * 64),
            ),
        )
        for argv, service_name, expected in cases:
            with self.subTest(argv=argv), patch(
                f"autospine_workbench.motion_stage_cli.{service_name}",
                return_value=bvh_result(),
            ) as service:
                status, response = self._dispatch(argv)
                self.assertEqual(0, status)
                service.assert_called_once_with(*expected)
                self.assertTrue(response["ok"])
                self.assertEqual("passed", response["status"])
                self.assertEqual(set(vars(bvh_result())), set(response) - {"ok", "status"})
                self.assertIsInstance(response["path"], str)

    def test_kimodo_dispatches_compile_verify_and_prints_all_identities(self):
        cases = (
            (
                ["compile-kimodo-motion", "source.npz", "sidecar.json", "map.json"],
                "compile_kimodo_motion_bundle",
                (self.state, Path("source.npz"), Path("sidecar.json"), Path("map.json")),
            ),
            (
                ["verify-kimodo-motion", "--clip-sha256", "5" * 64,
                 "--bundle-sha256", "7" * 64],
                "verify_kimodo_motion_bundle",
                (self.state, "5" * 64, "7" * 64),
            ),
        )
        for argv, service_name, expected in cases:
            with self.subTest(argv=argv), patch(
                f"autospine_workbench.motion_stage_cli.{service_name}",
                return_value=kimodo_result(),
            ) as service:
                status, response = self._dispatch(argv)
                self.assertEqual(0, status)
                service.assert_called_once_with(*expected)
                self.assertEqual(
                    set(vars(kimodo_result())), set(response) - {"ok", "status"}
                )
                self.assertEqual("kimodo_npz", response["source_kind"])

    def test_retarget_dispatches_exact_compile_and_verify_calls(self) -> None:
        with patch(
            "autospine_workbench.motion_stage_cli.compile_motion_retarget_bundle",
            return_value=retarget_result(),
        ) as service:
            status, response = self._dispatch([
                "compile-motion-retarget", "project", *_retarget_flags(),
            ])
            self.assertEqual(0, status)
            service.assert_called_once_with(
                self.state, "project",
                p3_rig_sha256=SHA["p3_rig"],
                p3_bundle_sha256=SHA["p3_bundle"],
                p4_profile_sha256=SHA["p4_profile"],
                p4_bundle_sha256=SHA["p4_bundle"],
                motion_clip_sha256=SHA["motion_clip"],
                motion_bundle_sha256=SHA["motion_bundle"],
            )
            self.assertEqual(set(vars(retarget_result())), set(response) - {"ok", "status"})
            self.assertEqual(retarget_result().source_addresses, response["source_addresses"])

        with patch(
            "autospine_workbench.motion_stage_cli.verify_motion_retarget_bundle",
            return_value=retarget_result(),
        ) as service:
            status, _response = self._dispatch([
                "verify-motion-retarget", "project",
                "--instance-sha256", SHA["instance"],
                "--bundle-sha256", SHA["bundle"],
            ])
            self.assertEqual(0, status)
            service.assert_called_once_with(
                self.state, "project",
                instance_sha256=SHA["instance"], bundle_sha256=SHA["bundle"],
            )

    def test_expected_service_errors_have_stable_json_and_status_two(self) -> None:
        cases = (
            (
                ["compile-bvh-motion", "source.bvh", "map.json"],
                "compile_bvh_motion_bundle", BvhMotionCommandError("bad BVH"),
            ),
            (
                ["compile-motion-retarget", "project", *_retarget_flags()],
                "compile_motion_retarget_bundle",
                MotionRetargetCommandError("bad retarget"),
            ),
            (
                ["compile-kimodo-motion", "source.npz", "sidecar.json", "map.json"],
                "compile_kimodo_motion_bundle",
                KimodoMotionCommandError("bad Kimodo"),
            ),
        )
        for argv, service_name, error in cases:
            with self.subTest(service=service_name), patch(
                f"autospine_workbench.motion_stage_cli.{service_name}",
                side_effect=error,
            ):
                status, response = self._dispatch(argv)
                self.assertEqual(2, status)
                self.assertEqual({
                    "ok": False, "status": "error", "error": str(error),
                }, response)

    def test_unknown_command_is_not_claimed_or_printed(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = dispatch_motion_stage_command(
                argparse.Namespace(command="unrelated")
            )
        self.assertIsNone(status)
        self.assertEqual("", output.getvalue())

    def _dispatch(self, argv: list[str]) -> tuple[int | None, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = dispatch_motion_stage_command(self.parser.parse_args(argv))
        return status, json.loads(output.getvalue())


def _retarget_flags() -> list[str]:
    return [
        "--p3-rig-sha256", SHA["p3_rig"],
        "--p3-bundle-sha256", SHA["p3_bundle"],
        "--p4-profile-sha256", SHA["p4_profile"],
        "--p4-bundle-sha256", SHA["p4_bundle"],
        "--motion-clip-sha256", SHA["motion_clip"],
        "--motion-bundle-sha256", SHA["motion_bundle"],
    ]


if __name__ == "__main__":
    unittest.main()
