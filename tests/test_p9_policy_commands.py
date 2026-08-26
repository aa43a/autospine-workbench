"""Safe command-boundary tests for P9 human review compilation."""

from __future__ import annotations

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

from autospine_workbench.p9_policy_commands import (  # noqa: E402
    P9PolicyCommandError,
    compile_motion_policy_decision_command,
    compile_reviewed_motion_policy_command,
)
from tests.motion_policy_decision_helpers import (  # noqa: E402
    MotionPolicyDecisionFixture,
    approved_review,
)


class P9PolicyCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = MotionPolicyDecisionFixture(self.root)
        self.foot = self.write("foot.json", self.fixture.foot)
        self.depth = self.write("depth.json", self.fixture.depth)
        self.review = self.write("review.json", {
            "review": approved_review(),
            "decisions": self.fixture.accept_all(),
            "root_release_keys": [],
            "draw_order_loop_reset": {"mode": "explicit", "approved": False},
        })

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_decision_and_reviewed_policy_are_canonical_read_only_outputs(self):
        decision = compile_motion_policy_decision_command(
            self.foot, self.depth, self.review
        )
        decision_path = self.write("decision.json", decision.report)
        with patch(
            "autospine_workbench.p9_policy_commands.VerifiedMeshBundleReader"
        ) as reader:
            reader.return_value.load.return_value = self.fixture.upstream.mesh
            policy = compile_reviewed_motion_policy_command(
                self.root, self.fixture.upstream.mesh.project_id,
                self.foot, self.depth, decision_path,
                p3_rig_sha256=self.fixture.upstream.mesh.rig_sha256,
                p3_bundle_sha256=self.fixture.upstream.mesh.bundle_sha256,
            )
        self.assertEqual("autospine-motion-policy-decision",
                         decision.report["format"])
        self.assertEqual("autospine-reviewed-motion-policy",
                         policy.report["format"])
        self.assertEqual(64, len(decision.report_sha256))
        self.assertEqual(64, len(policy.report_sha256))
        reader.return_value.load.assert_called_once_with(
            self.fixture.upstream.mesh.project_id,
            self.fixture.upstream.mesh.rig_sha256,
            self.fixture.upstream.mesh.bundle_sha256,
        )

    def test_duplicate_json_and_extra_review_fields_fail_before_bundle_load(self):
        bad = self.root / "bad.json"
        bad.write_text('{"format":"a","format":"b"}', encoding="utf-8")
        with self.assertRaises(P9PolicyCommandError):
            compile_motion_policy_decision_command(bad, self.depth, self.review)
        review = json.loads(self.review.read_text("utf-8"))
        review["automatic_default"] = True
        extra = self.write("extra.json", review)
        with self.assertRaisesRegex(P9PolicyCommandError, "unsupported"):
            compile_motion_policy_decision_command(
                self.foot, self.depth, extra
            )
        with patch(
            "autospine_workbench.p9_policy_commands.VerifiedMeshBundleReader"
        ) as reader, self.assertRaises(P9PolicyCommandError):
            compile_reviewed_motion_policy_command(
                self.root, "sample", bad, self.depth, self.review,
                p3_rig_sha256="1" * 64, p3_bundle_sha256="2" * 64,
            )
        reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
