"""Direct half-open MotionIR contact markers from Kimodo boolean labels."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .kimodo_npz_map_validation import require_kimodo_npz_map
from .kimodo_npz_projection import KimodoProjectedFrames
from .kimodo_npz_reader import KimodoNpzSnapshot


class KimodoNpzContactError(ValueError):
    """Raised when declared contact evidence differs from the motion snapshot."""


def kimodo_contact_markers(
    snapshot: KimodoNpzSnapshot,
    projected: KimodoProjectedFrames,
    mapping: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Collapse explicit contact columns into sorted limb intervals."""

    require_kimodo_npz_map(mapping)
    contact = mapping["contact"]
    if not contact["enabled"]:
        return []
    if snapshot.raw_npz_sha256 != projected.raw_npz_sha256 \
            or snapshot.frame_count != len(projected.frames):
        raise KimodoNpzContactError(
            "Kimodo contact snapshot differs from projected motion"
        )
    array = snapshot.arrays.get("foot_contacts")
    if array is None:
        raise KimodoNpzContactError("Kimodo foot contact array is missing")
    by_limb = {"leg.left": [], "leg.right": []}
    for channel in contact["channels"]:
        by_limb[channel["limb"]].append(channel["index"])
    ticks = tuple(frame.tick for frame in projected.frames)
    markers = []
    for limb in ("leg.left", "leg.right"):
        flags = [
            any(array.bool_at(frame, channel) for channel in by_limb[limb])
            for frame in range(snapshot.frame_count - 1)
        ]
        for start, end in _true_runs(flags):
            markers.append({
                "kind": "contact",
                "limb": limb,
                "start_tick": ticks[start],
                "end_tick": ticks[end],
                "mode": "annotation_only",
            })
    markers.sort(key=lambda marker: (
        marker["start_tick"], marker["end_tick"], marker["limb"]
    ))
    return markers


def _true_runs(flags: list[bool]) -> tuple[tuple[int, int], ...]:
    runs, start = [], None
    for index, active in enumerate(flags):
        if active and start is None:
            start = index
        if not active and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(flags)))
    return tuple(runs)
