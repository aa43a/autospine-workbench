"""Shared exact P8/P5/P3-like fixtures for depth-order tests."""

from __future__ import annotations

import json
import math
from pathlib import Path

from autospine_workbench.kimodo_camera_projection import (
    compile_verified_kimodo_projection,
)
from autospine_workbench.mesh_bundle_contract import build_mesh_bundle_contract
from autospine_workbench.mesh_bundle_integrity import VerifiedMeshBundle
from autospine_workbench.mesh_probe_report import build_mesh_probe_report
from autospine_workbench.mesh_visual_artifacts import renderer_identities
from autospine_workbench.motion_mesh_regression import (
    build_motion_mesh_regression,
)
from autospine_workbench.motion_retarget_bundle_contract import (
    build_motion_retarget_bundle_contract,
)
from autospine_workbench.motion_retarget_bundle_integrity import (
    VerifiedMotionRetargetBundle,
)
from autospine_workbench.motion_retarget_compiler import compile_motion_instance
from autospine_workbench.motion_retarget_report import build_motion_retarget_report
from autospine_workbench.motion_target_profile import compile_motion_target_profile
from autospine_workbench.projected_motion_bundle_reader import (
    VerifiedProjectedMotionBundleReader,
)
from autospine_workbench.projected_motion_bundle_store import (
    ProjectedMotionBundleStore,
)
from autospine_workbench.projected_motion_compile_run import (
    build_projected_motion_compile_run,
)
from autospine_workbench.projected_motion_legacy import (
    compile_projected_motion_to_motion_ir,
)
from autospine_workbench.resolved_project import canonical_sha256
from tests.projected_motion_bundle_helpers import ProjectedBundleFixture
from tests.test_kimodo_camera_projection import camera_document
from tests.test_mesh_bundle_contract import payload_noop
from tests.test_motion_target_profile import ik_fixture
from tests.test_spine42_json_adapter import rig_fixture


def rotate_x(degrees: float):
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    return (
        (1.0, 0.0, 0.0),
        (0.0, cosine, -sine),
        (0.0, sine, cosine),
    )


class DepthOrderFixture:
    def __init__(
        self, root: Path, *, head_degrees: float = 60.0,
        depth_positive: str = "away_from_camera",
    ) -> None:
        motion = {
            "local_overrides": {
                (1, "Head"): rotate_x(head_degrees),
                (2, "Head"): rotate_x(head_degrees),
            }
        }
        base = ProjectedBundleFixture(Path(root), motion_kwargs=motion)
        base.camera = camera_document(
            base.mapping, depth_positive=depth_positive
        )
        base.projected = compile_verified_kimodo_projection(
            base.p7, base.camera
        )
        base.legacy = compile_projected_motion_to_motion_ir(
            base.projected.document
        )
        base.run = build_projected_motion_compile_run(
            base.p7, base.camera, base.projected, base.legacy
        )
        published = ProjectedMotionBundleStore(base.state).publish(
            base.camera, base.projected.document, base.run.document
        )
        self.projected = VerifiedProjectedMotionBundleReader(base.state).load(
            published.projected_motion_sha256, published.bundle_sha256
        )
        rig = rig_fixture()
        rig["slots"][1]["setup_attachment"] = "leg-image"
        rig["attachments"][1] = {
            "id": "leg-image",
            "slot": "leg",
            "type": "region",
            "image_path": "layers/leg.png",
            "image_sha256": "5" * 64,
            "source_layer_ids": ["leg-layer"],
            "canvas_offset_xy": [120, 250],
            "pivot_xy": [10, 20],
            "size": [20, 40],
        }
        rig["skins"]["default"]["leg"] = ["leg-image"]
        project_id, _old_rig, run, _probes, _visuals, _pngs = payload_noop()
        rig["capabilities"] = ["region_attachment", "setup_draw_order"]
        rig["source"]["run_manifest_sha256"] = canonical_sha256(run)
        rig["source"]["layer_manifest_sha256"] = run["inputs"][
            "layer_manifest_sha256"
        ]
        probes = build_mesh_probe_report(rig, run, ()).document
        visuals = {
            "format": "autospine-mesh-visual-artifacts",
            "format_version": 1,
            "project_id": project_id,
            "source": {
                "rig_sha256": canonical_sha256(rig),
                "run_manifest_sha256": canonical_sha256(run),
                "probes_sha256": canonical_sha256(probes),
            },
            "renderers": renderer_identities(),
            "status": "passed",
            "summary": "reviewed-noop",
            "images": [],
            "targets": [],
            "artifacts": [],
        }
        contract = build_mesh_bundle_contract(
            project_id, rig, run, probes, visuals, {}
        )
        inputs = run["inputs"]
        self.mesh = VerifiedMeshBundle(
            path=Path(root) / "synthetic-p3",
            project_id=contract.project_id,
            rig_sha256=contract.rig_sha256,
            run_sha256=contract.run_sha256,
            probes_sha256=contract.probes_sha256,
            visuals_sha256=contract.visuals_sha256,
            bundle_sha256=contract.bundle_sha256,
            base_rig_sha256=inputs["base_rig_sha256"],
            base_bundle_sha256=inputs["base_bundle_sha256"],
            layer_manifest_sha256=inputs["layer_manifest_sha256"],
            resolved_project_sha256=inputs["resolved_project_sha256"],
            _document_json_items=tuple(
                (name, data.decode("utf-8"))
                for name, data in contract.document_bytes.items()
            ),
            _png_items=tuple(contract.png_bytes_by_path.items()),
        )
        self.target = compile_motion_target_profile(
            ik_fixture(self.mesh), self.mesh
        )
        retargeted = compile_motion_instance(base.p7, self.target)
        report = build_motion_retarget_report(
            base.p7, self.target, retargeted
        )
        mesh_report = build_motion_mesh_regression(
            retargeted.instance, self.target.document, self.mesh
        )
        contract = build_motion_retarget_bundle_contract(
            self.mesh.project_id, self.target.document,
            retargeted.instance, retargeted.run,
            report.document, mesh_report.document,
        )
        target, instance = self.target.document, retargeted.instance
        source = {
            "p3_rig_sha256": target["source"]["p3"]["rig_sha256"],
            "p3_bundle_sha256": target["source"]["p3"]["bundle_sha256"],
            "p4_profile_sha256": target["source"]["p4_profile_sha256"],
            "p4_bundle_sha256": target["source"]["p4_bundle_sha256"],
            "motion_clip_sha256": instance["source"]["motion_ir_sha256"],
            "motion_bundle_sha256": instance["source"]["motion_bundle_sha256"],
        }
        self.retarget = VerifiedMotionRetargetBundle(
            path=Path(root) / "synthetic-p5",
            project_id=contract.project_id,
            clip_id=contract.clip_id,
            target_profile_sha256=contract.target_profile_sha256,
            instance_sha256=contract.instance_sha256,
            run_document_sha256=contract.run_document_sha256,
            retarget_report_sha256=contract.report_sha256,
            mesh_regression_sha256=contract.mesh_report_sha256,
            bundle_sha256=contract.bundle_sha256,
            _source_items=tuple(source.items()),
            _document_items=tuple(contract.document_bytes.items()),
        )

    def policy(self, inputs) -> dict:
        return {
            "format": "autospine-depth-pair-policy",
            "format_version": 1,
            "policy_id": "face-vs-leg.front-v1",
            "project_id": self.mesh.project_id,
            "clip_id": self.projected.clip_id,
            "source": json.loads(json.dumps(inputs.identities)),
            "review": {"status": "approved", "method": "human"},
            "hysteresis": {
                "unit": "root_reference_normalized_depth",
                "enter_threshold": 0.05,
                "exit_threshold": 0.02,
                "minimum_hold_frames": 2,
            },
            "pairs": [{
                "pair_id": "face-vs-leg",
                "slots": [
                    {"slot_id": "face", "depth_role": "humanoid.head"},
                    {
                        "slot_id": "leg",
                        "depth_role": "humanoid.leg.upper.left",
                    },
                ],
                "setup_front_slot": "face",
            }],
        }
