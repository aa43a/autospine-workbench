"""Diagnostic pose evaluation against manually adjusted setup-pose joints."""

from __future__ import annotations

import math
import statistics
from typing import Any, Iterable, Mapping

from .candidate_provenance import required_sha256
from .pose_observations import PoseObservationSet
from .resolved_project import canonical_sha256


EVALUATOR_ID = "manual-limb-joint-distance"
EVALUATOR_VERSION = "1"
FLOAT_PRECISION_DECIMALS = 6
LIMB_JOINT_IDS = (
    "shoulder.left",
    "shoulder.right",
    "elbow.left",
    "elbow.right",
    "wrist.left",
    "wrist.right",
    "hip.left",
    "hip.right",
    "knee.left",
    "knee.right",
    "ankle.left",
    "ankle.right",
)
_PAIR_NAMES = ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")


class PoseEvaluationError(ValueError):
    """Raised when a report cannot be grounded in reviewed state."""


def evaluate_pose(
    project: Mapping[str, Any], observations: PoseObservationSet
) -> dict[str, Any]:
    """Create a threshold-free, content-addressable diagnostic report."""

    project_id = project.get("id")
    canvas = project.get("canvas") or {}
    width, height = canvas.get("width"), canvas.get("height")
    if (
        project_id != observations.project_id
        or not isinstance(width, int)
        or not isinstance(height, int)
        or (width, height) != observations.canvas_size
    ):
        raise PoseEvaluationError("Pose observations do not match the project")
    resolved = project.get("resolved")
    if not isinstance(resolved, Mapping):
        raise PoseEvaluationError("Project has no resolved snapshot")
    resolved_sha = required_sha256(resolved.get("sha256"), "resolved snapshot")
    inputs = resolved.get("inputs")
    if not isinstance(inputs, Mapping):
        raise PoseEvaluationError("Resolved snapshot has no pinned inputs")
    override_sha = required_sha256(inputs.get("override_sha256"), "override")
    revision = resolved.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise PoseEvaluationError("Resolved revision is invalid")
    pose_sha = required_sha256(observations.document_sha256, "pose observations")

    references = _manual_references(resolved, width, height)
    if not references:
        raise PoseEvaluationError("No manually adjusted limb joints are available")
    diagonal = math.hypot(width, height)
    joint_reports: dict[str, Any] = {}
    distances: dict[str, float] = {}
    for joint_id in LIMB_JOINT_IDS:
        reference = references.get(joint_id)
        observation = observations.joints.get(joint_id)
        if reference is None or observation is None:
            continue
        distance = math.hypot(observation.x - reference[0], observation.y - reference[1])
        distances[joint_id] = distance
        joint_reports[joint_id] = {
            "predicted_xy": [_quantize(observation.x), _quantize(observation.y)],
            "reference_xy": [_quantize(reference[0]), _quantize(reference[1])],
            "distance_px": _quantize(distance),
            "distance_canvas_diagonal_ratio": _quantize(distance / diagonal),
            "detector_score": _quantize(observation.detector_score),
            "visibility": observation.visibility,
        }

    reference_ids = [joint_id for joint_id in LIMB_JOINT_IDS if joint_id in references]
    matched_ids = [joint_id for joint_id in LIMB_JOINT_IDS if joint_id in distances]
    missing_observation_ids = [
        joint_id for joint_id in reference_ids if joint_id not in observations.joints
    ]
    missing_reference_ids = [
        joint_id for joint_id in LIMB_JOINT_IDS if joint_id not in references
    ]
    metrics = _metrics(
        [distances[joint_id] for joint_id in matched_ids],
        diagonal,
        len(reference_ids),
    )
    swap_diagnostic = _side_swap_diagnostic(references, observations)
    flags = {"NO_PASS_FAIL_THRESHOLDS"}
    if missing_reference_ids:
        flags.add("INCOMPLETE_MANUAL_REFERENCE")
    if missing_observation_ids:
        flags.add("MISSING_POSE_OBSERVATIONS")
    if not matched_ids:
        flags.add("NO_OVERLAPPING_OBSERVATIONS")
    if swap_diagnostic["lower_error_mapping"] == "swapped":
        flags.add("SIDE_SWAP_COUNTERFACTUAL_LOWER_ERROR")

    config = {
        "joint_ids": list(LIMB_JOINT_IDS),
        "reference_filter": "review_state=manual_adjusted",
        "normalization": "canvas_diagonal",
        "float_precision_decimals": FLOAT_PRECISION_DECIMALS,
    }
    input_identity = {
        "project_id": project_id,
        "pose_observations_sha256": pose_sha,
        "resolved_project_sha256": resolved_sha,
        "override_sha256": override_sha,
        "override_revision": revision,
        "references": {joint_id: list(references[joint_id]) for joint_id in reference_ids},
    }
    input_sha = canonical_sha256(input_identity)
    config_sha = canonical_sha256(config)
    run_sha = canonical_sha256(
        {
            "input_sha256": input_sha,
            "evaluator": EVALUATOR_ID,
            "evaluator_version": EVALUATOR_VERSION,
            "config_sha256": config_sha,
        }
    )
    return {
        "format": "autospine-pose-evaluation",
        "format_version": 1,
        "project_id": project_id,
        "source": {
            "pose_observations_sha256": pose_sha,
            "composite_sha256": observations.image_sha256,
            "resolved_project_sha256": resolved_sha,
            "override_sha256": override_sha,
            "override_revision": revision,
            "canvas_size": [width, height],
        },
        "evaluator": {
            "id": EVALUATOR_ID,
            "version": EVALUATOR_VERSION,
            "input_sha256": input_sha,
            "config_sha256": config_sha,
            "run_sha256": run_sha,
        },
        "reference": {
            "kind": "manual_adjusted_override",
            "requested_joint_ids": list(LIMB_JOINT_IDS),
            "reference_joint_ids": reference_ids,
            "missing_reference_ids": missing_reference_ids,
        },
        "metrics": metrics,
        "matched_joint_ids": matched_ids,
        "missing_observation_ids": missing_observation_ids,
        "joints": joint_reports,
        "side_swap_diagnostic": swap_diagnostic,
        "qa": {"status": "diagnostic", "flags": sorted(flags)},
    }


def _manual_references(
    resolved: Mapping[str, Any], width: int, height: int
) -> dict[str, tuple[float, float]]:
    skeleton = resolved.get("skeleton")
    if not isinstance(skeleton, Mapping) or not isinstance(skeleton.get("joints"), list):
        raise PoseEvaluationError("Resolved snapshot has no skeleton joints")
    references: dict[str, tuple[float, float]] = {}
    for joint in skeleton["joints"]:
        if not isinstance(joint, Mapping) or joint.get("review_state") != "manual_adjusted":
            continue
        joint_id = joint.get("id")
        if joint_id not in LIMB_JOINT_IDS:
            continue
        if joint_id in references:
            raise PoseEvaluationError("Resolved snapshot contains duplicate joint ids")
        x, y = joint.get("x"), joint.get("y")
        if not _finite(x) or not _finite(y) or not 0 <= float(x) <= width or not 0 <= float(y) <= height:
            raise PoseEvaluationError(f"Manual reference {joint_id} is invalid")
        references[str(joint_id)] = (float(x), float(y))
    return references


def _metrics(
    distances: Iterable[float], diagonal: float, reference_count: int
) -> dict[str, Any]:
    values = list(distances)
    count = len(values)
    result: dict[str, Any] = {
        "requested_count": len(LIMB_JOINT_IDS),
        "reference_count": reference_count,
        "matched_count": count,
        "reference_coverage": _quantize(reference_count / len(LIMB_JOINT_IDS)),
        "observation_coverage": _quantize(count / reference_count),
    }
    if not values:
        result.update(
            mean_error_px=None,
            median_error_px=None,
            rmse_error_px=None,
            max_error_px=None,
            mean_error_canvas_diagonal_ratio=None,
        )
        return result
    mean_error = statistics.fmean(values)
    result.update(
        mean_error_px=_quantize(mean_error),
        median_error_px=_quantize(statistics.median(values)),
        rmse_error_px=_quantize(math.sqrt(statistics.fmean(value * value for value in values))),
        max_error_px=_quantize(max(values)),
        mean_error_canvas_diagonal_ratio=_quantize(mean_error / diagonal),
    )
    return result


def _side_swap_diagnostic(
    references: Mapping[str, tuple[float, float]], observations: PoseObservationSet
) -> dict[str, Any]:
    as_mapped: list[float] = []
    swapped: list[float] = []
    pair_count = 0
    for name in _PAIR_NAMES:
        left_id, right_id = f"{name}.left", f"{name}.right"
        if (
            left_id not in references
            or right_id not in references
            or left_id not in observations.joints
            or right_id not in observations.joints
        ):
            continue
        pair_count += 1
        left_observation, right_observation = observations.joints[left_id], observations.joints[right_id]
        as_mapped.extend(
            (
                _distance(left_observation.x, left_observation.y, references[left_id]),
                _distance(right_observation.x, right_observation.y, references[right_id]),
            )
        )
        swapped.extend(
            (
                _distance(left_observation.x, left_observation.y, references[right_id]),
                _distance(right_observation.x, right_observation.y, references[left_id]),
            )
        )
    if not pair_count:
        return {
            "complete_pair_count": 0,
            "as_mapped_mean_error_px": None,
            "swapped_mean_error_px": None,
            "swapped_minus_as_mapped_px": None,
            "lower_error_mapping": "insufficient",
        }
    as_mean, swapped_mean = statistics.fmean(as_mapped), statistics.fmean(swapped)
    if math.isclose(as_mean, swapped_mean, rel_tol=0, abs_tol=1e-9):
        lower = "tie"
    else:
        lower = "as_mapped" if as_mean < swapped_mean else "swapped"
    return {
        "complete_pair_count": pair_count,
        "as_mapped_mean_error_px": _quantize(as_mean),
        "swapped_mean_error_px": _quantize(swapped_mean),
        "swapped_minus_as_mapped_px": _quantize(swapped_mean - as_mean),
        "lower_error_mapping": lower,
    }


def _distance(x: float, y: float, reference: tuple[float, float]) -> float:
    return math.hypot(x - reference[0], y - reference[1])


def _quantize(value: float) -> float:
    return round(float(value), FLOAT_PRECISION_DECIMALS)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
