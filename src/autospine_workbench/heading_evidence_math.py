"""Small deterministic math kernel for reviewed Kimodo heading evidence."""

from __future__ import annotations

import math

from .kimodo_npz_consistency import HEADING_NORM_TOLERANCE


DECIMALS = 9
_EPSILON = 1e-9
_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


class HeadingEvidenceMathError(ValueError):
    """Raised when heading or root-forward projection is not observable."""


def heading_frame_math(
    raw_components,
    component_axes,
    camera_basis,
    root_global_matrix,
    root_local_forward_axis: str,
) -> dict:
    """Interpret one reviewed two-component direction and cross-check root FK."""

    mapped = map_heading_components(
        raw_components, component_axes, camera_basis
    )
    world = mapped["world_direction_xyz"]
    lateral = mapped["camera_screen_x_component"]
    depth = mapped["camera_depth_component"]

    matrix = _matrix(root_global_matrix)
    local = [0.0, 0.0, 0.0]
    local_index, local_sign = _axis(root_local_forward_axis)
    local[local_index] = local_sign
    root_world = [
        sum(matrix[row][axis] * local[axis] for axis in range(3))
        for row in range(3)
    ]
    root_lateral = _axis_component(root_world, camera_basis["screen_x"])
    root_depth = _axis_component(root_world, camera_basis["depth"])
    root_length = math.hypot(root_lateral, root_depth)
    if root_length <= _EPSILON:
        raise HeadingEvidenceMathError(
            "Root local-forward is degenerate in the camera plane"
        )
    heading_length = math.hypot(lateral, depth)
    dot = (
        lateral * root_lateral + depth * root_depth
    ) / (heading_length * root_length)
    angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
    return {
        **mapped,
        "root_forward_camera_screen_x_component": _q(
            root_lateral / root_length
        ),
        "root_forward_camera_depth_component": _q(root_depth / root_length),
        "root_forward_angle_error_deg": _q(angle),
    }


def map_heading_components(raw_components, component_axes, camera_basis) -> dict:
    """Map only reviewed raw components; do not infer any root semantics."""

    raw = _vector(raw_components, 2, "raw heading")
    if abs(math.hypot(*raw) - 1.0) > HEADING_NORM_TOLERANCE:
        raise HeadingEvidenceMathError("Raw heading is not a unit direction")
    axes = tuple(component_axes)
    if len(axes) != 2:
        raise HeadingEvidenceMathError("Heading component axis count is invalid")
    world = [0.0, 0.0, 0.0]
    for value, token in zip(raw, axes):
        index, sign = _axis(token)
        world[index] += value * sign
    lateral = _axis_component(world, camera_basis["screen_x"])
    depth = _axis_component(world, camera_basis["depth"])
    if math.hypot(lateral, depth) <= _EPSILON:
        raise HeadingEvidenceMathError("Heading is degenerate in the camera plane")
    return {
        "world_direction_xyz": [_q(value) for value in world],
        "camera_screen_x_component": _q(lateral),
        "camera_depth_component": _q(depth),
        "raw_yaw_deg": _q(math.degrees(math.atan2(lateral, depth))),
    }


def unwrap_yaw_degrees(values) -> tuple[float, ...]:
    """Unwrap canonical atan2 samples without hiding full turns."""

    raw = [_number(value, "yaw") for value in values]
    if not raw:
        raise HeadingEvidenceMathError("Heading yaw sequence is empty")
    result = [raw[0]]
    for value in raw[1:]:
        delta = (value - result[-1] + 180.0) % 360.0 - 180.0
        result.append(_q(result[-1] + delta))
    return tuple(_q(value) for value in result)


def _axis_component(vector, token: str) -> float:
    index, sign = _axis(token)
    return float(vector[index]) * sign


def _axis(token: str) -> tuple[int, float]:
    if not isinstance(token, str) or len(token) != 2 \
            or token[0] not in "+-" or token[1] not in _AXIS_INDEX:
        raise HeadingEvidenceMathError("Signed axis is invalid")
    return _AXIS_INDEX[token[1]], -1.0 if token[0] == "-" else 1.0


def _matrix(value) -> tuple[tuple[float, ...], ...]:
    try:
        rows = tuple(tuple(_number(item, "matrix") for item in row) for row in value)
    except TypeError as exc:
        raise HeadingEvidenceMathError("Root global matrix is invalid") from exc
    if len(rows) != 3 or any(len(row) != 3 for row in rows):
        raise HeadingEvidenceMathError("Root global matrix is invalid")
    return rows


def _vector(value, length: int, label: str) -> tuple[float, ...]:
    try:
        result = tuple(_number(item, label) for item in value)
    except TypeError as exc:
        raise HeadingEvidenceMathError(f"{label} is invalid") from exc
    if len(result) != length:
        raise HeadingEvidenceMathError(f"{label} is invalid")
    return result


def _number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > 1e12:
        raise HeadingEvidenceMathError(f"{label} must be finite and bounded")
    return float(value)


def _q(value: float) -> float:
    result = round(_number(value, "heading result"), DECIMALS)
    return 0.0 if result == 0 else result
