"""Strict semantic validation for immutable bilateral split previews."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence

from .contract_types import MAX_LABEL_LENGTH, MAX_REASON_LENGTH
from .resolved_project import canonical_sha256


SPLIT_PREVIEW_FORMAT = "autospine-split-preview/v1"

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_ROLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SIDES = ("left", "right")


class SplitPreviewContractError(ValueError):
    """Raised when a split preview document violates the v1 contract."""


def require_valid_split_preview(document: Mapping[str, Any]) -> None:
    """Fail closed unless *document* is a complete v1 preview artifact."""

    root = _mapping(document, "split preview")
    _exact(
        root,
        {
            "format", "project_id", "layer_id", "resolved_snapshot_sha256",
            "layer_manifest_sha256", "split_spec", "operation_config_sha256",
            "review_target", "review_target_sha256",
        },
        "split preview",
    )
    if root.get("format") != SPLIT_PREVIEW_FORMAT:
        raise SplitPreviewContractError("Split preview format is unsupported")
    _safe_id(root.get("project_id"), "project id")
    layer_id = _safe_id(root.get("layer_id"), "layer id")
    for field in (
        "resolved_snapshot_sha256", "layer_manifest_sha256",
        "operation_config_sha256", "review_target_sha256",
    ):
        _sha(root.get(field), field)
    spec = _validate_embedded_spec(root.get("split_spec"))
    target = _mapping(root.get("review_target"), "review target")
    _validate_review_target(target, layer_id, spec, root["operation_config_sha256"])
    if canonical_sha256(target) != root["review_target_sha256"]:
        raise SplitPreviewContractError("Review target does not match its hash")


def _validate_embedded_spec(value: Any) -> Mapping[str, Any]:
    spec = _mapping(value, "split_spec")
    _exact(spec, {"parts"}, "split_spec")
    parts = _mapping(spec.get("parts"), "split_spec parts")
    _exact(parts, set(_SIDES), "split_spec parts")
    guide_fingerprints: dict[str, list[tuple[Any, ...]]] = {}
    for side in _SIDES:
        part = _mapping(parts.get(side), f"{side} split part")
        _exact(part, {"guide", "pivot", "candidate_bone"}, f"{side} split part")
        guide = _sequence(part.get("guide"), f"{side} guide")
        if not 2 <= len(guide) <= 8:
            raise SplitPreviewContractError(f"{side} guide must contain 2 to 8 anchors")
        identities: list[tuple[str, str]] = []
        fingerprints: list[tuple[Any, ...]] = []
        for item in guide:
            identity, fingerprint = _validate_anchor(item, side)
            identities.append(identity)
            fingerprints.append(fingerprint)
        if len(set(identities)) != len(identities):
            raise SplitPreviewContractError(f"{side} guide repeats an anchor")
        if any(a == b for a, b in zip(fingerprints, fingerprints[1:])):
            raise SplitPreviewContractError(f"{side} guide has a zero-length authored segment")
        guide_fingerprints[side] = fingerprints
        _validate_anchor(part.get("pivot"), side)
        bone = _safe_id(part.get("candidate_bone"), f"{side} candidate bone")
        if not bone.endswith(f".{side}"):
            raise SplitPreviewContractError(f"{side} candidate bone has the wrong side")
    left, right = guide_fingerprints["left"], guide_fingerprints["right"]
    if left == right or left == list(reversed(right)):
        raise SplitPreviewContractError("Left and right authored guides are degenerate")
    return spec


def _validate_anchor(value: Any, side: str) -> tuple[tuple[str, str], tuple[Any, ...]]:
    anchor = _mapping(value, f"{side} anchor")
    if anchor.get("kind") == "joint":
        _exact(anchor, {"kind", "joint_id"}, f"{side} joint anchor")
        joint_id = _safe_id(anchor.get("joint_id"), "joint id")
        if joint_id.endswith(tuple(f".{other}" for other in _SIDES if other != side)):
            raise SplitPreviewContractError(f"{side} anchor references the opposite side")
        return ("joint", joint_id), ("joint", joint_id)
    required = {"kind", "proxy_id", "xy", "label", "reason"}
    allowed = required | {"proxy_for_joint_id"}
    if (
        anchor.get("kind") != "manual_proxy"
        or not required.issubset(anchor)
        or not set(anchor).issubset(allowed)
    ):
        raise SplitPreviewContractError(f"{side} anchor fields are unsupported")
    proxy_id = _safe_id(anchor.get("proxy_id"), "proxy id")
    if not proxy_id.endswith(f".{side}"):
        raise SplitPreviewContractError(f"{side} proxy id has the wrong side")
    point = _point(anchor.get("xy"), f"{side} proxy point")
    for field, limit in (("label", MAX_LABEL_LENGTH), ("reason", MAX_REASON_LENGTH)):
        if not isinstance(anchor.get(field), str) or not anchor[field].strip():
            raise SplitPreviewContractError(f"{side} proxy {field} is empty")
        if len(anchor[field]) > limit:
            raise SplitPreviewContractError(f"{side} proxy {field} is too long")
    if "proxy_for_joint_id" in anchor:
        proxy_for = _safe_id(anchor["proxy_for_joint_id"], "proxy joint id")
        if proxy_for.endswith(tuple(f".{other}" for other in _SIDES if other != side)):
            raise SplitPreviewContractError(f"{side} proxy references the opposite side")
    return ("manual_proxy", proxy_id), ("manual_proxy_xy", *point)


def _validate_review_target(target, layer_id, spec, operation_sha) -> None:
    _exact(target, {"source", "operation", "parts"}, "review target")
    source = _mapping(target.get("source"), "review source")
    _exact(
        source,
        {"layer_id", "canonical_role", "raster_sha256", "rgba_sha256"},
        "review source",
    )
    if source.get("layer_id") != layer_id or not _SAFE_ROLE.fullmatch(
        str(source.get("canonical_role") or "")
    ):
        raise SplitPreviewContractError("Review source identity is invalid")
    _sha(source.get("raster_sha256"), "source raster")
    _sha(source.get("rgba_sha256"), "source RGBA")
    operation = _mapping(target.get("operation"), "review operation")
    _exact(
        operation,
        {"algorithm", "config_sha256", "output_rgba_sha256"},
        "review operation",
    )
    algorithm = _mapping(operation.get("algorithm"), "split algorithm")
    _exact(algorithm, {"id", "version"}, "split algorithm")
    _safe_id(algorithm.get("id"), "split algorithm id")
    version = algorithm.get("version")
    if (
        not isinstance(version, str)
        or not version
        or len(version) > 64
        or any(character.isspace() for character in version)
    ):
        raise SplitPreviewContractError("Split algorithm version is invalid")
    if operation.get("config_sha256") != operation_sha:
        raise SplitPreviewContractError("Review operation hash differs from the preview")
    outputs = _mapping(operation.get("output_rgba_sha256"), "split outputs")
    _exact(outputs, set(_SIDES), "split outputs")
    parts = _mapping(target.get("parts"), "review parts")
    _exact(parts, set(_SIDES), "review parts")
    orders: set[int] = set()
    for side in _SIDES:
        _sha(outputs.get(side), f"{side} output RGBA")
        part = _mapping(parts.get(side), f"{side} review part")
        _exact(
            part,
            {
                "layer_id", "side", "pivot_xy", "candidate_bone",
                "setup_draw_order", "raster_sha256",
            },
            f"{side} review part",
        )
        if part.get("layer_id") != f"{layer_id}--{side}" or part.get("side") != side:
            raise SplitPreviewContractError(f"{side} review child identity is invalid")
        _point(part.get("pivot_xy"), f"{side} review pivot")
        if part.get("candidate_bone") != spec["parts"][side]["candidate_bone"]:
            raise SplitPreviewContractError(f"{side} review bone differs from split_spec")
        authored_pivot = spec["parts"][side]["pivot"]
        if (
            authored_pivot["kind"] == "manual_proxy"
            and part["pivot_xy"] != authored_pivot["xy"]
        ):
            raise SplitPreviewContractError(
                f"{side} review pivot differs from manual split_spec"
            )
        order = part.get("setup_draw_order")
        if not isinstance(order, int) or isinstance(order, bool) or order in orders:
            raise SplitPreviewContractError(
                "Review child draw orders must be distinct integers"
            )
        orders.add(order)
        _sha(part.get("raster_sha256"), f"{side} child raster")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SplitPreviewContractError(f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SplitPreviewContractError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise SplitPreviewContractError(f"{label} fields are incomplete or unsupported")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise SplitPreviewContractError(f"{label} is invalid")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SplitPreviewContractError(f"{label} is not a lowercase SHA-256")
    return value


def _point(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise SplitPreviewContractError(f"{label} must be a point")
    return [_number(value[0], label), _number(value[1], label)]


def _number(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise SplitPreviewContractError(f"{label} must be finite")
    return float(value)
