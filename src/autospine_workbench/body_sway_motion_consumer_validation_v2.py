"""Strict detached replay for BodySwayMotionConsumerAdmission v2."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_bundle_reader_v2 import (
    VerifiedBodySwayDynamicSeamBundleV2,
)
from .body_sway_motion_consumer_admission_v2 import (
    HEAD_OBSERVATION_FIELDS,
    TOP_FIELDS,
    BodySwayMotionConsumerAdmissionV2Error,
    observation_from_document_v2,
    seal_body_sway_motion_consumer_admission_v2,
)
from .body_sway_motion_consumer_core_v2 import (
    compile_body_sway_motion_consumer_admission_core_v2,
)
from .body_sway_motion_consumer_profile_v2 import (
    FORMAT,
    FORMAT_VERSION,
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_JSON_DEPTH,
    MAX_DOCUMENT_JSON_NODES,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


class BodySwayMotionConsumerAdmissionV2ValidationError(ValueError):
    """Raised when detached v2 admission is forged or overclaims."""


def require_body_sway_motion_consumer_admission_v2(
    document: Mapping[str, Any], *,
    dynamic_seam_bundle: VerifiedBodySwayDynamicSeamBundleV2,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> None:
    """Recompute exact bundles and the head seal without observing heads."""

    root = _bounded_object_copy(document)
    _require_admitted(root, dynamic_seam_bundle, reviewed_bundle)


def body_sway_motion_consumer_admission_canonical_bytes_v2(
    document: Mapping[str, Any], *,
    dynamic_seam_bundle: VerifiedBodySwayDynamicSeamBundleV2,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> bytes:
    root = _bounded_object_copy(document)
    _require_admitted(root, dynamic_seam_bundle, reviewed_bundle)
    return canonical_json_bytes(root)


def body_sway_motion_consumer_admission_sha256_v2(
    document: Mapping[str, Any], *,
    dynamic_seam_bundle: VerifiedBodySwayDynamicSeamBundleV2,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> str:
    return hashlib.sha256(
        body_sway_motion_consumer_admission_canonical_bytes_v2(
            document, dynamic_seam_bundle=dynamic_seam_bundle,
            reviewed_bundle=reviewed_bundle,
        )
    ).hexdigest()


def _require_admitted(root, dynamic_bundle, reviewed_bundle):
    try:
        if set(root) != TOP_FIELDS:
            raise BodySwayMotionConsumerAdmissionV2ValidationError(
                "Motion consumer v2 admission fields are unsupported"
            )
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise BodySwayMotionConsumerAdmissionV2ValidationError(
                "Motion consumer v2 admission format is unsupported"
            )
        source = root.get("source")
        if type(source) is not dict \
                or type(source.get(
                    "body_sway_dynamic_seam_probe_v2"
                )) is not dict:
            raise BodySwayMotionConsumerAdmissionV2ValidationError(
                "Motion consumer v2 embedded P10.5d probe is missing"
            )
        core = compile_body_sway_motion_consumer_admission_core_v2(
            dynamic_bundle, reviewed_bundle,
        )
        heads = root.get("head_observations")
        if type(heads) is not dict or set(heads) != HEAD_OBSERVATION_FIELDS:
            raise BodySwayMotionConsumerAdmissionV2ValidationError(
                "Motion consumer v2 head-observation fields are unsupported"
            )
        before = _observation_entry(heads.get("before"), "before")
        after = _observation_entry(heads.get("after"), "after")
        expected = seal_body_sway_motion_consumer_admission_v2(
            core,
            observation_from_document_v2(core, before["observation"]),
            observation_from_document_v2(core, after["observation"]),
        )
        if canonical_json_bytes(root) != expected.canonical_bytes:
            raise BodySwayMotionConsumerAdmissionV2ValidationError(
                "Motion consumer v2 admission differs from exact replay"
            )
    except BodySwayMotionConsumerAdmissionV2ValidationError:
        raise
    except (
        AttributeError, BodySwayMotionConsumerAdmissionV2Error, KeyError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerAdmissionV2ValidationError(
            f"Motion consumer v2 admission validation failed: {exc}"
        ) from exc


def _observation_entry(value, label):
    if type(value) is not dict or set(value) != {
        "observation", "canonical_sha256"
    } or type(value.get("observation")) is not dict \
            or type(value.get("canonical_sha256")) is not str:
        raise BodySwayMotionConsumerAdmissionV2ValidationError(
            f"Motion consumer v2 {label} observation entry is invalid"
        )
    expected = hashlib.sha256(
        canonical_json_bytes(value["observation"])
    ).hexdigest()
    if value["canonical_sha256"] != expected:
        raise BodySwayMotionConsumerAdmissionV2ValidationError(
            f"Motion consumer v2 {label} observation digest is inconsistent"
        )
    return value


def _bounded_object_copy(value):
    try:
        require_bounded_json_tree(
            value, max_nodes=MAX_DOCUMENT_JSON_NODES,
            max_depth=MAX_DOCUMENT_JSON_DEPTH,
        )
        encoded = canonical_json_bytes(value)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise BodySwayMotionConsumerAdmissionV2ValidationError(
                "Motion consumer v2 admission exceeds its byte limit"
            )
        copied = json.loads(encoded)
        if type(copied) is not dict:
            raise BodySwayMotionConsumerAdmissionV2ValidationError(
                "Motion consumer v2 admission must be an exact object"
            )
        return copied
    except BodySwayMotionConsumerAdmissionV2ValidationError:
        raise
    except (
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerAdmissionV2ValidationError(
            f"Motion consumer v2 admission JSON is invalid: {exc}"
        ) from exc


__all__ = [
    "BodySwayMotionConsumerAdmissionV2ValidationError",
    "body_sway_motion_consumer_admission_canonical_bytes_v2",
    "body_sway_motion_consumer_admission_sha256_v2",
    "require_body_sway_motion_consumer_admission_v2",
]
