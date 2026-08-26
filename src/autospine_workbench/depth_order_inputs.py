"""Exact P8/P5/P3 admission boundary for depth-order candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .mesh_bundle_admission import (
    MeshBundleAdmissionError,
    require_exact_mesh_bundle,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_retarget_bundle_contract import (
    build_motion_retarget_bundle_contract,
)
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .motion_roles import CANONICAL_BONE_ROLE_ITEMS
from .motion_target_validation import require_motion_target_profile
from .projected_motion_bundle_contract import (
    build_projected_motion_bundle_contract,
)
from .projected_motion_bundle_integrity import VerifiedProjectedMotionBundle
from .projected_motion_validation import require_projected_motion_ir


class DepthOrderInputError(ValueError):
    """Raised when exact P8, P5, and P3 inputs are stale or cross-wired."""


@dataclass(frozen=True, slots=True)
class DepthOrderInputs:
    """Isolated documents and identities admitted for one policy review."""

    projected: dict[str, Any]
    camera: dict[str, Any]
    target: dict[str, Any]
    rig: dict[str, Any]
    identities: dict[str, dict[str, str]]


def require_depth_order_inputs(
    projected_bundle: VerifiedProjectedMotionBundle,
    retarget_bundle: VerifiedMotionRetargetBundle,
    mesh_bundle: VerifiedMeshBundle,
) -> DepthOrderInputs:
    """Rebuild exact upstream contracts and require a single shared chain."""

    try:
        if type(projected_bundle) is not VerifiedProjectedMotionBundle:
            raise DepthOrderInputError(
                "Depth-order candidates require an exact verified P8 bundle"
            )
        if type(retarget_bundle) is not VerifiedMotionRetargetBundle:
            raise DepthOrderInputError(
                "Depth-order candidates require an exact verified P5 bundle"
            )
        if type(mesh_bundle) is not VerifiedMeshBundle:
            raise DepthOrderInputError(
                "Depth-order candidates require an exact verified P3 bundle"
            )
        projected, camera = _projected(projected_bundle)
        target = _retarget(retarget_bundle)
        rig = require_exact_mesh_bundle(mesh_bundle)
        _cross(projected_bundle, retarget_bundle, mesh_bundle,
               projected, target, rig)
        return DepthOrderInputs(
            projected=projected,
            camera=camera,
            target=target,
            rig=rig,
            identities=_identities(
                projected_bundle, retarget_bundle, mesh_bundle
            ),
        )
    except DepthOrderInputError:
        raise
    except (
        KeyError, MeshBundleAdmissionError, OverflowError, TypeError, ValueError,
    ) as exc:
        raise DepthOrderInputError(
            f"Depth-order input verification failed: {exc}"
        ) from exc


def _projected(bundle: VerifiedProjectedMotionBundle):
    contract = build_projected_motion_bundle_contract(
        bundle.camera, bundle.projected_motion, bundle.run_manifest
    )
    source = bundle.projected_motion["source"]
    checks = (
        (contract.clip_id, bundle.clip_id),
        (contract.projected_motion_sha256, bundle.projected_motion_sha256),
        (contract.camera_sha256, bundle.camera_sha256),
        (contract.run_sha256, bundle.run_sha256),
        (contract.legacy_motion_sha256, bundle.legacy_motion_sha256),
        (contract.bundle_sha256, bundle.bundle_sha256),
        (source["motion_ir_sha256"], bundle.p7_motion_sha256),
        (source["motion_bundle_sha256"], bundle.p7_bundle_sha256),
        (source["motion_run_sha256"], bundle.p7_run_sha256),
    )
    if bundle.inventory != contract.inventory \
            or bundle.document_bytes != contract.document_bytes \
            or any(left != right for left, right in checks):
        raise DepthOrderInputError(
            "Verified P8 identities differ from canonical content"
        )
    projected = bundle.projected_motion
    require_projected_motion_ir(projected)
    return projected, bundle.camera


def _retarget(bundle: VerifiedMotionRetargetBundle):
    values = (
        bundle.target_profile, bundle.motion_instance, bundle.run_manifest,
        bundle.retarget_report, bundle.mesh_regression,
    )
    contract = build_motion_retarget_bundle_contract(bundle.project_id, *values)
    checks = (
        (contract.project_id, bundle.project_id),
        (contract.clip_id, bundle.clip_id),
        (contract.target_profile_sha256, bundle.target_profile_sha256),
        (contract.instance_sha256, bundle.instance_sha256),
        (contract.run_document_sha256, bundle.run_document_sha256),
        (contract.report_sha256, bundle.retarget_report_sha256),
        (contract.mesh_report_sha256, bundle.mesh_regression_sha256),
        (contract.bundle_sha256, bundle.bundle_sha256),
    )
    expected_sources = _retarget_sources(values[0], values[1])
    if bundle.inventory != contract.inventory \
            or bundle.document_bytes != contract.document_bytes \
            or bundle.source_addresses != expected_sources \
            or any(left != right for left, right in checks):
        raise DepthOrderInputError(
            "Verified P5 identities differ from canonical content"
        )
    require_motion_target_profile(values[0])
    return values[0]


def _retarget_sources(target, instance) -> dict[str, str]:
    p3, motion = target["source"]["p3"], instance["source"]
    return {
        "p3_rig_sha256": p3["rig_sha256"],
        "p3_bundle_sha256": p3["bundle_sha256"],
        "p4_profile_sha256": target["source"]["p4_profile_sha256"],
        "p4_bundle_sha256": target["source"]["p4_bundle_sha256"],
        "motion_clip_sha256": motion["motion_ir_sha256"],
        "motion_bundle_sha256": motion["motion_bundle_sha256"],
    }


def _cross(p8, p5, p3, projected, target, rig) -> None:
    instance = p5.motion_instance
    motion = instance["source"]
    timing = projected["timing"]
    if p8.clip_id != p5.clip_id \
            or projected["clip_id"] != instance["clip_id"] \
            or any(timing[field] != instance["timing"][field]
                   for field in ("ticks_per_second", "duration_ticks", "loop")):
        raise DepthOrderInputError("P8 and P5 clip identities differ")
    expected_motion = (
        (motion["motion_ir_sha256"], p8.p7_motion_sha256),
        (motion["motion_ir_sha256"], p8.legacy_motion_sha256),
        (motion["motion_bundle_sha256"], p8.p7_bundle_sha256),
        (motion["motion_run_sha256"], p8.p7_run_sha256),
    )
    if any(left != right for left, right in expected_motion):
        raise DepthOrderInputError("P8 and P5 do not share one exact P7 motion")
    p3_source = target["source"]["p3"]
    expected_p3 = {field: getattr(p3, field) for field in SOURCE_IDENTITY_FIELDS}
    if target["project_id"] != p5.project_id or p3.project_id != p5.project_id \
            or p3_source != expected_p3:
        raise DepthOrderInputError("P5 target and P3 identity chains differ")
    target_roles = {
        row["role"]: row["bone_id"] for row in target["bones"]
    }
    if list(target_roles.items()) != list(CANONICAL_BONE_ROLE_ITEMS):
        raise DepthOrderInputError("P5 target role inventory is not canonical")
    rig_bones = {row["id"] for row in rig["bones"]}
    if not set(target_roles.values()) <= rig_bones:
        raise DepthOrderInputError("P5 target bones are absent from P3 RigIR")


def _identities(p8, p5, p3) -> dict[str, dict[str, str]]:
    return {
        "p8": {
            "projected_motion_sha256": p8.projected_motion_sha256,
            "bundle_sha256": p8.bundle_sha256,
            "camera_sha256": p8.camera_sha256,
            "run_sha256": p8.run_sha256,
            "legacy_motion_sha256": p8.legacy_motion_sha256,
            "p7_motion_sha256": p8.p7_motion_sha256,
            "p7_bundle_sha256": p8.p7_bundle_sha256,
            "p7_run_sha256": p8.p7_run_sha256,
        },
        "p5": {
            "target_profile_sha256": p5.target_profile_sha256,
            "instance_sha256": p5.instance_sha256,
            "run_sha256": p5.run_document_sha256,
            "retarget_report_sha256": p5.retarget_report_sha256,
            "mesh_regression_sha256": p5.mesh_regression_sha256,
            "bundle_sha256": p5.bundle_sha256,
        },
        "p3": {
            field: getattr(p3, field) for field in SOURCE_IDENTITY_FIELDS
        },
    }
