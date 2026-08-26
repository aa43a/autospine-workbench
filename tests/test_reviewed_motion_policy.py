"""End-to-end P9.4 ReviewedMotionPolicy compiler tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_policy_decision import (  # noqa: E402
    build_motion_policy_decision,
)
from autospine_workbench.reviewed_motion_policy import (  # noqa: E402
    ReviewedMotionPolicyError,
    compile_reviewed_motion_policy,
)
from autospine_workbench.reviewed_motion_policy_validation import (  # noqa: E402
    require_reviewed_motion_policy,
)
from tests.motion_policy_decision_helpers import (  # noqa: E402
    MotionPolicyDecisionFixture,
    approved_review,
)


class ReviewedMotionPolicyTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return MotionPolicyDecisionFixture(Path(temporary.name))

    def decision(self, fixture, depth=None, *, reject_depth=False, reset=False):
        selected_depth = fixture.depth if depth is None else depth
        decisions = fixture.accept_all(depth=selected_depth)
        if reject_depth:
            for row in decisions:
                if row["candidate_id"].startswith("depth-"):
                    row.update({
                        "action": "reject",
                        "reason_code": "keep-reviewed-setup-order",
                    })
        return build_motion_policy_decision(
            fixture.foot,
            selected_depth,
            review=approved_review(),
            decisions=decisions,
            root_release_keys=[],
            draw_order_loop_reset={"mode": "explicit", "approved": reset},
        ).document

    def test_compiles_exact_canonical_policy_without_mutating_inputs(self):
        fixture = self.fixture()
        decision = self.decision(fixture)
        before = deepcopy(decision)
        first = compile_reviewed_motion_policy(
            decision, fixture.foot, fixture.depth, fixture.upstream.mesh
        )
        second = compile_reviewed_motion_policy(
            deepcopy(decision), deepcopy(fixture.foot),
            deepcopy(fixture.depth), fixture.upstream.mesh,
        )
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(before, decision)
        document = first.document
        require_reviewed_motion_policy(document)
        self.assertEqual(
            fixture.upstream.mesh.rig_sha256,
            document["source"]["p3"]["rig_sha256"],
        )
        self.assertEqual(
            document["timing"]["frame_count"],
            len(document["root_correction_keys"]),
        )
        self.assertEqual(
            ["leg", "face"], document["slot_order"]["setup_slot_ids"]
        )
        changed = first.document
        changed["root_correction_keys"][0]["correction_xy_px"][0] = 99.0
        self.assertNotEqual(changed, first.document)

    def test_static_loop_is_valid_without_a_redundant_reset_key(self):
        fixture = self.fixture()
        loop_depth = deepcopy(fixture.depth)
        loop_depth["timing"]["loop"] = True
        decision = self.decision(
            fixture, loop_depth, reject_depth=True, reset=False
        )
        policy = compile_reviewed_motion_policy(
            decision, fixture.foot, loop_depth, fixture.upstream.mesh
        ).document
        self.assertEqual(
            [{"tick": 0, "slot_ids": ["leg", "face"]}],
            policy["slot_order"]["keys"],
        )
        self.assertEqual([0.0, 0.0],
                         policy["root_correction_keys"][0]["correction_xy_px"])
        self.assertEqual([0.0, 0.0],
                         policy["root_correction_keys"][-1]["correction_xy_px"])

    def test_stale_or_spoofed_p3_bundle_fails_closed(self):
        fixture = self.fixture()
        decision = self.decision(fixture)
        spoofed = replace(fixture.upstream.mesh, rig_sha256="f" * 64)
        with self.assertRaises(ReviewedMotionPolicyError):
            compile_reviewed_motion_policy(
                decision, fixture.foot, fixture.depth, spoofed
            )
        stale = deepcopy(decision)
        stale["source"]["p3"]["rig_sha256"] = "e" * 64
        with self.assertRaises(ReviewedMotionPolicyError):
            compile_reviewed_motion_policy(
                stale, fixture.foot, fixture.depth, fixture.upstream.mesh
            )


if __name__ == "__main__":
    unittest.main()
