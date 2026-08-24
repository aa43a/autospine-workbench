"""Convert pinned COCO17 detections to canonical limb observations."""

from __future__ import annotations

from typing import Any

from .coco17_detections import Coco17DetectionSet


ADAPTER_ID = "coco17-limb-adapter"
ADAPTER_VERSION = "1"
FLOAT_PRECISION_DECIMALS = 6
SIDE_MAPPINGS = frozenset({"as_reported", "swap_left_right"})
VIEW_ORIENTATIONS = frozenset(
    {"front", "back", "left_profile", "right_profile", "three_quarter", "unknown"}
)
MIRROR_STATES = frozenset({"not_mirrored", "mirrored", "unknown"})

_COCO_LIMB_MAP = (
    (5, "shoulder.left"),
    (6, "shoulder.right"),
    (7, "elbow.left"),
    (8, "elbow.right"),
    (9, "wrist.left"),
    (10, "wrist.right"),
    (11, "hip.left"),
    (12, "hip.right"),
    (13, "knee.left"),
    (14, "knee.right"),
    (15, "ankle.left"),
    (16, "ankle.right"),
)


class Coco17AdapterError(ValueError):
    """Raised when subject or side selection is not explicit and reproducible."""


def adapt_coco17_detections(
    detections: Coco17DetectionSet,
    *,
    selected_index: int | None,
    selection_method: str | None,
    side_mapping: str,
    view_orientation: str,
    mirror_state: str,
) -> dict[str, Any]:
    """Build a pose-observations-v2 document without score calibration."""

    if side_mapping not in SIDE_MAPPINGS:
        raise Coco17AdapterError("side_mapping must be explicit")
    if view_orientation not in VIEW_ORIENTATIONS:
        raise Coco17AdapterError("view_orientation must be explicit")
    if mirror_state not in MIRROR_STATES:
        raise Coco17AdapterError("mirror_state must be explicit")
    selected_index, selection_method = _select_subject(
        detections, selected_index, selection_method
    )
    selected = detections.detections[selected_index]
    coordinate_transform = (
        "unmirror_x"
        if detections.coordinate_image_space == "horizontally_mirrored_project_canvas"
        else "identity"
    )
    joints: dict[str, Any] = {}
    for coco_index, reported_joint_id in _COCO_LIMB_MAP:
        joint_id = (
            _swap_side(reported_joint_id)
            if side_mapping == "swap_left_right"
            else reported_joint_id
        )
        x, y = selected.keypoints[coco_index]
        if coordinate_transform == "unmirror_x":
            x = detections.canvas_size[0] - 1 - x
        joints[joint_id] = {
            "xy": [_quantize(x), _quantize(y)],
            "detector_score": _quantize(selected.keypoint_scores[coco_index]),
            "visibility": selected.visibility[coco_index],
        }
    return {
        "format": "autospine-pose-observations",
        "format_version": 2,
        "project_id": detections.project_id,
        "source": {
            "image_kind": "composite",
            "image_sha256": detections.image_sha256,
            "canvas_size": list(detections.canvas_size),
        },
        "detector": dict(detections.detector),
        "subject": {
            "detected_count": len(detections.detections),
            "selected_index": selected_index,
            "selection_method": selection_method,
        },
        "adapter": {
            "id": ADAPTER_ID,
            "version": ADAPTER_VERSION,
            "input_format": "autospine-coco17-detections/v1",
            "input_document_sha256": detections.document_sha256,
            "input_side_naming": "coco_character_side",
            "coordinate_transform": coordinate_transform,
            "side_mapping": side_mapping,
            "view_orientation": view_orientation,
            "mirror_state": mirror_state,
            "float_precision_decimals": FLOAT_PRECISION_DECIMALS,
        },
        "coordinate_system": {
            "origin": "top_left",
            "x_axis": "right",
            "y_axis": "down",
            "units": "pixel",
            "side_naming": "character_side",
        },
        "joints": joints,
    }


def _select_subject(
    detections: Coco17DetectionSet,
    selected_index: int | None,
    selection_method: str | None,
) -> tuple[int, str]:
    count = len(detections.detections)
    if count == 1:
        if selected_index not in (None, 0) or selection_method not in (None, "single"):
            raise Coco17AdapterError("A single subject must use index 0 and method single")
        return 0, "single"
    if not isinstance(selected_index, int) or isinstance(selected_index, bool):
        raise Coco17AdapterError("Multiple subjects require --selected-index")
    if not 0 <= selected_index < count:
        raise Coco17AdapterError("Selected subject index is outside detections")
    if selection_method == "manual":
        return selected_index, "manual"
    if selection_method != "largest_area":
        raise Coco17AdapterError("Multiple subjects require manual or largest_area selection")
    areas = []
    for detection in detections.detections:
        if detection.bbox_xywh is None:
            raise Coco17AdapterError("largest_area selection requires every bbox_xywh")
        areas.append(detection.bbox_xywh[2] * detection.bbox_xywh[3])
    largest = max(areas)
    winners = [index for index, area in enumerate(areas) if area == largest]
    if len(winners) != 1 or selected_index != winners[0]:
        raise Coco17AdapterError("Selected subject is not the unique largest bbox")
    return selected_index, "largest_area"


def _swap_side(joint_id: str) -> str:
    if joint_id.endswith(".left"):
        return joint_id.rsplit(".", 1)[0] + ".right"
    if joint_id.endswith(".right"):
        return joint_id.rsplit(".", 1)[0] + ".left"
    raise AssertionError(f"Cannot swap non-sided joint: {joint_id}")


def _quantize(value: float) -> float:
    return round(float(value), FLOAT_PRECISION_DECIMALS)
