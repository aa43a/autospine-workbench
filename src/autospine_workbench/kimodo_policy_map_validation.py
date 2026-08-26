"""Reviewed interpretation map for Kimodo heading and contact evidence."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import re
from typing import Any

from .camera_model_validation import (
    CameraModelError,
    camera_model_sha256,
    require_camera_matches_kimodo_map,
)
from .kimodo_npz_map_validation import (
    KimodoNpzMapError,
    kimodo_npz_map_sha256,
    require_kimodo_npz_map,
)


FORMAT = "autospine-kimodo-policy-map"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_AXES = frozenset(("+X", "-X", "+Y", "-Y", "+Z", "-Z"))
_TOP = {
    "format", "format_version", "policy_map_id", "source", "heading",
    "contact",
}
_SOURCE = {"kimodo_map_sha256", "camera_sha256"}
_HEADING = {
    "source", "vector_semantics", "components", "root_joint_name",
    "root_local_forward_axis", "yaw_convention", "crosscheck",
}
_COMPONENT = {"index", "source_axis"}
_CROSSCHECK = {"policy", "maximum_angle_error_deg"}
_CONTACT_MAPPED = {"status", "source", "interval", "proxies"}
_CONTACT_UNAVAILABLE = {"status", "reason_code"}
_PROXY = {
    "index", "limb", "point", "proxy_joint_name", "proxy_quality",
}
_PROXY_BY_POINT = {
    ("leg.left", "heel"): ("LeftFoot", "ankle-joint-proxy"),
    ("leg.left", "toe"): ("LeftToeBase", "toe-base-joint-proxy"),
    ("leg.left", "toe_end"): ("LeftToeEnd", "toe-end-joint-proxy"),
    ("leg.right", "heel"): ("RightFoot", "ankle-joint-proxy"),
    ("leg.right", "toe"): ("RightToeBase", "toe-base-joint-proxy"),
    ("leg.right", "toe_end"): ("RightToeEnd", "toe-end-joint-proxy"),
}


class KimodoPolicyMapError(ValueError):
    """Raised when reviewed ancillary-array semantics are ambiguous."""


def kimodo_policy_map_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical identity of one structurally valid policy map."""

    require_kimodo_policy_map(document)
    return hashlib.sha256(_canonical(document)).hexdigest()


def require_kimodo_policy_map(
    document: Mapping[str, Any],
    *,
    kimodo_map: Mapping[str, Any] | None = None,
    camera: Mapping[str, Any] | None = None,
) -> None:
    """Validate policy semantics and, when supplied, their exact P7/P8 basis."""

    try:
        root = _object(document, "Kimodo policy map")
        _exact(root, _TOP, "Kimodo policy map")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise KimodoPolicyMapError("Kimodo policy map format is unsupported")
        _safe_id(root.get("policy_map_id"))
        source = _source(root.get("source"))
        heading_axes = _heading(root.get("heading"))
        _contact(root.get("contact"), kimodo_map)
        if (kimodo_map is None) != (camera is None):
            raise KimodoPolicyMapError(
                "Kimodo policy map basis requires both map and camera"
            )
        if kimodo_map is not None and camera is not None:
            _cross_source(source, heading_axes, kimodo_map, camera)
        if len(_canonical(root)) > MAX_DOCUMENT_BYTES:
            raise KimodoPolicyMapError("Kimodo policy map byte limit exceeded")
    except KimodoPolicyMapError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise KimodoPolicyMapError(
            f"Kimodo policy map validation failed: {exc}"
        ) from exc


def _source(value: Any) -> Mapping[str, Any]:
    source = _object(value, "Kimodo policy map source")
    _exact(source, _SOURCE, "Kimodo policy map source")
    for field in _SOURCE:
        _sha(source.get(field), field)
    return source


def _heading(value: Any) -> tuple[str, str]:
    heading = _object(value, "Kimodo heading policy")
    _exact(heading, _HEADING, "Kimodo heading policy")
    if heading.get("source") != "global_root_heading" \
            or heading.get("vector_semantics") != "character_forward_world" \
            or heading.get("root_joint_name") != "Hips" \
            or heading.get("yaw_convention") != \
            "atan2_camera_screen_x_over_camera_depth":
        raise KimodoPolicyMapError("Kimodo heading interpretation is unsupported")
    local_forward = heading.get("root_local_forward_axis")
    if local_forward not in _AXES:
        raise KimodoPolicyMapError("Kimodo root local-forward axis is invalid")
    rows = _array(heading.get("components"), "Kimodo heading components")
    if len(rows) != 2:
        raise KimodoPolicyMapError("Kimodo heading must have two components")
    axes = []
    for index, raw in enumerate(rows):
        row = _object(raw, "Kimodo heading component")
        _exact(row, _COMPONENT, "Kimodo heading component")
        if type(row.get("index")) is not int or row.get("index") != index \
                or row.get("source_axis") not in _AXES:
            raise KimodoPolicyMapError(
                "Kimodo heading components must be canonically indexed axes"
            )
        axes.append(str(row["source_axis"]))
    if len({axis[1] for axis in axes}) != 2:
        raise KimodoPolicyMapError("Kimodo heading component axes must be distinct")
    if str(local_forward)[1] not in {axis[1] for axis in axes}:
        raise KimodoPolicyMapError(
            "Kimodo root local-forward axis must lie in the heading plane"
        )
    crosscheck = _object(heading.get("crosscheck"), "Kimodo heading crosscheck")
    _exact(crosscheck, _CROSSCHECK, "Kimodo heading crosscheck")
    if crosscheck.get("policy") != "projected_root_forward_angle":
        raise KimodoPolicyMapError("Kimodo heading crosscheck is unsupported")
    maximum = crosscheck.get("maximum_angle_error_deg")
    if isinstance(maximum, bool) or not isinstance(maximum, (int, float)) \
            or not math.isfinite(maximum) or not 0 <= float(maximum) <= 180:
        raise KimodoPolicyMapError("Kimodo heading angle tolerance is invalid")
    return axes[0], axes[1]


def _contact(value: Any, mapping: Mapping[str, Any] | None) -> None:
    contact = _object(value, "Kimodo contact policy")
    status = contact.get("status")
    if status == "unavailable":
        _exact(contact, _CONTACT_UNAVAILABLE, "Kimodo contact policy")
        if contact.get("reason_code") != "map_contact_disabled":
            raise KimodoPolicyMapError("Kimodo contact reason is unsupported")
        if mapping is not None and mapping["contact"]["enabled"]:
            raise KimodoPolicyMapError("Enabled contact map cannot be unavailable")
        return
    if status != "mapped":
        raise KimodoPolicyMapError("Kimodo contact policy status is unsupported")
    _exact(contact, _CONTACT_MAPPED, "Kimodo contact policy")
    if contact.get("source") != "foot_contacts" \
            or contact.get("interval") != "half_open":
        raise KimodoPolicyMapError("Kimodo contact interpretation is unsupported")
    proxies = _array(contact.get("proxies"), "Kimodo contact proxies")
    if not 1 <= len(proxies) <= 6:
        raise KimodoPolicyMapError("Kimodo contact proxy count is invalid")
    normalized = []
    for index, raw in enumerate(proxies):
        row = _object(raw, "Kimodo contact proxy")
        _exact(row, _PROXY, "Kimodo contact proxy")
        key = (row.get("limb"), row.get("point"))
        expected = _PROXY_BY_POINT.get(key)
        if type(row.get("index")) is not int or row.get("index") != index \
                or expected != (
                    row.get("proxy_joint_name"), row.get("proxy_quality")
                ):
            raise KimodoPolicyMapError(
                "Kimodo contact proxy differs from the pinned SOMA77 policy"
            )
        normalized.append((index, *key))
    if mapping is not None:
        mapped = mapping["contact"]
        if not mapped["enabled"]:
            raise KimodoPolicyMapError("Disabled contact map cannot have proxies")
        expected = [
            (row["index"], row["limb"], row["point"])
            for row in mapped["channels"]
        ]
        if normalized != expected:
            raise KimodoPolicyMapError(
                "Kimodo contact proxies differ from mapped channels"
            )


def _cross_source(source, heading_axes, mapping, camera) -> None:
    try:
        require_kimodo_npz_map(mapping)
        require_camera_matches_kimodo_map(camera, mapping)
    except (KimodoNpzMapError, CameraModelError) as exc:
        raise KimodoPolicyMapError("Kimodo policy source basis is invalid") from exc
    if source["kimodo_map_sha256"] != kimodo_npz_map_sha256(mapping) \
            or source["camera_sha256"] != camera_model_sha256(camera):
        raise KimodoPolicyMapError("Kimodo policy source identity differs")
    required = {
        camera["basis"]["screen_x"][1], camera["basis"]["depth"][1]
    }
    if {axis[1] for axis in heading_axes} != required:
        raise KimodoPolicyMapError(
            "Kimodo heading axes must cover camera lateral and depth axes"
        )


def _safe_id(value: Any) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise KimodoPolicyMapError("Kimodo policy map id is invalid")


def _sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise KimodoPolicyMapError(f"Kimodo policy {label} is invalid")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KimodoPolicyMapError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise KimodoPolicyMapError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise KimodoPolicyMapError(f"{label} fields are incomplete or unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
