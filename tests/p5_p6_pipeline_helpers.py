"""Shared P5/P6 execution helpers for source-format pipeline gates."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any

from autospine_workbench.motion_mesh_regression import (
    build_motion_mesh_regression,
)
from autospine_workbench.motion_retarget_bundle_store import (
    MotionRetargetBundleStore,
)
from autospine_workbench.motion_retarget_compiler import (
    compile_motion_instance,
)
from autospine_workbench.motion_retarget_report import (
    build_motion_retarget_report,
)
from autospine_workbench.motion_target_profile import (
    compile_motion_target_profile,
)
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.spine42_bundle_integrity import (
    VerifiedSpine42BundleReader,
)
from autospine_workbench.spine42_bundle_store import Spine42BundleStore
from autospine_workbench.spine42_json_adapter import build_spine42_json
from tests.test_motion_target_profile import ik_fixture, mesh_fixture
from tests.test_spine42_json_adapter import rig_fixture


@dataclass(frozen=True)
class P5P6RigResult:
    """Artifacts and immutable publication results from one target rig."""

    rig: dict[str, Any]
    mesh: Any
    target: Any
    retargeted: Any
    report: Any
    mesh_report: Any
    p5_bundle: Any
    skeleton: dict[str, Any]
    first_export: Any
    second_export: Any
    verified_export: Any


def region_rig(setup_rig: dict[str, Any], image_sha256: str) -> dict[str, Any]:
    """Attach one deterministic region image to an exact setup skeleton."""

    rig = rig_fixture()
    setup_by_id = {
        bone["id"]: deepcopy(bone["setup"])
        for bone in setup_rig["bones"]
    }
    for bone in rig["bones"]:
        bone["setup"] = setup_by_id[bone["id"]]
    face = deepcopy(rig["attachments"][0])
    face["image_sha256"] = image_sha256
    rig["capabilities"] = ["region_attachment", "setup_draw_order"]
    rig["slots"] = [deepcopy(rig["slots"][0])]
    rig["attachments"] = [face]
    rig["skins"] = {"default": {"face": ["face-image"]}}
    return rig


def exact_motion_target(rig: dict[str, Any]):
    """Build a target whose P3 evidence hashes match ``rig`` exactly."""

    provisional = mesh_fixture(rig, converted=False)
    documents = dict(provisional._document_json_items)
    mesh = replace(
        provisional,
        rig_sha256=canonical_sha256(rig),
        run_sha256=canonical_sha256(json.loads(documents["run-manifest.json"])),
        probes_sha256=canonical_sha256(json.loads(documents["probes.json"])),
        visuals_sha256=canonical_sha256(json.loads(documents["visuals.json"])),
    )
    return mesh, compile_motion_target_profile(ik_fixture(mesh), mesh)


def run_p5_p6_rig(
    state_root: Path,
    motion: Any,
    setup_rig: dict[str, Any],
    image: bytes,
    atlas: Any,
) -> P5P6RigResult:
    """Retarget one verified motion and publish/read back P5 and P6 bundles."""

    image_sha256 = hashlib.sha256(image).hexdigest()
    rig = region_rig(setup_rig, image_sha256)
    mesh, target = exact_motion_target(rig)
    retargeted = compile_motion_instance(motion, target)
    report = build_motion_retarget_report(motion, target, retargeted)
    mesh_report = build_motion_mesh_regression(
        retargeted.instance, target.document, mesh
    )
    p5_bundle = MotionRetargetBundleStore(state_root).publish(
        target.document["project_id"], target.document,
        retargeted.instance, retargeted.run,
        report.document, mesh_report.document,
    )
    skeleton = build_spine42_json(
        rig, motion_instance=retargeted.instance,
        target_profile=target.document,
    )
    p3_source = {
        "rig_sha256": target.document["source"]["p3"]["rig_sha256"],
        "bundle_sha256": target.document["source"]["p3"]["bundle_sha256"],
    }
    p5_source = {
        "target_profile_sha256": target.sha256,
        "motion_instance_sha256": retargeted.instance_sha256,
        "bundle_sha256": p5_bundle.bundle_sha256,
        "clip_id": motion.motion["clip_id"],
    }
    store = Spine42BundleStore(state_root)
    first_export = store.publish(
        target.document["project_id"], p3_source, skeleton,
        atlas.atlas_bytes, atlas.png_bytes,
        {"face-image": image_sha256}, p5_source=p5_source,
    )
    second_export = store.publish(
        target.document["project_id"], p3_source, skeleton,
        atlas.atlas_bytes, atlas.png_bytes,
        {"face-image": image_sha256}, p5_source=p5_source,
    )
    verified_export = VerifiedSpine42BundleReader(state_root).load(
        first_export.project_id, first_export.skeleton_json_sha256,
        first_export.bundle_sha256,
    )
    return P5P6RigResult(
        rig=rig,
        mesh=mesh,
        target=target,
        retargeted=retargeted,
        report=report,
        mesh_report=mesh_report,
        p5_bundle=p5_bundle,
        skeleton=skeleton,
        first_export=first_export,
        second_export=second_export,
        verified_export=verified_export,
    )
