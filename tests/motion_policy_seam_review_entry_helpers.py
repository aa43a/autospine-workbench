"""Persisted A/B inputs for P9-to-seam review entry tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from autospine_workbench.depth_order_inputs import require_depth_order_inputs
from autospine_workbench.depth_pair_policy import depth_pair_policy_sha256
from autospine_workbench.layer_manifest import LayerManifestBundleStore
from autospine_workbench.mesh_bundle_reader import VerifiedMeshBundleReader
from autospine_workbench.mesh_bundle_store import MeshBundleStore
from autospine_workbench.mesh_pipeline import VerifiedMeshPipeline
from autospine_workbench.motion_policy_review_packages import (
    list_motion_policy_review_packages,
)
from autospine_workbench.region_rig import compile_region_rig
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.rig_bundle import RigBundleStore
from tests.motion_policy_decision_helpers import MotionPolicyDecisionFixture
from tests.motion_policy_review_package_helpers import write_review_package
from tests.p10_candidate_helpers import PROJECT, _resolved_for_project
from tests.test_seam_anchor_review_http_evidence_e2e import (
    _manifest_and_assets,
)
from tests.test_verified_mesh_compiler import _probes


class MotionPolicySeamReviewEntryFixture:
    """Build one observable A and one lower-limb-unobservable B package."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.state = self.root / "state"
        source = MotionPolicyDecisionFixture(self.root / "motion-source")
        inputs = require_depth_order_inputs(
            source.upstream.projected,
            source.upstream.retarget,
            source.upstream.mesh,
        )
        self.base_policy = source.upstream.policy(inputs)
        self.base_foot = source.foot
        self.base_depth = source.depth
        self.mesh_a = self._publish_mesh("a", blocked=False)
        self.mesh_b = self._publish_mesh("b", blocked=True)
        self._write_package(self.mesh_a, "motion-a")
        self._write_package(self.mesh_b, "motion-b")
        self._write_package(
            self.mesh_a, "motion-crosswired",
            layer_manifest_sha256="f" * 64,
        )
        rows = list_motion_policy_review_packages(self.state)["packages"]
        self.package_ids = {
            row["motion_id"]: row["package_id"] for row in rows
        }

    def _publish_mesh(self, suffix: str, *, blocked: bool):
        manifest, assets, sizes = _manifest_and_assets(
            self.root / f"assets-{suffix}"
        )
        if blocked:
            manifest["layers"] = [
                row for row in manifest["layers"]
                if row["semantic"]["canonical_role"]
                != "body.leg"
            ]
            kept = {row["layer_id"] for row in manifest["layers"]}
            assets = {key: value for key, value in assets.items() if key in kept}
            sizes = {key: value for key, value in sizes.items() if key in kept}
        compiled = compile_region_rig(
            manifest,
            _resolved_for_project(),
            layer_manifest_sha256=canonical_sha256(manifest),
            image_sizes=sizes,
        )
        layers, _manifest_sha = LayerManifestBundleStore(
            self.state
        ).publish(PROJECT, manifest, assets)
        rig_path, rig_sha = RigBundleStore(self.state).publish(
            PROJECT,
            compiled.rig,
            compiled.run_manifest,
            _probes(PROJECT, compiled.rig, compiled.run_manifest),
            layers,
        )
        result = VerifiedMeshPipeline(self.state).build(
            PROJECT, rig_sha, rig_path.name,
        )
        address = MeshBundleStore(self.state).publish(
            PROJECT,
            result.rig,
            result.run_manifest,
            result.probes,
            result.visuals,
            result.pngs,
        )
        return VerifiedMeshBundleReader(self.state).load(
            PROJECT, address.rig_sha256, address.bundle_sha256,
        )

    def _write_package(
        self, mesh, motion_id: str, *,
        layer_manifest_sha256: str | None = None,
    ) -> None:
        policy = deepcopy(self.base_policy)
        foot = deepcopy(self.base_foot)
        depth = deepcopy(self.base_depth)
        for document in (policy, foot, depth):
            document["project_id"] = PROJECT
        p3 = _p3_source(mesh)
        if layer_manifest_sha256 is not None:
            p3["layer_manifest_sha256"] = layer_manifest_sha256
        policy["source"]["p3"] = deepcopy(p3)
        depth["source"]["p3"] = deepcopy(p3)
        foot["source"]["p3_rig_sha256"] = mesh.rig_sha256
        foot["source"]["p3_bundle_sha256"] = mesh.bundle_sha256
        depth["source"]["depth_pair_policy_sha256"] = (
            depth_pair_policy_sha256(policy)
        )
        write_review_package(
            self.state, policy, foot, depth, motion_id=motion_id,
        )


def _p3_source(mesh) -> dict[str, str]:
    return {
        "base_rig_sha256": mesh.base_rig_sha256,
        "base_bundle_sha256": mesh.base_bundle_sha256,
        "layer_manifest_sha256": mesh.layer_manifest_sha256,
        "resolved_project_sha256": mesh.resolved_project_sha256,
        "rig_sha256": mesh.rig_sha256,
        "run_sha256": mesh.run_sha256,
        "probes_sha256": mesh.probes_sha256,
        "visuals_sha256": mesh.visuals_sha256,
        "bundle_sha256": mesh.bundle_sha256,
    }
