"""Strict identity comparisons for P10.7b v2 request preparation."""

from __future__ import annotations

from collections.abc import Mapping

from .p10_spine42_v3_runtime_job_validation_v2 import (
    AUTH_PATTERN, PAYLOAD_FIELDS, require_optional_sha, require_sha,
)
from .spine42_v3_runtime_candidate_catalog_v2 import (
    Spine42V3RuntimeCandidateCatalogV2,
)

SOURCE_FIELDS = (
    "project_id", "clip_id", "skeleton_json_sha256",
    "spine42_v3_bundle_sha256", "source_contract_sha256", "profile_sha256",
    "capture_plan_sha256", "admission_sha256",
)
_SELECTION_FIELDS = {
    "mode", "reason_code", "requested_spine_run_id",
    "recommended_candidate_id", "recommended_entry_sha256",
}


def require_preflight_payload_v2(value):
    """Reject malformed browser input before any expensive local discovery."""

    if not isinstance(value, Mapping) or set(value) != PAYLOAD_FIELDS:
        raise ValueError("Runtime preflight browser fields are invalid")
    require_sha(value.get("candidate_id"))
    require_sha(value.get("entry_sha256"))
    authorization = value.get("authorization_id")
    if type(authorization) is not str \
            or AUTH_PATTERN.fullmatch(authorization) is None \
            or value.get("explicit_runtime_license_confirmation") is not True \
            or value.get("explicit_run_confirmation") is not True:
        raise ValueError("Runtime preflight authorization is invalid")
    require_optional_sha(value.get("retry_of_job_id"))
    return value


def require_automatic_selection_v2(catalog, candidate_id, entry_sha256):
    if type(catalog) is not Spine42V3RuntimeCandidateCatalogV2:
        raise ValueError("Runtime automatic selection type is invalid")
    row = catalog.selection
    if type(row) is not dict or set(row) != _SELECTION_FIELDS \
            or row.get("mode") != "automatic" \
            or row.get("recommended_candidate_id") != candidate_id \
            or row.get("recommended_entry_sha256") != entry_sha256:
        raise ValueError("Runtime automatic selection changed")


def source_matches_candidate_output_v2(source, output):
    return (
        source.project_id, source.clip_id, source.skeleton_json_sha256,
        source.spine42_v3_bundle_sha256,
    ) == (
        output["project_id"], output["clip_id"],
        output["skeleton_json_sha256"], output["bundle_sha256"],
    )


def same_runtime_source_v2(left, right):
    return all(getattr(left, name) == getattr(right, name)
               for name in SOURCE_FIELDS) \
        and left.document_bytes == right.document_bytes


__all__ = [
    "SOURCE_FIELDS", "require_automatic_selection_v2",
    "require_preflight_payload_v2",
    "same_runtime_source_v2", "source_matches_candidate_output_v2",
]
