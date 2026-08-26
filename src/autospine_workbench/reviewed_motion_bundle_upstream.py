"""Admission helpers for exact P3/P5 reviewed-motion dependencies."""

from __future__ import annotations

from .mesh_bundle_admission import MeshBundleAdmissionError, require_exact_mesh_bundle
from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_retarget_bundle_contract import (
    MotionRetargetBundleContractError,
    build_motion_retarget_bundle_contract,
)
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle


class ReviewedMotionBundleUpstreamError(ValueError):
    """Raised when a nominally verified P3/P5 snapshot is spoofed or stale."""


def require_reviewed_motion_upstreams(
    mesh_bundle: VerifiedMeshBundle,
    retarget_bundle: VerifiedMotionRetargetBundle,
) -> tuple[dict, dict]:
    """Rebuild admitted upstream contracts and return isolated P5 inputs."""

    try:
        require_exact_mesh_bundle(mesh_bundle)
        if type(retarget_bundle) is not VerifiedMotionRetargetBundle:
            raise ReviewedMotionBundleUpstreamError(
                "P5 admission requires an exact VerifiedMotionRetargetBundle"
            )
        documents = (
            retarget_bundle.target_profile,
            retarget_bundle.motion_instance,
            retarget_bundle.run_manifest,
            retarget_bundle.retarget_report,
            retarget_bundle.mesh_regression,
        )
        rebuilt = build_motion_retarget_bundle_contract(
            retarget_bundle.project_id, *documents
        )
        checks = (
            (rebuilt.project_id, retarget_bundle.project_id),
            (rebuilt.clip_id, retarget_bundle.clip_id),
            (rebuilt.target_profile_sha256,
             retarget_bundle.target_profile_sha256),
            (rebuilt.instance_sha256, retarget_bundle.instance_sha256),
            (rebuilt.run_document_sha256,
             retarget_bundle.run_document_sha256),
            (rebuilt.report_sha256,
             retarget_bundle.retarget_report_sha256),
            (rebuilt.mesh_report_sha256,
             retarget_bundle.mesh_regression_sha256),
            (rebuilt.bundle_sha256, retarget_bundle.bundle_sha256),
        )
        if rebuilt.document_bytes != retarget_bundle.document_bytes \
                or rebuilt.inventory != retarget_bundle.inventory \
                or any(left != right for left, right in checks):
            raise ReviewedMotionBundleUpstreamError(
                "Verified P5 bundle differs from its canonical content"
            )
        target, instance = documents[0], documents[1]
        expected_sources = {
            "p3_rig_sha256": target["source"]["p3"]["rig_sha256"],
            "p3_bundle_sha256": target["source"]["p3"]["bundle_sha256"],
            "p4_profile_sha256": target["source"]["p4_profile_sha256"],
            "p4_bundle_sha256": target["source"]["p4_bundle_sha256"],
            "motion_clip_sha256": instance["source"]["motion_ir_sha256"],
            "motion_bundle_sha256": instance["source"]["motion_bundle_sha256"],
        }
        if retarget_bundle.source_addresses != expected_sources:
            raise ReviewedMotionBundleUpstreamError(
                "Verified P5 source-address inventory is stale"
            )
        if mesh_bundle.project_id != retarget_bundle.project_id \
                or target["source"]["p3"]["rig_sha256"] != mesh_bundle.rig_sha256 \
                or target["source"]["p3"]["bundle_sha256"] != mesh_bundle.bundle_sha256:
            raise ReviewedMotionBundleUpstreamError(
                "Exact P3 and P5 bundle chains differ"
            )
        return instance, target
    except ReviewedMotionBundleUpstreamError:
        raise
    except (
        MeshBundleAdmissionError, MotionRetargetBundleContractError,
        AttributeError, KeyError, TypeError, ValueError,
    ) as exc:
        raise ReviewedMotionBundleUpstreamError(
            f"Reviewed-motion upstream admission failed: {exc}"
        ) from exc
