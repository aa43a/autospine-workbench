"""Matrix-FK consistency gate for immutable Kimodo SOMA77 snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math

from .kimodo_npz_reader import KimodoNpzSnapshot
from .kimodo_npz_source import kimodo_npz_source_sha256, require_kimodo_npz_source
from .kimodo_soma77 import SOMA77_JOINT_NAMES, SOMA77_PARENT_INDICES
from .npy_snapshot import NpyArraySnapshot


MATRIX_ORTHONORMAL_TOLERANCE = 5e-4
MATRIX_CROSSCHECK_TOLERANCE = 5e-4
POSITION_CROSSCHECK_METERS = 5e-4
HEADING_NORM_TOLERANCE = 5e-3
MAX_ABS_POSITION_METERS = 10_000.0
PRECISION_DECIMALS = 12
Matrix3 = tuple[tuple[float, float, float], ...]
Vector3 = tuple[float, float, float]


class KimodoNpzConsistencyError(ValueError):
    """Raised when redundant Kimodo arrays do not describe one motion."""


@dataclass(frozen=True, slots=True)
class ValidatedKimodoMotion:
    """Frozen FK reconstruction admitted by all redundant NPZ evidence."""

    raw_npz_sha256: str
    source_sha256: str
    array_inventory_sha256: str
    frame_count: int
    max_global_matrix_error: float
    max_position_error_meters: float
    max_root_position_error_meters: float
    max_heading_norm_error: float | None
    _positions: tuple[tuple[Vector3, ...], ...] = field(repr=False)

    @property
    def positions(self) -> tuple[tuple[Vector3, ...], ...]:
        return self._positions


def validate_kimodo_consistency(
    snapshot: KimodoNpzSnapshot,
    source: Mapping[str, object],
) -> ValidatedKimodoMotion:
    """Rebuild global matrices and positions from local rotations plus root."""

    try:
        require_kimodo_npz_source(source)
        if type(snapshot) is not KimodoNpzSnapshot \
                or snapshot.source_sha256 != kimodo_npz_source_sha256(source) \
                or snapshot.frame_count != source["raw_npz"]["frame_count"]:
            raise KimodoNpzConsistencyError(
                "Kimodo snapshot differs from its source interpretation"
            )
        arrays = snapshot.arrays
        required = {
            "local_rot_mats", "global_rot_mats", "posed_joints",
            "root_positions", "foot_contacts",
        }
        if not required.issubset(arrays):
            raise KimodoNpzConsistencyError("Kimodo motion arrays are incomplete")
        frame_zero_globals, matrix_error = _global_frame(arrays, 0)
        offsets = _frame_zero_offsets(arrays["posed_joints"], frame_zero_globals)
        positions, max_matrix, max_position, max_root = [], matrix_error, 0.0, 0.0
        for frame in range(snapshot.frame_count):
            globals_, error = _global_frame(arrays, frame)
            max_matrix = max(max_matrix, error)
            root = _vector(arrays["root_positions"], frame)
            _bounded_vector(root, "root position")
            rebuilt = _rebuild_positions(root, globals_, offsets)
            source_positions = tuple(
                _joint_vector(arrays["posed_joints"], frame, joint)
                for joint in range(len(SOMA77_JOINT_NAMES))
            )
            for point in source_positions:
                _bounded_vector(point, "posed joint")
            position_error = max(
                _vector_error(left, right)
                for left, right in zip(rebuilt, source_positions)
            )
            root_error = _vector_error(root, source_positions[0])
            if position_error > POSITION_CROSSCHECK_METERS \
                    or root_error > POSITION_CROSSCHECK_METERS:
                raise KimodoNpzConsistencyError(
                    "Kimodo local/root FK differs from posed joint evidence"
                )
            max_position = max(max_position, position_error)
            max_root = max(max_root, root_error)
            positions.append(rebuilt)
        heading_error = _optional_evidence(arrays, snapshot.frame_count)
        return ValidatedKimodoMotion(
            raw_npz_sha256=snapshot.raw_npz_sha256,
            source_sha256=snapshot.source_sha256,
            array_inventory_sha256=snapshot.array_inventory_sha256,
            frame_count=snapshot.frame_count,
            max_global_matrix_error=_quantize(max_matrix),
            max_position_error_meters=_quantize(max_position),
            max_root_position_error_meters=_quantize(max_root),
            max_heading_norm_error=(
                None if heading_error is None else _quantize(heading_error)
            ),
            _positions=tuple(positions),
        )
    except KimodoNpzConsistencyError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise KimodoNpzConsistencyError(
            f"Kimodo consistency validation failed: {exc}"
        ) from exc


def _global_frame(
    arrays: dict[str, NpyArraySnapshot], frame: int
) -> tuple[tuple[Matrix3, ...], float]:
    local_array, source_array = arrays["local_rot_mats"], arrays["global_rot_mats"]
    computed: list[Matrix3] = []
    maximum = 0.0
    for joint, parent in enumerate(SOMA77_PARENT_INDICES):
        local = _matrix(local_array, frame, joint)
        source_global = _matrix(source_array, frame, joint)
        _require_rotation(local, "local rotation")
        _require_rotation(source_global, "global rotation")
        global_ = local if parent is None else _multiply(computed[parent], local)
        error = _matrix_error(global_, source_global)
        if error > MATRIX_CROSSCHECK_TOLERANCE:
            raise KimodoNpzConsistencyError(
                "Kimodo local rotation hierarchy differs from global rotations"
            )
        maximum = max(maximum, error)
        computed.append(global_)
    return tuple(computed), maximum


def _frame_zero_offsets(
    posed: NpyArraySnapshot, globals_: tuple[Matrix3, ...]
) -> tuple[Vector3, ...]:
    points = tuple(
        _joint_vector(posed, 0, joint)
        for joint in range(len(SOMA77_JOINT_NAMES))
    )
    offsets: list[Vector3] = [(0.0, 0.0, 0.0)]
    for joint, parent in enumerate(SOMA77_PARENT_INDICES[1:], 1):
        if parent is None:
            raise KimodoNpzConsistencyError("SOMA77 hierarchy has multiple roots")
        delta = _subtract(points[joint], points[parent])
        offsets.append(_apply(_transpose(globals_[parent]), delta))
    return tuple(offsets)


def _rebuild_positions(
    root: Vector3,
    globals_: tuple[Matrix3, ...],
    offsets: tuple[Vector3, ...],
) -> tuple[Vector3, ...]:
    points: list[Vector3] = [root]
    for joint, parent in enumerate(SOMA77_PARENT_INDICES[1:], 1):
        if parent is None:
            raise KimodoNpzConsistencyError("SOMA77 hierarchy has multiple roots")
        points.append(_add(points[parent], _apply(globals_[parent], offsets[joint])))
    return tuple(points)


def _optional_evidence(
    arrays: dict[str, NpyArraySnapshot], frame_count: int
) -> float | None:
    smooth = arrays.get("smooth_root_pos")
    if smooth is not None:
        for frame in range(frame_count):
            _bounded_vector(_vector(smooth, frame), "smoothed root position")
    heading = arrays.get("global_root_heading")
    if heading is None:
        return None
    maximum = 0.0
    for frame in range(frame_count):
        x, y = heading.float_at(frame, 0), heading.float_at(frame, 1)
        error = abs(math.hypot(x, y) - 1.0)
        if error > HEADING_NORM_TOLERANCE:
            raise KimodoNpzConsistencyError(
                "Kimodo global root heading is not a unit direction"
            )
        maximum = max(maximum, error)
    return maximum


def _matrix(array: NpyArraySnapshot, frame: int, joint: int) -> Matrix3:
    return tuple(tuple(array.float_at(frame, joint, row, column)
                       for column in range(3)) for row in range(3))


def _joint_vector(array: NpyArraySnapshot, frame: int, joint: int) -> Vector3:
    return tuple(array.float_at(frame, joint, axis) for axis in range(3))


def _vector(array: NpyArraySnapshot, frame: int) -> Vector3:
    return tuple(array.float_at(frame, axis) for axis in range(3))


def _require_rotation(matrix: Matrix3, label: str) -> None:
    transpose = _transpose(matrix)
    identity = _multiply(transpose, matrix)
    orthogonal_error = max(
        abs(identity[row][column] - (1.0 if row == column else 0.0))
        for row in range(3) for column in range(3)
    )
    if orthogonal_error > MATRIX_ORTHONORMAL_TOLERANCE \
            or abs(_determinant(matrix) - 1.0) > MATRIX_ORTHONORMAL_TOLERANCE:
        raise KimodoNpzConsistencyError(f"Kimodo {label} is not in SO(3)")


def _multiply(left: Matrix3, right: Matrix3) -> Matrix3:
    return tuple(tuple(sum(left[row][axis] * right[axis][column]
                           for axis in range(3))
                       for column in range(3)) for row in range(3))


def _apply(matrix: Matrix3, vector: Vector3) -> Vector3:
    return tuple(sum(matrix[row][axis] * vector[axis] for axis in range(3))
                 for row in range(3))


def _transpose(matrix: Matrix3) -> Matrix3:
    return tuple(tuple(matrix[column][row] for column in range(3))
                 for row in range(3))


def _determinant(matrix: Matrix3) -> float:
    a, b, c = matrix
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def _matrix_error(left: Matrix3, right: Matrix3) -> float:
    return max(abs(left[row][column] - right[row][column])
               for row in range(3) for column in range(3))


def _vector_error(left: Vector3, right: Vector3) -> float:
    return max(abs(left[axis] - right[axis]) for axis in range(3))


def _bounded_vector(value: Vector3, label: str) -> None:
    if any(not math.isfinite(number) or abs(number) > MAX_ABS_POSITION_METERS
           for number in value):
        raise KimodoNpzConsistencyError(f"Kimodo {label} is outside its bounds")


def _add(left: Vector3, right: Vector3) -> Vector3:
    return tuple(left[index] + right[index] for index in range(3))


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(left[index] - right[index] for index in range(3))


def _quantize(value: float) -> float:
    result = round(float(value), PRECISION_DECIMALS)
    return 0.0 if result == 0 else result
