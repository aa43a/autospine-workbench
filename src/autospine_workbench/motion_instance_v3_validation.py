"""Strict pure semantic replay for body-sway MotionInstance v3."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .body_sway_motion_consumer_p9 import (
    BodySwayMotionConsumerP9Error,
    require_verified_reviewed_motion_bundle,
)
from .body_sway_motion_consumer_validation import (
    BodySwayMotionConsumerAdmissionValidationError,
    body_sway_motion_consumer_admission_canonical_bytes,
)
from .motion_instance_v3_contract import (
    MotionInstanceV3ContractError,
    build_motion_instance_v3_document,
)
from .motion_instance_v3_shape import (
    MotionInstanceV3ShapeError,
    require_motion_instance_v3_shape,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT_JSON_NODES = 1_000_000
MAX_DOCUMENT_JSON_DEPTH = 32


class MotionInstanceV3ValidationError(ValueError):
    """Raised when v3 structure or exact source replay differs."""


def require_motion_instance_v3(
    document: Mapping[str, Any],
    *,
    admission: Mapping[str, Any],
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> None:
    """Validate v3 and replay it from one canonical P10.6a/P9 pair."""

    root = _bounded_object_copy(document)
    _require_shape(root)
    _require_exact_replay(root, admission, reviewed_bundle)


def motion_instance_v3_canonical_bytes(
    document: Mapping[str, Any],
    *,
    admission: Mapping[str, Any],
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> bytes:
    """Return canonical bytes only after strict semantic replay."""

    root = _bounded_object_copy(document)
    _require_shape(root)
    _require_exact_replay(root, admission, reviewed_bundle)
    return canonical_json_bytes(root)


def motion_instance_v3_sha256(
    document: Mapping[str, Any],
    *,
    admission: Mapping[str, Any],
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> str:
    """Return the canonical v3 identity after strict semantic replay."""

    return hashlib.sha256(motion_instance_v3_canonical_bytes(
        document, admission=admission, reviewed_bundle=reviewed_bundle
    )).hexdigest()


def _require_shape(root: dict[str, Any]) -> None:
    try:
        require_motion_instance_v3_shape(root)
    except MotionInstanceV3ShapeError as exc:
        raise MotionInstanceV3ValidationError(str(exc)) from exc


def _require_exact_replay(root, admission, reviewed_bundle) -> None:
    try:
        admission_bytes = body_sway_motion_consumer_admission_canonical_bytes(
            admission, reviewed_bundle=reviewed_bundle
        )
        admitted = json.loads(admission_bytes)
        motion = require_verified_reviewed_motion_bundle(
            reviewed_bundle, admitted["source"]["p9"]
        )
        expected = build_motion_instance_v3_document(
            admitted,
            motion,
            admission_sha256=hashlib.sha256(admission_bytes).hexdigest(),
            p9_bundle_sha256=reviewed_bundle.bundle_sha256,
        )
        if canonical_json_bytes(root) != canonical_json_bytes(expected):
            raise MotionInstanceV3ValidationError(
                "MotionInstance v3 differs from exact P10.6a/P9 replay"
            )
    except MotionInstanceV3ValidationError:
        raise
    except (
        BodySwayMotionConsumerAdmissionValidationError,
        BodySwayMotionConsumerP9Error, MotionInstanceV3ContractError,
        AttributeError, KeyError, OverflowError, TypeError, ValueError,
    ) as exc:
        raise MotionInstanceV3ValidationError(
            f"MotionInstance v3 exact replay failed: {exc}"
        ) from exc


def _bounded_object_copy(value: Any) -> dict[str, Any]:
    try:
        require_bounded_json_tree(
            value, max_nodes=MAX_DOCUMENT_JSON_NODES,
            max_depth=MAX_DOCUMENT_JSON_DEPTH,
        )
        encoded = canonical_json_bytes(value)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise MotionInstanceV3ValidationError(
                "MotionInstance v3 exceeds its byte limit"
            )
        copied = json.loads(encoded)
        if type(copied) is not dict:
            raise MotionInstanceV3ValidationError(
                "MotionInstance v3 must be an exact JSON object"
            )
        return copied
    except MotionInstanceV3ValidationError:
        raise
    except (
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise MotionInstanceV3ValidationError(
            f"MotionInstance v3 JSON is invalid: {exc}"
        ) from exc


__all__ = [
    "MotionInstanceV3ValidationError",
    "motion_instance_v3_canonical_bytes", "motion_instance_v3_sha256",
    "require_motion_instance_v3",
]
