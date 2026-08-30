"""Pending depth-pair proposal tests."""

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

from autospine_workbench.depth_order_inputs import (  # noqa: E402
    require_depth_order_inputs,
)
from autospine_workbench.depth_pair_policy import (  # noqa: E402
    require_depth_pair_policy,
)
from autospine_workbench.depth_pair_policy_proposal import (  # noqa: E402
    DepthPairPolicyProposalError,
    compile_depth_pair_policy_proposal,
)
from tests.depth_order_helpers import DepthOrderFixture  # noqa: E402


class DepthPairPolicyProposalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = DepthOrderFixture(Path(temporary.name))
        self.inputs = require_depth_order_inputs(
            fixture.projected, fixture.retarget, fixture.mesh
        )

    def proposal(self, inputs=None):
        return compile_depth_pair_policy_proposal(
            inputs or self.inputs,
            motion_id="wave-left-r15-draft",
            pair_id="face-vs-moving-layer",
            first_slot_id="leg",
            second_slot_id="face",
        )

    def test_proposal_stays_pending_and_projects_to_a_valid_policy(self):
        proposal = self.proposal()
        self.assertEqual(
            "autospine-depth-pair-policy-proposal", proposal["format"]
        )
        self.assertEqual(
            {"status": "pending_human_review", "method": "human"},
            proposal["review"],
        )
        self.assertEqual("face", proposal["pairs"][0]["setup_front_slot"])
        self.assertEqual(
            ["face", "leg"],
            [row["slot_id"] for row in proposal["pairs"][0]["slots"]],
        )
        approved = deepcopy(proposal)
        approved["format"] = "autospine-depth-pair-policy"
        approved["review"] = {"status": "approved", "method": "human"}
        approved.pop("proposal")
        require_depth_pair_policy(approved, inputs=self.inputs)

    def test_role_is_derived_from_current_slot_bone(self):
        rig = deepcopy(self.inputs.rig)
        next(row for row in rig["slots"] if row["id"] == "leg")[
            "bone"
        ] = "upper-arm.left"
        changed = replace(self.inputs, rig=rig)
        proposal = self.proposal(changed)
        roles = {
            row["slot_id"]: row["depth_role"]
            for row in proposal["pairs"][0]["slots"]
        }
        self.assertEqual("humanoid.arm.upper.left", roles["leg"])

    def test_missing_duplicate_or_unobservable_scope_fails(self):
        cases = (
            {"first_slot_id": "missing", "second_slot_id": "face"},
            {"first_slot_id": "face", "second_slot_id": "face"},
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(
                DepthPairPolicyProposalError
            ):
                compile_depth_pair_policy_proposal(
                    self.inputs,
                    motion_id="wave-left-r15-draft",
                    pair_id="face-vs-moving-layer",
                    **values,
                )

    def test_proposal_never_emits_an_unapprovable_policy_shell(self):
        invalid = (
            {"motion_id": "m" * 127, "pair_id": "p" * 127},
            {"enter_threshold": 1025.0, "exit_threshold": 1.0},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(
                DepthPairPolicyProposalError
            ):
                compile_depth_pair_policy_proposal(
                    self.inputs,
                    motion_id=values.get("motion_id", "wave-left-r15-draft"),
                    pair_id=values.get("pair_id", "face-vs-moving-layer"),
                    first_slot_id="leg",
                    second_slot_id="face",
                    enter_threshold=values.get("enter_threshold", 0.05),
                    exit_threshold=values.get("exit_threshold", 0.02),
                )


if __name__ == "__main__":
    unittest.main()
