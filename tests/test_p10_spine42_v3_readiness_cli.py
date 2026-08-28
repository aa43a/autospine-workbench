"""Parser, command boundary, and canonical readiness CLI tests."""

from __future__ import annotations

import argparse
from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.cli import build_parser, main  # noqa: E402
import autospine_workbench.p10_spine42_v3_readiness_cli as cli  # noqa: E402
from autospine_workbench.p10_spine42_v3_readiness_commands import (  # noqa: E402
    P10Spine42V3ReadinessCommandError,
    P10Spine42V3ReadinessCommandResult,
    audit_body_sway_spine42_v3_readiness_command,
)
from autospine_workbench.spine42_v3_readiness_manifest import (  # noqa: E402
    canonical_spine42_v3_readiness_request_bytes,
    spine42_v3_readiness_request_sha256,
)
from autospine_workbench.spine42_v3_readiness import (  # noqa: E402
    audit_spine42_v3_readiness,
)
from autospine_workbench.spine42_v3_readiness_validation import (  # noqa: E402
    REPORT_DOMAIN,
)
from autospine_workbench.spine42_v3_raster_review_values import (  # noqa: E402
    domain_sha256,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="readiness-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    cli.add_p10_spine42_v3_readiness_subcommands(
        subparsers, Path("default-state")
    )
    return value


def argv(*extra: str) -> list[str]:
    return [
        cli.COMMAND,
        "--manifest", r"C:\private\readiness.json",
        "--state-root", r"C:\private\state",
        *extra,
    ]


def bare_report() -> dict:
    return {
        "format": "autospine-spine42-v3-readiness-report",
        "format_version": 1,
        "samples": [{
            "project_id": "sample-a",
            "status": "blocked",
            "blockers": [{
                "code": "reviewed_motion_address_missing",
                "stage": "P9",
            }],
        }],
        "status": "blocked_prerequisites_or_review",
        "readiness_report_sha256": "b" * 64,
    }


def command_result() -> P10Spine42V3ReadinessCommandResult:
    return P10Spine42V3ReadinessCommandResult(
        request_sha256="a" * 64,
        _canonical_json=json.dumps(
            bare_report(), sort_keys=True, separators=(",", ":")
        ),
    )


def all_null_request() -> dict:
    return {
        "format": "autospine-spine42-v3-readiness-request",
        "format_version": 1,
        "samples": [{
            "project_id": "sample-a",
            "layer_manifest_sha256": "1" * 64,
            "p3_rig_sha256": "2" * 64,
            "p3_bundle_sha256": "3" * 64,
            "reviewed_motion_address": None,
            "reviewed_seam_anchor_set_address": None,
            "motion_instance_v3_address": None,
            "spine42_v3_address": None,
            "runtime_capture_address": None,
            "raster_review_decision": None,
        }],
    }


class P10Spine42V3ReadinessCliTests(unittest.TestCase):
    def test_parser_requires_manifest_and_root_registers_command(self):
        parsed = parser().parse_args(argv())
        self.assertEqual(Path(r"C:\private\readiness.json"), parsed.manifest)
        self.assertEqual(Path(r"C:\private\state"), parsed.state_root)
        values = argv()
        index = values.index("--manifest")
        del values[index:index + 2]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser().parse_args(values)
        self.assertIn(
            cli.COMMAND,
            build_parser()._subparsers._group_actions[0].choices,
        )

    @patch.object(cli, "audit_body_sway_spine42_v3_readiness_command")
    def test_default_wrapper_is_canonical_and_root_dispatches(self, service):
        service.return_value = command_result()
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, main(argv()))
        payload = json.loads(output.getvalue())
        self.assertEqual({
            "mode": "audited",
            "ok": True,
            "readiness": bare_report(),
            "request_sha256": "a" * 64,
        }, payload)
        service.assert_called_once_with(
            Path(r"C:\private\state"),
            Path(r"C:\private\readiness.json"),
        )
        self.assertNotIn(r"C:\private", output.getvalue())
        self.assertEqual(
            json.dumps(
                payload, ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            ),
            output.getvalue().strip(),
        )

    @patch.object(cli, "audit_body_sway_spine42_v3_readiness_command")
    def test_document_only_returns_bare_business_status(self, service):
        service.return_value = command_result()
        with redirect_stdout(io.StringIO()) as output:
            status = cli.dispatch_p10_spine42_v3_readiness_command(
                parser().parse_args(argv("--document-only"))
            )
        self.assertEqual(0, status)
        self.assertEqual(bare_report(), json.loads(output.getvalue()))
        self.assertNotIn('"ok"', output.getvalue())
        self.assertNotIn('"mode"', output.getvalue())

    @patch.object(cli, "audit_body_sway_spine42_v3_readiness_command")
    def test_failure_is_fixed_redacted_and_unrelated_is_ignored(self, service):
        private = r"C:\private\readiness.json: duplicate key"
        service.side_effect = P10Spine42V3ReadinessCommandError(private)
        with redirect_stdout(io.StringIO()) as output:
            status = cli.dispatch_p10_spine42_v3_readiness_command(
                parser().parse_args(argv())
            )
        self.assertEqual(2, status)
        self.assertEqual({
            "error_code": cli.ERROR_CODE,
            "message": cli.ERROR_MESSAGE,
            "ok": False,
            "status": "error",
        }, json.loads(output.getvalue()))
        self.assertNotIn(private, output.getvalue())
        self.assertIsNone(cli.dispatch_p10_spine42_v3_readiness_command(
            argparse.Namespace(command="unrelated")
        ))


class P10Spine42V3ReadinessCommandTests(unittest.TestCase):
    def test_all_null_downstream_request_is_read_once_and_zero_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            state.mkdir()
            manifest = root / "request.json"
            request = all_null_request()
            manifest.write_bytes(
                canonical_spine42_v3_readiness_request_bytes(request)
            )
            expected = audit_spine42_v3_readiness(request, state)
            evaluator = Mock(return_value=expected)
            before = tuple(state.rglob("*"))
            result = audit_body_sway_spine42_v3_readiness_command(
                state, manifest, evaluator=evaluator
            )
            self.assertEqual(before, tuple(state.rglob("*")))
            self.assertEqual(expected, result.document)
            self.assertEqual(
                spine42_v3_readiness_request_sha256(request),
                result.request_sha256,
            )
            evaluator.assert_called_once_with(request, state)

    def test_actual_all_null_audit_returns_ordered_structured_blockers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            state.mkdir()
            manifest = root / "request.json"
            manifest.write_bytes(
                canonical_spine42_v3_readiness_request_bytes(
                    all_null_request()
                )
            )
            before = tuple(state.rglob("*"))
            result = audit_body_sway_spine42_v3_readiness_command(
                state, manifest
            )
            self.assertEqual(before, tuple(state.rglob("*")))
            report = result.document
            self.assertEqual(
                "blocked_prerequisites_or_review", report["status"]
            )
            checkpoints = report["samples"][0]["checkpoints"]
            self.assertEqual(8, len(checkpoints))
            self.assertEqual(
                "exact_reviewed_motion_address_not_declared",
                checkpoints[1]["reason_codes"][0],
            )
            self.assertEqual(
                "runtime_capture_address_not_declared",
                checkpoints[5]["reason_codes"][0],
            )
            self.assertTrue(all(
                row["next_action_code"] for row in checkpoints
            ))

    def test_noncanonical_manifest_is_a_fixed_command_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "request.json"
            manifest.write_text(
                json.dumps(all_null_request(), indent=2), encoding="utf-8"
            )
            with self.assertRaises(P10Spine42V3ReadinessCommandError):
                audit_body_sway_spine42_v3_readiness_command(
                    root / "state", manifest, evaluator=Mock()
                )

    def test_injected_evaluator_cannot_bypass_report_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "request.json"
            manifest.write_bytes(
                canonical_spine42_v3_readiness_request_bytes(
                    all_null_request()
                )
            )
            with self.assertRaises(P10Spine42V3ReadinessCommandError):
                audit_body_sway_spine42_v3_readiness_command(
                    root / "state", manifest,
                    evaluator=Mock(return_value=bare_report()),
                )

    def test_valid_report_must_be_bound_to_the_exact_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "request.json"
            value = all_null_request()
            manifest.write_bytes(
                canonical_spine42_v3_readiness_request_bytes(value)
            )
            report = deepcopy(audit_spine42_v3_readiness(value, root / "state"))
            report["request_sha256"] = "f" * 64
            body = deepcopy(report)
            body.pop("readiness_report_sha256")
            report["readiness_report_sha256"] = domain_sha256(
                REPORT_DOMAIN, body
            )
            with self.assertRaises(P10Spine42V3ReadinessCommandError):
                audit_body_sway_spine42_v3_readiness_command(
                    root / "state", manifest,
                    evaluator=Mock(return_value=report),
                )


if __name__ == "__main__":
    unittest.main()
