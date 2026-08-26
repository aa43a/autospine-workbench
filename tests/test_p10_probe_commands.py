"""Persisted-chain and safe-file tests for the P10.2 probe command."""

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

from autospine_workbench.body_sway_probe_validation import (  # noqa: E402
    body_sway_probe_report_sha256,
)
from autospine_workbench.cli import main  # noqa: E402
from autospine_workbench.idle_behavior_candidates import (  # noqa: E402
    compile_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_candidate_validation import (  # noqa: E402
    idle_behavior_candidates_sha256,
)
from autospine_workbench.idle_behavior_decision import (  # noqa: E402
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_decision_validation import (  # noqa: E402
    idle_behavior_decision_sha256,
)
from autospine_workbench.p10_exact_chain import load_p10_exact_chain  # noqa: E402
from autospine_workbench.p10_probe_commands import (  # noqa: E402
    MAX_INPUT_DOCUMENT_BYTES,
    P10ProbeCommandError,
    compile_body_sway_probe_command,
)
from autospine_workbench.safe_input_files import (  # noqa: E402
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)
from tests.idle_behavior_decision_helpers import (  # noqa: E402
    adjust_decision,
    completed_review,
)
from tests.p10_candidate_helpers import P10PersistedFixture  # noqa: E402
from tests.p10_decision_command_helpers import write_json  # noqa: E402
from tests.p9_v2_helpers import tree  # noqa: E402


class P10ProbeCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = P10PersistedFixture(cls.root)
        cls.chain = load_p10_exact_chain(
            cls.fixture.state,
            cls.fixture.mesh.project_id,
            **cls.fixture.command_kwargs,
        )
        cls.candidates = compile_idle_behavior_candidates(
            cls.chain.manifest,
            cls.chain.mesh_bundle,
            cls.chain.retarget_bundle,
            cls.chain.reviewed_contract,
        ).document
        cls.decision = build_idle_behavior_decision(
            cls.candidates,
            review=completed_review(),
            decisions=[adjust_decision(cls.candidates)],
        ).document
        inputs = cls.root / "probe-inputs"
        inputs.mkdir()
        cls.candidate_path = write_json(
            inputs / "candidates.json", cls.candidates
        )
        cls.decision_path = write_json(
            inputs / "decision.json", cls.decision
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def compile(self, **changes):
        values = {**self.fixture.command_kwargs, **changes}
        return compile_body_sway_probe_command(
            self.fixture.state,
            self.fixture.mesh.project_id,
            self.candidate_path,
            self.decision_path,
            **values,
        )

    def cli_argv(self):
        values = [
            "compile-body-sway-probe", self.fixture.mesh.project_id,
            "--candidates", str(self.candidate_path),
            "--decision", str(self.decision_path),
            "--state-root", str(self.fixture.state),
            "--document-only",
        ]
        for field, value in self.fixture.command_kwargs.items():
            values.extend((f"--{field.replace('_', '-')}", value))
        return values

    def test_real_persisted_chain_reads_each_file_once_and_writes_nothing(self):
        before = tree(self.root)
        with patch(
            "autospine_workbench.p10_probe_commands.read_real_file",
            wraps=read_real_file,
        ) as reader, patch(
            "autospine_workbench.p10_probe_commands.strict_json_object",
            wraps=strict_json_object,
        ) as decoder:
            first = self.compile()
        second = self.compile()
        self.assertEqual(before, tree(self.root))
        self.assertEqual(first, second)
        self.assertEqual(2, reader.call_count)
        self.assertEqual(2, decoder.call_count)
        self.assertEqual(
            [self.candidate_path, self.decision_path],
            [call.args[0] for call in reader.call_args_list],
        )
        self.assertTrue(all(
            call.args[1] == MAX_INPUT_DOCUMENT_BYTES
            for call in reader.call_args_list
        ))
        self.assertEqual(
            (*self.chain.input_paths, self.candidate_path, self.decision_path),
            first.input_paths,
        )
        self.assertEqual(
            idle_behavior_candidates_sha256(self.candidates),
            first.idle_behavior_candidates_sha256,
        )
        self.assertEqual(
            idle_behavior_decision_sha256(self.decision),
            first.idle_behavior_decision_sha256,
        )
        self.assertEqual(
            body_sway_probe_report_sha256(first.document),
            first.body_sway_probe_report_sha256,
        )
        self.assertIn(first.document["status"], {
            "manual_visual_required", "structural_rejected",
        })
        self.assertEqual("blocked", first.document["release_gate"]["status"])

    def test_document_only_is_stable_canonical_and_zero_write(self):
        before = tree(self.root)
        lines = []
        for _index in range(2):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, main(self.cli_argv()))
            lines.append(output.getvalue().strip())
        self.assertEqual(before, tree(self.root))
        self.assertEqual(lines[0], lines[1])
        document = json.loads(lines[0])
        self.assertEqual(
            "autospine-body-sway-probe-report", document["format"]
        )
        self.assertNotIn("input_paths", lines[0])
        self.assertNotIn("completed_diagnostic", lines[0])
        self.assertEqual(json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ), lines[0])

    def test_each_explicit_sha_rejects_cross_wiring_without_writes(self):
        identities = tuple(self.fixture.command_kwargs.values())
        before = tree(self.root)
        for field, original in self.fixture.command_kwargs.items():
            wrong = next(value for value in identities if value != original)
            with self.subTest(field=field), self.assertRaises(
                P10ProbeCommandError
            ):
                self.compile(**{field: wrong})
            self.assertEqual(before, tree(self.root))

    def test_directory_duplicate_nonfinite_alias_and_race_fail_closed(self):
        invalid = self.root / "invalid"
        invalid.mkdir()
        duplicate = invalid / "duplicate.json"
        duplicate.write_text('{"x":1,"x":2}', encoding="utf-8")
        nonfinite = invalid / "nonfinite.json"
        nonfinite.write_text('{"x":NaN}', encoding="utf-8")
        for candidate_path, decision_path in (
            (invalid, self.decision_path),
            (duplicate, self.decision_path),
            (self.candidate_path, nonfinite),
        ):
            with self.subTest(path=candidate_path), self.assertRaises(
                P10ProbeCommandError
            ):
                compile_body_sway_probe_command(
                    self.fixture.state, self.fixture.mesh.project_id,
                    candidate_path, decision_path,
                    **self.fixture.command_kwargs,
                )
        alias = invalid / "candidate-alias.json"
        try:
            alias.symlink_to(self.candidate_path)
        except OSError:
            alias = None
        if alias is not None:
            with self.assertRaises(P10ProbeCommandError):
                compile_body_sway_probe_command(
                    self.fixture.state, self.fixture.mesh.project_id,
                    alias, self.decision_path,
                    **self.fixture.command_kwargs,
                )
        for message in ("path contains an alias", "changed while it was read"):
            with self.subTest(message=message), patch(
                "autospine_workbench.p10_probe_commands.read_real_file",
                side_effect=SafeInputFileError(message),
            ), self.assertRaisesRegex(P10ProbeCommandError, message):
                self.compile()
        self.assertEqual(64 * 1024 * 1024, MAX_INPUT_DOCUMENT_BYTES)

    def test_command_source_has_no_latest_scan_or_write_path(self):
        source = (
            SRC / "autospine_workbench" / "p10_probe_commands.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("latest", ".glob(", ".rglob(", "write_", "publish"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
