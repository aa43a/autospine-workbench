"""Strict canonical input boundary for external pose detector observations."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from .resolved_project import canonical_sha256


MAX_POSE_DOCUMENT_BYTES = 1_000_000
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VISIBILITY = frozenset({"visible", "occluded", "out_of_frame", "unknown"})
_SELECTION = frozenset({"single", "manual", "largest_area", "tracker"})


class PoseObservationError(ValueError):
    """Raised when detector output cannot be consumed without guessing."""


@dataclass(frozen=True, slots=True)
class PoseJointObservation:
    x: float
    y: float
    detector_score: float
    visibility: str


@dataclass(frozen=True, slots=True)
class PoseObservationSet:
    project_id: str
    image_sha256: str
    canvas_size: tuple[int, int]
    detector_id: str
    detector_version: str
    model_revision: str
    config_sha256: str
    runtime: str
    detected_count: int
    selected_index: int
    selection_method: str
    joints: Mapping[str, PoseJointObservation]
    document_sha256: str
    document: Mapping[str, Any] | None = None


def load_pose_observations(
    path: Path,
    *,
    expected_project_id: str,
    expected_image_sha256: str,
    expected_canvas_size: tuple[int, int],
) -> PoseObservationSet:
    document = _read_document(Path(path))
    root = _mapping(document, "$")
    _fields(
        root,
        {
            "format",
            "format_version",
            "project_id",
            "source",
            "detector",
            "subject",
            "coordinate_system",
            "joints",
        },
        "$",
    )
    if root.get("format") != "autospine-pose-observations" or root.get("format_version") != 1:
        raise PoseObservationError("Unsupported pose observation format")
    project_id = _identifier(root.get("project_id"), "$.project_id")
    if project_id != expected_project_id:
        raise PoseObservationError("Pose observations belong to another project")

    source = _mapping(root.get("source"), "$.source")
    _fields(source, {"image_kind", "image_sha256", "canvas_size"}, "$.source")
    if source.get("image_kind") != "composite":
        raise PoseObservationError("Pose source must be the project composite")
    image_sha256 = _digest(source.get("image_sha256"), "$.source.image_sha256")
    if image_sha256 != expected_image_sha256:
        raise PoseObservationError("Pose source image hash does not match the project composite")
    canvas_size = _canvas(source.get("canvas_size"))
    if canvas_size != expected_canvas_size:
        raise PoseObservationError("Pose canvas does not match the project canvas")

    detector = _mapping(root.get("detector"), "$.detector")
    _fields(
        detector,
        {"id", "version", "model_revision", "config_sha256", "runtime"},
        "$.detector",
        optional={"model_sha256"},
    )
    detector_id = _identifier(detector.get("id"), "$.detector.id")
    detector_version = _text(detector.get("version"), "$.detector.version", 128)
    model_revision = _text(detector.get("model_revision"), "$.detector.model_revision", 256)
    config_sha256 = _digest(detector.get("config_sha256"), "$.detector.config_sha256")
    runtime = _text(detector.get("runtime"), "$.detector.runtime", 128)
    if "model_sha256" in detector:
        _digest(detector.get("model_sha256"), "$.detector.model_sha256")

    subject = _mapping(root.get("subject"), "$.subject")
    _fields(subject, {"detected_count", "selected_index", "selection_method"}, "$.subject")
    detected_count = _integer(subject.get("detected_count"), "$.subject.detected_count", 1, 100)
    selected_index = _integer(subject.get("selected_index"), "$.subject.selected_index", 0, 99)
    selection_method = subject.get("selection_method")
    if selection_method not in _SELECTION or selected_index >= detected_count:
        raise PoseObservationError("Selected pose subject is invalid")
    if detected_count == 1 and selection_method != "single":
        raise PoseObservationError("A single detected subject must use selection_method=single")
    if detected_count > 1 and selection_method == "single":
        raise PoseObservationError("Multiple subjects require an explicit selection method")

    _coordinate_system(root.get("coordinate_system"))
    joints = _joints(root.get("joints"), canvas_size)
    return PoseObservationSet(
        project_id=project_id,
        image_sha256=image_sha256,
        canvas_size=canvas_size,
        detector_id=detector_id,
        detector_version=detector_version,
        model_revision=model_revision,
        config_sha256=config_sha256,
        runtime=runtime,
        detected_count=detected_count,
        selected_index=selected_index,
        selection_method=str(selection_method),
        joints=joints,
        document_sha256=canonical_sha256(root),
        document=root,
    )


def _read_document(path: Path) -> Any:
    try:
        if path.stat().st_size > MAX_POSE_DOCUMENT_BYTES:
            raise PoseObservationError("Pose observation document is too large")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except PoseObservationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PoseObservationError("Cannot read pose observation document") from exc


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PoseObservationError(f"{path} must be an object")
    return value


def _fields(
    value: Mapping[str, Any],
    required: set[str],
    path: str,
    *,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    unknown = sorted(key for key in value if not isinstance(key, str) or key not in allowed)
    if unknown:
        raise PoseObservationError(f"{path} contains unknown fields")
    missing = sorted(field for field in required if field not in value)
    if missing:
        raise PoseObservationError(f"{path} is missing required fields")


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise PoseObservationError(f"{path} must be a safe identifier")
    return value


def _digest(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise PoseObservationError(f"{path} must be a lowercase SHA-256")
    return value


def _text(value: Any, path: str, limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise PoseObservationError(f"{path} must be non-empty text")
    return value


def _integer(value: Any, path: str, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise PoseObservationError(f"{path} is outside its integer range")
    return value


def _canvas(value: Any) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) or item < 1 for item in value)
    ):
        raise PoseObservationError("$.source.canvas_size must be [width, height]")
    return int(value[0]), int(value[1])


def _coordinate_system(value: Any) -> None:
    coordinate = _mapping(value, "$.coordinate_system")
    expected = {
        "origin": "top_left",
        "x_axis": "right",
        "y_axis": "down",
        "units": "pixel",
        "side_naming": "character_side",
    }
    _fields(coordinate, set(expected), "$.coordinate_system")
    if dict(coordinate) != expected:
        raise PoseObservationError("Pose coordinate system is not canonical")


def _joints(value: Any, canvas: tuple[int, int]) -> dict[str, PoseJointObservation]:
    raw_joints = _mapping(value, "$.joints")
    if not raw_joints:
        raise PoseObservationError("Pose observations must contain at least one joint")
    result: dict[str, PoseJointObservation] = {}
    for raw_id, raw_joint in raw_joints.items():
        joint_id = _identifier(raw_id, "$.joints")
        joint = _mapping(raw_joint, f"$.joints.{joint_id}")
        _fields(joint, {"xy", "detector_score", "visibility"}, f"$.joints.{joint_id}")
        xy = joint.get("xy")
        if not isinstance(xy, list) or len(xy) != 2 or not all(_finite(item) for item in xy):
            raise PoseObservationError(f"$.joints.{joint_id}.xy must contain finite numbers")
        x, y = float(xy[0]), float(xy[1])
        if not 0 <= x <= canvas[0] or not 0 <= y <= canvas[1]:
            raise PoseObservationError(f"$.joints.{joint_id}.xy lies outside the canvas")
        score = joint.get("detector_score")
        if not _finite(score) or not 0 <= float(score) <= 1:
            raise PoseObservationError(f"$.joints.{joint_id}.detector_score is invalid")
        visibility = joint.get("visibility")
        if visibility not in _VISIBILITY:
            raise PoseObservationError(f"$.joints.{joint_id}.visibility is invalid")
        result[joint_id] = PoseJointObservation(x, y, float(score), str(visibility))
    return result


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
