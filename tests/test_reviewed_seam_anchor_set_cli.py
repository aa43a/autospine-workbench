"""Focused command and CLI tests for reviewed seam-anchor set bundles."""

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
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.cli import (  # noqa: E402
    build_parser as build_root_parser,
    main as root_main,
)
from autospine_workbench.reviewed_seam_anchor_set_cli import (  # noqa: E402
    COMPILE_ERROR_CODE,
    VERIFY_ERROR_CODE,
    add_reviewed_seam_anchor_set_subcommands,
    dispatch_reviewed_seam_anchor_set_command,
)
from autospine_workbench.reviewed_seam_anchor_set_commands import (  # noqa: E402
    ReviewedSeamAnchorSetCommandError,
    ReviewedSeamAnchorSetCommandResult,
    compile_reviewed_seam_anchor_set_command,
    verify_reviewed_seam_anchor_set_command,
)
from autospine_workbench.reviewed_seam_anchor_set_inputs import (  # noqa: E402
    ReviewedSeamAnchorSetInputsError,
)
from autospine_workbench.seam_anchor_review_application import (  # noqa: E402
    SeamAnchorReviewApplication,
)
from tests.p9_v2_helpers import tree  # noqa: E402
from tests.reviewed_seam_anchor_set_bundle_helpers import (  # noqa: E402
    PersistedReviewedSeamAnchorSetFixture,
)

SHA = {
    name: character * 64
    for name, character in (
        ("manifest", "1"), ("rig", "2"), ("p3_bundle", "3"),
        ("candidate", "4"), ("decision", "5"),
        ("reviewed_set", "6"), ("bundle", "7"),
    )
}

def parser(default: Path) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="p10-5c-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_reviewed_seam_anchor_set_subcommands(subparsers, default)
    return value


def compile_argv(*extra: str) -> list[str]:
    return [
        "compile-reviewed-seam-anchor-set", "sample",
        "--layer-manifest-sha256", SHA["manifest"],
        "--p3-rig-sha256", SHA["rig"],
        "--p3-bundle-sha256", SHA["p3_bundle"],
        "--candidate-sha256", SHA["candidate"],
        "--review-revision", "2",
        "--decision-sha256", SHA["decision"],
        *extra,
    ]


def command_result(mode: str = "compiled") -> ReviewedSeamAnchorSetCommandResult:
    return ReviewedSeamAnchorSetCommandResult(
        mode=mode,
        project_id="sample",
        layer_manifest_sha256=SHA["manifest"],
        p3_rig_sha256=SHA["rig"],
        p3_bundle_sha256=SHA["p3_bundle"],
        candidate_sha256=SHA["candidate"],
        decision_sha256=SHA["decision"],
        review_revision=2,
        reviewed_set_sha256=SHA["reviewed_set"],
        bundle_sha256=SHA["bundle"],
        artifact_status="reviewed_static_anchor_set_compiled",
        release_gate_status="blocked",
        release_gate_reason_codes=("dynamic_seam_safety_unproven",),
        relationship_count=6,
        anchor_pair_count=36,
        head_observation_method=(
            "double_snapshot" if mode == "compiled" else None
        ),
        head_observation_scope=(
            "compile_time" if mode == "compiled" else None
        ),
        permanent_authority_claimed=(False if mode == "compiled" else None),
    )


class ReviewedSeamAnchorSetCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path("exact-state")
        self.parser = parser(self.state)

    def dispatch(self, argv: list[str]) -> tuple[int | None, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = dispatch_reviewed_seam_anchor_set_command(
                self.parser.parse_args(argv)
            )
        return status, output.getvalue()

    def test_parser_requires_every_exact_address_and_positive_revision(self):
        parsed = self.parser.parse_args(compile_argv())
        self.assertEqual(self.state, parsed.state_root)
        self.assertEqual(2, parsed.review_revision)
        required = (
            "--layer-manifest-sha256", "--p3-rig-sha256",
            "--p3-bundle-sha256", "--candidate-sha256",
            "--review-revision", "--decision-sha256",
        )
        for flag in required:
            values = compile_argv()
            index = values.index(flag)
            del values[index:index + 2]
            with self.subTest(flag=flag), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                self.parser.parse_args(values)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(compile_argv(
                "--review-revision", "0"
            ))

    def test_compile_and_verify_dispatch_exact_calls_and_stable_json(self):
        outputs = []
        for _index in range(2):
            with patch(
                "autospine_workbench.reviewed_seam_anchor_set_cli."
                "compile_reviewed_seam_anchor_set_command",
                return_value=command_result(),
            ) as service:
                status, output = self.dispatch(compile_argv())
            self.assertEqual(0, status)
            service.assert_called_once_with(
                self.state,
                "sample",
                layer_manifest_sha256=SHA["manifest"],
                p3_rig_sha256=SHA["rig"],
                p3_bundle_sha256=SHA["p3_bundle"],
                candidate_sha256=SHA["candidate"],
                review_revision=2,
                decision_sha256=SHA["decision"],
            )
            outputs.append(output)
        self.assertEqual(outputs[0], outputs[1])
        payload = json.loads(outputs[0])
        self.assertTrue(payload["ok"])
        self.assertEqual("compiled", payload["status"])
        self.assertEqual({
            "layer_manifest_sha256": SHA["manifest"],
            "p3_rig_sha256": SHA["rig"],
            "p3_bundle_sha256": SHA["p3_bundle"],
            "seam_anchor_candidate_sha256": SHA["candidate"],
            "review_revision": 2,
            "seam_anchor_review_decision_sha256": SHA["decision"],
        }, payload["source"])
        self.assertFalse(
            payload["head_observation"]["permanent_authority_claimed"]
        )
        self.assertNotIn("path", payload)
        self.assertNotIn("reused", payload)

        verify = [
            "verify-reviewed-seam-anchor-set", "sample",
            "--reviewed-set-sha256", SHA["reviewed_set"],
            "--bundle-sha256", SHA["bundle"],
        ]
        with patch(
            "autospine_workbench.reviewed_seam_anchor_set_cli."
            "verify_reviewed_seam_anchor_set_command",
            return_value=command_result("verified"),
        ) as service:
            status, output = self.dispatch(verify)
        self.assertEqual(0, status)
        service.assert_called_once_with(
            self.state, "sample",
            reviewed_set_sha256=SHA["reviewed_set"],
            bundle_sha256=SHA["bundle"],
        )
        self.assertIsNone(json.loads(output)["head_observation"])

    def test_blocked_or_stale_error_is_fixed_and_never_publishes(self):
        for detail in ("blocked review", "stale review head"):
            with self.subTest(detail=detail), patch(
                "autospine_workbench.reviewed_seam_anchor_set_commands."
                "prepare_current_head_reviewed_seam_anchor_set",
                side_effect=ReviewedSeamAnchorSetInputsError(detail),
            ), patch(
                "autospine_workbench.reviewed_seam_anchor_set_commands."
                "ReviewedSeamAnchorSetBundleStore.publish"
            ) as publish, redirect_stdout(io.StringIO()) as output:
                status = root_main(compile_argv(
                    "--state-root", str(self.state)
                ))
            self.assertEqual(2, status)
            publish.assert_not_called()
            self.assertEqual({
                "error_code": COMPILE_ERROR_CODE,
                "message": "Reviewed seam-anchor set compilation failed.",
                "ok": False,
                "status": "error",
            }, json.loads(output.getvalue()))

    def test_verify_error_has_distinct_stable_code(self):
        with patch(
            "autospine_workbench.reviewed_seam_anchor_set_cli."
            "verify_reviewed_seam_anchor_set_command",
            side_effect=ReviewedSeamAnchorSetCommandError("private path"),
        ):
            status, output = self.dispatch([
                "verify-reviewed-seam-anchor-set", "sample",
                "--reviewed-set-sha256", SHA["reviewed_set"],
                "--bundle-sha256", SHA["bundle"],
            ])
        self.assertEqual(2, status)
        self.assertEqual(VERIFY_ERROR_CODE, json.loads(output)["error_code"])
        self.assertNotIn("private", output)

    def test_root_parser_registers_both_commands(self):
        self.assertEqual(
            "compile-reviewed-seam-anchor-set",
            build_root_parser().parse_args(compile_argv()).command,
        )


class ReviewedSeamAnchorSetCommandIntegrationTests(unittest.TestCase):
    def test_current_head_compile_reuse_verify_and_wrong_addresses(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PersistedReviewedSeamAnchorSetFixture(Path(temporary))
            prepared = SeamAnchorReviewApplication(fixture.state).prepare(
                fixture.address
            )
            keywords = {
                "layer_manifest_sha256": fixture.address.layer_manifest_sha256,
                "p3_rig_sha256": fixture.address.p3_rig_sha256,
                "p3_bundle_sha256": fixture.address.p3_bundle_sha256,
                "candidate_sha256": prepared.candidate_sha256,
                "review_revision": fixture.current_revision,
                "decision_sha256": fixture.current_head_sha256,
            }
            baseline = tree(fixture.state)
            for changed in (
                {"candidate_sha256": "f" * 64},
                {
                    "review_revision": fixture.published.review_revision,
                    "decision_sha256": fixture.published.decision_sha256,
                },
            ):
                with self.subTest(changed=changed), self.assertRaises(
                    ReviewedSeamAnchorSetCommandError
                ):
                    compile_reviewed_seam_anchor_set_command(
                        fixture.state,
                        fixture.address.project_id,
                        **(keywords | changed),
                    )
                self.assertEqual(baseline, tree(fixture.state))

            first = compile_reviewed_seam_anchor_set_command(
                fixture.state, fixture.address.project_id, **keywords
            )
            second = compile_reviewed_seam_anchor_set_command(
                fixture.state, fixture.address.project_id, **keywords
            )
            self.assertEqual(first, second)
            self.assertEqual("compiled", first.mode)
            verified = verify_reviewed_seam_anchor_set_command(
                fixture.state,
                fixture.address.project_id,
                reviewed_set_sha256=first.reviewed_set_sha256,
                bundle_sha256=first.bundle_sha256,
            )
            self.assertEqual(first.output, verified.output)
            before_wrong_verify = tree(fixture.state)
            with self.assertRaises(ReviewedSeamAnchorSetCommandError):
                verify_reviewed_seam_anchor_set_command(
                    fixture.state,
                    fixture.address.project_id,
                    reviewed_set_sha256="e" * 64,
                    bundle_sha256=first.bundle_sha256,
                )
            self.assertEqual(before_wrong_verify, tree(fixture.state))


if __name__ == "__main__":
    unittest.main()
