"""Strict, explicit input contract for P10.7b readiness audits."""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any, Never

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .safe_input_files import SafeInputFileError, strict_json_object
from .seam_anchor_review_json import canonical_json_bytes, require_bounded_json_tree
from .spine42_v3_raster_review_validation import (
    DECISION_AUTHORITY, DECISION_FORMAT, DECISION_RELEASE_GATE,
    DECISION_SEMANTICS, FORMAT_VERSION as RASTER_REVIEW_FORMAT_VERSION,
)
from .spine42_v3_raster_review_values import (
    MAX_REVIEW_ROWS, Spine42V3RasterReviewError, require_review_source,
    self_hash, sha_value, text_value, token_value,
)

REQUEST_FORMAT = "autospine-spine42-v3-readiness-request"
REQUEST_FORMAT_VERSION = 1
REQUEST_HASH_DOMAIN = "autospine-spine42-v3-readiness-request/v1"
RASTER_DECISION_HASH_DOMAIN = "autospine-spine42-v3-raster-review-decision/v1"
MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_REQUEST_NODES = 250_000
MAX_REQUEST_DEPTH = 32
MAX_SAMPLES = 8

_ROOT_FIELDS = {"format", "format_version", "samples"}
_SAMPLE_FIELDS = {
    "project_id", "layer_manifest_sha256", "p3_rig_sha256",
    "p3_bundle_sha256", "reviewed_motion_address",
    "reviewed_seam_anchor_set_address", "motion_instance_v3_address",
    "spine42_v3_address", "runtime_capture_address", "raster_review_decision",
}
_ADDRESS_FIELDS = {
    "reviewed_motion_address": {"motion_instance_v2_sha256", "bundle_sha256"},
    "reviewed_seam_anchor_set_address": {
        "reviewed_seam_anchor_set_sha256", "bundle_sha256"},
    "motion_instance_v3_address": {"motion_instance_v3_sha256", "bundle_sha256"},
    "spine42_v3_address": {"skeleton_json_sha256", "bundle_sha256"},
    "runtime_capture_address": {
        "spine42_v3_bundle_sha256", "capture_bundle_sha256"},
}
_DECISION_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "source", "review",
    "case_decisions", "attachment_decisions", "claims", "semantics",
    "authority", "status", "release_gate", "decision_sha256",
}
_REVIEW_FIELDS = {
    "method", "status", "reviewer_id", "notes", "revision",
    "supersedes_decision_sha256",
}
_CLAIM_FIELDS = {
    "human_reviewed", "sampled_raster_visual_quality",
    "sampled_complete_attachment_inventory_reviewed",
    "continuous_runtime_raster_safety", "persistent_current_head_authority",
    "publishable_spine_timeline", "release_authority",
}


class Spine42V3ReadinessManifestError(ValueError):
    """Raised when an audit request is ambiguous, unsafe, or cross-wired."""


def parse_spine42_v3_readiness_request(data: bytes) -> dict[str, Any]:
    """Parse only exact canonical UTF-8 bytes and validate the full request."""
    try:
        if type(data) is not bytes or not data or len(data) > MAX_REQUEST_BYTES:
            _fail("Readiness request bytes are invalid or exceed their limit")
        result = require_spine42_v3_readiness_request(
            strict_json_object(data, "Spine v3 readiness request")
        )
        if data != canonical_json_bytes(result):
            _fail("Readiness request is not canonical JSON")
        return result
    except Spine42V3ReadinessManifestError:
        raise
    except (SafeInputFileError, ValueError) as exc:
        raise Spine42V3ReadinessManifestError(
            "Readiness request could not be parsed"
        ) from exc


def require_spine42_v3_readiness_request(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact fields, addresses, ordering, and dependency closure."""
    try:
        require_bounded_json_tree(
            value, max_nodes=MAX_REQUEST_NODES, max_depth=MAX_REQUEST_DEPTH,
        )
        if type(value) is not dict or set(value) != _ROOT_FIELDS \
                or value.get("format") != REQUEST_FORMAT \
                or type(value.get("format_version")) is not int \
                or value.get("format_version") != REQUEST_FORMAT_VERSION:
            _fail("Readiness request root fields are invalid")
        rows = value.get("samples")
        if type(rows) is not list or not 1 <= len(rows) <= MAX_SAMPLES:
            _fail("Readiness request sample count is invalid")
        samples = [_sample(row) for row in rows]
        ids = [row["project_id"] for row in samples]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            _fail("Readiness samples need unique ascending project ids")
        return _copy({
            "format": REQUEST_FORMAT, "format_version": REQUEST_FORMAT_VERSION,
            "samples": samples,
        })
    except Spine42V3ReadinessManifestError:
        raise
    except (
        AttributeError, LayerManifestError, OverflowError, RecursionError,
        Spine42V3RasterReviewError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3ReadinessManifestError(
            "Readiness request validation failed"
        ) from exc


def canonical_spine42_v3_readiness_request_bytes(
    value: Mapping[str, Any],
) -> bytes:
    """Return the only canonical bytes for one fully validated request."""
    return canonical_json_bytes(require_spine42_v3_readiness_request(value))


def spine42_v3_readiness_request_sha256(value: Mapping[str, Any]) -> str:
    """Hash one validated request in an explicit, versioned domain."""
    framed = canonical_json_bytes({
        "domain": REQUEST_HASH_DOMAIN,
        "request": require_spine42_v3_readiness_request(value),
    })
    return hashlib.sha256(framed).hexdigest()


def _sample(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _SAMPLE_FIELDS:
        _fail("Readiness sample fields are invalid")
    result = {
        "project_id": require_safe_token(value["project_id"], "Project id"),
        "layer_manifest_sha256": require_sha256(
            value["layer_manifest_sha256"], "Layer Manifest"),
        "p3_rig_sha256": require_sha256(value["p3_rig_sha256"], "P3 rig"),
        "p3_bundle_sha256": require_sha256(
            value["p3_bundle_sha256"], "P3 bundle"),
    }
    for field, fields in _ADDRESS_FIELDS.items():
        result[field] = _address(value[field], field, fields)
    _dependencies(result)
    decision = value["raster_review_decision"]
    result["raster_review_decision"] = (
        None if decision is None else _decision(decision, result)
    )
    return result


def _address(value: Any, label: str, fields: set[str]):
    if value is None:
        return None
    if type(value) is not dict or set(value) != fields:
        _fail(f"Readiness {label} fields are invalid")
    return {field: require_sha256(value[field], f"{label}.{field}")
            for field in sorted(fields)}


def _dependencies(sample: dict[str, Any]) -> None:
    motion = sample["reviewed_motion_address"]
    seam = sample["reviewed_seam_anchor_set_address"]
    instance = sample["motion_instance_v3_address"]
    spine = sample["spine42_v3_address"]
    capture = sample["runtime_capture_address"]
    if (instance is not None and (motion is None or seam is None)) \
            or (spine is not None and instance is None) \
            or (capture is not None and spine is None):
        _fail("Readiness request contains an inverted dependency")
    if capture is not None and capture["spine42_v3_bundle_sha256"] \
            != spine["bundle_sha256"]:
        _fail("Runtime capture is cross-wired to its Spine bundle")


def _decision(value: Any, sample: dict[str, Any]) -> dict[str, Any]:
    capture, spine = (
        sample["runtime_capture_address"], sample["spine42_v3_address"])
    if capture is None or type(value) is not dict or set(value) != _DECISION_FIELDS:
        _fail("Raster decision requires one exact runtime capture")
    if value.get("format") != DECISION_FORMAT \
            or type(value.get("format_version")) is not int \
            or value.get("format_version") != RASTER_REVIEW_FORMAT_VERSION \
            or value.get("project_id") != sample["project_id"] \
            or value.get("decision_sha256") != self_hash(
                value, "decision_sha256", RASTER_DECISION_HASH_DOMAIN):
        _fail("Raster decision identity is invalid")
    token_value(value.get("clip_id"), "clip id")
    require_review_source(value.get("source"), True)
    source = value["source"]
    if source["skeleton_json_sha256"] != spine["skeleton_json_sha256"] \
            or source["spine42_v3_bundle_sha256"] != spine["bundle_sha256"] \
            or source["runtime_capture_bundle_sha256"] \
            != capture["capture_bundle_sha256"]:
        _fail("Raster decision source is cross-wired")
    _review(value.get("review"))
    actions = _decision_rows(value.get("case_decisions"), "case_id")
    actions += _decision_rows(value.get("attachment_decisions"), "attachment_key")
    _decision_claims(value, actions)
    return _copy(value)


def _review(value: Any) -> None:
    if type(value) is not dict or set(value) != _REVIEW_FIELDS \
            or value.get("method") != "human" \
            or value.get("status") != "completed" \
            or type(value.get("revision")) is not int \
            or value.get("revision") != 1 \
            or value.get("supersedes_decision_sha256") is not None:
        _fail("Raster decision human review metadata is invalid")
    token_value(value.get("reviewer_id"), "reviewer id")
    text_value(value.get("notes"), "review notes", allow_empty=True)


def _decision_rows(value: Any, key: str) -> list[str]:
    if type(value) is not list or not 1 <= len(value) <= MAX_REVIEW_ROWS:
        _fail("Raster decision row count is invalid")
    seen, actions = set(), []
    for row in value:
        fields = {key, "evidence_sha256", "action", "notes"}
        if type(row) is not dict or set(row) != fields \
                or row.get(key) in seen \
                or row.get("action") not in {"approve", "reject", "unobservable"}:
            _fail("Raster decision row is invalid")
        token_value(row[key], key, allow_pair=key == "attachment_key")
        sha_value(row["evidence_sha256"], "decision evidence")
        notes = text_value(row["notes"], "decision notes", allow_empty=True)
        if row["action"] != "approve" and not notes.strip():
            _fail("Non-approved raster rows require notes")
        seen.add(row[key])
        actions.append(row["action"])
    return actions


def _decision_claims(value: dict[str, Any], actions: list[str]) -> None:
    claims = value.get("claims")
    false_claims = (
        "continuous_runtime_raster_safety", "persistent_current_head_authority",
        "publishable_spine_timeline", "release_authority",
    )
    if type(claims) is not dict or set(claims) != _CLAIM_FIELDS \
            or claims.get("human_reviewed") is not True \
            or any(claims.get(field) is not False for field in false_claims):
        _fail("Raster decision claims are invalid")
    approved = claims.get("sampled_raster_visual_quality")
    if type(approved) is not bool \
            or claims.get("sampled_complete_attachment_inventory_reviewed") \
            is not approved \
            or (approved and any(action != "approve" for action in actions)) \
            or value.get("status") != (
                "sampled_raster_approved" if approved else "sampled_raster_rejected") \
            or not _same(value.get("semantics"), DECISION_SEMANTICS) \
            or not _same(value.get("authority"), DECISION_AUTHORITY) \
            or not _same(value.get("release_gate"), DECISION_RELEASE_GATE):
        _fail("Raster decision bounded authority is invalid")


def _copy(value: Any) -> Any:
    return json.loads(canonical_json_bytes(value))


def _same(left: Any, right: Any) -> bool:
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def _fail(message: str) -> Never:
    raise Spine42V3ReadinessManifestError(message)


__all__ = [
    "MAX_REQUEST_BYTES", "MAX_SAMPLES", "REQUEST_FORMAT",
    "REQUEST_FORMAT_VERSION", "REQUEST_HASH_DOMAIN",
    "Spine42V3ReadinessManifestError",
    "canonical_spine42_v3_readiness_request_bytes",
    "parse_spine42_v3_readiness_request",
    "require_spine42_v3_readiness_request",
    "spine42_v3_readiness_request_sha256",
]
