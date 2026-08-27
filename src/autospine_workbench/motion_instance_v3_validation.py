"""Strict pure semantic replay for body-sway MotionInstance v3."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from typing import Any

from .body_sway_motion_consumer_p9 import (
    BodySwayMotionConsumerP9Error,
    require_verified_reviewed_motion_bundle,
)
from .body_sway_motion_consumer_validation import (
    BodySwayMotionConsumerAdmissionValidationError,
    body_sway_motion_consumer_admission_canonical_bytes,
)
from .motion_instance_v2_validation import (
    MotionInstanceV2ValidationError,
    require_motion_instance_v2,
)
from .motion_instance_validation import (
    MAX_KEYS_PER_TRACK,
    MotionInstanceValidationError,
    require_motion_instance,
)
from .motion_instance_v3_contract import (
    FORMAT,
    FORMAT_VERSION,
    MotionInstanceV3ContractError,
    build_motion_instance_v3_document,
    motion_instance_v3_profile,
    motion_instance_v3_profile_sha256,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT_JSON_NODES = 1_000_000
MAX_DOCUMENT_JSON_DEPTH = 32
MAX_TRACKS = 18
MAX_ROTATION_KEYS = 69_632
MAX_TOTAL_KEYS = MAX_ROTATION_KEYS + MAX_KEYS_PER_TRACK
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "clip_id", "timing", "source", "profile",
    "target_space", "tracks", "markers", "draw_order",
}
_SOURCE = {
    "body_sway_motion_consumer_admission_sha256", "p9",
    "motion_domain_sha256", "rotation_timeline_sha256",
    "base_channels_sha256", "rig_ir_sha256", "target_profile_sha256",
    "motion_instance_v3_profile_sha256",
}
_P9 = {"motion_instance_v2_sha256", "bundle_sha256"}


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
        if set(root) != _TOP:
            raise MotionInstanceV3ValidationError(
                "MotionInstance v3 fields are unsupported"
            )
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise MotionInstanceV3ValidationError(
                "MotionInstance v3 format is unsupported"
            )
        source = _require_source(root.get("source"))
        if root.get("profile") != motion_instance_v3_profile() \
                or source["motion_instance_v3_profile_sha256"] \
                != motion_instance_v3_profile_sha256():
            raise MotionInstanceV3ValidationError(
                "MotionInstance v3 profile is unsupported or stale"
            )
        _require_payload(root, source)
    except MotionInstanceV3ValidationError:
        raise
    except (
        MotionInstanceValidationError, MotionInstanceV2ValidationError,
        KeyError, OverflowError, TypeError, ValueError,
    ) as exc:
        raise MotionInstanceV3ValidationError(
            f"MotionInstance v3 shape validation failed: {exc}"
        ) from exc


def _require_source(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _SOURCE:
        raise MotionInstanceV3ValidationError(
            "MotionInstance v3 source fields are unsupported"
        )
    p9 = value.get("p9")
    if type(p9) is not dict or set(p9) != _P9:
        raise MotionInstanceV3ValidationError(
            "MotionInstance v3 P9 source fields are unsupported"
        )
    for field in _SOURCE - {"p9"}:
        _require_sha(value.get(field), field)
    for field in _P9:
        _require_sha(p9.get(field), f"p9.{field}")
    return value


def _require_payload(root, source) -> None:
    tracks = root.get("tracks")
    if not isinstance(tracks, list) or not 1 <= len(tracks) <= MAX_TRACKS:
        raise MotionInstanceV3ValidationError(
            "MotionInstance v3 track limit exceeded"
        )
    dummy = _dummy_track(root.get("timing"))
    require_motion_instance(_v1_shadow(root, source, [dummy], root.get(
        "markers"
    )))
    previous, seen, total = None, set(), 0
    for track in tracks:
        require_motion_instance(_v1_shadow(root, source, [track], []))
        identity = (track["bone_id"], track["property"])
        if identity in seen or previous is not None and identity <= previous:
            raise MotionInstanceV3ValidationError(
                "MotionInstance v3 tracks must be sorted and unique"
            )
        seen.add(identity)
        previous = identity
        total += len(track["keys"])
    if total > MAX_TOTAL_KEYS:
        raise MotionInstanceV3ValidationError(
            "MotionInstance v3 total key limit exceeded"
        )
    require_motion_instance_v2(_v2_shadow(root, source, dummy))


def _v1_shadow(root, source, tracks, markers):
    return {
        "format": FORMAT,
        "format_version": 1,
        "clip_id": root.get("clip_id"),
        "timing": root.get("timing"),
        "source": {
            "motion_ir_sha256": source["p9"][
                "motion_instance_v2_sha256"
            ],
            "motion_bundle_sha256": source["p9"]["bundle_sha256"],
            "motion_run_sha256": source[
                "body_sway_motion_consumer_admission_sha256"
            ],
            "target_profile_sha256": source["target_profile_sha256"],
            "retarget_run_identity_sha256": source["motion_domain_sha256"],
        },
        "target_space": {
            field: root.get("target_space", {}).get(field)
            for field in (
                "translation", "rotation", "positive_rotation",
                "interpolation",
            )
        },
        "tracks": tracks,
        "markers": markers,
    }


def _v2_shadow(root, source, dummy):
    return {
        "format": FORMAT,
        "format_version": 2,
        "clip_id": root.get("clip_id"),
        "timing": root.get("timing"),
        "source": {
            "base_motion_instance_sha256": source["p9"][
                "motion_instance_v2_sha256"
            ],
            "base_retarget_bundle_sha256": source["p9"]["bundle_sha256"],
            "target_profile_sha256": source["target_profile_sha256"],
            "reviewed_motion_policy_sha256": source[
                "body_sway_motion_consumer_admission_sha256"
            ],
            "motion_policy_decision_sha256": source[
                "motion_domain_sha256"
            ],
            "p3_rig_sha256": source["rig_ir_sha256"],
            "p3_bundle_sha256": source["base_channels_sha256"],
        },
        "target_space": root.get("target_space"),
        "tracks": [dummy],
        "markers": [],
        "draw_order": root.get("draw_order"),
    }


def _dummy_track(timing):
    duration = timing.get("duration_ticks") \
        if type(timing) is dict else None
    if type(duration) is not int or isinstance(duration, bool) or duration < 1:
        duration = 1
    return {
        "bone_id": "root-pelvis",
        "property": "rotation",
        "keys": [
            {"tick": 0, "value": 0.0},
            {"tick": duration, "value": 0.0},
        ],
    }


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


def _require_sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise MotionInstanceV3ValidationError(
            f"MotionInstance v3 {label} is not a SHA-256 digest"
        )


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
