"""Strict inner and exact-source validation for P5 motion target profiles."""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any

from .ik_target_geometry import SOURCE_IDENTITY_FIELDS, solver_config
from .ik_target_profile import (
    PROFILE_FORMAT as IK_PROFILE_FORMAT,
    PROFILE_VERSION as IK_PROFILE_VERSION,
    SOLVER_ID,
    SOLVER_VERSION,
)
from .ik_target_profile_validation import (
    IkTargetProfileValidationError,
    require_ik_target_profile,
)
from .manifest_artifacts import LayerManifestError, require_safe_token
from .motion_roles import CANONICAL_IK_HANDLES
from .motion_target_comparison import geometry_equivalent
from .motion_target_geometry import (
    GEOMETRY_TOLERANCE_PX,
    NUMERIC_PRECISION_DECIMALS,
    MotionTargetGeometryError,
    derive_motion_setup_from_projection,
)
from .resolved_project import canonical_sha256


PROFILE_FORMAT, PROFILE_VERSION = "autospine-motion-target-profile", 1
PROFILE_GENERATOR_ID, PROFILE_GENERATOR_VERSION = "motion-target-profile-compiler", "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "project_id", "source", "target_space",
    "generator", "bones", "ik_handles", "body_frame", "reference_length",
    "mesh_evidence",
}
_MESH_TARGET_FIELDS = {
    "attachment_id", "source_layer_id", "side",
    "proximal_bone_id", "distal_bone_id",
}


class MotionTargetValidationError(ValueError):
    """Raised when a P5 target profile is ambiguous, stale, or non-finite."""


def require_motion_target_profile(
    document: Mapping[str, Any],
    *,
    verified_ik=None,
    verified_mesh=None,
) -> None:
    """Validate standalone semantics and optionally reproduce exact bindings."""
    try:
        root = _object(document, "motion target profile")
        _strict_json_tree(root)
        _exact(root, _TOP, "motion target profile")
        if root.get("format") != PROFILE_FORMAT or root.get("format_version") != 1 \
                or isinstance(root.get("format_version"), bool):
            raise MotionTargetValidationError("Motion target profile version is invalid")
        project_id = require_safe_token(root.get("project_id"), "Project id")
        p3_source = _source(root.get("source"))
        canvas = _space(root.get("target_space"))
        _generator(root.get("generator"))
        geometry = derive_motion_setup_from_projection(root.get("bones"))
        handles = _handles(
            root.get("ik_handles"), project_id, p3_source, canvas
        )
        if not geometry_equivalent(root["ik_handles"], geometry.ik_handles):
            raise MotionTargetValidationError(
                "Motion target handles differ from projected bone setup"
            )
        if not geometry_equivalent(root.get("body_frame"), geometry.body_frame):
            raise MotionTargetValidationError(
                "Motion target body frame differs from projected bone setup"
            )
        _reference(root.get("reference_length"), handles)
        _mesh_evidence(root.get("mesh_evidence"))
        canonical_sha256(root)
        if (verified_ik is None) != (verified_mesh is None):
            raise MotionTargetValidationError(
                "Both verified P4 and P3 inputs are required for exact binding"
            )
        if verified_ik is not None:
            from .motion_target_profile import _derive_document
            expected = _derive_document(verified_ik, verified_mesh)
            if canonical_sha256(root) != canonical_sha256(expected):
                raise MotionTargetValidationError(
                    "Motion target profile differs from exact verified inputs"
                )
    except MotionTargetValidationError:
        raise
    except (IkTargetProfileValidationError, LayerManifestError,
            MotionTargetGeometryError, KeyError, TypeError, ValueError,
            OverflowError) as exc:
        raise MotionTargetValidationError(
            f"Motion target profile validation failed: {exc}"
        ) from exc


def _source(value):
    source = _object(value, "motion target source")
    _exact(
        source,
        {"p4_profile_sha256", "p4_probes_sha256", "p4_bundle_sha256", "p3"},
        "motion target source",
    )
    for field in ("p4_profile_sha256", "p4_probes_sha256", "p4_bundle_sha256"):
        _sha(source.get(field), field)
    p3 = _object(source.get("p3"), "motion target P3 source")
    _exact(p3, set(SOURCE_IDENTITY_FIELDS), "motion target P3 source")
    for field in SOURCE_IDENTITY_FIELDS:
        _sha(p3.get(field), field)
    return dict(p3)


def _space(value):
    space = _object(value, "motion target space")
    _exact(
        space,
        {"translation", "rotation", "scale", "canvas"},
        "motion target space",
    )
    if (space.get("translation"), space.get("rotation"), space.get("scale")) != \
            ("setup-local-pixel", "setup-local-degree", "positive-unit-only"):
        raise MotionTargetValidationError("Motion target setup space is unsupported")
    canvas = _object(space.get("canvas"), "motion target canvas")
    _exact(
        canvas,
        {"width", "height", "origin", "x_axis", "y_axis", "units"},
        "motion target canvas",
    )
    dimensions_invalid = any(
        type(canvas.get(field)) is not int or canvas[field] < 1
        for field in ("width", "height")
    )
    axes = {
        key: canvas.get(key) for key in ("origin", "x_axis", "y_axis", "units")
    }
    expected_axes = {
        "origin": "top_left", "x_axis": "right",
        "y_axis": "down", "units": "pixel",
    }
    if dimensions_invalid or axes != expected_axes:
        raise MotionTargetValidationError("Motion target canvas is invalid")
    return dict(canvas)


def _generator(value):
    generator = _object(value, "motion target generator")
    _exact(
        generator,
        {"id", "version", "numeric_precision_decimals"},
        "motion target generator",
    )
    expected = {
        "id": PROFILE_GENERATOR_ID,
        "version": PROFILE_GENERATOR_VERSION,
        "numeric_precision_decimals": NUMERIC_PRECISION_DECIMALS,
    }
    if generator != expected:
        raise MotionTargetValidationError("Motion target generator is unsupported")


def _handles(value, project_id, p3_source, canvas):
    if not isinstance(value, list) or len(value) != 4:
        raise MotionTargetValidationError("Motion target must bind four IK handles")
    require_ik_target_profile({
        "format": IK_PROFILE_FORMAT, "format_version": IK_PROFILE_VERSION,
        "project_id": project_id, "source": p3_source, "canvas": canvas,
        "solver": {
            "id": SOLVER_ID, "version": SOLVER_VERSION,
            "config": solver_config(),
        },
        "handles": value,
    })
    if [item.get("id") for item in value] != list(CANONICAL_IK_HANDLES):
        raise MotionTargetValidationError("Motion target handle order is invalid")
    return {item["id"]: item for item in value}


def _mesh_evidence(value):
    evidence = _object(value, "motion target mesh evidence")
    fields = {
        "status", "summary", "rig_qa_status", "probes_status",
        "visuals_status", "target_inventory",
    }
    _exact(evidence, fields, "motion target mesh evidence")
    if any(evidence.get(field) != "passed" for field in
           ("rig_qa_status", "probes_status", "visuals_status")):
        raise MotionTargetValidationError("Motion target P3 evidence did not pass")
    targets = evidence.get("target_inventory")
    if not isinstance(targets, list):
        raise MotionTargetValidationError("Motion target mesh inventory must be an array")
    ids = []
    for index, raw in enumerate(targets):
        item = _object(raw, f"mesh target {index}")
        _exact(item, _MESH_TARGET_FIELDS, f"mesh target {index}")
        ids.append(require_safe_token(item.get("attachment_id"), "Mesh attachment id"))
        require_safe_token(item.get("source_layer_id"), "Mesh source layer id")
        if item.get("side") not in {"left", "right"} or \
                item.get("proximal_bone_id") != f"thigh.{item.get('side')}" or \
                item.get("distal_bone_id") != f"calf.{item.get('side')}":
            raise MotionTargetValidationError("Motion target mesh chain is invalid")
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise MotionTargetValidationError("Motion target mesh inventory order is invalid")
    summary = "reviewed-noop" if not targets else f"converted={len(targets)}"
    status = "reviewed-noop" if not targets else "converted"
    if evidence.get("summary") != summary or evidence.get("status") != status:
        raise MotionTargetValidationError("Motion target mesh summary is invalid")


def _reference(value, handles):
    reference = _object(value, "motion target reference length")
    _exact(
        reference,
        {"value_px", "method", "handle_ids"},
        "motion target reference length",
    )
    expected = (handles["leg.left"]["kinematic_reach"]["maximum_px"] +
                handles["leg.right"]["kinematic_reach"]["maximum_px"]) / 2.0
    if reference.get("method") != "mean-leg-maximum-kinematic-reach" or \
            reference.get("handle_ids") != ["leg.left", "leg.right"] or \
            not _close(
                _number(reference.get("value_px"), "reference length"),
                expected,
                GEOMETRY_TOLERANCE_PX,
            ):
        raise MotionTargetValidationError("Motion target reference length is invalid")


def _object(value, label):
    if not isinstance(value, Mapping):
        raise MotionTargetValidationError(f"{label} must be an object")
    return value


def _exact(value, fields, label):
    if set(value) != fields:
        raise MotionTargetValidationError(
            f"{label} fields are incomplete or unsupported"
        )


def _sha(value, label):
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise MotionTargetValidationError(f"{label} SHA-256 is invalid")


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise MotionTargetValidationError(f"{label} must be finite")
    return float(value)


def _close(left, right, tolerance):
    return abs(left - right) <= tolerance


def _strict_json_tree(value):
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise MotionTargetValidationError(
                "Motion target JSON keys must be strings"
            )
        for item in value.values():
            _strict_json_tree(item)
    elif isinstance(value, list):
        for item in value:
            _strict_json_tree(item)
    elif isinstance(value, tuple):
        raise MotionTargetValidationError("Motion target arrays must be JSON lists")
    elif isinstance(value, float) and not math.isfinite(value):
        raise MotionTargetValidationError("Motion target numbers must be finite")
