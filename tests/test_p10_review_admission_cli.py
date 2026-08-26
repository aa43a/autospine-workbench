"""Parser, canonical output, and redaction tests for P10.4a CLI."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_review_admission_cli import (  # noqa: E402
    COMMAND,
    ERROR_CODE,
)
from autospine_workbench.p10_review_admission_commands import (  # noqa: E402
    P10ReviewAdmissionCommandError,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.p10_review_admission_helpers import (  # noqa: E402
    P10ReviewAdmissionFixture,
)
from tests.p9_v2_helpers import tree  # noqa: E402


SHA_VALUES = tuple(character * 64 for character in "abcdefghijkl")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="review-admission-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("default-state"))
    return value


def argv() -> list[str]:
    values = [
        COMMAND, "sample",
        "--candidates", "private/candidates.json",
        "--decision", "private/decision.json",
        "--probe-report", "private/probe.json",
    ]
    for option, sha in zip(_SHA_OPTIONS, SHA_VALUES, strict=True):
        values.extend((option, sha))
    values.extend(("--visual-revision", "3", "--state-root", "private/state"))
    return values


def result() -> SimpleNamespace:
    claims = {
        "sampled_visual_approved": True,
        "head_observed_at_compile_time": True,
        "safe_range": False,
        "continuous_time": False,
        "reviewed_seam_anchors": False,
        "publishable_timeline": False,
        "release_authority": False,
    }
    gate = {"status": "blocked", "reason_codes": ["safe_range_unproven"]}
    document = {
        "format": "autospine-body-sway-review-admission",
        "project_id": "sample",
        "clip_id": "idle",
        "source": {
            "p10_chain": {"layer_manifest_sha256": SHA_VALUES[0]},
        },
        "status": "admitted_for_safety_analysis",
        "claims": claims,
        "release_gate": gate,
    }
    names = (
        "idle_behavior_candidates_sha256",
        "idle_behavior_decision_sha256",
        "body_sway_probe_report_sha256",
        "temporary_preview_sha256",
        "preview_artifact_set_sha256",
        "runtime_capture_manifest_sha256",
        "runtime_capture_bundle_sha256",
        "capture_artifact_set_sha256",
        "visual_candidate_sha256",
        "visual_decision_sha256",
        "admission_sha256",
    )
    values = {name: SHA_VALUES[index] for index, name in enumerate(names)}
    return SimpleNamespace(
        **values,
        visual_revision=3,
        input_paths=(Path(r"C:\private\candidate.json"),),
        document=document,
    )


class P10ReviewAdmissionCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = parser()

    def test_parser_requires_every_exact_input_and_integer_revision(self):
        parsed = self.parser.parse_args(argv())
        self.assertEqual(COMMAND, parsed.command)
        self.assertEqual(Path("private/candidates.json"), parsed.candidates)
        self.assertEqual(3, parsed.visual_revision)
        required = [
            "--candidates", "--decision", "--probe-report",
            *_SHA_OPTIONS, "--visual-revision",
        ]
        for option in required:
            values = argv()
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(option=option), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                self.parser.parse_args(values)
        values = argv()
        values[values.index("--visual-revision") + 1] = "not-an-integer"
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(values)

    @patch(
        "autospine_workbench.p10_review_admission_cli."
        "compile_body_sway_review_admission_command"
    )
    def test_summary_and_document_only_are_canonical_and_path_free(self, compile_):
        compiled = result()
        compile_.return_value = compiled
        outputs = []
        for extra in ([], ["--document-only"]):
            with redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args([*argv(), *extra])
                )
            self.assertEqual(0, status)
            outputs.append(output.getvalue().strip())
        summary, document = map(json.loads, outputs)
        self.assertEqual(compiled.admission_sha256,
                         summary["admission_sha256"])
        self.assertEqual(3, summary["inputs"]["visual_revision"])
        self.assertEqual(
            SHA_VALUES[0],
            summary["inputs"]["p10_chain"]["layer_manifest_sha256"],
        )
        self.assertEqual(compiled.document, document)
        self.assertNotIn("input_paths", outputs[0])
        self.assertNotIn(r"C:\private", "".join(outputs))
        self.assertEqual(outputs[1], json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ))

    @patch(
        "autospine_workbench.p10_review_admission_cli."
        "compile_body_sway_review_admission_command"
    )
    def test_command_failure_is_stable_and_redacted(self, compile_):
        private = r"C:\Users\private\review.json"
        compile_.side_effect = P10ReviewAdmissionCommandError(private)
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args(argv())
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual(ERROR_CODE, payload["error_code"])
        self.assertEqual("error", payload["status"])
        self.assertNotIn(private, output.getvalue())

    def test_real_command_is_deterministic_zero_write_and_path_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = P10ReviewAdmissionFixture(Path(temporary))
            command = _fixture_argv(fixture)
            before = tree(fixture.root)
            outputs = []
            for extra in ([], ["--document-only"]):
                with fake_runtime_profile(), redirect_stdout(
                    io.StringIO()
                ) as output:
                    status = dispatch_projection_stage_command(
                        self.parser.parse_args([*command, *extra])
                    )
                self.assertEqual(0, status)
                outputs.append(output.getvalue())
            self.assertEqual(before, tree(fixture.root))
            summary, document = map(json.loads, outputs)
            self.assertEqual(summary["admission_sha256"], _sha(document))
            self.assertNotIn("path", _recursive_keys(summary))
            self.assertNotIn("path", _recursive_keys(document))
            self.assertNotIn(str(fixture.root), "".join(outputs))


def _fixture_argv(fixture: P10ReviewAdmissionFixture) -> list[str]:
    values = [
        COMMAND, fixture.address.project_id,
        "--candidates", str(fixture.candidates_path),
        "--decision", str(fixture.decision_path),
        "--probe-report", str(fixture.probe_report_path),
    ]
    for name, value in fixture.command_kwargs.items():
        values.extend((f"--{name.replace('_', '-')}", str(value)))
    values.extend(("--state-root", str(fixture.state_root)))
    return values


def _sha(document: dict) -> str:
    import hashlib

    canonical = json.dumps(
        document, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _recursive_keys(value) -> set[str]:
    if type(value) is dict:
        return set(value).union(*(
            _recursive_keys(item) for item in value.values()
        ))
    if type(value) is list:
        return set().union(*(_recursive_keys(item) for item in value))
    return set()


_SHA_OPTIONS = (
    "--layer-manifest-sha256",
    "--p3-rig-sha256",
    "--p3-bundle-sha256",
    "--motion-instance-sha256",
    "--motion-retarget-bundle-sha256",
    "--motion-instance-v2-sha256",
    "--reviewed-motion-bundle-sha256",
    "--temporary-preview-sha256",
    "--runtime-capture-bundle-sha256",
    "--capture-artifact-set-sha256",
    "--visual-candidate-sha256",
    "--visual-decision-sha256",
)


if __name__ == "__main__":
    unittest.main()
