"""Parser and canonical dispatch tests for P9 policy commands."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p9_policy_commands import (  # noqa: E402
    P9PolicyCommandResult,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)


def parser():
    value = argparse.ArgumentParser()
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("state"))
    return value


class P9PolicyCliTests(unittest.TestCase):
    def test_both_commands_dispatch_exact_arguments_and_canonical_json(self):
        result = P9PolicyCommandResult(
            input_paths=(Path("a"),), report_sha256="f" * 64,
            report={"format": "autospine-test"},
        )
        cases = (
            (
                ["compile-motion-policy-decision", "--foot-candidates", "f.json",
                 "--depth-candidates", "d.json", "--review-input", "r.json"],
                "compile_motion_policy_decision_command",
            ),
            (
                ["compile-reviewed-motion-policy", "sample",
                 "--foot-candidates", "f.json", "--depth-candidates", "d.json",
                 "--decision", "x.json", "--p3-rig-sha256", "1" * 64,
                 "--p3-bundle-sha256", "2" * 64],
                "compile_reviewed_motion_policy_command",
            ),
        )
        for argv, service_name in cases:
            with self.subTest(command=argv[0]), patch(
                f"autospine_workbench.p9_policy_cli.{service_name}",
                return_value=result,
            ) as service, redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(parser().parse_args(argv))
            self.assertEqual(0, status)
            service.assert_called_once()
            line = output.getvalue().strip()
            payload = json.loads(line)
            self.assertEqual(
                json.dumps(payload, sort_keys=True, separators=(",", ":")), line
            )
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
