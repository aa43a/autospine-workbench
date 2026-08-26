"""Parser, dispatch, and aggregate CLI tests for P10 decisions."""

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
from autospine_workbench.p10_decision_commands import (  # noqa: E402
    P10DecisionCommandError,
    P10DecisionCommandResult,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)
from tests.p10_decision_command_helpers import (  # noqa: E402
    candidate_document,
    review_input,
    write_json,
)
from tests.p9_v2_helpers import tree  # noqa: E402


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("state"))
    return value


def argv(*extra: str) -> list[str]:
    return [
        "compile-idle-behavior-decision",
        "--candidates", "candidates.json",
        "--review-input", "review.json",
        *extra,
    ]


def result() -> P10DecisionCommandResult:
    document = {
        "format": "autospine-idle-behavior-decision",
        "format_version": 1,
        "summary": {"decision_count": 1},
    }
    return P10DecisionCommandResult(
        input_paths=(Path("candidates.json"), Path("review.json")),
        idle_behavior_candidates_sha256="a" * 64,
        idle_behavior_decision_sha256="b" * 64,
        document=document,
    )


class P10DecisionCliDispatchTests(unittest.TestCase):
    def test_parser_requires_both_paths_and_has_no_state_argument(self):
        parsed = parser().parse_args(argv())
        self.assertEqual(Path("candidates.json"), parsed.candidates)
        self.assertEqual(Path("review.json"), parsed.review_input)
        self.assertFalse(hasattr(parsed, "state_root"))
        for flag in ("--candidates", "--review-input"):
            values = argv()
            index = values.index(flag)
            del values[index:index + 2]
            with self.subTest(flag=flag), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                parser().parse_args(values)

    def test_dispatch_is_canonical_and_passes_exact_paths(self):
        with patch(
            "autospine_workbench.p10_decision_cli."
            "compile_idle_behavior_decision_command",
            return_value=result(),
        ) as service, redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                parser().parse_args(argv())
            )
        self.assertEqual(0, status)
        service.assert_called_once_with(
            Path("candidates.json"), Path("review.json")
        )
        line = output.getvalue().strip()
        payload = json.loads(line)
        self.assertTrue(payload["ok"])
        self.assertEqual("a" * 64, payload["idle_behavior_candidates_sha256"])
        self.assertEqual("b" * 64, payload["idle_behavior_decision_sha256"])
        self.assertEqual(
            json.dumps(
                payload, ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            ),
            line,
        )

    def test_document_only_is_stable_and_excludes_wrapper(self):
        lines = []
        for _index in range(2):
            with patch(
                "autospine_workbench.p10_decision_cli."
                "compile_idle_behavior_decision_command",
                return_value=result(),
            ), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, dispatch_projection_stage_command(
                    parser().parse_args(argv("--document-only"))
                ))
            lines.append(output.getvalue().strip())
        self.assertEqual(lines[0], lines[1])
        self.assertEqual(result().document, json.loads(lines[0]))
        self.assertNotIn("input_paths", lines[0])
        self.assertNotIn("idle_behavior_decision_sha256", lines[0])

    def test_domain_error_is_canonical_and_returns_two(self):
        with patch(
            "autospine_workbench.p10_decision_cli."
            "compile_idle_behavior_decision_command",
            side_effect=P10DecisionCommandError("broken"),
        ), redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                parser().parse_args(argv())
            )
        self.assertEqual(2, status)
        self.assertEqual(
            {"error": "broken", "ok": False, "status": "error"},
            json.loads(output.getvalue()),
        )


class P10DecisionIntegratedCliTests(unittest.TestCase):
    def test_main_reads_exact_files_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = candidate_document()
            candidate_path = write_json(root / "candidates.json", candidates)
            review_path = write_json(
                root / "review.json", review_input(candidates)
            )
            before = tree(root)
            with redirect_stdout(io.StringIO()) as output:
                status = main([
                    "compile-idle-behavior-decision",
                    "--candidates", str(candidate_path),
                    "--review-input", str(review_path),
                    "--document-only",
                ])
            self.assertEqual(0, status)
            self.assertEqual(before, tree(root))
            document = json.loads(output.getvalue())
            self.assertEqual(
                "autospine-idle-behavior-decision", document["format"]
            )
            self.assertEqual(1, document["summary"]["decision_count"])
            self.assertNotIn("input_paths", output.getvalue())


if __name__ == "__main__":
    unittest.main()
