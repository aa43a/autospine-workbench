"""Strict, content-bound interpretation metadata for Kimodo NPZ bytes."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from typing import Any

from .kimodo_soma77 import (
    PROFILE_ID as SOMA77_PROFILE_ID,
    SOMA77_DEFINITION_SHA256,
    SOMA77_JOINT_NAMES,
)


FORMAT = "autospine-kimodo-npz-source"
FORMAT_VERSION = 1
MAX_RAW_NPZ_BYTES = 128 * 1024 * 1024
MAX_SOURCE_DOCUMENT_BYTES = 64 * 1024
MAX_FRAMES = 4096
MAX_FPS_TERM = 1000
COORDINATE_SYSTEM = {
    "handedness": "right",
    "right_axis": "+X",
    "up_axis": "+Y",
    "forward_axis": "+Z",
    "length_unit": "meter",
    "side_naming": "character_side",
}
CORE_ARRAY_NAMES = (
    "posed_joints",
    "global_rot_mats",
    "local_rot_mats",
    "foot_contacts",
    "root_positions",
)
COMPLETE_ARRAY_NAMES = (
    "posed_joints",
    "global_rot_mats",
    "local_rot_mats",
    "foot_contacts",
    "smooth_root_pos",
    "root_positions",
    "global_root_heading",
)
CONTACT_LAYOUTS = {
    "left-heel-toe-right-heel-toe-v1": 4,
    "left-heel-toe-toe_end-right-heel-toe-toe_end-v1": 6,
}

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[0-9a-f]{40,64}")
_TOP = {
    "format", "format_version", "source_id", "raw_npz", "producer",
    "skeleton", "coordinate_system", "array_profile",
}


class KimodoNpzSourceError(ValueError):
    """Raised when Kimodo source interpretation or provenance is ambiguous."""


def kimodo_npz_source_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical identity of a fully validated source sidecar."""

    require_kimodo_npz_source(document)
    return hashlib.sha256(_canonical(document)).hexdigest()


def require_kimodo_npz_source(
    document: Mapping[str, Any], *, raw_npz: bytes | None = None
) -> None:
    """Validate a sidecar and optionally bind it to the exact raw NPZ bytes."""

    try:
        root = _object(document, "Kimodo NPZ source")
        _exact(root, _TOP, "Kimodo NPZ source")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise KimodoNpzSourceError("Kimodo NPZ source format is unsupported")
        _safe_id(root.get("source_id"), "source_id")
        source = _raw_npz(root.get("raw_npz"))
        _producer(root.get("producer"))
        _skeleton(root.get("skeleton"))
        if root.get("coordinate_system") != COORDINATE_SYSTEM:
            raise KimodoNpzSourceError(
                "Kimodo NPZ coordinate system is unsupported"
            )
        _array_profile(root.get("array_profile"))
        if raw_npz is not None:
            _cross_raw(raw_npz, source)
        if len(_canonical(root)) > MAX_SOURCE_DOCUMENT_BYTES:
            raise KimodoNpzSourceError(
                "Kimodo NPZ source document byte limit exceeded"
            )
    except KimodoNpzSourceError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise KimodoNpzSourceError(
            f"Kimodo NPZ source validation failed: {exc}"
        ) from exc


def expected_array_names(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the exact canonical NPY member stem inventory for a sidecar."""

    require_kimodo_npz_source(document)
    inventory = document["array_profile"]["inventory"]
    return CORE_ARRAY_NAMES if inventory == "core-v1" else COMPLETE_ARRAY_NAMES


def expected_contact_count(document: Mapping[str, Any]) -> int:
    """Return the exact foot-contact column count declared by a sidecar."""

    require_kimodo_npz_source(document)
    return CONTACT_LAYOUTS[document["array_profile"]["contact_layout"]]


def _raw_npz(value: Any) -> Mapping[str, Any]:
    source = _object(value, "Kimodo NPZ raw source")
    _exact(
        source,
        {"sha256", "byte_length", "frame_count", "frames_per_second"},
        "Kimodo NPZ raw source",
    )
    _sha256(source.get("sha256"), "raw NPZ SHA")
    length = source.get("byte_length")
    if type(length) is not int or not 1 <= length <= MAX_RAW_NPZ_BYTES:
        raise KimodoNpzSourceError("Kimodo NPZ byte length is invalid")
    frames = source.get("frame_count")
    if type(frames) is not int or not 2 <= frames <= MAX_FRAMES:
        raise KimodoNpzSourceError("Kimodo NPZ frame count is invalid")
    fps = _object(source.get("frames_per_second"), "Kimodo NPZ frame rate")
    _exact(fps, {"numerator", "denominator"}, "Kimodo NPZ frame rate")
    for field in ("numerator", "denominator"):
        term = fps.get(field)
        if type(term) is not int or not 1 <= term <= MAX_FPS_TERM:
            raise KimodoNpzSourceError("Kimodo NPZ frame rate is invalid")
    return source


def _producer(value: Any) -> None:
    producer = _object(value, "Kimodo NPZ producer")
    status = producer.get("status")
    if status == "recorded":
        _exact(producer, {
            "status", "implementation", "repository_revision", "model_id",
            "checkpoint_revision", "checkpoint_manifest_sha256",
            "generation_request_sha256", "seed", "sample_index",
        }, "Kimodo NPZ recorded producer")
        if producer.get("implementation") != "nv-tlabs/kimodo":
            raise KimodoNpzSourceError("Kimodo producer implementation is unsupported")
        for field in ("repository_revision", "checkpoint_revision"):
            revision = producer.get(field)
            if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
                raise KimodoNpzSourceError(f"Kimodo producer {field} is invalid")
        _safe_id(producer.get("model_id"), "model_id")
        for field in ("checkpoint_manifest_sha256", "generation_request_sha256"):
            _sha256(producer.get(field), field)
        seed = producer.get("seed")
        sample = producer.get("sample_index")
        if type(seed) is not int or not -(2 ** 63) <= seed < 2 ** 63:
            raise KimodoNpzSourceError("Kimodo producer seed is invalid")
        if type(sample) is not int or not 0 <= sample <= 1_000_000:
            raise KimodoNpzSourceError("Kimodo producer sample index is invalid")
        return
    if status == "unavailable":
        _exact(
            producer, {"status", "implementation", "reason_code"},
            "Kimodo NPZ unavailable producer",
        )
        if producer.get("implementation") != "nv-tlabs/kimodo" \
                or producer.get("reason_code") not in {
                    "legacy_export", "external_export",
                }:
            raise KimodoNpzSourceError("Kimodo unavailable provenance is invalid")
        return
    raise KimodoNpzSourceError("Kimodo producer status is unsupported")


def _skeleton(value: Any) -> None:
    skeleton = _object(value, "Kimodo NPZ skeleton")
    _exact(
        skeleton, {"profile_id", "joint_count", "definition_sha256"},
        "Kimodo NPZ skeleton",
    )
    if skeleton.get("profile_id") != SOMA77_PROFILE_ID \
            or type(skeleton.get("joint_count")) is not int \
            or skeleton.get("joint_count") != len(SOMA77_JOINT_NAMES) \
            or skeleton.get("definition_sha256") != SOMA77_DEFINITION_SHA256:
        raise KimodoNpzSourceError("Kimodo SOMA77 definition identity drifted")


def _array_profile(value: Any) -> None:
    profile = _object(value, "Kimodo NPZ array profile")
    _exact(
        profile,
        {"inventory", "float_dtype", "contact_dtype", "contact_layout"},
        "Kimodo NPZ array profile",
    )
    if profile.get("inventory") not in {"core-v1", "complete-v1"} \
            or profile.get("float_dtype") != "<f4" \
            or profile.get("contact_dtype") != "|b1" \
            or profile.get("contact_layout") not in CONTACT_LAYOUTS:
        raise KimodoNpzSourceError("Kimodo NPZ array profile is unsupported")


def _cross_raw(raw_npz: bytes, source: Mapping[str, Any]) -> None:
    if type(raw_npz) is not bytes or not 1 <= len(raw_npz) <= MAX_RAW_NPZ_BYTES:
        raise KimodoNpzSourceError("Kimodo raw NPZ must be bounded immutable bytes")
    if len(raw_npz) != source["byte_length"] \
            or hashlib.sha256(raw_npz).hexdigest() != source["sha256"]:
        raise KimodoNpzSourceError("Kimodo raw NPZ identity differs from sidecar")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise KimodoNpzSourceError(f"Kimodo NPZ {label} is invalid")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise KimodoNpzSourceError(f"Kimodo NPZ {label} is invalid")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KimodoNpzSourceError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise KimodoNpzSourceError(f"{label} fields are incomplete or unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
