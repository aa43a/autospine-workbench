"""Strict canonical-source validation for BodySwayDynamicSeamProbe v2."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_profile_v2 import (
    FORMAT,
    FORMAT_VERSION,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_JSON_DEPTH,
    MAX_SOURCE_JSON_NODES,
    SOURCE_FIELDS,
)
from .body_sway_dynamic_seam_source_v2 import (
    BodySwayDynamicSeamSourceV2Error,
    build_body_sway_dynamic_seam_source_v2,
)
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


class BodySwayDynamicSeamSourceV2ValidationError(ValueError):
    """Raised when a v2 source closure is malformed, forged, or cross-wired."""


def require_body_sway_dynamic_seam_source_v2(
    source: Mapping[str, Any],
) -> dict[str, Any]:
    """Fully replay all embedded evidence and return a detached closure."""

    try:
        raw = _bounded_object_copy(source)
        if set(raw) != SOURCE_FIELDS:
            raise BodySwayDynamicSeamSourceV2ValidationError(
                "Dynamic seam source v2 fields are unsupported"
            )
        if raw.get("format") != FORMAT \
                or type(raw.get("format_version")) is not int \
                or raw["format_version"] != FORMAT_VERSION:
            raise BodySwayDynamicSeamSourceV2ValidationError(
                "Dynamic seam source v2 format is unsupported"
            )
        rebuilt = build_body_sway_dynamic_seam_source_v2(
            continuous_proof_v2=(
                raw["body_sway_continuous_preview_proof_v2"]
            ),
            seam_anchor_candidates_v1=raw["seam_anchor_candidates_v1"],
            seam_anchor_review_decision_v1=(
                raw["seam_anchor_review_decision_v1"]
            ),
            reviewed_seam_anchor_set_v1=(
                raw["reviewed_seam_anchor_set_v1"]
            ),
            reviewed_set_v1_bundle_sha256=(
                raw["reviewed_seam_anchor_set_v1_bundle_sha256"]
            ),
        )
        if canonical_json_bytes(raw) != canonical_json_bytes(rebuilt):
            raise BodySwayDynamicSeamSourceV2ValidationError(
                "Dynamic seam source v2 identities differ from exact replay"
            )
        return rebuilt
    except BodySwayDynamicSeamSourceV2ValidationError:
        raise
    except BodySwayDynamicSeamSourceV2Error as exc:
        raise BodySwayDynamicSeamSourceV2ValidationError(
            f"Dynamic seam source v2 validation failed: {exc}"
        ) from exc
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamSourceV2ValidationError(
            f"Dynamic seam source v2 validation failed: {exc}"
        ) from exc


def body_sway_dynamic_seam_source_canonical_bytes_v2(
    source: Mapping[str, Any],
) -> bytes:
    """Return canonical bytes only after complete mixed-version replay."""

    admitted = require_body_sway_dynamic_seam_source_v2(source)
    return canonical_json_bytes(admitted)


def body_sway_dynamic_seam_source_document_sha256_v2(
    source: Mapping[str, Any],
) -> str:
    """Address the entire validated source document, including its seal."""

    return hashlib.sha256(
        body_sway_dynamic_seam_source_canonical_bytes_v2(source)
    ).hexdigest()


def _bounded_object_copy(value: Any) -> dict[str, Any]:
    try:
        require_bounded_json_tree(
            value, max_nodes=MAX_SOURCE_JSON_NODES,
            max_depth=MAX_SOURCE_JSON_DEPTH,
        )
        encoded = canonical_json_bytes(value)
        if len(encoded) > MAX_SOURCE_BYTES:
            raise BodySwayDynamicSeamSourceV2ValidationError(
                "Dynamic seam source v2 exceeds its byte limit"
            )
        copied = json.loads(encoded)
        if type(copied) is not dict:
            raise BodySwayDynamicSeamSourceV2ValidationError(
                "Dynamic seam source v2 must be an exact JSON object"
            )
        return copied
    except BodySwayDynamicSeamSourceV2ValidationError:
        raise
    except (
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamSourceV2ValidationError(
            f"Dynamic seam source v2 JSON is invalid: {exc}"
        ) from exc


__all__ = [
    "BodySwayDynamicSeamSourceV2ValidationError",
    "body_sway_dynamic_seam_source_canonical_bytes_v2",
    "body_sway_dynamic_seam_source_document_sha256_v2",
    "require_body_sway_dynamic_seam_source_v2",
]
