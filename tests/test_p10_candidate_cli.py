"""Canonical parser and CLI tests for P10 candidate compilation."""

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

from autospine_workbench.cli import main  # noqa: E402
from autospine_workbench.p10_candidate_commands import (  # noqa: E402
    P10CandidateCommandError,
    P10CandidateCommandResult,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)
from tests.p10_candidate_helpers import P10PersistedFixture  # noqa: E402
from tests.p9_v2_helpers import tree  # noqa: E402


FIELDS = (
    "layer-manifest-sha256",
    "p3-rig-sha256",
    "p3-bundle-sha256",
    "motion-instance-sha256",
    "motion-retarget-bundle-sha256",
    "motion-instance-v2-sha256",
    "reviewed-motion-bundle-sha256",
)
SHAS = {field: f"{index:x}" * 64 for index, field in enumerate(FIELDS, 1)}


def parser(default: Path) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, default)
    return value


def argv(*extra: str) -> list[str]:
    result = ["compile-idle-behavior-candidates", "sample"]
    for field in FIELDS:
        result.extend((f"--{field}", SHAS[field]))
    return [*result, *extra]


def command_result() -> P10CandidateCommandResult:
    document = {
        "format": "autospine-idle-behavior-candidates",
        "format_version": 1,
        "summary": {"status": "candidate_only"},
    }
    return P10CandidateCommandResult(
        input_paths=(Path("exact/manifest"), Path("exact/p9")),
        idle_behavior_candidates_sha256="f" * 64,
        document=document,
    )


class P10CandidateCliDispatchTests(unittest.TestCase):
    def test_parser_requires_addresses_and_accepts_state_default_override(self):
        default = Path("default-state")
        parsed = parser(default).parse_args(argv())
        self.assertEqual(default, parsed.state_root)
        override = parser(default).parse_args(
            argv("--state-root", "other-state")
        )
        self.assertEqual(Path("other-state"), override.state_root)
        for field in FIELDS:
            values = argv()
            index = values.index(f"--{field}")
            del values[index:index + 2]
            with self.subTest(field=field), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                parser(default).parse_args(values)

    def test_dispatch_passes_every_exact_identity_and_wraps_paths(self):
        with patch(
            "autospine_workbench.p10_candidate_cli."
            "compile_idle_behavior_candidates_command",
            return_value=command_result(),
        ) as service, redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                parser(Path("state")).parse_args(argv())
            )
        self.assertEqual(0, status)
        service.assert_called_once_with(
            Path("state"),
            "sample",
            layer_manifest_sha256=SHAS["layer-manifest-sha256"],
            p3_rig_sha256=SHAS["p3-rig-sha256"],
            p3_bundle_sha256=SHAS["p3-bundle-sha256"],
            motion_instance_sha256=SHAS["motion-instance-sha256"],
            motion_retarget_bundle_sha256=(
                SHAS["motion-retarget-bundle-sha256"]
            ),
            motion_instance_v2_sha256=SHAS["motion-instance-v2-sha256"],
            reviewed_motion_bundle_sha256=(
                SHAS["reviewed-motion-bundle-sha256"]
            ),
        )
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual("f" * 64, payload["idle_behavior_candidates_sha256"])
        self.assertEqual(
            [str(Path("exact/manifest")), str(Path("exact/p9"))],
            payload["input_paths"],
        )

    def test_document_only_is_stable_canonical_and_excludes_wrapper(self):
        lines = []
        for _index in range(2):
            with patch(
                "autospine_workbench.p10_candidate_cli."
                "compile_idle_behavior_candidates_command",
                return_value=command_result(),
            ), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, dispatch_projection_stage_command(
                    parser(Path("state")).parse_args(argv("--document-only"))
                ))
            lines.append(output.getvalue().strip())
        self.assertEqual(lines[0], lines[1])
        self.assertEqual(command_result().document, json.loads(lines[0]))
        self.assertNotIn("input_paths", lines[0])
        self.assertNotIn("idle_behavior_candidates_sha256", lines[0])
        self.assertEqual(
            json.dumps(
                command_result().document,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            lines[0],
        )

    def test_domain_error_is_canonical_and_returns_two(self):
        with patch(
            "autospine_workbench.p10_candidate_cli."
            "compile_idle_behavior_candidates_command",
            side_effect=P10CandidateCommandError("broken"),
        ), redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                parser(Path("state")).parse_args(argv())
            )
        self.assertEqual(2, status)
        self.assertEqual(
            {"error": "broken", "ok": False, "status": "error"},
            json.loads(output.getvalue()),
        )


class P10CandidateIntegratedCliTests(unittest.TestCase):
    def test_document_only_uses_persisted_readers_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = P10PersistedFixture(Path(temporary))
            values = [
                "compile-idle-behavior-candidates",
                fixture.mesh.project_id,
            ]
            for field, value in fixture.command_kwargs.items():
                values.extend((f"--{field.replace('_', '-')}", value))
            values.extend((
                "--state-root", str(fixture.state), "--document-only",
            ))
            before = tree(fixture.state)
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, main(values))
            self.assertEqual(before, tree(fixture.state))
            document = json.loads(output.getvalue())
            self.assertEqual(
                "autospine-idle-behavior-candidates", document["format"]
            )
            self.assertEqual("candidate_only", document["summary"]["status"])
            self.assertNotIn("input_paths", output.getvalue())


if __name__ == "__main__":
    unittest.main()
