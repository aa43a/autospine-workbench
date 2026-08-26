"""Bounded value validation for raw Kimodo policy signal arrays."""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any

from .kimodo_npz_consistency import (
    HEADING_NORM_TOLERANCE,
    MAX_ABS_POSITION_METERS,
)


_SHA = re.compile(r"^[0-9a-f]{64}$")
_CONTACT_ROWS = {
    "left-heel-toe-right-heel-toe-v1": (
        (0, "leg.left", "heel"), (1, "leg.left", "toe"),
        (2, "leg.right", "heel"), (3, "leg.right", "toe"),
    ),
    "left-heel-toe-toe_end-right-heel-toe-toe_end-v1": (
        (0, "leg.left", "heel"), (1, "leg.left", "toe"),
        (2, "leg.left", "toe_end"), (3, "leg.right", "heel"),
        (4, "leg.right", "toe"), (5, "leg.right", "toe_end"),
    ),
}


class KimodoPolicySignalError(ValueError):
    """Raised when ancillary values do not match their pinned profile."""


def require_policy_array_profile(value: Any) -> Mapping[str, Any]:
    profile = _object(value, "Kimodo policy array profile")
    _exact(profile, {"inventory", "contact_layout"}, "Kimodo policy array profile")
    if profile.get("inventory") not in {"core-v1", "complete-v1"} \
            or profile.get("contact_layout") not in _CONTACT_ROWS:
        raise KimodoPolicySignalError("Kimodo policy array profile is unsupported")
    return profile


def require_policy_signals(
    value: Any, profile: Mapping[str, Any], frames: int
) -> None:
    signals = _object(value, "Kimodo policy signals")
    _exact(
        signals,
        {"foot_contact_channels", "global_root_heading", "smooth_root_position"},
        "Kimodo policy signals",
    )
    _contacts(signals["foot_contact_channels"], profile, frames)
    inventory = profile["inventory"]
    _vector_signal(
        signals["global_root_heading"], inventory, frames,
        source_array="global_root_heading", width=2,
        coordinate_space="source_two_component_uninterpreted",
        unit="unit_direction", maximum=2.0, unit_direction=True,
    )
    _vector_signal(
        signals["smooth_root_position"], inventory, frames,
        source_array="smooth_root_pos", width=3,
        coordinate_space="source_xyz", unit="meter",
        maximum=MAX_ABS_POSITION_METERS, unit_direction=False,
    )


def _contacts(value: Any, profile: Mapping[str, Any], frames: int) -> None:
    signal = _object(value, "Kimodo foot contact evidence")
    fields = {
        "status", "source_array", "dtype", "shape", "layout",
        "raw_npy_sha256", "payload_sha256", "channels",
    }
    _exact(signal, fields, "Kimodo foot contact evidence")
    rows = _CONTACT_ROWS[profile["contact_layout"]]
    if signal.get("status") != "available" \
            or signal.get("source_array") != "foot_contacts" \
            or signal.get("dtype") != "|b1" \
            or signal.get("shape") != [frames, len(rows)] \
            or signal.get("layout") != profile["contact_layout"]:
        raise KimodoPolicySignalError(
            "Kimodo foot contact metadata differs from its array profile"
        )
    _digest_fields(signal, "foot contact")
    channels = _array(signal.get("channels"), "Kimodo foot contact channels")
    if len(channels) != len(rows):
        raise KimodoPolicySignalError(
            "Kimodo foot contact channel count differs from its layout"
        )
    for raw, expected in zip(channels, rows):
        channel = _object(raw, "Kimodo foot contact channel")
        _exact(channel, {"index", "limb", "point", "values"},
               "Kimodo foot contact channel")
        values = _array(channel.get("values"), "Kimodo foot contact values")
        if (channel.get("index"), channel.get("limb"), channel.get("point")) \
                != expected or len(values) != frames \
                or any(type(item) is not bool for item in values):
            raise KimodoPolicySignalError(
                "Kimodo foot contact channel values are invalid"
            )


def _vector_signal(
    value: Any, inventory: str, frames: int, *, source_array: str,
    width: int, coordinate_space: str, unit: str, maximum: float,
    unit_direction: bool,
) -> None:
    signal = _object(value, f"Kimodo {source_array} evidence")
    if inventory == "core-v1":
        expected = {
            "status": "unavailable", "source_array": source_array,
            "reason_code": "array_not_in_core_v1",
        }
        if signal != expected:
            raise KimodoPolicySignalError(
                f"Kimodo core-v1 {source_array} must be explicitly unavailable"
            )
        return
    fields = {
        "status", "source_array", "dtype", "shape", "coordinate_space",
        "unit", "raw_npy_sha256", "payload_sha256", "values",
    }
    _exact(signal, fields, f"Kimodo {source_array} evidence")
    if signal.get("status") != "available" \
            or signal.get("source_array") != source_array \
            or signal.get("dtype") != "<f4" \
            or signal.get("shape") != [frames, width] \
            or signal.get("coordinate_space") != coordinate_space \
            or signal.get("unit") != unit:
        raise KimodoPolicySignalError(f"Kimodo {source_array} metadata is invalid")
    _digest_fields(signal, source_array)
    values = _array(signal.get("values"), f"Kimodo {source_array} values")
    if len(values) != frames:
        raise KimodoPolicySignalError(f"Kimodo {source_array} frame count differs")
    for raw in values:
        vector = _array(raw, f"Kimodo {source_array} vector")
        if len(vector) != width:
            raise KimodoPolicySignalError(f"Kimodo {source_array} vector width differs")
        numbers = [_number(item, maximum) for item in vector]
        if unit_direction and abs(math.hypot(*numbers) - 1.0) \
                > HEADING_NORM_TOLERANCE:
            raise KimodoPolicySignalError(
                "Kimodo global root heading is not a unit direction"
            )


def _digest_fields(signal: Mapping[str, Any], label: str) -> None:
    for field in ("raw_npy_sha256", "payload_sha256"):
        value = signal.get(field)
        if not isinstance(value, str) or not _SHA.fullmatch(value):
            raise KimodoPolicySignalError(f"Kimodo {label} {field} is invalid")


def _number(value: Any, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > maximum:
        raise KimodoPolicySignalError(
            "Kimodo policy numeric evidence is not finite and bounded"
        )
    return float(value)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KimodoPolicySignalError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise KimodoPolicySignalError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise KimodoPolicySignalError(
            f"{label} fields are incomplete or unsupported"
        )
