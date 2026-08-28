"""Parser and redacted CLI tests for real Kimodo pilot intake."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.kimodo_pilot_intake_cli import (
    COMMAND,
    ERROR_CODE,
    add_kimodo_pilot_intake_subcommands,
    dispatch_kimodo_pilot_intake_command,
)
from autospine_workbench.kimodo_pilot_intake_commands import (
    KimodoPilotIntakeCommandError,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="intake-test")
    add_kimodo_pilot_intake_subcommands(value.add_subparsers(dest="command"))
    return value


def arguments() -> argparse.Namespace:
    return parser().parse_args([
        COMMAND,
        r"C:\private\motion.npz",
        r"C:\private\source.json",
        r"C:\private\map.json",
        r"C:\private\camera.json",
        "--checkpoint-manifest", r"C:\private\checkpoint.manifest",
        "--generation-request", r"C:\private\request.json",
    ])


class KimodoPilotIntakeCliTests(unittest.TestCase):
    def test_parser_exposes_every_explicit_input_without_state_root(self) -> None:
        parsed = arguments()
        self.assertEqual(COMMAND, parsed.command)
        self.assertEqual(Path(r"C:\private\motion.npz"), parsed.raw_npz)
        self.assertFalse(hasattr(parsed, "state_root"))
        self.assertFalse(parsed.document_only)

    @patch(
        "autospine_workbench.kimodo_pilot_intake_cli."
        "audit_kimodo_pilot_intake_command"
    )
    def test_success_is_canonical_and_document_only_is_supported(
        self, audit: Mock,
    ) -> None:
        audit.return_value = Mock(document={"status": "eligible_for_p7_p8_compile"})
        parsed = arguments()
        output = io.StringIO()
        with patch("sys.stdout", output):
            self.assertEqual(0, dispatch_kimodo_pilot_intake_command(parsed))
        self.assertEqual({
            "intake": {"status": "eligible_for_p7_p8_compile"},
            "mode": "audited",
            "ok": True,
        }, json.loads(output.getvalue()))
        parsed.document_only = True
        output = io.StringIO()
        with patch("sys.stdout", output):
            self.assertEqual(0, dispatch_kimodo_pilot_intake_command(parsed))
        self.assertEqual(
            {"status": "eligible_for_p7_p8_compile"},
            json.loads(output.getvalue()),
        )

    @patch(
        "autospine_workbench.kimodo_pilot_intake_cli."
        "audit_kimodo_pilot_intake_command"
    )
    def test_failures_are_fixed_and_path_free(self, audit: Mock) -> None:
        audit.side_effect = KimodoPilotIntakeCommandError(
            r"failed at C:\private\motion.npz"
        )
        output = io.StringIO()
        with patch("sys.stdout", output):
            self.assertEqual(2, dispatch_kimodo_pilot_intake_command(arguments()))
        response = json.loads(output.getvalue())
        self.assertEqual(ERROR_CODE, response["error_code"])
        self.assertNotIn("private", output.getvalue())

    def test_unrelated_command_is_not_consumed(self) -> None:
        self.assertIsNone(dispatch_kimodo_pilot_intake_command(
            argparse.Namespace(command="serve")
        ))


if __name__ == "__main__":
    unittest.main()
