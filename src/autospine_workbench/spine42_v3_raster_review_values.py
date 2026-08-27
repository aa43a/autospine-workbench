"""Bounded scalar and evidence-row validators for P10.7b review."""
from __future__ import annotations
from collections.abc import Mapping
import hashlib
import json
import math
import re

MAX_REVIEW_ROWS = 96
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class Spine42V3RasterReviewError(ValueError):
    """Raised when sampled evidence cannot form an exhaustive review."""


def self_hash(row, field, domain):
    body = json.loads(canonical_json(row))
    body.pop(field, None)
    return domain_sha256(domain, body)


def domain_sha256(domain, value):
    return canonical_sha256({"domain": domain, "value": value})


def canonical_sha256(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def canonical_json(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":"))
    except (OverflowError, TypeError, ValueError) as exc:
        raise Spine42V3RasterReviewError("Review JSON is invalid") from exc


def object_value(value, label):
    if not isinstance(value, Mapping):
        raise Spine42V3RasterReviewError(f"{label} must be an object")
    return value


def rows_value(value, label):
    if not isinstance(value, list):
        raise Spine42V3RasterReviewError(f"{label} must be a list")
    return [object_value(item, label) for item in value]


def sha_value(value, label):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise Spine42V3RasterReviewError(f"{label} SHA-256 is invalid")
    return value


def token_value(value, label, *, allow_pair=False):
    pattern = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$" if allow_pair else None
    valid = re.fullmatch(pattern, value) if pattern and isinstance(value, str) \
        else _TOKEN.fullmatch(value) if isinstance(value, str) else None
    if valid is None:
        raise Spine42V3RasterReviewError(f"{label} is invalid")
    return value


def text_value(value, label, *, allow_empty):
    if not isinstance(value, str) or len(value) > 2000 \
            or (not allow_empty and not value.strip()):
        raise Spine42V3RasterReviewError(f"{label} is invalid")
    return value


def require_review_source(value, include_candidate):
    source = object_value(value, "review source")
    fields = {
        "skeleton_json_sha256", "spine42_v3_bundle_sha256",
        "run_document_sha256", "capture_plan_sha256",
        "runtime_session_set_sha256", "runtime_capture_manifest_sha256",
        "runtime_capture_bundle_sha256", "raster_metrics_sha256",
    }
    if include_candidate:
        fields.add("candidate_sha256")
    if set(source) != fields:
        raise Spine42V3RasterReviewError("Review source fields are invalid")
    for key, digest in source.items():
        sha_value(digest, key)


def require_candidate_cases(value):
    rows, seen = rows_value(value, "case candidates"), set()
    if not rows or len(rows) > MAX_REVIEW_ROWS:
        raise Spine42V3RasterReviewError("Candidate case inventory is invalid")
    fields = {"case_id", "tick", "time_seconds", "composite",
              "metrics_passed", "reason_codes", "evidence_sha256"}
    for row in rows:
        reasons = row.get("reason_codes")
        invalid = set(row) != fields or row.get("case_id") in seen \
            or type(row.get("tick")) is not int or row["tick"] < 0 \
            or not _finite(row.get("time_seconds")) \
            or type(row.get("metrics_passed")) is not bool \
            or type(reasons) is not list \
            or any(type(item) is not str for item in reasons) \
            or len(set(reasons)) != len(reasons) \
            or row.get("metrics_passed") is not (not reasons) \
            or row.get("evidence_sha256") != self_hash(
                row, "evidence_sha256", "p10.7b-case/v1")
        if invalid:
            raise Spine42V3RasterReviewError("Candidate case row is invalid")
        token_value(row["case_id"], "case id")
        _artifact(row["composite"])
        seen.add(row["case_id"])
    return rows


def require_candidate_attachments(value, cases):
    rows, seen = rows_value(value, "attachment candidates"), set()
    if not rows or len(rows) > MAX_REVIEW_ROWS:
        raise Spine42V3RasterReviewError("Candidate attachment inventory is invalid")
    case_ids = [row["case_id"] for row in cases]
    fields = {"attachment_key", "ordinal", "slot_id", "attachment_id",
              "frames", "evidence_sha256"}
    for ordinal, row in enumerate(rows):
        frames = row.get("frames")
        invalid = set(row) != fields or row.get("attachment_key") in seen \
            or row.get("ordinal") != ordinal or not isinstance(frames, list) \
            or [frame.get("case_id") for frame in frames] != case_ids \
            or row.get("evidence_sha256") != self_hash(
                row, "evidence_sha256", "p10.7b-attachment/v1")
        if invalid:
            raise Spine42V3RasterReviewError("Candidate attachment row is invalid")
        token_value(row["attachment_key"], "attachment key", allow_pair=True)
        token_value(row["slot_id"], "slot id")
        token_value(row["attachment_id"], "attachment id")
        if row["attachment_key"] != f"{row['slot_id']}::{row['attachment_id']}":
            raise Spine42V3RasterReviewError("Attachment key is inconsistent")
        for frame in frames:
            _frame(frame)
        seen.add(row["attachment_key"])
    return rows


def _artifact(row):
    row = object_value(row, "case composite")
    invalid = set(row) != {"artifact_id", "stored_path", "sha256", "size_bytes"} \
        or type(row.get("artifact_id")) is not str \
        or row.get("stored_path") != f"captures/{row['artifact_id']}.png" \
        or type(row.get("size_bytes")) is not int or row["size_bytes"] <= 0
    if invalid:
        raise Spine42V3RasterReviewError("Case composite is invalid")
    sha_value(row.get("sha256"), "case composite")


def _frame(row):
    fields = {"case_id", "artifact_id", "stored_path", "sha256", "nonempty",
              "boundary_pixels", "clipped_boundary_pixels"}
    invalid = not isinstance(row, Mapping) or set(row) != fields \
        or type(row.get("artifact_id")) is not str \
        or row.get("stored_path") != f"captures/{row['artifact_id']}.png" \
        or type(row.get("nonempty")) is not bool \
        or any(type(row.get(key)) is not int or row[key] < 0 for key in (
            "boundary_pixels", "clipped_boundary_pixels"))
    if invalid:
        raise Spine42V3RasterReviewError("Attachment frame is invalid")
    sha_value(row.get("sha256"), "attachment frame")


def _finite(value):
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


__all__ = [
    "Spine42V3RasterReviewError", "canonical_json", "canonical_sha256",
    "domain_sha256", "object_value", "require_candidate_attachments",
    "require_candidate_cases", "require_review_source", "rows_value",
    "self_hash", "sha_value", "text_value", "token_value",
]
