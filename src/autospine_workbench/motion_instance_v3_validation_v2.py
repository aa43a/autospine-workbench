"""Strict MotionInstance v3 replay from a version-isolated v2 source."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .motion_instance_v3_contract_v2 import (
    MotionInstanceV3V2ContractError,
    build_motion_instance_v3_document_v2,
)
from .motion_instance_v3_prepared_v2 import PreparedMotionInstanceV3V2
from .motion_instance_v3_shape import (
    MotionInstanceV3ShapeError,
    require_motion_instance_v3_shape,
)
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT_JSON_NODES = 1_000_000
MAX_DOCUMENT_JSON_DEPTH = 32


class MotionInstanceV3V2ValidationError(ValueError):
    """Raised when v3 bytes differ from their exact P10.6a v2 replay."""


def require_motion_instance_v3_v2(
    document: Mapping[str, Any], *,
    prepared: PreparedMotionInstanceV3V2,
) -> None:
    """Validate shape, prepared source closure, and exact payload bytes."""

    root = _bounded_object_copy(document)
    _require_shape(root)
    _require_exact_replay(root, prepared)


def motion_instance_v3_canonical_bytes_v2(
    document: Mapping[str, Any], *,
    prepared: PreparedMotionInstanceV3V2,
) -> bytes:
    root = _bounded_object_copy(document)
    _require_shape(root)
    _require_exact_replay(root, prepared)
    return canonical_json_bytes(root)


def motion_instance_v3_sha256_v2(
    document: Mapping[str, Any], *,
    prepared: PreparedMotionInstanceV3V2,
) -> str:
    return hashlib.sha256(motion_instance_v3_canonical_bytes_v2(
        document, prepared=prepared,
    )).hexdigest()


def expected_motion_instance_v3_document_v2(
    prepared: PreparedMotionInstanceV3V2,
) -> dict[str, Any]:
    """Return the exact v3 payload reconstructed from an issued source."""

    try:
        _require_prepared(prepared)
        return build_motion_instance_v3_document_v2(
            prepared.admission,
            prepared.motion_instance_v2,
            admission_sha256=prepared.admission_sha256,
            p9_bundle_sha256=prepared.reviewed_motion_bundle_sha256,
        )
    except MotionInstanceV3V2ValidationError:
        raise
    except (
        AttributeError, KeyError, MotionInstanceV3V2ContractError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise MotionInstanceV3V2ValidationError(
            f"MotionInstance v3 v2 exact replay failed: {exc}"
        ) from exc


def _require_shape(root: dict[str, Any]) -> None:
    try:
        require_motion_instance_v3_shape(root)
    except MotionInstanceV3ShapeError as exc:
        raise MotionInstanceV3V2ValidationError(str(exc)) from exc


def _require_exact_replay(root, prepared) -> None:
    expected = expected_motion_instance_v3_document_v2(prepared)
    if canonical_json_bytes(root) != canonical_json_bytes(expected):
        raise MotionInstanceV3V2ValidationError(
            "MotionInstance v3 differs from exact P10.6a v2/P9 replay"
        )


def _require_prepared(prepared: Any) -> None:
    if type(prepared) is not PreparedMotionInstanceV3V2:
        raise MotionInstanceV3V2ValidationError(
            "MotionInstance v3 v2 replay requires an issued prepared source"
        )
    admission = prepared.admission
    source = admission.get("source")
    if type(source) is not dict or (
        admission.get("project_id"), admission.get("clip_id"),
        source.get("dynamic_seam_probe_sha256"),
        source.get("dynamic_seam_bundle_sha256"),
        source.get("p9", {}).get("motion_instance_v2_sha256"),
        source.get("p9", {}).get("bundle_sha256"),
    ) != (
        prepared.project_id, prepared.clip_id,
        prepared.dynamic_seam_probe_sha256,
        prepared.dynamic_seam_bundle_sha256,
        prepared.motion_instance_v2_sha256,
        prepared.reviewed_motion_bundle_sha256,
    ) or hashlib.sha256(prepared.admission_bytes).hexdigest() \
            != prepared.admission_sha256:
        raise MotionInstanceV3V2ValidationError(
            "Prepared v2 source closure differs from its exact addresses"
        )


def _bounded_object_copy(value: Any) -> dict[str, Any]:
    try:
        require_bounded_json_tree(
            value, max_nodes=MAX_DOCUMENT_JSON_NODES,
            max_depth=MAX_DOCUMENT_JSON_DEPTH,
        )
        encoded = canonical_json_bytes(value)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise MotionInstanceV3V2ValidationError(
                "MotionInstance v3 exceeds its byte limit"
            )
        copied = json.loads(encoded)
        if type(copied) is not dict:
            raise MotionInstanceV3V2ValidationError(
                "MotionInstance v3 must be an exact JSON object"
            )
        return copied
    except MotionInstanceV3V2ValidationError:
        raise
    except (
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise MotionInstanceV3V2ValidationError(
            f"MotionInstance v3 JSON is invalid: {exc}"
        ) from exc


__all__ = [
    "MotionInstanceV3V2ValidationError",
    "expected_motion_instance_v3_document_v2",
    "motion_instance_v3_canonical_bytes_v2", "motion_instance_v3_sha256_v2",
    "require_motion_instance_v3_v2",
]
