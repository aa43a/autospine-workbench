"""Strict public replay for BodySwayMotionConsumerAdmission v1."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .body_sway_motion_consumer_admission import (
    HEAD_OBSERVATION_FIELDS,
    TOP_FIELDS,
    BodySwayMotionConsumerAdmissionError,
    observation_from_document,
    seal_body_sway_motion_consumer_admission,
)
from .body_sway_motion_consumer_core import (
    compile_body_sway_motion_consumer_admission_core,
)
from .body_sway_motion_consumer_profile import (
    FORMAT,
    FORMAT_VERSION,
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_JSON_DEPTH,
    MAX_DOCUMENT_JSON_NODES,
)
from .body_sway_dynamic_seam_validation import (
    body_sway_dynamic_seam_probe_canonical_bytes,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


class BodySwayMotionConsumerAdmissionValidationError(ValueError):
    """Raised when detached admission evidence is forged or overclaims."""


def require_body_sway_motion_consumer_admission(
    document: Mapping[str, Any],
    *,
    dynamic_seam_probe: Mapping[str, Any] | None = None,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> None:
    """Recompute detached evidence; this does not reobserve current heads."""

    root = _bounded_object_copy(document)
    _require_admitted(root, dynamic_seam_probe, reviewed_bundle)


def body_sway_motion_consumer_admission_canonical_bytes(
    document: Mapping[str, Any],
    *,
    dynamic_seam_probe: Mapping[str, Any] | None = None,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> bytes:
    """Return detached canonical bytes only after complete semantic replay."""

    root = _bounded_object_copy(document)
    _require_admitted(root, dynamic_seam_probe, reviewed_bundle)
    return canonical_json_bytes(root)


def body_sway_motion_consumer_admission_sha256(
    document: Mapping[str, Any],
    *,
    dynamic_seam_probe: Mapping[str, Any] | None = None,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> str:
    """Return the canonical admission identity after complete replay."""

    return hashlib.sha256(
        body_sway_motion_consumer_admission_canonical_bytes(
            document,
            dynamic_seam_probe=dynamic_seam_probe,
            reviewed_bundle=reviewed_bundle,
        )
    ).hexdigest()


def _require_admitted(root, dynamic_seam_probe, reviewed_bundle) -> None:
    try:
        if set(root) != TOP_FIELDS:
            raise BodySwayMotionConsumerAdmissionValidationError(
                "Motion consumer admission fields are unsupported"
            )
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise BodySwayMotionConsumerAdmissionValidationError(
                "Motion consumer admission format is unsupported"
            )
        source = root.get("source")
        if type(source) is not dict \
                or type(source.get("body_sway_dynamic_seam_probe")) is not dict:
            raise BodySwayMotionConsumerAdmissionValidationError(
                "Motion consumer embedded dynamic seam probe is missing"
            )
        embedded_probe = source["body_sway_dynamic_seam_probe"]
        embedded_bytes = body_sway_dynamic_seam_probe_canonical_bytes(
            embedded_probe
        )
        if dynamic_seam_probe is not None \
                and body_sway_dynamic_seam_probe_canonical_bytes(
                    dynamic_seam_probe
                ) != embedded_bytes:
            raise BodySwayMotionConsumerAdmissionValidationError(
                "Explicit dynamic seam probe differs from embedded evidence"
            )
        core = compile_body_sway_motion_consumer_admission_core(
            embedded_probe, reviewed_bundle
        )
        heads = root.get("head_observations")
        if type(heads) is not dict or set(heads) != HEAD_OBSERVATION_FIELDS:
            raise BodySwayMotionConsumerAdmissionValidationError(
                "Motion consumer head-observation fields are unsupported"
            )
        before = _observation_entry(heads.get("before"), "before")
        after = _observation_entry(heads.get("after"), "after")
        before_value = observation_from_document(
            core.head_identity, before["observation"]
        )
        after_value = observation_from_document(
            core.head_identity, after["observation"]
        )
        expected = seal_body_sway_motion_consumer_admission(
            core, before_value, after_value
        )
        if canonical_json_bytes(root) != expected.canonical_bytes:
            raise BodySwayMotionConsumerAdmissionValidationError(
                "Motion consumer admission differs from exact recomputation"
            )
    except BodySwayMotionConsumerAdmissionValidationError:
        raise
    except (
        AttributeError, BodySwayMotionConsumerAdmissionError, KeyError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerAdmissionValidationError(
            f"Motion consumer admission validation failed: {exc}"
        ) from exc


def _observation_entry(value, label):
    if type(value) is not dict or set(value) != {
        "observation", "canonical_sha256"
    } or type(value.get("observation")) is not dict \
            or type(value.get("canonical_sha256")) is not str:
        raise BodySwayMotionConsumerAdmissionValidationError(
            f"Motion consumer {label} observation entry is invalid"
        )
    expected = hashlib.sha256(
        canonical_json_bytes(value["observation"])
    ).hexdigest()
    if value["canonical_sha256"] != expected:
        raise BodySwayMotionConsumerAdmissionValidationError(
            f"Motion consumer {label} observation digest is inconsistent"
        )
    return value


def _bounded_object_copy(value: Any) -> dict[str, Any]:
    try:
        require_bounded_json_tree(
            value, max_nodes=MAX_DOCUMENT_JSON_NODES,
            max_depth=MAX_DOCUMENT_JSON_DEPTH,
        )
        encoded = canonical_json_bytes(value)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise BodySwayMotionConsumerAdmissionValidationError(
                "Motion consumer admission exceeds its byte limit"
            )
        copied = json.loads(encoded)
        if type(copied) is not dict:
            raise BodySwayMotionConsumerAdmissionValidationError(
                "Motion consumer admission must be an exact JSON object"
            )
        return copied
    except BodySwayMotionConsumerAdmissionValidationError:
        raise
    except (
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerAdmissionValidationError(
            f"Motion consumer admission JSON is invalid: {exc}"
        ) from exc


__all__ = [
    "BodySwayMotionConsumerAdmissionValidationError",
    "body_sway_motion_consumer_admission_canonical_bytes",
    "body_sway_motion_consumer_admission_sha256",
    "require_body_sway_motion_consumer_admission",
]
