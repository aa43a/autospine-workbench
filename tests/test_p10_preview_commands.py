"""Persisted exact-chain tests for the P10.3a preview command service."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
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

from autospine_workbench.p10_preview_commands import (  # noqa: E402
    MAX_INPUT_DOCUMENT_BYTES,
    P10PreviewCommandError,
    compile_body_sway_preview_command,
    preview_artifact_sha256s,
)
from autospine_workbench.safe_input_files import (  # noqa: E402
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)
from tests.body_sway_preview_helpers import BodySwayPreviewFixture  # noqa: E402
from tests.p10_decision_command_helpers import write_json  # noqa: E402
from tests.p9_v2_helpers import tree  # noqa: E402


class P10PreviewCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = BodySwayPreviewFixture(cls.root)
        inputs = cls.root / "preview-inputs"
        inputs.mkdir()
        cls.candidate_path = write_json(
            inputs / "candidates.json", cls.fixture.candidates
        )
        cls.decision_path = write_json(
            inputs / "decision.json", cls.fixture.decision
        )
        cls.report_path = write_json(
            inputs / "probe-report.json", cls.fixture.report.document
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def compile(self, **changes):
        values = {**self.fixture.persisted.command_kwargs, **changes}
        return compile_body_sway_preview_command(
            self.fixture.persisted.state,
            self.fixture.persisted.mesh.project_id,
            self.candidate_path,
            self.decision_path,
            self.report_path,
            **values,
        )

    def test_exact_files_are_read_once_result_is_frozen_and_zero_write(self):
        before = tree(self.root)
        with patch(
            "autospine_workbench.p10_preview_commands.read_real_file",
            wraps=read_real_file,
        ) as reader, patch(
            "autospine_workbench.p10_preview_commands.strict_json_object",
            wraps=strict_json_object,
        ) as decoder:
            first = self.compile()
        second = self.compile()
        self.assertEqual(before, tree(self.root))
        self.assertEqual(first, second)
        self.assertEqual(3, reader.call_count)
        self.assertEqual(3, decoder.call_count)
        self.assertEqual(
            [self.candidate_path, self.decision_path, self.report_path],
            [call.args[0] for call in reader.call_args_list],
        )
        self.assertTrue(all(
            call.args[1] == MAX_INPUT_DOCUMENT_BYTES
            for call in reader.call_args_list
        ))
        self.assertEqual(
            (*self.fixture.chain.input_paths, self.candidate_path,
             self.decision_path, self.report_path),
            first.input_paths,
        )
        self.assertEqual(5, len(first.artifact_bytes))
        self.assertEqual(
            {row["path"]: row["sha256"] for row in first.artifact_files},
            preview_artifact_sha256s(first),
        )
        changed = first.document
        changed["summary"].clear()
        self.assertTrue(first.document["summary"])
        with self.assertRaises(FrozenInstanceError):
            first.temporary_preview_sha256 = "f" * 64  # type: ignore[misc]

    def test_each_exact_address_rejects_cross_wiring_without_writes(self):
        identities = tuple(self.fixture.persisted.command_kwargs.values())
        before = tree(self.root)
        for field, original in self.fixture.persisted.command_kwargs.items():
            wrong = next(value for value in identities if value != original)
            with self.subTest(field=field), self.assertRaises(
                P10PreviewCommandError
            ):
                self.compile(**{field: wrong})
            self.assertEqual(before, tree(self.root))

    def test_invalid_json_alias_and_read_race_fail_closed(self):
        invalid = self.root / "invalid-preview"
        invalid.mkdir()
        duplicate = invalid / "duplicate.json"
        duplicate.write_text('{"x":1,"x":2}', encoding="utf-8")
        nonfinite = invalid / "nonfinite.json"
        nonfinite.write_text('{"x":NaN}', encoding="utf-8")
        for paths in (
            (duplicate, self.decision_path, self.report_path),
            (self.candidate_path, nonfinite, self.report_path),
            (self.candidate_path, self.decision_path, invalid),
        ):
            with self.subTest(paths=paths), self.assertRaises(
                P10PreviewCommandError
            ):
                compile_body_sway_preview_command(
                    self.fixture.persisted.state,
                    self.fixture.persisted.mesh.project_id,
                    *paths,
                    **self.fixture.persisted.command_kwargs,
                )
        alias = invalid / "candidate-alias.json"
        try:
            alias.symlink_to(self.candidate_path)
        except OSError:
            alias = None
        if alias is not None:
            with self.assertRaises(P10PreviewCommandError):
                compile_body_sway_preview_command(
                    self.fixture.persisted.state,
                    self.fixture.persisted.mesh.project_id,
                    alias, self.decision_path, self.report_path,
                    **self.fixture.persisted.command_kwargs,
                )
        for message in ("path contains an alias", "changed while it was read"):
            with self.subTest(message=message), patch(
                "autospine_workbench.p10_preview_commands.read_real_file",
                side_effect=SafeInputFileError(message),
            ), self.assertRaisesRegex(P10PreviewCommandError, message):
                self.compile()

    def test_stale_or_rejected_report_and_non_result_hash_fail_closed(self):
        changed = self.fixture.report.document
        changed["status"] = "structural_rejected"
        rejected = write_json(self.root / "rejected-report.json", changed)
        with self.assertRaises(P10PreviewCommandError):
            compile_body_sway_preview_command(
                self.fixture.persisted.state,
                self.fixture.persisted.mesh.project_id,
                self.candidate_path, self.decision_path, rejected,
                **self.fixture.persisted.command_kwargs,
            )
        with self.assertRaises(P10PreviewCommandError):
            preview_artifact_sha256s(object())  # type: ignore[arg-type]

    def test_source_has_no_latest_scan_or_write_path(self):
        source = (
            SRC / "autospine_workbench" / "p10_preview_commands.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("latest", ".glob(", ".rglob(", "write_", "publish"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
