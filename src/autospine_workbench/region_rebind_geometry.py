"""Prepared region-corner motion evidence for candidate bone bindings."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .mesh_skinning_prepared import (
    evaluate_skinning_pose,
    prepare_skinning_binding,
    prepare_skinning_rig,
    skin_prepared_vertices,
)
from .region_rebind_inputs import AdmittedRegionRebindInputs, relationship
from .region_rebind_profile import (
    NUMERIC_PRECISION_DECIMALS,
    SETUP_RECONSTRUCTION_TOLERANCE_PX,
)
from .resolved_project import canonical_sha256
from .rig_fk import evaluate_world_setup


@dataclass(frozen=True, slots=True)
class PreparedRegionRebindGeometry:
    admitted: AdmittedRegionRebindInputs
    skinning_rig: object
    samples: tuple[tuple[object, tuple[float, float], object], ...]
    setup_world: dict[str, dict]


def prepare_region_rebind_geometry(
    admitted: AdmittedRegionRebindInputs,
) -> PreparedRegionRebindGeometry:
    """Prepare the exact rig and every finite sampled FK pose once."""

    rig = prepare_skinning_rig(list(admitted.bones.values()))
    samples = tuple(
        (sample, translation, evaluate_skinning_pose(rig, dict(rotations)))
        for sample, rotations, translation in admitted.samples
    )
    return PreparedRegionRebindGeometry(
        admitted, rig, samples,
        evaluate_world_setup(list(admitted.bones.values())),
    )


def evaluate_region_rebind_candidate(prepared, source, bone_id):
    """Return bounded metrics and a digest of all sampled posed corners."""

    admitted, rig = prepared.admitted, prepared.skinning_rig
    corners = admitted.corners_xy
    weights = tuple(({"bone": bone_id, "weight": 1.0},) for _ in corners)
    binding = prepare_skinning_binding(rig, corners, weights)
    setup_pose = evaluate_skinning_pose(rig, {})
    reconstructed = skin_prepared_vertices(setup_pose, binding)
    setup_error = max(_distance(a, b) for a, b in zip(corners, reconstructed))
    if setup_error > SETUP_RECONSTRUCTION_TOLERANCE_PX:
        raise ValueError("candidate cannot reconstruct setup")
    observations, compensated_samples = [], []
    overflow_samples = overflow_vertices = 0
    max_overflow = 0.0
    envelope = [math.inf, math.inf, -math.inf, -math.inf]
    for sample, translation, pose in prepared.samples:
        local = skin_prepared_vertices(pose, binding)
        posed = tuple((x + translation[0], y + translation[1]) for x, y in local)
        overflow = tuple(_overflow(point, admitted.canvas_size) for point in posed)
        overflow_samples += int(any(value > 0.0 for value in overflow))
        overflow_vertices += sum(value > 0.0 for value in overflow)
        max_overflow = max(max_overflow, *overflow)
        _expand(envelope, posed)
        compensated_samples.append(tuple(
            (x - translation[0], y - translation[1]) for x, y in posed
        ))
        observations.append({"tick": sample.tick, "vertices_xy": _points(posed)})
    setup_center = _centroid(corners)
    centers = [
        _distance(_centroid(points), setup_center)
        for points in compensated_samples
    ]
    vertices = [
        _distance(point, corners[index])
        for points in compensated_samples for index, point in enumerate(points)
    ]
    diagonal = max(_distance(corners[0], corners[2]), 1e-12)
    subtree = _inside_subtree_segments(prepared, bone_id, corners)
    pivot = admitted.attachment.get("pivot_xy")
    pivot_xy = _finite_point(pivot, "region pivot")
    frame = prepared.setup_world[bone_id]
    metrics = {
        "sample_count": len(prepared.samples),
        "fk_status": "passed",
        "setup_reconstruction_max_error_px": quantize(setup_error),
        "root_compensated_centroid_motion_rms_px": quantize(_rms(centers)),
        "root_compensated_max_vertex_motion_px": quantize(max(vertices)),
        "normalized_centroid_motion_rms": quantize(_rms(centers) / diagonal),
        "normalized_max_vertex_motion": quantize(max(vertices) / diagonal),
        "setup_subtree_segment_coverage_count": len(subtree),
        "setup_subtree_segment_ids_fully_inside_region": list(subtree),
        "setup_pivot_distance_to_bone_origin_px": quantize(
            _distance(pivot_xy, frame["origin_xy"])
        ),
        "setup_pivot_distance_to_bone_endpoint_px": quantize(
            _distance(pivot_xy, frame["endpoint_xy"])
        ),
        "viewport_overflow_sample_count": overflow_samples,
        "viewport_overflow_vertex_count": overflow_vertices,
        "max_viewport_overflow_px": quantize(max_overflow),
        "sampled_envelope_xyxy": [quantize(value) for value in envelope],
    }
    payload = {"source": source, "bone_id": bone_id, "metrics": metrics}
    return {
        "candidate_id": f"region-rebind-{canonical_sha256(payload)}",
        "bone_id": bone_id,
        "relationship": relationship(
            admitted.current_bone_id, bone_id, admitted.bones,
        ),
        "hop_distance": 0 if bone_id == admitted.current_bone_id else 1,
        "metrics": metrics,
        "evidence_sha256": canonical_sha256({
            "source": source, "bone_id": bone_id, "observations": observations,
        }),
    }


def candidate_rank(row):
    metrics = row["metrics"]
    return (
        -metrics["setup_subtree_segment_coverage_count"],
        metrics["normalized_centroid_motion_rms"],
        metrics["normalized_max_vertex_motion"],
        metrics["viewport_overflow_sample_count"],
        metrics["max_viewport_overflow_px"], row["bone_id"],
    )


def quantize(value):
    result = round(float(value), NUMERIC_PRECISION_DECIMALS)
    return 0.0 if result == 0.0 else result


def _expand(envelope, points):
    for x, y in points:
        envelope[0] = min(envelope[0], x)
        envelope[1] = min(envelope[1], y)
        envelope[2] = max(envelope[2], x)
        envelope[3] = max(envelope[3], y)


def _overflow(point, canvas):
    x, y = point
    return max(0.0, -x, x - canvas[0], -y, y - canvas[1])


def _centroid(points):
    return (
        sum(x for x, _ in points) / len(points),
        sum(y for _, y in points) / len(points),
    )


def _distance(left, right):
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _rms(values):
    return math.sqrt(sum(value * value for value in values) / len(values))


def _points(value):
    return [[quantize(x), quantize(y)] for x, y in value]


def _inside_subtree_segments(prepared, bone_id, corners):
    admitted = prepared.admitted
    subtree = {bone_id, *(
        child for child, row in admitted.bones.items()
        if row.get("parent") == bone_id
    )}
    return tuple(sorted(
        candidate for candidate in subtree
        if _inside(prepared.setup_world[candidate]["origin_xy"], corners)
        and _inside(prepared.setup_world[candidate]["endpoint_xy"], corners)
    ))


def _inside(point, corners):
    xs, ys = [row[0] for row in corners], [row[1] for row in corners]
    return min(xs) <= point[0] <= max(xs) and min(ys) <= point[1] <= max(ys)


def _finite_point(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must contain two numbers")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must be finite")
    return result
