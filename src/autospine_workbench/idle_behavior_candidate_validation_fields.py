"""Reusable field and evidence checks for IdleBehaviorCandidates v1."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class IdleBehaviorCandidateFieldError(ValueError):
    """Raised when one candidate field is unsafe or non-canonical."""


def require_evidence(value: Any) -> None:
    """Validate sorted layer, binding, bone, and existing-track evidence."""

    evidence = object_value(value, "Idle behavior evidence")
    exact_fields(
        evidence, {"layers", "bindings", "bone_ids", "existing_tracks"},
        "Idle behavior evidence",
    )
    _sorted_objects(evidence.get("layers"), "layers", "layer_id", _layer)
    _sorted_objects(
        evidence.get("bindings"), "bindings", "attachment_id", _binding,
    )
    require_sorted_ids(evidence.get("bone_ids"), "bone ids")
    rows = array_value(evidence.get("existing_tracks"), "existing tracks")
    keys = []
    for raw in rows:
        row = object_value(raw, "Idle behavior existing track")
        exact_fields(
            row, {"bone_id", "property"}, "Idle behavior existing track"
        )
        bone_id = identifier_value(row.get("bone_id"), "track bone_id")
        if row.get("property") not in {"rotation", "translation"}:
            raise IdleBehaviorCandidateFieldError(
                "Idle behavior track property is unsupported"
            )
        keys.append((bone_id, row["property"]))
    _strict_order(keys, "existing tracks")


def _layer(row: Mapping[str, Any]) -> None:
    exact_fields(
        row,
        {"layer_id", "canonical_role", "side", "raster_sha256", "review_state"},
        "Idle behavior layer",
    )
    identifier_value(row.get("layer_id"), "layer_id")
    identifier_value(row.get("canonical_role"), "canonical_role")
    if row.get("side") not in {
        "left", "right", "center", "bilateral", "unknown",
    } or row.get("review_state") not in {"reviewed", "unreviewed"}:
        raise IdleBehaviorCandidateFieldError(
            "Idle behavior layer classification is unsupported"
        )
    digest_value(row.get("raster_sha256"), "layer raster_sha256")


def _binding(row: Mapping[str, Any]) -> None:
    exact_fields(
        row, {"attachment_id", "slot_id", "bone_id", "image_sha256", "type"},
        "Idle behavior binding",
    )
    for field in ("attachment_id", "slot_id", "bone_id"):
        identifier_value(row.get(field), field)
    digest_value(row.get("image_sha256"), "binding image_sha256")
    if row.get("type") not in {"region", "mesh"}:
        raise IdleBehaviorCandidateFieldError(
            "Idle behavior binding type is unsupported"
        )


def _sorted_objects(value: Any, label: str, key: str, validate) -> None:
    rows = array_value(value, f"Idle behavior {label}")
    keys = []
    for raw in rows:
        row = object_value(raw, f"Idle behavior {label} row")
        validate(row)
        keys.append(row[key])
    _strict_order(keys, label)


def require_sorted_ids(value: Any, label: str) -> None:
    rows = array_value(value, f"Idle behavior {label}")
    _strict_order([identifier_value(item, label) for item in rows], label)


def _strict_order(keys: list[Any], label: str) -> None:
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise IdleBehaviorCandidateFieldError(
            f"Idle behavior {label} must be sorted and unique"
        )


def digest_value(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise IdleBehaviorCandidateFieldError(
            f"Idle behavior {label} is not a SHA-256"
        )


def identifier_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise IdleBehaviorCandidateFieldError(
            f"Idle behavior {label} is invalid"
        )
    return value


def object_value(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IdleBehaviorCandidateFieldError(f"{label} must be an object")
    return value


def array_value(value: Any, label: str, *, maximum: int = 4096) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        raise IdleBehaviorCandidateFieldError(
            f"{label} must be an array with at most {maximum} items"
        )
    return value


def exact_fields(
    value: Mapping[str, Any], fields: set[str], label: str
) -> None:
    if set(value) != fields:
        raise IdleBehaviorCandidateFieldError(f"{label} fields are unsupported")
