"""Compact, reviewable representative samples for BodySwayProbeReport v1."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .body_sway_probe_profile import NUMERIC_PRECISION_DECIMALS
from .idle_behavior_decision_validation_fields import (
    array_value,
    digest_value,
    exact_fields,
    identifier_value,
    object_value,
)
from .resolved_project import canonical_sha256


MAX_ATTACHMENTS = 4096
MAX_BONES = 4096
MAX_REPRESENTATIVE_SAMPLES = 256
MAX_ABS_POSE_NUMBER = 1_000_000_000_000.0
SAMPLE_HASH_DOMAIN = "autospine-body-sway-representative-sample/v1"
_SAMPLE_FIELDS = {
    "tick", "base_rotation_deg", "overlay_rotation_deg",
    "combined_rotation_deg", "root_translation_xy", "sample_sha256",
}
_HASH_FIELDS = _SAMPLE_FIELDS - {"sample_sha256"}


class BodySwayProbeSampleError(ValueError):
    """Raised when compact representative evidence is stale or ambiguous."""


def require_sample_stream(
    value: Any, *, duration: int, loop: bool, overlay_bone_ids: list[str],
    amplitudes: Mapping[str, float], schedule_count: int,
) -> dict[str, int]:
    """Validate stream seals, inventories, and visible representative poses."""

    stream = object_value(value, "Body-sway sample stream")
    exact_fields(
        stream,
        {
            "sample_stream_sha256", "rig_bone_ids", "rotation_bone_ids",
            "overlay_bone_ids", "attachments", "representative_samples",
        },
        "Body-sway sample stream",
    )
    digest_value(stream.get("sample_stream_sha256"), "sample_stream_sha256")
    rig_bone_ids = _id_inventory(stream.get("rig_bone_ids"), "rig bones")
    rotation_bone_ids = _id_inventory(
        stream.get("rotation_bone_ids"), "rotation-track bones",
    )
    if stream.get("overlay_bone_ids") != overlay_bone_ids:
        raise BodySwayProbeSampleError(
            "Body-sway overlay inventory differs from its selection"
        )
    if not set(rotation_bone_ids) <= set(rig_bone_ids) \
            or not set(overlay_bone_ids) <= set(rotation_bone_ids):
        raise BodySwayProbeSampleError(
            "Body-sway rotation and overlay inventories must be rig subsets"
        )
    attachments = _attachments(stream.get("attachments"))
    representatives = _representatives(
        stream.get("representative_samples"), duration=duration,
        rotation_bone_ids=rotation_bone_ids,
        overlay_bone_ids=overlay_bone_ids, amplitudes=amplitudes,
    )
    if len(representatives) > schedule_count:
        raise BodySwayProbeSampleError(
            "Representative samples exceed the sealed schedule count"
        )
    start_pose, end_pose = representatives[0][1], representatives[-1][1]
    if start_pose[1] != end_pose[1]:
        raise BodySwayProbeSampleError(
            "Body-sway overlay representative endpoints must always close"
        )
    return {
        "loop_pose_closed": start_pose == end_pose,
        "rig_bone_count": len(rig_bone_ids),
        "rotation_bone_count": len(rotation_bone_ids),
        "overlay_bone_count": len(overlay_bone_ids),
        "attachment_count": len(attachments),
        "mesh_attachment_count": sum(
            row["type"] == "mesh" for row in attachments
        ),
        "representative_sample_count": len(representatives),
    }


def representative_sample_sha256(sample: Mapping[str, Any]) -> str:
    """Hash all visible pose fields under a versioned domain separator."""

    row = object_value(sample, "Body-sway representative sample")
    if set(row) != _SAMPLE_FIELDS and set(row) != _HASH_FIELDS:
        raise BodySwayProbeSampleError(
            "Body-sway representative sample fields are unsupported"
        )
    return canonical_sha256({
        "domain": SAMPLE_HASH_DOMAIN,
        "tick": row["tick"],
        "base_rotation_deg": row["base_rotation_deg"],
        "overlay_rotation_deg": row["overlay_rotation_deg"],
        "combined_rotation_deg": row["combined_rotation_deg"],
        "root_translation_xy": row["root_translation_xy"],
    })


def _attachments(value: Any) -> list[Mapping[str, Any]]:
    rows = array_value(
        value, "Body-sway attachment inventory", maximum=MAX_ATTACHMENTS,
    )
    identifiers = []
    for raw in rows:
        row = object_value(raw, "Body-sway attachment")
        exact_fields(row, {"attachment_id", "type"}, "Body-sway attachment")
        identifiers.append(identifier_value(row.get("attachment_id"), "attachment_id"))
        if row.get("type") not in {"region", "mesh"}:
            raise BodySwayProbeSampleError(
                "Body-sway attachment type is unsupported"
            )
    if identifiers != sorted(identifiers) or len(identifiers) != len(set(identifiers)):
        raise BodySwayProbeSampleError(
            "Body-sway attachments must be sorted and unique"
        )
    return rows


def _id_inventory(value: Any, label: str) -> list[str]:
    rows = array_value(value, f"Body-sway {label}", minimum=1, maximum=MAX_BONES)
    identifiers = [identifier_value(item, label) for item in rows]
    if identifiers != sorted(identifiers) \
            or len(identifiers) != len(set(identifiers)):
        raise BodySwayProbeSampleError(
            f"Body-sway {label} must be sorted and unique"
        )
    return identifiers


def _representatives(
    value: Any, *, duration: int, rotation_bone_ids: list[str],
    overlay_bone_ids: list[str], amplitudes: Mapping[str, float],
) -> list[tuple[int, tuple[Any, ...]]]:
    rows = array_value(
        value, "Body-sway representative samples", minimum=2,
        maximum=MAX_REPRESENTATIVE_SAMPLES,
    )
    result, previous = [], -1
    for raw in rows:
        row = object_value(raw, "Body-sway representative sample")
        exact_fields(row, _SAMPLE_FIELDS, "Body-sway representative sample")
        tick = _integer(row.get("tick"), 0, duration, "representative tick")
        if tick <= previous:
            raise BodySwayProbeSampleError(
                "Body-sway representative ticks must be sorted and unique"
            )
        previous = tick
        base = _rotations(
            row.get("base_rotation_deg"), rotation_bone_ids, "base",
        )
        overlay = _rotations(
            row.get("overlay_rotation_deg"), rotation_bone_ids, "overlay",
            overlay_bone_ids=overlay_bone_ids, amplitudes=amplitudes,
        )
        combined = _rotations(
            row.get("combined_rotation_deg"), rotation_bone_ids, "combined",
        )
        expected = tuple(_quantize(left + right) for left, right in zip(
            base, overlay, strict=True
        ))
        if combined != expected:
            raise BodySwayProbeSampleError(
                "Representative combined rotations differ from base plus overlay"
            )
        root = _vector(row.get("root_translation_xy"), "root translation")
        if row.get("sample_sha256") != representative_sample_sha256(row):
            raise BodySwayProbeSampleError(
                "Representative sample SHA differs from its visible pose"
            )
        result.append((tick, (base, overlay, combined, root)))
    if result[0][0] != 0 or result[-1][0] != duration:
        raise BodySwayProbeSampleError(
            "Representative samples must include clip endpoints"
        )
    return result


def _rotations(
    value: Any, bone_ids: list[str], label: str,
    *, overlay_bone_ids: list[str] | None = None,
    amplitudes: Mapping[str, float] | None = None,
) -> tuple[float, ...]:
    rows = array_value(
        value, f"Body-sway {label} rotations", minimum=len(bone_ids),
        maximum=len(bone_ids),
    )
    if [row.get("bone_id") if isinstance(row, Mapping) else None for row in rows] \
            != bone_ids:
        raise BodySwayProbeSampleError(
            f"Representative {label} rotations differ from the selected bone order"
        )
    result = []
    for raw in rows:
        row = object_value(raw, f"Body-sway {label} rotation")
        exact_fields(row, {"bone_id", "value"}, f"Body-sway {label} rotation")
        number = _canonical_number(row.get("value"), f"{label} rotation")
        if amplitudes is not None:
            bone_id = row["bone_id"]
            if bone_id not in overlay_bone_ids and number != 0.0:
                raise BodySwayProbeSampleError(
                    "Representative overlay changes a non-overlay bone"
                )
            if bone_id in amplitudes \
                    and abs(number) > abs(_quantize(amplitudes[bone_id])):
                raise BodySwayProbeSampleError(
                    "Representative overlay exceeds its reviewed amplitude"
                )
        result.append(number)
    return tuple(result)


def _vector(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise BodySwayProbeSampleError(
            f"Body-sway {label} must contain x and y"
        )
    return (
        _canonical_number(value[0], label),
        _canonical_number(value[1], label),
    )


def _integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise BodySwayProbeSampleError(f"Body-sway {label} is invalid")
    return value


def _canonical_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > MAX_ABS_POSE_NUMBER:
        raise BodySwayProbeSampleError(f"Body-sway {label} must be finite and bounded")
    number = float(value)
    if round(number, NUMERIC_PRECISION_DECIMALS) != number \
            or number == 0.0 and math.copysign(1.0, number) < 0:
        raise BodySwayProbeSampleError(
            f"Body-sway {label} is not canonical to nine decimals"
        )
    return number


def _quantize(value: float) -> float:
    result = round(float(value), NUMERIC_PRECISION_DECIMALS)
    return 0.0 if result == 0 else result
