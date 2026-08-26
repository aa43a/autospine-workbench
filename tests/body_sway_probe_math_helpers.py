"""Compact exact inputs for P10.2 body-sway math tests."""

from __future__ import annotations

from copy import deepcopy

from autospine_workbench.idle_behavior_inventory import BODY_BONE_IDS


def timing(duration: int = 1_000_000, *, loop: bool = True) -> dict:
    return {
        "ticks_per_second": 1_000_000,
        "duration_ticks": duration,
        "loop": loop,
    }


def phases(values=(0.0, 0.125, 0.25, 0.75)) -> list[dict]:
    return [
        {"bone_id": bone_id, "value": value}
        for bone_id, value in zip(BODY_BONE_IDS, values, strict=True)
    ]


def amplitudes(values=(1.0, 1.0, 1.0, 1.0)) -> list[dict]:
    return [
        {"bone_id": bone_id, "value": value}
        for bone_id, value in zip(BODY_BONE_IDS, values, strict=True)
    ]


def tracks(
    duration: int = 1_000_000,
    *,
    authored_tick: int | None = None,
    rotation_end: float = 0.0,
    root_end=(0.0, 0.0),
) -> list[dict]:
    middle = duration // 2 if authored_tick is None else authored_tick
    if not 0 < middle < duration:
        raise ValueError("authored_tick must be inside the clip")
    result = [
        {
            "bone_id": "neck-head",
            "property": "rotation",
            "keys": [
                {"tick": 0, "value": 0.0},
                {"tick": middle, "value": 4.0},
                {"tick": duration, "value": rotation_end},
            ],
        },
        {
            "bone_id": "root-pelvis",
            "property": "translation",
            "keys": [
                {"tick": 0, "value": [0.0, 0.0]},
                {"tick": middle, "value": [10.0, -4.0]},
                {"tick": duration, "value": list(root_end)},
            ],
        },
    ]
    return deepcopy(result)
