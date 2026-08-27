"""Isolated parser, canonical output, and redaction tests for P10.5a."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.seam_anchor_candidate_cli import (
    COMMAND,
    ERROR_CODE,
    add_seam_anchor_candidate_subcommands,
    dispatch_seam_anchor_candidate_command,
)
from autospine_workbench.seam_anchor_candidate_commands import (
    SeamAnchorCandidateCommandError,
)
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.p9_v2_helpers import tree


SHAS = tuple(character * 64 for character in "abc")
OPTIONS = (
    "--layer-manifest-sha256",
    "--p3-rig-sha256",
    "--p3-bundle-sha256",
)


def parser(default: Path = Path("default-state")) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="seam-anchor-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_seam_anchor_candidate_subcommands(subparsers, default)
    return value


def argv(*extra: str) -> list[str]:
    values = [COMMAND, "sample"]
    for option, sha256 in zip(OPTIONS, SHAS, strict=True):
        values.extend((option, sha256))
    return [*values, *extra]


def result() -> SimpleNamespace:
    document = {
        "project_id": "sample",
        "summary": {
            "status": "manual_review_required",
            "relationship_count": 6,
        },
        "claims": {"release_authority": False},
        "release_gate": {
            "status": "blocked",
            "reason_codes": ["human_review_required"],
        },
    }
    return SimpleNamespace(
        input_paths=(Path(r"C:\private\manifest"),),
        seam_anchor_candidates_sha256="d" * 64,
        document=document,
    )


class SeamAnchorCandidateCliTests(unittest.TestCase):
    def test_parser_requires_all_addresses_and_accepts_state_override(self):
        parsed = parser().parse_args(argv())
        self.assertEqual(Path("default-state"), parsed.state_root)
        self.assertEqual(
            Path("other-state"),
            parser().parse_args(
                argv("--state-root", "other-state")
            ).state_root,
        )
        for option in OPTIONS:
            values = argv()
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(option=option), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                parser().parse_args(values)

    @patch(
        "autospine_workbench.seam_anchor_candidate_cli."
        "compile_seam_anchor_candidates_command"
    )
    def test_dispatch_passes_exact_identity_and_output_is_path_free(self, call):
        call.return_value = result()
        outputs = []
        for extra in ((), ("--document-only",)):
            with redirect_stdout(io.StringIO()) as output:
                status = dispatch_seam_anchor_candidate_command(
                    parser().parse_args(argv(*extra))
                )
            self.assertEqual(0, status)
            outputs.append(output.getvalue().strip())
        call.assert_called_with(
            Path("default-state"), "sample",
            layer_manifest_sha256=SHAS[0],
            p3_rig_sha256=SHAS[1],
            p3_bundle_sha256=SHAS[2],
        )
        summary, document = map(json.loads, outputs)
        self.assertEqual("d" * 64,
                         summary["seam_anchor_candidates_sha256"])
        self.assertEqual(result().document, document)
        self.assertNotIn("input_paths", outputs[0])
        self.assertNotIn(r"C:\private", "".join(outputs))
        canonical = json.dumps(
            result().document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        self.assertEqual(canonical, outputs[1])

    @patch(
        "autospine_workbench.seam_anchor_candidate_cli."
        "compile_seam_anchor_candidates_command"
    )
    def test_failure_is_stable_redacted_and_unrelated_is_ignored(self, call):
        private = r"C:\Users\private\bundle"
        call.side_effect = SeamAnchorCandidateCommandError(private)
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_seam_anchor_candidate_command(
                parser().parse_args(argv())
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual(ERROR_CODE, payload["error_code"])
        self.assertNotIn(private, output.getvalue())
        self.assertIsNone(dispatch_seam_anchor_candidate_command(
            argparse.Namespace(command="another-command")
        ))

    def test_real_document_only_is_deterministic_and_zero_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = P10PersistedFixture(Path(temporary))
            values = [COMMAND, fixture.mesh.project_id]
            for option, sha256 in (
                (OPTIONS[0], fixture.layer_manifest_sha256),
                (OPTIONS[1], fixture.mesh.rig_sha256),
                (OPTIONS[2], fixture.mesh.bundle_sha256),
            ):
                values.extend((option, sha256))
            values.extend((
                "--state-root", str(fixture.state), "--document-only",
            ))
            before = tree(fixture.state)
            outputs = []
            for _index in range(2):
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(
                        0,
                        dispatch_seam_anchor_candidate_command(
                            parser().parse_args(values)
                        ),
                    )
                outputs.append(output.getvalue())
            self.assertEqual(before, tree(fixture.state))
            self.assertEqual(outputs[0], outputs[1])
            document = json.loads(outputs[0])
            self.assertEqual(
                "autospine-seam-anchor-candidates", document["format"]
            )
            self.assertNotIn("input_paths", outputs[0])


if __name__ == "__main__":
    unittest.main()
