"""Shared deterministic track overlay used by v2 compile and exact review."""

from __future__ import annotations

import json
from typing import Any

from .motion_instance_v2_sampling import quantize_vector, sample_vector_keys
from .motion_roles import CANONICAL_BONE_ID_BY_ROLE


ROOT_BONE_ID = CANONICAL_BONE_ID_BY_ROLE["humanoid.root"]
ROOT_TRACK_ID = (ROOT_BONE_ID, "translation")


def overlay_motion_tracks(base: dict, policy: dict) -> list[dict[str, Any]]:
    """Return base tracks with the reviewed correction added to root motion."""

    tracks = [_copy(row) for row in base["tracks"]]
    root_index = next(
        (index for index, row in enumerate(tracks)
         if (row["bone_id"], row["property"]) == ROOT_TRACK_ID),
        None,
    )
    base_keys = [] if root_index is None else tracks[root_index]["keys"]
    correction_keys = policy["root_correction_keys"]
    ticks = {0, base["timing"]["duration_ticks"]}
    ticks.update(row["tick"] for row in base_keys)
    ticks.update(row["tick"] for row in correction_keys)
    root_track = {
        "bone_id": ROOT_BONE_ID,
        "property": "translation",
        "keys": [{
            "tick": tick,
            "value": _sum_at_tick(base_keys, correction_keys, tick),
        } for tick in sorted(ticks)],
    }
    if root_index is None:
        tracks.append(root_track)
    else:
        tracks[root_index] = root_track
    return sorted(tracks, key=lambda row: (row["bone_id"], row["property"]))


def _sum_at_tick(base_keys, correction_keys, tick: int) -> list[float]:
    base = (
        (0.0, 0.0) if not base_keys else
        sample_vector_keys(base_keys, tick, value_field="value")
    )
    correction = sample_vector_keys(
        correction_keys, tick, value_field="correction_xy_px"
    )
    return quantize_vector((
        base[0] + correction[0], base[1] + correction[1]
    ))


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
