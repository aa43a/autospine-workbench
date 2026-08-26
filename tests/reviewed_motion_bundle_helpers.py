"""Shared exact P9 reviewed-motion storage fixture."""

from __future__ import annotations

from pathlib import Path

from autospine_workbench.motion_instance_v2_compiler import (
    compile_motion_instance_v2,
)
from autospine_workbench.motion_policy_decision import (
    build_motion_policy_decision,
)
from autospine_workbench.reviewed_motion_bundle_contract import (
    build_reviewed_motion_bundle_contract,
)
from autospine_workbench.reviewed_motion_bundle_store import (
    ReviewedMotionBundleStore,
)
from autospine_workbench.reviewed_motion_bundle_upstream import (
    require_reviewed_motion_upstreams,
)
from autospine_workbench.reviewed_motion_policy import (
    compile_reviewed_motion_policy,
)
from tests.motion_policy_decision_helpers import (
    MotionPolicyDecisionFixture,
    approved_review,
)


class ReviewedMotionStorageFixture:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.state_root = self.root / "state"
        source = MotionPolicyDecisionFixture(self.root / "upstream")
        self.mesh = source.upstream.mesh
        self.retarget = source.upstream.retarget
        decision = build_motion_policy_decision(
            source.foot,
            source.depth,
            review=approved_review(),
            decisions=source.accept_all(),
            root_release_keys=[],
            draw_order_loop_reset={"mode": "explicit", "approved": False},
        ).document
        policy = compile_reviewed_motion_policy(
            decision, source.foot, source.depth, self.mesh
        ).document
        base, target = require_reviewed_motion_upstreams(
            self.mesh, self.retarget
        )
        v2 = compile_motion_instance_v2(base, target, policy).document
        self.documents = (source.foot, source.depth, decision, policy, v2)
        self.contract = build_reviewed_motion_bundle_contract(
            self.mesh.project_id, *self.documents, self.mesh, base, target
        )

    def publish(self):
        return ReviewedMotionBundleStore(self.state_root).publish(
            self.mesh.project_id, *self.documents, self.mesh, self.retarget
        )
