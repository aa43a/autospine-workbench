"""CLI safety contract for non-authoritative P9 draft preparation."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p9_review_draft import (  # noqa: E402
    P9ReviewDraftResult,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)


SHA = "a" * 64


class P9ReviewDraftCliTests(unittest.TestCase):
    def parser(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command", required=True)
        add_projection_stage_subcommands(subparsers, Path("state"))
        return parser

    def argv(self):
        result = [
            "prepare-motion-policy-review-draft", "sample",
            "wave-left-r15-draft",
        ]
        for field in (
            "p3-rig", "p3-bundle", "p4-profile", "p4-bundle",
            "motion-instance", "motion-retarget-bundle", "p7-motion",
            "p7-bundle", "p8-motion", "p8-bundle",
        ):
            result.extend((f"--{field}-sha256", SHA))
        result.extend((
            "--first-slot-id", "moving", "--second-slot-id", "face",
            "--pair-id", "moving-vs-face", "--state-root",
            "C:/private/autospine-review-state",
        ))
        return result

    def test_success_receipt_cannot_claim_approval_or_adoption(self):
        prepared = P9ReviewDraftResult(
            motion_namespace="wave-left-r15-draft",
            project_id="sample",
            reused=False,
            manifest_sha256="b" * 64,
            foot_candidates_sha256="c" * 64,
            proposal_sha256="d" * 64,
        )
        with patch(
            "autospine_workbench.p9_review_draft_cli."
            "prepare_p9_review_draft",
            return_value=prepared,
        ) as prepare, redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser().parse_args(self.argv())
            )
        self.assertEqual(0, status)
        result = json.loads(output.getvalue())
        self.assertEqual(
            "pending_human_depth_policy_review", result["status"]
        )
        self.assertFalse(result["approved_depth_policy"])
        self.assertFalse(result["depth_candidates_emitted"])
        self.assertFalse(result["p9_adoption_emitted"])
        self.assertNotIn("directory", result)
        self.assertNotIn("input_bundle_paths", output.getvalue())
        self.assertNotIn("private", output.getvalue())
        self.assertNotIn("autospine-review-state", output.getvalue())
        self.assertEqual(
            Path("C:/private/autospine-review-state"),
            prepare.call_args.args[0],
        )


if __name__ == "__main__":
    unittest.main()
