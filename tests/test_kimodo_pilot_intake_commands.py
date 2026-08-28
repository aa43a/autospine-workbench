"""Filesystem boundary tests for the zero-write Kimodo pilot audit."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_pilot_intake_commands import (  # noqa: E402
    KimodoPilotIntakeCommandError,
    audit_kimodo_pilot_intake_command,
)
from autospine_workbench.motion_kimodo_commands import (  # noqa: E402
    compile_kimodo_motion_bundle,
)
from autospine_workbench.safe_input_files import read_real_file  # noqa: E402
from tests.kimodo_pilot_intake_helpers import KimodoPilotInputs  # noqa: E402


class KimodoPilotIntakeCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.inputs = KimodoPilotInputs()
        self.paths = self.inputs.write(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_reads_each_input_once_returns_isolated_report_and_writes_nothing(self):
        calls: list[Path] = []

        def tracked(path, maximum, label):
            calls.append(Path(path))
            return read_real_file(path, maximum, label)

        before = self._snapshot()
        with patch(
            "autospine_workbench.kimodo_pilot_intake_commands.read_real_file",
            side_effect=tracked,
        ):
            result = audit_kimodo_pilot_intake_command(*self.paths)
        after = self._snapshot()

        self.assertEqual(list(self.paths), calls)
        self.assertEqual(before, after)
        document = result.document
        self.assertEqual(result.report_sha256, document["intake_report_sha256"])
        document["status"] = "tampered"
        self.assertEqual("eligible_for_p7_p8_compile", result.document["status"])
        self.assertNotIn(str(self.root), repr(result.document))

    def test_digest_failure_is_zero_write_and_does_not_leak_paths(self):
        self.paths[4].write_bytes(b"different checkpoint")
        before = self._snapshot()
        with self.assertRaises(KimodoPilotIntakeCommandError) as caught:
            audit_kimodo_pilot_intake_command(*self.paths)
        self.assertEqual(before, self._snapshot())
        self.assertEqual("Kimodo pilot intake command failed", str(caught.exception))
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_preview_identity_matches_the_subsequent_p7_publication(self):
        intake = audit_kimodo_pilot_intake_command(*self.paths).document
        published = compile_kimodo_motion_bundle(
            self.root / "state", self.paths[0], self.paths[1], self.paths[2]
        )

        self.assertEqual(
            intake["p7_preview"]["motion_ir_sha256"],
            published.motion_ir_sha256,
        )
        self.assertEqual(
            intake["p7_preview"]["compile_run_sha256"],
            published.run_sha256,
        )
        self.assertEqual(
            intake["p7_preview"]["array_inventory_sha256"],
            published.array_inventory_sha256,
        )

    def test_malformed_json_and_empty_external_file_fail_closed(self):
        for index, data in enumerate((b'{"format":1,"format":2}', b"[]")):
            target = self.paths[1 + index]
            original = target.read_bytes()
            target.write_bytes(data)
            with self.subTest(index=index), self.assertRaises(
                KimodoPilotIntakeCommandError
            ):
                audit_kimodo_pilot_intake_command(*self.paths)
            target.write_bytes(original)

        self.paths[5].write_bytes(b"")
        with self.assertRaises(KimodoPilotIntakeCommandError):
            audit_kimodo_pilot_intake_command(*self.paths)

    def _snapshot(self) -> dict[str, bytes]:
        return {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in sorted(self.root.rglob("*")) if path.is_file()
        }


if __name__ == "__main__":
    unittest.main()
