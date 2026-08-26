"""Shared explicit review inputs for MotionPolicyDecision tests."""

from __future__ import annotations

from pathlib import Path

from autospine_workbench.depth_order_candidates import (
    compile_depth_order_candidates,
)
from autospine_workbench.depth_order_inputs import require_depth_order_inputs
from autospine_workbench.foot_lock_candidate import compile_foot_lock_candidates
from autospine_workbench.motion_policy_candidate_inventory import (
    derive_motion_policy_candidates,
)
from tests.depth_order_helpers import DepthOrderFixture


class MotionPolicyDecisionFixture:
    def __init__(
        self, root: Path, *, correction_limit: float = 10.0,
        residual_limit: float = 1_000_000.0,
    ) -> None:
        self.upstream = DepthOrderFixture(Path(root))
        inputs = require_depth_order_inputs(
            self.upstream.projected,
            self.upstream.retarget,
            self.upstream.mesh,
        )
        policy = self.upstream.policy(inputs)
        self.depth = compile_depth_order_candidates(
            self.upstream.projected,
            self.upstream.retarget,
            self.upstream.mesh,
            policy,
        ).document
        self.foot = compile_foot_lock_candidates(
            self.upstream.projected,
            self.upstream.retarget,
            max_correction_reference_ratio=correction_limit,
            max_residual_px=residual_limit,
        ).document

    def inventory(self, *, depth: dict | None = None):
        return derive_motion_policy_candidates(self.foot, depth or self.depth)

    def accept_all(self, *, depth: dict | None = None) -> list[dict]:
        return [{
            "candidate_id": candidate.candidate_id,
            "action": "accept",
            "reason_code": "human-reviewed",
            "payload": None,
        } for candidate in self.inventory(depth=depth).candidates]


def approved_review(revision: int = 1) -> dict:
    return {"status": "approved", "method": "human", "revision": revision}
