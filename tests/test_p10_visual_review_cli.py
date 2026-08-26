"""Parser, canonical output, and redaction tests for P10.3c review CLI."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
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

from autospine_workbench.body_sway_visual_review_address import (  # noqa: E402
    ExactVisualReviewAddress,
)
from autospine_workbench.body_sway_visual_review_application import (  # noqa: E402
    BodySwayVisualReviewApplicationError,
    PreparedBodySwayVisualReview,
    SubmittedBodySwayVisualReview,
)
from autospine_workbench.body_sway_visual_review_history import (  # noqa: E402
    BodySwayVisualReviewRevisionConflict,
)
from autospine_workbench.body_sway_visual_review_history_snapshot import (  # noqa: E402
    BodySwayVisualReviewHistoryRow,
    BodySwayVisualReviewHistorySnapshot,
)
from autospine_workbench.body_sway_visual_review_profile import (  # noqa: E402
    MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
)
from autospine_workbench.p10_visual_review_cli import (  # noqa: E402
    CONFLICT_ERROR_CODE,
    PREPARE_ERROR_CODE,
    SUBMIT_ERROR_CODE,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.body_sway_visual_review_helpers import (  # noqa: E402
    BodySwayVisualReviewFixture,
)


SHAS = tuple(character * 64 for character in "abcd")
ADDRESS = ExactVisualReviewAddress("sample", *SHAS[:3])


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="visual-review-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("default-state"))
    return value


def address_argv(command: str) -> list[str]:
    return [
        command, ADDRESS.project_id,
        "--temporary-preview-sha256", ADDRESS.temporary_preview_sha256,
        "--runtime-capture-bundle-sha256",
        ADDRESS.runtime_capture_bundle_sha256,
        "--capture-artifact-set-sha256",
        ADDRESS.capture_artifact_set_sha256,
        "--state-root", "private-state",
    ]


def prepared() -> PreparedBodySwayVisualReview:
    candidate = {
        "format": "candidate", "status": "candidate_only",
        "summary": {"case_count": 3},
        "release_gate": {"status": "blocked", "reason_codes": ["review"]},
        "cases": [{"case_id": "setup"}],
    }
    history = BodySwayVisualReviewHistorySnapshot(
        "sample", SHAS[3], 1, 1, "e" * 64,
        (BodySwayVisualReviewHistoryRow(
            1, "e" * 64, "sampled_visual_approved"
        ),),
    )
    return PreparedBodySwayVisualReview(
        ADDRESS, SHAS[3], json.dumps(
            candidate, sort_keys=True, separators=(",", ":")
        ), history,
    )


def submitted() -> SubmittedBodySwayVisualReview:
    return SubmittedBodySwayVisualReview(
        ADDRESS, SHAS[3], "e" * 64, 1, "sampled_visual_approved",
        "blocked", ("safe_range_unproven",), 3, 3, 0, 0, False,
    )


class P10VisualReviewCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = parser()

    def test_parser_requires_complete_four_part_address_and_submission(self):
        args = self.parser.parse_args(
            address_argv("prepare-body-sway-visual-review")
        )
        self.assertEqual("sample", args.project_id)
        self.assertEqual(Path("private-state"), args.state_root)
        for option in (
            "--temporary-preview-sha256",
            "--runtime-capture-bundle-sha256",
            "--capture-artifact-set-sha256",
        ):
            values = address_argv("prepare-body-sway-visual-review")
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(option=option), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                self.parser.parse_args(values)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(
                address_argv("submit-body-sway-visual-review")
            )

    @patch(
        "autospine_workbench.p10_visual_review_cli."
        "BodySwayVisualReviewApplication"
    )
    def test_prepare_summary_and_document_only_keep_exact_identity(self, app):
        app.return_value.prepare.return_value = prepared()
        outputs = []
        for extra in ([], ["--document-only"]):
            with redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args([
                        *address_argv("prepare-body-sway-visual-review"),
                        *extra,
                    ])
                )
            self.assertEqual(0, status)
            outputs.append(output.getvalue().strip())
        summary, document = map(json.loads, outputs)
        self.assertEqual(ADDRESS.public_document(), summary["address"])
        self.assertEqual(SHAS[3], summary["candidate"]["candidate_sha256"])
        self.assertEqual("e" * 64,
                         summary["history"]["head_decision_sha256"])
        self.assertEqual(prepared().candidate_document, document["candidate"])
        self.assertEqual(SHAS[3], document["candidate_sha256"])
        self.assertNotIn("private-state", "".join(outputs))
        self.assertEqual(
            outputs[1], json.dumps(
                document, ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            )
        )

    def test_document_only_real_service_never_exposes_storage_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = BodySwayVisualReviewFixture(Path(temporary))
            address = ExactVisualReviewAddress(*fixture.address)
            argv = [
                "prepare-body-sway-visual-review", address.project_id,
                "--temporary-preview-sha256",
                address.temporary_preview_sha256,
                "--runtime-capture-bundle-sha256",
                address.runtime_capture_bundle_sha256,
                "--capture-artifact-set-sha256",
                address.capture_artifact_set_sha256,
                "--state-root", str(fixture.state_root),
                "--document-only",
            ]
            with fake_runtime_profile(), redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args(argv)
                )
        self.assertEqual(0, status)
        document = json.loads(output.getvalue())
        self.assertNotIn("path", _recursive_keys(document["candidate"]))
        self.assertNotIn('"path":', output.getvalue())

    @patch(
        "autospine_workbench.p10_visual_review_cli."
        "BodySwayVisualReviewApplication"
    )
    def test_submit_reads_strict_json_and_prints_bounded_result(self, app):
        app.return_value.submit.return_value = submitted()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "submission.json"
            path.write_text('{"base_revision":0}', encoding="utf-8")
            with redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args([
                        *address_argv("submit-body-sway-visual-review"),
                        "--submission", str(path),
                    ])
                )
        self.assertEqual(0, status)
        payload = json.loads(output.getvalue())
        self.assertEqual("sampled_visual_approved", payload["status"])
        self.assertEqual("blocked", payload["release_gate"]["status"])
        self.assertEqual(ADDRESS.public_document(), payload["address"])
        self.assertNotIn(str(path), output.getvalue())
        self.assertNotIn("private-state", output.getvalue())

    @patch(
        "autospine_workbench.p10_visual_review_cli."
        "BodySwayVisualReviewApplication"
    )
    def test_duplicate_nonfinite_and_oversize_inputs_fail_without_service(self, app):
        invalid = (
            b'{"base_revision":0,"base_revision":1}',
            b'{"base_revision":NaN}',
            b" " * (MAX_VISUAL_REVIEW_DOCUMENT_BYTES + 1),
        )
        with tempfile.TemporaryDirectory() as temporary:
            for index, data in enumerate(invalid):
                path = Path(temporary) / f"invalid-{index}.json"
                path.write_bytes(data)
                with self.subTest(index=index), redirect_stdout(
                    io.StringIO()
                ) as output:
                    status = dispatch_projection_stage_command(
                        self.parser.parse_args([
                            *address_argv("submit-body-sway-visual-review"),
                            "--submission", str(path),
                        ])
                    )
                self.assertEqual(2, status)
                self.assertEqual(SUBMIT_ERROR_CODE,
                                 json.loads(output.getvalue())["error_code"])
        app.return_value.submit.assert_not_called()

    @patch(
        "autospine_workbench.p10_visual_review_cli."
        "BodySwayVisualReviewApplication"
    )
    def test_failures_are_stable_redacted_and_conflict_is_typed(self, app):
        private = r"C:\Users\private\capture.png"
        app.return_value.prepare.side_effect = \
            BodySwayVisualReviewApplicationError(private)
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(self.parser.parse_args(
                address_argv("prepare-body-sway-visual-review")
            ))
        self.assertEqual(2, status)
        self.assertEqual(PREPARE_ERROR_CODE,
                         json.loads(output.getvalue())["error_code"])
        self.assertNotIn(private, output.getvalue())

        app.return_value.submit.side_effect = BodySwayVisualReviewRevisionConflict(
            private, requested_revision=2, current_revision=3,
            requested_head="e" * 64, current_head="f" * 64,
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "submission.json"
            path.write_text("{}", encoding="utf-8")
            with redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(self.parser.parse_args([
                    *address_argv("submit-body-sway-visual-review"),
                    "--submission", str(path),
                ]))
        payload = json.loads(output.getvalue())
        self.assertEqual(3, status)
        self.assertEqual(CONFLICT_ERROR_CODE, payload["error_code"])
        self.assertEqual(3, payload["current_revision"])
        self.assertNotIn(private, output.getvalue())


def _recursive_keys(value) -> set[str]:
    if type(value) is dict:
        keys = set(value)
        for item in value.values():
            keys.update(_recursive_keys(item))
        return keys
    if type(value) is list:
        keys = set()
        for item in value:
            keys.update(_recursive_keys(item))
        return keys
    return set()


if __name__ == "__main__":
    unittest.main()
