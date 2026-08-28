"""Fail-closed bridge from ProjectedMotionIR v1 to legacy MotionIR v1."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math
from typing import Any

from .kimodo_npz_projection import PRECISION_DECIMALS
from .motion_validation import (
    FORMAT,
    FORMAT_VERSION,
    MotionValidationError,
    motion_coordinate_system,
    require_motion_ir,
)
from .projected_motion_geometry_validation import ProjectedMotionValidationError
from .projected_motion_validation import require_projected_motion_ir


class ProjectedMotionLegacyError(ValueError):
    """Raised when projected evidence cannot safely form legacy MotionIR."""


def compile_projected_motion_to_motion_ir(
    projected_motion: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile observable projected tracks into setup-local MotionIR v1.

    MotionIR v1 cannot represent collapsed projection evidence.  The bridge
    therefore rejects the entire input instead of carrying an old angle or
    inventing a replacement value.
    """

    try:
        require_projected_motion_ir(projected_motion)
        tracks = projected_motion["segment_tracks"]
        _reject_collapsed_samples(tracks)
        world_changes = _world_angle_changes(tracks)
        output_tracks = _rotation_tracks(tracks, world_changes)
        output_tracks.append(_root_translation_track(projected_motion))
        output_tracks.sort(key=lambda track: (
            track["target_kind"], track["target"], track["property"]
        ))
        timing = projected_motion["timing"]
        result = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "clip_id": projected_motion["clip_id"],
            "ticks_per_second": timing["ticks_per_second"],
            "duration_ticks": timing["duration_ticks"],
            "loop": timing["loop"],
            "coordinate_system": motion_coordinate_system(),
            "tracks": output_tracks,
            "markers": deepcopy(projected_motion["markers"]),
        }
        require_motion_ir(result)
        return result
    except ProjectedMotionLegacyError:
        raise
    except (
        KeyError,
        MotionValidationError,
        ProjectedMotionValidationError,
        TypeError,
        ValueError,
    ) as exc:
        raise ProjectedMotionLegacyError(
            f"ProjectedMotionIR legacy compilation failed: {exc}"
        ) from exc


def _reject_collapsed_samples(tracks) -> None:
    for track in tracks:
        for sample in track["samples"]:
            if sample["projection_state"] == "collapsed":
                raise ProjectedMotionLegacyError(
                    "ProjectedMotionIR legacy compilation rejects collapsed "
                    f"sample {track['role']} frame "
                    f"{sample['source_frame_index']}"
                )


def _world_angle_changes(tracks) -> dict[str, tuple[float, ...]]:
    # Keep the sealed nine-decimal evidence intact until the setup-local
    # subtraction is complete.  Quantizing each world delta first can move a
    # child and its parent across different five-decimal rounding boundaries.
    result = {}
    for track in tracks:
        samples = track["samples"]
        baseline = float(samples[0]["projected_world_angle_deg"])
        result[track["role"]] = tuple(
            float(sample["projected_world_angle_deg"]) - baseline
            for sample in samples
        )
    return result


def _rotation_tracks(tracks, world_changes) -> list[dict[str, Any]]:
    result = []
    for track in tracks:
        role = track["role"]
        parent = track["delta_parent_role"]
        values = world_changes[role]
        parent_values = world_changes[parent] if parent is not None else None
        result.append({
            "target_kind": "bone_role",
            "target": role,
            "property": "rotation",
            "interpolation": "linear",
            "keys": [
                {
                    "tick": sample["tick"],
                    "value": _quantize(
                        values[index]
                        - (parent_values[index] if parent_values else 0.0)
                    ),
                }
                for index, sample in enumerate(track["samples"])
            ],
        })
    return result


def _root_translation_track(projected_motion) -> dict[str, Any]:
    return {
        "target_kind": "bone_role",
        "target": "humanoid.root",
        "property": "translation",
        "interpolation": "linear",
        "keys": [
            {
                "tick": sample["tick"],
                "value": [
                    _quantize(float(component))
                    for component in sample["screen_translation_normalized"]
                ],
            }
            for sample in projected_motion["root_samples"]
        ],
    }


def _quantize(value: float) -> float:
    if not math.isfinite(value):
        raise ProjectedMotionLegacyError(
            "ProjectedMotionIR legacy compilation produced non-finite output"
        )
    result = round(float(value), PRECISION_DECIMALS)
    return 0.0 if result == 0 else result
