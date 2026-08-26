"""Exact P8/P5 admission boundary for target-specific foot-lock evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .motion_retarget_bundle_contract import (
    build_motion_retarget_bundle_contract,
)
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .motion_retarget_bundle_integrity import MotionRetargetBundleIntegrityError
from .projected_motion_bundle_contract import (
    build_projected_motion_bundle_contract,
)
from .projected_motion_bundle_integrity import VerifiedProjectedMotionBundle


class FootLockCandidateInputError(ValueError):
    """Raised when exact P8 and P5 inputs are stale or cross-wired."""


@dataclass(frozen=True, slots=True)
class FootLockCandidateInputs:
    projected: dict[str, Any]
    target: dict[str, Any]
    instance: dict[str, Any]
    frame_ticks: tuple[int, ...]
    contacts: tuple[dict[str, Any], ...]
    reference_length_px: float


def require_foot_lock_candidate_inputs(
    projected_bundle: VerifiedProjectedMotionBundle,
    retarget_bundle: VerifiedMotionRetargetBundle,
) -> FootLockCandidateInputs:
    """Admit exact bundle types and require one shared P7 motion identity."""

    try:
        if type(projected_bundle) is not VerifiedProjectedMotionBundle:
            raise FootLockCandidateInputError(
                "Foot-lock candidates require an exact verified P8 bundle"
            )
        if type(retarget_bundle) is not VerifiedMotionRetargetBundle:
            raise FootLockCandidateInputError(
                "Foot-lock candidates require an exact verified P5 bundle"
            )
        _require_projected_bundle(projected_bundle)
        _require_retarget_bundle(retarget_bundle)
        projected = projected_bundle.projected_motion
        target = retarget_bundle.target_profile
        instance = retarget_bundle.motion_instance
        frames = tuple(projected["frames"])
        frame_ticks = tuple(row["tick"] for row in frames)
        contacts = tuple(
            marker for marker in instance["markers"]
            if marker["limb"].startswith("leg.")
        )
        missing = sorted({
            marker["start_tick"] for marker in contacts
        } - set(frame_ticks))
        if missing:
            raise FootLockCandidateInputError(
                "Contact start tick is absent from P8 source frames: "
                + ", ".join(str(value) for value in missing)
            )
        _require_cross_binding(
            projected_bundle, retarget_bundle, projected, target, instance
        )
        return FootLockCandidateInputs(
            projected=projected,
            target=target,
            instance=instance,
            frame_ticks=frame_ticks,
            contacts=contacts,
            reference_length_px=float(target["reference_length"]["value_px"]),
        )
    except FootLockCandidateInputError:
        raise
    except (
        MotionRetargetBundleIntegrityError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise FootLockCandidateInputError(
            f"Foot-lock candidate input verification failed: {exc}"
        ) from exc


def _require_projected_bundle(bundle: VerifiedProjectedMotionBundle) -> None:
    contract = build_projected_motion_bundle_contract(
        bundle.camera, bundle.projected_motion, bundle.run_manifest
    )
    identities = (
        (contract.clip_id, bundle.clip_id),
        (contract.projected_motion_sha256, bundle.projected_motion_sha256),
        (contract.camera_sha256, bundle.camera_sha256),
        (contract.run_sha256, bundle.run_sha256),
        (contract.legacy_motion_sha256, bundle.legacy_motion_sha256),
        (contract.bundle_sha256, bundle.bundle_sha256),
    )
    source = bundle.projected_motion["source"]
    upstream = (
        (source["motion_ir_sha256"], bundle.p7_motion_sha256),
        (source["motion_bundle_sha256"], bundle.p7_bundle_sha256),
        (source["motion_run_sha256"], bundle.p7_run_sha256),
    )
    if bundle.inventory != contract.inventory \
            or bundle.document_bytes != contract.document_bytes \
            or any(left != right for left, right in (*identities, *upstream)):
        raise FootLockCandidateInputError(
            "Verified P8 bundle identities differ from canonical content"
        )


def _require_retarget_bundle(bundle: VerifiedMotionRetargetBundle) -> None:
    values = (
        bundle.target_profile, bundle.motion_instance, bundle.run_manifest,
        bundle.retarget_report, bundle.mesh_regression,
    )
    contract = build_motion_retarget_bundle_contract(bundle.project_id, *values)
    identities = (
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
            or any(left != right for left, right in identities):
        raise FootLockCandidateInputError(
            "Verified P5 bundle identities differ from canonical content"
        )


def _retarget_sources(target, instance) -> dict[str, str]:
    p3, source = target["source"]["p3"], instance["source"]
    return {
        "p3_rig_sha256": p3["rig_sha256"],
        "p3_bundle_sha256": p3["bundle_sha256"],
        "p4_profile_sha256": target["source"]["p4_profile_sha256"],
        "p4_bundle_sha256": target["source"]["p4_bundle_sha256"],
        "motion_clip_sha256": source["motion_ir_sha256"],
        "motion_bundle_sha256": source["motion_bundle_sha256"],
    }


def _require_cross_binding(p8, p5, projected, target, instance) -> None:
    source = instance["source"]
    motion = (
        (source["motion_ir_sha256"], p8.p7_motion_sha256),
        (source["motion_bundle_sha256"], p8.p7_bundle_sha256),
        (source["motion_run_sha256"], p8.p7_run_sha256),
    )
    timing_fields = ("ticks_per_second", "duration_ticks", "loop")
    timing_differs = any(
        projected["timing"][field] != instance["timing"][field]
        for field in timing_fields
    )
    if p8.clip_id != p5.clip_id or projected["clip_id"] != instance["clip_id"] \
            or target["project_id"] != p5.project_id \
            or timing_differs \
            or any(left != right for left, right in motion):
        raise FootLockCandidateInputError(
            "P8 projection and P5 target do not share one exact P7 motion"
        )
    projected_contacts = tuple(
        (row["limb"], row["start_tick"], row["end_tick"], row["mode"])
        for row in projected["markers"]
    )
    instance_contacts = tuple(
        (row["limb"], row["start_tick"], row["end_tick"], row["mode"])
        for row in instance["markers"] if row["limb"].startswith("leg.")
    )
    if projected_contacts != instance_contacts:
        raise FootLockCandidateInputError(
            "P8 and P5 leg contact intervals differ"
        )
