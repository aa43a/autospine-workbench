"""Root CLI wiring for the exact-address P5 command surface."""

from __future__ import annotations

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

from autospine_workbench.cli import build_parser, main  # noqa: E402
from tests.test_bvh_motion_compile_run import RAW, mapping  # noqa: E402


class P5CliWiringTests(unittest.TestCase):
    def test_root_parser_registers_all_four_p5_commands(self) -> None:
        cases = (
            ["compile-bvh-motion", "source.bvh", "map.json"],
            [
                "verify-bvh-motion", "--clip-sha256", "a" * 64,
                "--bundle-sha256", "b" * 64,
            ],
            [
                "compile-motion-retarget", "project",
                "--p3-rig-sha256", "1" * 64,
                "--p3-bundle-sha256", "2" * 64,
                "--p4-profile-sha256", "3" * 64,
                "--p4-bundle-sha256", "4" * 64,
                "--motion-clip-sha256", "5" * 64,
                "--motion-bundle-sha256", "6" * 64,
            ],
            [
                "verify-motion-retarget", "project",
                "--instance-sha256", "7" * 64,
                "--bundle-sha256", "8" * 64,
            ],
        )
        for argv in cases:
            with self.subTest(command=argv[0]):
                self.assertEqual(argv[0], build_parser().parse_args(argv).command)

    def test_root_main_delegates_one_parsed_namespace(self) -> None:
        argv = [
            "verify-motion-retarget", "project",
            "--instance-sha256", "7" * 64,
            "--bundle-sha256", "8" * 64,
        ]
        with patch(
            "autospine_workbench.cli._dispatch_motion_stage", return_value=23,
        ) as dispatch:
            self.assertEqual(23, main(argv))
        args = dispatch.call_args.args[0]
        self.assertEqual("verify-motion-retarget", args.command)
        self.assertEqual("project", args.project_id)

    def test_root_cli_compiles_and_read_only_verifies_real_bvh_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, map_path, state = (
                root / "source.bvh", root / "map.json", root / "state"
            )
            source.write_bytes(RAW)
            map_path.write_text(json.dumps(mapping()), encoding="utf-8")
            compiled = self._run([
                "compile-bvh-motion", str(source), str(map_path),
                "--state-root", str(state),
            ])
            verified = self._run([
                "verify-bvh-motion",
                "--clip-sha256", compiled["clip_sha256"],
                "--bundle-sha256", compiled["bundle_sha256"],
                "--state-root", str(state),
            ])
            self.assertFalse(compiled["reused"])
            self.assertIsNone(verified["reused"])
            for field in (
                "clip_id", "map_id", "raw_bvh_sha256", "bvh_map_sha256",
                "motion_ir_sha256", "clip_sha256", "run_sha256",
                "bundle_sha256", "source_kind",
            ):
                self.assertEqual(compiled[field], verified[field])

    def _run(self, argv: list[str]) -> dict:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(argv))
        return json.loads(output.getvalue())


if __name__ == "__main__":
    unittest.main()
