"""Parser, exact dispatch, canonical output, and redaction tests."""

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
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.cli import build_parser, main
import autospine_workbench.p10_spine42_v3_raster_review_cli as cli
from autospine_workbench.p10_spine42_v3_raster_review_commands import (
    P10Spine42V3RasterReviewCommandError,
)


SHAS = tuple(character * 64 for character in "abcd")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="spine42-v3-review-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    cli.add_p10_spine42_v3_raster_review_subcommands(
        subparsers, Path("default-state")
    )
    return value


def prepare_argv() -> list[str]:
    return [
        cli.PREPARE_COMMAND, "fixture-project",
        "--spine42-v3-bundle-sha256", SHAS[0],
        "--capture-bundle-sha256", SHAS[1],
        "--state-root", r"C:\private\state",
    ]


def submit_argv(*, previous: bool = True) -> list[str]:
    values = [
        cli.SUBMIT_COMMAND, "fixture-project",
        "--spine42-v3-bundle-sha256", SHAS[0],
        "--capture-bundle-sha256", SHAS[1],
        "--candidate", r"C:\private\candidate.json",
        "--review-input", r"C:\private\review.json",
        "--state-root", r"C:\private\state",
    ]
    if previous:
        values.extend((
            "--previous-decision", r"C:\private\previous.json",
        ))
    return values


def result(mode: str) -> SimpleNamespace:
    digest_field = "candidate_sha256" if mode == "candidate" \
        else "decision_sha256"
    document = {
        "format": f"fixture-{mode}", "project_id": "fixture-project",
        "clip_id": "idle", digest_field: SHAS[2],
        "status": "candidate_only" if mode == "candidate"
        else "sampled_raster_approved",
        "release_gate": {"status": "blocked"},
    }
    return SimpleNamespace(mode=mode, document=document)


class P10Spine42V3RasterReviewCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = parser()

    def test_parser_requires_exact_address_and_review_files(self):
        cases = (
            (prepare_argv(), (
                "--spine42-v3-bundle-sha256", "--capture-bundle-sha256",
            )),
            (submit_argv(), (
                "--spine42-v3-bundle-sha256", "--capture-bundle-sha256",
                "--candidate", "--review-input",
            )),
        )
        for values, required in cases:
            self.assertEqual(values[0], build_parser().parse_args(values).command)
            for option in required:
                attack = list(values)
                index = attack.index(option)
                del attack[index:index + 2]
                with self.subTest(option=option), redirect_stderr(
                    io.StringIO()
                ), self.assertRaises(SystemExit):
                    self.parser.parse_args(attack)

    @patch.object(cli, "prepare_spine42_v3_raster_review_command")
    def test_prepare_dispatches_exact_address_and_prints_document(self, call):
        call.return_value = result("candidate")
        with redirect_stdout(io.StringIO()) as output:
            status = main(prepare_argv())
        self.assertEqual(0, status)
        call.assert_called_once_with(
            Path(r"C:\private\state"), "fixture-project",
            spine42_v3_bundle_sha256=SHAS[0],
            capture_bundle_sha256=SHAS[1],
        )
        self.assertEqual(result("candidate").document,
                         json.loads(output.getvalue()))

    @patch.object(cli, "submit_spine42_v3_raster_review_command")
    def test_submit_replays_exact_address_and_forwards_revision(self, call):
        call.return_value = result("decision")
        with redirect_stdout(io.StringIO()) as output:
            status = cli.dispatch_p10_spine42_v3_raster_review_command(
                self.parser.parse_args(submit_argv())
            )
        self.assertEqual(0, status)
        call.assert_called_once_with(
            Path(r"C:\private\state"), "fixture-project",
            Path(r"C:\private\candidate.json"),
            Path(r"C:\private\review.json"),
            spine42_v3_bundle_sha256=SHAS[0],
            capture_bundle_sha256=SHAS[1],
            previous_decision_path=Path(r"C:\private\previous.json"),
        )
        expected = json.dumps(
            result("decision").document, ensure_ascii=False,
            allow_nan=False, sort_keys=True, separators=(",", ":"),
        )
        self.assertEqual(expected, output.getvalue().strip())

    def test_failures_are_fixed_redacted_and_unrelated_is_ignored(self):
        cases = (
            (prepare_argv(), "prepare_spine42_v3_raster_review_command",
             cli.PREPARE_ERROR_CODE, cli.PREPARE_ERROR_MESSAGE),
            (submit_argv(), "submit_spine42_v3_raster_review_command",
             cli.SUBMIT_ERROR_CODE, cli.SUBMIT_ERROR_MESSAGE),
        )
        private = r"C:\private\candidate.json"
        for values, target, code, message in cases:
            with patch.object(
                cli, target,
                side_effect=P10Spine42V3RasterReviewCommandError(private),
            ), redirect_stdout(io.StringIO()) as output:
                status = cli.dispatch_p10_spine42_v3_raster_review_command(
                    self.parser.parse_args(values)
                )
            self.assertEqual(2, status)
            self.assertEqual({
                "error_code": code, "message": message,
                "ok": False, "status": "error",
            }, json.loads(output.getvalue()))
            self.assertNotIn(private, output.getvalue())
        self.assertIsNone(
            cli.dispatch_p10_spine42_v3_raster_review_command(
                argparse.Namespace(command="unrelated")
            )
        )


if __name__ == "__main__":
    unittest.main()
