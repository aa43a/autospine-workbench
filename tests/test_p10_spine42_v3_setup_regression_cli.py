"""P10.7c CLI registration, exit status, and redaction tests."""

from __future__ import annotations

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

from autospine_workbench.cli import build_parser  # noqa: E402
import autospine_workbench.p10_spine42_v3_setup_regression_cli as module  # noqa: E402
from autospine_workbench.p10_spine42_v3_setup_regression_commands import (  # noqa: E402
    P10Spine42V3SetupRegressionCommandError,
)


class P10Spine42V3SetupRegressionCliTests(unittest.TestCase):
    def args(self):
        return build_parser().parse_args([
            module.COMMAND,
            "--manifest", "request.json",
            "--p6-export-contract", "p6.json",
            "--runtime-golden-contract", "runtime.json",
            "--state-root", "state",
        ])

    def dispatch(self, result=None, error=None):
        output = io.StringIO()
        effect = error if error is not None else None
        with patch.object(
            module, "compare_body_sway_spine42_v3_setup_command",
            return_value=result, side_effect=effect,
        ), patch("sys.stdout", output):
            status = module.dispatch_p10_spine42_v3_setup_regression_command(
                self.args()
            )
        return status, json.loads(output.getvalue())

    def test_parser_registers_all_explicit_inputs(self):
        args = self.args()
        self.assertEqual(module.COMMAND, args.command)
        self.assertEqual(Path("request.json"), args.manifest)
        self.assertEqual(Path("p6.json"), args.p6_export_contract)
        self.assertEqual(Path("runtime.json"), args.runtime_golden_contract)

    def test_pass_and_valid_rejection_have_distinct_exit_codes(self):
        for result_status, expected_exit in (("passed", 0), ("rejected", 1)):
            with self.subTest(status=result_status):
                result = SimpleNamespace(
                    status=result_status,
                    request_sha256="a" * 64,
                    report_sha256="b" * 64,
                    document={"status": result_status},
                )
                status, payload = self.dispatch(result=result)
                self.assertEqual(expected_exit, status)
                self.assertEqual(result_status, payload["status"])
                self.assertEqual(result_status == "passed", payload["ok"])

    def test_internal_failure_is_fixed_and_path_free(self):
        status, payload = self.dispatch(error=
            P10Spine42V3SetupRegressionCommandError("secret C:/state"))
        self.assertEqual(2, status)
        self.assertEqual(module.ERROR_CODE, payload["error_code"])
        self.assertNotIn("secret", json.dumps(payload))
        self.assertNotIn("C:/state", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
