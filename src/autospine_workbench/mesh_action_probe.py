"""Deterministic setup, rigid, and two-direction bend probes for P3 meshes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import json
from typing import Any, TypeAlias

from .mesh_action_probe_inputs import ActionProbeInputError, normalize_probe_input
from .mesh_deformation_metrics import (
    DeformationMetrics,
    DeformationMetricsError,
    measure_deformation,
)
from .mesh_skinning import MeshSkinningError, skin_vertices_lbs


BEND_STEP_DEGREES = 5
MAX_BEND_DEGREES = 135
MIN_AREA_RATIO = 0.02
MAX_AREA_RATIO = 20.0
MAX_EDGE_STRETCH = 3.0

Point: TypeAlias = tuple[float, float]


class MeshActionProbeError(ValueError):
    """Raised when an action probe cannot produce trustworthy evidence."""


@dataclass(frozen=True, slots=True)
class ProbeThresholds:
    min_area_ratio: float = MIN_AREA_RATIO
    max_area_ratio: float = MAX_AREA_RATIO
    max_edge_stretch: float = MAX_EDGE_STRETCH

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ActionPoseEvidence:
    pose_id: str
    bone_id: str | None
    angle_deg: int
    status: str
    reasons: tuple[str, ...]
    metrics: DeformationMetrics

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        return result


@dataclass(frozen=True, slots=True)
class BendSweep:
    direction: str
    max_contiguous_magnitude_deg: int
    first_failure: ActionPoseEvidence | None
    samples: tuple[ActionPoseEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "max_contiguous_magnitude_deg": self.max_contiguous_magnitude_deg,
            "first_failure": (
                self.first_failure.to_dict() if self.first_failure else None
            ),
            "samples": [sample.to_dict() for sample in self.samples],
        }


@dataclass(frozen=True, slots=True)
class MeshActionProbeResult:
    step_degrees: int
    maximum_bend_degrees: int
    thresholds: ProbeThresholds
    setup_canvas_vertices_xy: tuple[Point, ...]
    setup: ActionPoseEvidence
    proximal_negative: ActionPoseEvidence
    proximal_positive: ActionPoseEvidence
    distal_negative: BendSweep
    distal_positive: BendSweep

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "autospine-mesh-action-probe",
            "format_version": 1,
            "profile": "two-bone-lbs-action-probe-v1",
            "status": "passed",
            "step_degrees": self.step_degrees,
            "maximum_bend_degrees": self.maximum_bend_degrees,
            "thresholds": self.thresholds.to_dict(),
            "setup_canvas_vertices_xy": [
                [x, y] for x, y in self.setup_canvas_vertices_xy
            ],
            "setup": self.setup.to_dict(),
            "proximal_rigid": {
                "negative": self.proximal_negative.to_dict(),
                "positive": self.proximal_positive.to_dict(),
            },
            "distal_bend": {
                "negative": self.distal_negative.to_dict(),
                "positive": self.distal_positive.to_dict(),
            },
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )


def run_mesh_action_probe(
    rig_bones: Sequence[Mapping[str, Any]],
    mesh_attachment: Mapping[str, Any],
    *,
    proximal_bone_id: str,
    distal_bone_id: str,
    step_degrees: int = BEND_STEP_DEGREES,
) -> MeshActionProbeResult:
    """Probe one source-local RigIR mesh against its designated bone chain."""

    if type(step_degrees) is not int or step_degrees != BEND_STEP_DEGREES:
        raise MeshActionProbeError("action probe step must be the pinned 5 degrees")
    try:
        inputs = normalize_probe_input(
            rig_bones, mesh_attachment, proximal_bone_id, distal_bone_id
        )
    except ActionProbeInputError as exc:
        raise MeshActionProbeError(str(exc)) from exc
    bones = inputs.rig_bones
    vertices, triangles, weights = (
        inputs.vertices_xy, inputs.triangles, inputs.weights
    )

    setup, setup_vertices = _evaluate(
        bones, vertices, triangles, weights, {}, "setup", None, 0
    )
    _require_passed(setup, "setup pose")
    proximal_negative = _rigid_probe(
        -90, bones, vertices, triangles, weights, proximal_bone_id
    )
    proximal_positive = _rigid_probe(
        90, bones, vertices, triangles, weights, proximal_bone_id
    )

    distal_negative = _sweep(
        -1, bones, vertices, triangles, weights, distal_bone_id
    )
    distal_positive = _sweep(
        1, bones, vertices, triangles, weights, distal_bone_id
    )
    return MeshActionProbeResult(
        step_degrees=BEND_STEP_DEGREES,
        maximum_bend_degrees=MAX_BEND_DEGREES,
        thresholds=ProbeThresholds(),
        setup_canvas_vertices_xy=setup_vertices,
        setup=setup,
        proximal_negative=proximal_negative,
        proximal_positive=proximal_positive,
        distal_negative=distal_negative,
        distal_positive=distal_positive,
    )


def _sweep(direction, bones, vertices, triangles, weights, distal_id) -> BendSweep:
    samples: list[ActionPoseEvidence] = []
    maximum = 0
    first_failure: ActionPoseEvidence | None = None
    for magnitude in range(BEND_STEP_DEGREES, MAX_BEND_DEGREES + 1, BEND_STEP_DEGREES):
        angle = direction * magnitude
        evidence, _ = _evaluate(
            bones,
            vertices,
            triangles,
            weights,
            {distal_id: angle},
            f"distal:{angle:+04d}",
            distal_id,
            angle,
        )
        samples.append(evidence)
        if first_failure is None:
            if evidence.status == "passed":
                maximum = magnitude
            else:
                first_failure = evidence
    return BendSweep(
        direction="negative" if direction < 0 else "positive",
        max_contiguous_magnitude_deg=maximum,
        first_failure=first_failure,
        samples=tuple(samples),
    )


def _rigid_probe(angle, bones, vertices, triangles, weights, proximal_id):
    evidence, _ = _evaluate(
        bones, vertices, triangles, weights, {proximal_id: angle},
        f"proximal:{angle:+04d}", proximal_id, angle,
    )
    _require_passed(evidence, f"proximal rigid {angle:+d} pose")
    return evidence


def _evaluate(bones, vertices, triangles, weights, pose, pose_id, bone_id, angle):
    try:
        posed = skin_vertices_lbs(bones, vertices, weights, pose)
        assessment = measure_deformation(
            vertices,
            posed,
            triangles,
            min_area_ratio=MIN_AREA_RATIO,
            max_area_ratio=MAX_AREA_RATIO,
            max_edge_stretch=MAX_EDGE_STRETCH,
        )
    except (MeshSkinningError, DeformationMetricsError) as exc:
        raise MeshActionProbeError(f"action pose {pose_id} is invalid: {exc}") from exc
    evidence = ActionPoseEvidence(
        pose_id=pose_id,
        bone_id=bone_id,
        angle_deg=angle,
        status=assessment.status,
        reasons=assessment.reasons,
        metrics=assessment.metrics,
    )
    return evidence, posed


def _require_passed(evidence: ActionPoseEvidence, label: str) -> None:
    if evidence.status != "passed":
        reasons = ", ".join(evidence.reasons) or "unknown deformation failure"
        raise MeshActionProbeError(f"{label} failed strict thresholds: {reasons}")
