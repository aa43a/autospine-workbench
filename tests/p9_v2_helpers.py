"""Shared exact in-memory inputs for P9.5 command boundary tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from tests.filesystem_snapshot import snapshot_file

from autospine_workbench.motion_policy_decision import (
    build_motion_policy_decision,
)
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.reviewed_motion_policy import (
    compile_reviewed_motion_policy,
)
from tests.motion_policy_decision_helpers import (
    MotionPolicyDecisionFixture,
    approved_review,
)


class P9V2Fixture:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        source = MotionPolicyDecisionFixture(self.root)
        decision = build_motion_policy_decision(
            source.foot,
            source.depth,
            review=approved_review(),
            decisions=source.accept_all(),
            root_release_keys=[],
            draw_order_loop_reset={"mode": "explicit", "approved": False},
        ).document
        self.policy = compile_reviewed_motion_policy(
            decision, source.foot, source.depth, source.upstream.mesh
        ).document
        self.p5 = source.upstream.retarget
        rig = source.upstream.mesh.rig
        images = {}
        for index, attachment in enumerate(rig["attachments"]):
            width, height = attachment["size"]
            pixel = bytes((20 + index, 40 + index, 60 + index, 255))
            images[attachment["id"]] = encode_rgba_png(
                RgbaImage(width, height, pixel * (width * height))
            )
        self.mesh = SimpleNamespace(
            path=self.root / "exact-p3",
            project_id=source.upstream.mesh.project_id,
            p3_rig_sha256=source.upstream.mesh.rig_sha256,
            p3_bundle_sha256=source.upstream.mesh.bundle_sha256,
            rig=rig,
            png_by_attachment=images,
        )
        self.policy_path = self.root / "reviewed-policy.json"
        self.policy_path.write_text(
            json.dumps(
                self.policy,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        self.state = self.root / "state"
        self.state.mkdir(exist_ok=True)
        (self.state / "sentinel.txt").write_text("unchanged", encoding="utf-8")

    @property
    def project_id(self) -> str:
        return self.p5.project_id


def tree(root: Path) -> dict:
    return {
        path.relative_to(root).as_posix(): snapshot_file(root, path)
        for path in root.rglob("*")
        if path.is_file()
    }
