"""Strict pinned input contract for model-neutral COCO17 detections."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from .resolved_project import canonical_sha256


MAX_DETECTION_DOCUMENT_BYTES = 2_000_000
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VISIBILITY = frozenset({"visible", "occluded", "out_of_frame", "unknown"})


class Coco17DetectionError(ValueError):
    """Raised when COCO17 input would require an implicit interpretation."""


@dataclass(frozen=True, slots=True)
class Coco17Detection:
    keypoints: tuple[tuple[float, float], ...]
    keypoint_scores: tuple[float, ...]
    visibility: tuple[str, ...]
    bbox_xywh: tuple[float, float, float, float] | None
    instance_score: float | None


@dataclass(frozen=True, slots=True)
class Coco17DetectionSet:
    project_id: str
    image_sha256: str
    canvas_size: tuple[int, int]
    coordinate_image_space: str
    detector: Mapping[str, Any]
    detections: tuple[Coco17Detection, ...]
    document_sha256: str
    document: Mapping[str, Any]


def load_coco17_detections(
    path: Path,
    *,
    expected_project_id: str,
    expected_image_sha256: str,
    expected_canvas_size: tuple[int, int],
) -> Coco17DetectionSet:
    """Load detections already expressed in original project-canvas pixels."""

    root = _mapping(_read_document(Path(path)), "$")
    _fields(
        root,
        {
            "format",
            "format_version",
            "project_id",
            "source",
            "detector",
            "coordinate_system",
            "detected_count",
            "detections",
        },
        "$",
    )
    if root.get("format") != "autospine-coco17-detections" or root.get("format_version") != 1:
        raise Coco17DetectionError("Unsupported COCO17 detection format")
    project_id = _identifier(root.get("project_id"), "$.project_id")
    if project_id != expected_project_id:
        raise Coco17DetectionError("COCO17 detections belong to another project")

    source = _mapping(root.get("source"), "$.source")
    _fields(source, {"image_kind", "image_sha256", "canvas_size"}, "$.source")
    if source.get("image_kind") != "composite":
        raise Coco17DetectionError("COCO17 source must be the project composite")
    image_sha256 = _digest(source.get("image_sha256"), "$.source.image_sha256")
    if image_sha256 != expected_image_sha256:
        raise Coco17DetectionError("COCO17 source hash does not match the project composite")
    canvas_size = _canvas(source.get("canvas_size"))
    if canvas_size != expected_canvas_size:
        raise Coco17DetectionError("COCO17 canvas does not match the project canvas")

    detector = _detector(root.get("detector"))
    coordinate_image_space = _coordinate_system(root.get("coordinate_system"))
    detected_count = _integer(root.get("detected_count"), "$.detected_count", 1, 100)
    raw_detections = root.get("detections")
    if not isinstance(raw_detections, list) or len(raw_detections) != detected_count:
        raise Coco17DetectionError("$.detections must match detected_count")
    detections = tuple(
        _detection(value, f"$.detections[{index}]", canvas_size)
        for index, value in enumerate(raw_detections)
    )
    return Coco17DetectionSet(
        project_id=project_id,
        image_sha256=image_sha256,
        canvas_size=canvas_size,
        coordinate_image_space=coordinate_image_space,
        detector=detector,
        detections=detections,
        document_sha256=canonical_sha256(root),
        document=root,
    )


def _read_document(path: Path) -> Any:
    try:
        if path.stat().st_size > MAX_DETECTION_DOCUMENT_BYTES:
            raise Coco17DetectionError("COCO17 detection document is too large")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_unique_object)
    except Coco17DetectionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Coco17DetectionError("Cannot read COCO17 detection document") from exc


def _detector(value: Any) -> dict[str, Any]:
    detector = _mapping(value, "$.detector")
    _fields(
        detector,
        {"id", "version", "model_revision", "config_sha256", "runtime"},
        "$.detector",
        optional={"model_sha256"},
    )
    result = {
        "id": _identifier(detector.get("id"), "$.detector.id"),
        "version": _text(detector.get("version"), "$.detector.version", 128),
        "model_revision": _text(
            detector.get("model_revision"), "$.detector.model_revision", 256
        ),
        "config_sha256": _digest(
            detector.get("config_sha256"), "$.detector.config_sha256"
        ),
        "runtime": _text(detector.get("runtime"), "$.detector.runtime", 128),
    }
    if "model_sha256" in detector:
        result["model_sha256"] = _digest(
            detector.get("model_sha256"), "$.detector.model_sha256"
        )
    return result


def _detection(value: Any, path: str, canvas: tuple[int, int]) -> Coco17Detection:
    item = _mapping(value, path)
    _fields(
        item,
        {"keypoints", "keypoint_scores"},
        path,
        optional={"visibility", "bbox_xywh", "instance_score"},
    )
    raw_points = item.get("keypoints")
    if not isinstance(raw_points, list) or len(raw_points) != 17:
        raise Coco17DetectionError(f"{path}.keypoints must contain 17 [x, y] pairs")
    points: list[tuple[float, float]] = []
    for index, raw_point in enumerate(raw_points):
        if (
            not isinstance(raw_point, list)
            or len(raw_point) != 2
            or not all(_finite(number) for number in raw_point)
        ):
            raise Coco17DetectionError(f"{path}.keypoints[{index}] is invalid")
        x, y = float(raw_point[0]), float(raw_point[1])
        if not 0 <= x < canvas[0] or not 0 <= y < canvas[1]:
            raise Coco17DetectionError(f"{path}.keypoints[{index}] lies outside the canvas")
        points.append((x, y))

    raw_scores = item.get("keypoint_scores")
    if not isinstance(raw_scores, list) or len(raw_scores) != 17:
        raise Coco17DetectionError(f"{path}.keypoint_scores must contain 17 values")
    scores = tuple(_score(value, f"{path}.keypoint_scores[{index}]") for index, value in enumerate(raw_scores))

    raw_visibility = item.get("visibility", ["unknown"] * 17)
    if (
        not isinstance(raw_visibility, list)
        or len(raw_visibility) != 17
        or any(value not in _VISIBILITY for value in raw_visibility)
    ):
        raise Coco17DetectionError(f"{path}.visibility must contain 17 visibility labels")
    bbox = _bbox(item.get("bbox_xywh"), f"{path}.bbox_xywh", canvas)
    instance_score = (
        _score(item.get("instance_score"), f"{path}.instance_score")
        if "instance_score" in item
        else None
    )
    return Coco17Detection(
        keypoints=tuple(points),
        keypoint_scores=scores,
        visibility=tuple(str(value) for value in raw_visibility),
        bbox_xywh=bbox,
        instance_score=instance_score,
    )


def _bbox(
    value: Any, path: str, canvas: tuple[int, int]
) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4 or not all(_finite(item) for item in value):
        raise Coco17DetectionError(f"{path} must be finite [x, y, width, height]")
    x, y, width, height = (float(item) for item in value)
    if width <= 0 or height <= 0 or x >= canvas[0] or y >= canvas[1] or x + width <= 0 or y + height <= 0:
        raise Coco17DetectionError(f"{path} must have positive area intersecting the canvas")
    return x, y, width, height


def _coordinate_system(value: Any) -> str:
    coordinate = _mapping(value, "$.coordinate_system")
    expected = {
        "origin": "top_left",
        "x_axis": "right",
        "y_axis": "down",
        "units": "pixel",
        "side_naming": "coco_character_side",
    }
    _fields(coordinate, set(expected) | {"image_space"}, "$.coordinate_system")
    if any(coordinate.get(key) != expected_value for key, expected_value in expected.items()):
        raise Coco17DetectionError("COCO17 coordinates must be original-canvas pixels")
    image_space = coordinate.get("image_space")
    if image_space not in {"project_canvas", "horizontally_mirrored_project_canvas"}:
        raise Coco17DetectionError("COCO17 coordinate image_space must be explicit")
    return str(image_space)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Coco17DetectionError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Coco17DetectionError(f"{path} must be an object")
    return value


def _fields(
    value: Mapping[str, Any],
    required: set[str],
    path: str,
    *,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    if any(not isinstance(key, str) or key not in allowed for key in value):
        raise Coco17DetectionError(f"{path} contains unknown fields")
    if any(field not in value for field in required):
        raise Coco17DetectionError(f"{path} is missing required fields")


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise Coco17DetectionError(f"{path} must be a safe identifier")
    return value


def _digest(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise Coco17DetectionError(f"{path} must be a lowercase SHA-256")
    return value


def _text(value: Any, path: str, limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise Coco17DetectionError(f"{path} must be non-empty text")
    return value


def _integer(value: Any, path: str, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise Coco17DetectionError(f"{path} is outside its integer range")
    return value


def _canvas(value: Any) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) or item < 1 for item in value)
    ):
        raise Coco17DetectionError("$.source.canvas_size must be [width, height]")
    return int(value[0]), int(value[1])


def _score(value: Any, path: str) -> float:
    if not _finite(value) or not 0 <= float(value) <= 1:
        raise Coco17DetectionError(f"{path} must lie in [0, 1]")
    return float(value)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
