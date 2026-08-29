"""Parser, canonical output, and redaction tests for P10.5b CLI."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.projection_stage_cli import (
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)
from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_application_models import (
    PreparedSeamAnchorReview,
    SubmittedSeamAnchorReview,
)
from autospine_workbench.seam_anchor_review_errors import (
    SeamAnchorReviewRevisionConflict,
)
from autospine_workbench.seam_anchor_review_history_models import (
    SeamAnchorReviewHistoryRow,
    SeamAnchorReviewHistorySnapshot,
)
from autospine_workbench.seam_anchor_review_cli import (
    CONFLICT_ERROR_CODE,
    SUBMIT_ERROR_CODE,
)


ADDRESS = ExactSeamAnchorReviewAddress(
    "sample", "a" * 64, "b" * 64, "c" * 64
)


def parser():
    result = argparse.ArgumentParser(prog="seam-review-test")
    subparsers = result.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("default-state"))
    return result


def argv(command):
    return [
        command, ADDRESS.project_id,
        "--layer-manifest-sha256", ADDRESS.layer_manifest_sha256,
        "--p3-rig-sha256", ADDRESS.p3_rig_sha256,
        "--p3-bundle-sha256", ADDRESS.p3_bundle_sha256,
        "--state-root", "private-state",
    ]


def prepared():
    candidate = {
        "summary": {
            "status": "manual_review_required", "relationship_count": 6
        },
        "release_gate": {"status": "blocked", "reasons": ["review"]},
    }
    history = SeamAnchorReviewHistorySnapshot(
        "sample", "d" * 64, 1, 1, "e" * 64,
        (SeamAnchorReviewHistoryRow(1, "e" * 64,
                                    "reviewed_anchor_set_blocked"),),
    )
    return PreparedSeamAnchorReview(
        ADDRESS, "d" * 64,
        json.dumps(candidate, sort_keys=True, separators=(",", ":")),
        history, 400, 400,
    )


def submitted():
    return SubmittedSeamAnchorReview(
        ADDRESS, "d" * 64, "e" * 64, 1,
        "reviewed_anchor_set_blocked", "blocked",
        ("dynamic_seam_safety_unproven",),
        6, 0, 0, 0, 6, 0, False,
    )


class SeamAnchorReviewCliTests(unittest.TestCase):
    def setUp(self):
        self.parser = parser()

    def test_parser_requires_exact_address_and_submission(self):
        args = self.parser.parse_args(argv("prepare-seam-anchor-review"))
        self.assertEqual(Path("private-state"), args.state_root)
        for option in (
            "--layer-manifest-sha256", "--p3-rig-sha256",
            "--p3-bundle-sha256",
        ):
            values = argv("prepare-seam-anchor-review")
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(option=option), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                self.parser.parse_args(values)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(argv("submit-seam-anchor-review"))

    @patch(
        "autospine_workbench.seam_anchor_review_cli."
        "SeamAnchorReviewApplication"
    )
    def test_prepare_summary_and_document_are_path_free(self, app):
        app.return_value.prepare.return_value = prepared()
        outputs = []
        for extra in ([], ["--document-only"]):
            with redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args([
                        *argv("prepare-seam-anchor-review"), *extra
                    ])
                )
            self.assertEqual(0, status)
            outputs.append(json.loads(output.getvalue()))
        self.assertEqual(ADDRESS.public_document(), outputs[0]["address"])
        self.assertEqual("d" * 64,
                         outputs[0]["candidate"]["candidate_sha256"])
        self.assertEqual(prepared().candidate_document,
                         outputs[1]["candidate"])
        self.assertNotIn("private-state", json.dumps(outputs))

    @patch(
        "autospine_workbench.seam_anchor_review_cli."
        "SeamAnchorReviewApplication"
    )
    def test_submit_strict_json_result_and_typed_conflict(self, app):
        app.return_value.submit.return_value = submitted()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "submission.json"
            path.write_text("{}", encoding="utf-8")
            with redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args([
                        *argv("submit-seam-anchor-review"),
                        "--submission", str(path),
                    ])
                )
            self.assertEqual(0, status)
            self.assertEqual("reviewed_anchor_set_blocked",
                             json.loads(output.getvalue())["status"])

            app.return_value.submit.side_effect = \
                SeamAnchorReviewRevisionConflict(
                    r"C:\private\state", requested_revision=2,
                    current_revision=3, requested_head="e" * 64,
                    current_head="f" * 64,
                )
            with redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args([
                        *argv("submit-seam-anchor-review"),
                        "--submission", str(path),
                    ])
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(3, status)
        self.assertEqual(CONFLICT_ERROR_CODE, payload["error_code"])
        self.assertNotIn("private", output.getvalue())

    @patch(
        "autospine_workbench.seam_anchor_review_cli."
        "SeamAnchorReviewApplication"
    )
    def test_duplicate_and_nonfinite_submission_fail_before_service(self, app):
        invalid = (
            b'{"base_revision":0,"base_revision":1}',
            b'{"base_revision":NaN}',
        )
        with tempfile.TemporaryDirectory() as temporary:
            for index, data in enumerate(invalid):
                path = Path(temporary) / f"bad-{index}.json"
                path.write_bytes(data)
                with redirect_stdout(io.StringIO()) as output:
                    status = dispatch_projection_stage_command(
                        self.parser.parse_args([
                            *argv("submit-seam-anchor-review"),
                            "--submission", str(path),
                        ])
                    )
                self.assertEqual(2, status)
                self.assertEqual(SUBMIT_ERROR_CODE,
                                 json.loads(output.getvalue())["error_code"])
        app.return_value.submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
