"""Strict semantics for review-only target-specific foot-lock candidates."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .foot_lock_candidate_inputs import (
    FootLockCandidateInputError,
    require_foot_lock_candidate_inputs,
)
from .foot_lock_candidate_math_validation import (
    number as _number,
    require_contacts as _contacts,
    require_samples as _samples,
    require_summary as _summary,
    vector_close as _vector_close,
)
from .motion_instance_sampling import sample_instance_pose
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .projected_motion_bundle_integrity import VerifiedProjectedMotionBundle
from .resolved_project import canonical_sha256
from .exact_json_contract import exact_json_equal


FORMAT = "autospine-foot-lock-candidates"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "policy", "reference", "contacts", "samples", "summary",
}
_SOURCE = {
    "projected_motion_sha256", "projected_bundle_sha256", "camera_sha256",
    "p7_motion_sha256", "p7_bundle_sha256", "p7_run_sha256",
    "target_profile_sha256", "motion_instance_sha256",
    "retarget_bundle_sha256", "retarget_run_document_sha256",
    "p3_rig_sha256", "p3_bundle_sha256", "instance_motion_ir_sha256",
    "instance_motion_bundle_sha256",
}


class FootLockCandidateValidationError(ValueError):
    """Raised when foot-lock candidates are ambiguous or mathematically stale."""


def foot_lock_policy(
    max_correction_reference_ratio: float,
    max_residual_px: float,
) -> dict[str, Any]:
    """Return the pinned v1 review policy with explicit threshold units."""

    return {
        "mode": "candidate_only",
        "contact_source": "motion_instance.annotation_only",
        "interval_semantics": "half_open",
        "sample_schedule": "p8_source_frame_ticks",
        "anchor": "distal_endpoint_at_contact_start",
        "correction": "additive_target_root_translation",
        "correction_unit": "pixel",
        "single_support_solver": "exact_anchor_delta",
        "dual_support_solver": "unweighted_least_squares_mean",
        "release": "unresolved",
        "apply_policy": "review_required",
        "decision_emitted": False,
        "runtime_timeline_emitted": False,
        "clipping": "forbidden",
        "correction_limit": {
            "maximum": max_correction_reference_ratio,
            "quantity": "correction_magnitude_over_target_reference",
            "unit": "ratio",
        },
        "residual_limit": {
            "maximum": max_residual_px,
            "quantity": "per_contact_residual_magnitude",
            "unit": "pixel",
        },
    }


def require_foot_lock_candidates(
    document: Mapping[str, Any],
    *,
    projected_bundle: VerifiedProjectedMotionBundle | None = None,
    retarget_bundle: VerifiedMotionRetargetBundle | None = None,
) -> None:
    """Validate standalone math and optionally bind both exact input bundles."""

    try:
        root = _object(document, "Foot-lock candidates")
        _exact(root, _TOP, "Foot-lock candidates")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise FootLockCandidateValidationError(
                "Foot-lock candidate format is unsupported"
            )
        _identifier(root.get("project_id"), "project_id")
        _identifier(root.get("clip_id"), "clip_id")
        source = _source(root.get("source"))
        correction_limit, residual_limit = _policy(root.get("policy"))
        reference = _reference(root.get("reference"))
        contacts = _contacts(root.get("contacts"))
        stats = _samples(
            root.get("samples"), contacts, reference,
            correction_limit, residual_limit,
        )
        _summary(root.get("summary"), len(contacts), stats)
        if (projected_bundle is None) != (retarget_bundle is None):
            raise FootLockCandidateValidationError(
                "Both exact P8 and P5 inputs are required for cross-binding"
            )
        if projected_bundle is not None and retarget_bundle is not None:
            _cross_inputs(root, source, projected_bundle, retarget_bundle)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise FootLockCandidateValidationError(
                "Foot-lock candidate byte limit exceeded"
            )
    except FootLockCandidateValidationError:
        raise
    except (
        FootLockCandidateInputError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise FootLockCandidateValidationError(
            f"Foot-lock candidate validation failed: {exc}"
        ) from exc


def foot_lock_candidates_sha256(document: Mapping[str, Any]) -> str:
    require_foot_lock_candidates(document)
    return canonical_sha256(document)


def _source(value) -> Mapping[str, Any]:
    source = _object(value, "Foot-lock candidate source")
    _exact(source, _SOURCE, "Foot-lock candidate source")
    if any(not isinstance(source.get(field), str)
           or not _SHA.fullmatch(source[field]) for field in _SOURCE):
        raise FootLockCandidateValidationError(
            "Foot-lock candidate source SHA-256 is invalid"
        )
    if source["p7_motion_sha256"] != source["instance_motion_ir_sha256"] \
            or source["p7_bundle_sha256"] != \
            source["instance_motion_bundle_sha256"]:
        raise FootLockCandidateValidationError(
            "Foot-lock candidate P8 and P5 motion sources differ"
        )
    return source


def _policy(value) -> tuple[float, float]:
    policy = _object(value, "Foot-lock candidate policy")
    required = foot_lock_policy(1.0, 1.0)
    _exact(policy, set(required), "Foot-lock candidate policy")
    correction = _threshold(
        policy.get("correction_limit"),
        "correction_magnitude_over_target_reference", "ratio", positive=True,
    )
    residual = _threshold(
        policy.get("residual_limit"),
        "per_contact_residual_magnitude", "pixel", positive=False,
    )
    if not exact_json_equal(
        policy, foot_lock_policy(correction, residual)
    ):
        raise FootLockCandidateValidationError(
            "Foot-lock candidate policy is unsupported"
        )
    return correction, residual


def _threshold(value, quantity, unit, *, positive) -> float:
    row = _object(value, "Foot-lock candidate threshold")
    _exact(row, {"maximum", "quantity", "unit"}, "Foot-lock threshold")
    maximum = _number(row.get("maximum"))
    if (positive and maximum <= 0) or (not positive and maximum < 0) \
            or row.get("quantity") != quantity or row.get("unit") != unit:
        raise FootLockCandidateValidationError(
            "Foot-lock candidate threshold is invalid"
        )
    return maximum


def _reference(value) -> float:
    row = _object(value, "Foot-lock candidate reference")
    _exact(row, {"kind", "value_px", "unit"}, "Foot-lock reference")
    length = _number(row.get("value_px"))
    if length <= 0 or row.get("kind") != \
            "target_profile.mean-leg-maximum-kinematic-reach" \
            or row.get("unit") != "pixel":
        raise FootLockCandidateValidationError(
            "Foot-lock candidate target reference is invalid"
        )
    return length


def _cross_inputs(root, source, p8, p5) -> None:
    inputs = require_foot_lock_candidate_inputs(p8, p5)
    p3 = inputs.target["source"]["p3"]
    instance_source = inputs.instance["source"]
    expected_source = {
        "projected_motion_sha256": p8.projected_motion_sha256,
        "projected_bundle_sha256": p8.bundle_sha256,
        "camera_sha256": p8.camera_sha256,
        "p7_motion_sha256": p8.p7_motion_sha256,
        "p7_bundle_sha256": p8.p7_bundle_sha256,
        "p7_run_sha256": p8.p7_run_sha256,
        "target_profile_sha256": p5.target_profile_sha256,
        "motion_instance_sha256": p5.instance_sha256,
        "retarget_bundle_sha256": p5.bundle_sha256,
        "retarget_run_document_sha256": p5.run_document_sha256,
        "p3_rig_sha256": p3["rig_sha256"],
        "p3_bundle_sha256": p3["bundle_sha256"],
        "instance_motion_ir_sha256": instance_source["motion_ir_sha256"],
        "instance_motion_bundle_sha256": instance_source["motion_bundle_sha256"],
    }
    if source != expected_source or root["project_id"] != p5.project_id \
            or root["clip_id"] != p8.clip_id \
            or root["reference"]["value_px"] != inputs.reference_length_px:
        raise FootLockCandidateValidationError(
            "Foot-lock candidate exact source binding differs"
        )
    expected_contacts = tuple(
        (row["limb"], row["proximal_bone_id"], row["distal_bone_id"],
         row["start_tick"], row["end_tick"])
        for row in inputs.contacts
    )
    actual_contacts = tuple(
        (row["limb"], row["proximal_bone_id"], row["distal_bone_id"],
         row["start_tick"], row["end_tick"])
        for row in root["contacts"]
    )
    frames = tuple((row["source_frame_index"], row["tick"])
                   for row in root["samples"])
    expected_frames = tuple((row["source_frame_index"], row["tick"])
                            for row in inputs.projected["frames"])
    if actual_contacts != expected_contacts or frames != expected_frames:
        raise FootLockCandidateValidationError(
            "Foot-lock contacts or frame schedule differ from exact inputs"
        )
    by_id = {row["contact_id"]: row for row in root["contacts"]}
    for sample in root["samples"]:
        pose = sample_instance_pose(
            inputs.instance, target_profile=inputs.target, tick=sample["tick"]
        )
        for observation in sample["observations"]:
            contact = by_id[observation["contact_id"]]
            endpoint = pose[contact["distal_bone_id"]]["endpoint_xy"]
            if not _vector_close(observation["current_endpoint_px"], endpoint):
                raise FootLockCandidateValidationError(
                    "Foot-lock endpoint differs from exact P5 FK"
                )
    for contact in root["contacts"]:
        pose = sample_instance_pose(
            inputs.instance, target_profile=inputs.target,
            tick=contact["start_tick"],
        )
        endpoint = pose[contact["distal_bone_id"]]["endpoint_xy"]
        if not _vector_close(contact["anchor_endpoint_px"], endpoint):
            raise FootLockCandidateValidationError(
                "Foot-lock anchor differs from exact P5 FK"
            )


def _identifier(value, label) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise FootLockCandidateValidationError(f"Foot-lock {label} is invalid")
    return value


def _object(value, label) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FootLockCandidateValidationError(f"{label} must be an object")
    return value


def _exact(value, fields, label) -> None:
    if set(value) != fields:
        raise FootLockCandidateValidationError(
            f"{label} fields are incomplete or unsupported"
        )
