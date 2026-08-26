"""Exact ancillary-array extraction for Kimodo policy evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .kimodo_npz_consistency import validate_kimodo_consistency
from .kimodo_npz_reader import decode_kimodo_npz


_CONTACT_ROWS = {
    "left-heel-toe-right-heel-toe-v1": (
        (0, "leg.left", "heel"),
        (1, "leg.left", "toe"),
        (2, "leg.right", "heel"),
        (3, "leg.right", "toe"),
    ),
    "left-heel-toe-toe_end-right-heel-toe-toe_end-v1": (
        (0, "leg.left", "heel"),
        (1, "leg.left", "toe"),
        (2, "leg.left", "toe_end"),
        (3, "leg.right", "heel"),
        (4, "leg.right", "toe"),
        (5, "leg.right", "toe_end"),
    ),
}


def extract_kimodo_policy_arrays(
    raw_npz: bytes,
    source: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Decode exact NPZ bytes and preserve policy-relevant raw channels."""

    snapshot = decode_kimodo_npz(raw_npz, source)
    validate_kimodo_consistency(snapshot, source)
    arrays = snapshot.arrays
    frames = snapshot.frame_count
    inventory = source["array_profile"]["inventory"]
    layout = source["array_profile"]["contact_layout"]
    contacts = arrays["foot_contacts"]
    signals = {
        "foot_contact_channels": {
            "status": "available",
            "source_array": "foot_contacts",
            "dtype": contacts.dtype,
            "shape": list(contacts.shape),
            "layout": layout,
            "raw_npy_sha256": contacts.raw_npy_sha256,
            "payload_sha256": contacts.payload_sha256,
            "channels": [
                {
                    "index": index,
                    "limb": limb,
                    "point": point,
                    "values": [
                        contacts.bool_at(frame, index) for frame in range(frames)
                    ],
                }
                for index, limb, point in _CONTACT_ROWS[layout]
            ],
        },
        "global_root_heading": _heading(arrays, frames, inventory),
        "smooth_root_position": _smooth_root(arrays, frames, inventory),
    }
    return {
        "inventory": inventory,
        "contact_layout": layout,
    }, signals


def _heading(arrays, frames: int, inventory: str) -> dict[str, Any]:
    array = arrays.get("global_root_heading")
    if array is None:
        return _unavailable("global_root_heading", inventory)
    return {
        "status": "available",
        "source_array": "global_root_heading",
        "dtype": array.dtype,
        "shape": list(array.shape),
        "coordinate_space": "source_two_component_uninterpreted",
        "unit": "unit_direction",
        "raw_npy_sha256": array.raw_npy_sha256,
        "payload_sha256": array.payload_sha256,
        "values": [
            [array.float_at(frame, component) for component in range(2)]
            for frame in range(frames)
        ],
    }


def _smooth_root(arrays, frames: int, inventory: str) -> dict[str, Any]:
    array = arrays.get("smooth_root_pos")
    if array is None:
        return _unavailable("smooth_root_pos", inventory)
    return {
        "status": "available",
        "source_array": "smooth_root_pos",
        "dtype": array.dtype,
        "shape": list(array.shape),
        "coordinate_space": "source_xyz",
        "unit": "meter",
        "raw_npy_sha256": array.raw_npy_sha256,
        "payload_sha256": array.payload_sha256,
        "values": [
            [array.float_at(frame, axis) for axis in range(3)]
            for frame in range(frames)
        ],
    }


def _unavailable(source_array: str, inventory: str) -> dict[str, Any]:
    if inventory != "core-v1":
        raise ValueError(f"Complete Kimodo array is missing: {source_array}")
    return {
        "status": "unavailable",
        "source_array": source_array,
        "reason_code": "array_not_in_core_v1",
    }
