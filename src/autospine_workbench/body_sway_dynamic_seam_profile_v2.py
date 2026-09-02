"""Pinned identity and resource limits for the P10.5d v2 source closure."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .body_sway_continuous_proof_profile_v2 import (
    MAX_DOCUMENT_BYTES as MAX_CONTINUOUS_PROOF_V2_BYTES,
)
from .resolved_project import canonical_sha256
from .reviewed_seam_anchor_set_profile import (
    MAX_DOCUMENT_BYTES as MAX_REVIEWED_SET_V1_BYTES,
)
from .seam_anchor_candidate_profile import (
    MAX_DOCUMENT_BYTES as MAX_SEAM_CANDIDATE_V1_BYTES,
)
from .seam_anchor_review_profile import (
    MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES as MAX_SEAM_DECISION_V1_BYTES,
)


FORMAT = "autospine-body-sway-dynamic-seam-source"
FORMAT_VERSION = 2
SOURCE_HASH_DOMAIN = "autospine-body-sway-dynamic-seam-source/v2"
MAX_SOURCE_OWN_BYTES = 64 * 1024
MAX_SOURCE_BYTES = (
    MAX_CONTINUOUS_PROOF_V2_BYTES
    + MAX_SEAM_CANDIDATE_V1_BYTES
    + MAX_SEAM_DECISION_V1_BYTES
    + MAX_REVIEWED_SET_V1_BYTES
    + MAX_SOURCE_OWN_BYTES
)
MAX_SOURCE_JSON_NODES = 1_000_000
MAX_SOURCE_JSON_DEPTH = 160
SOURCE_FIELDS = {
    "format",
    "format_version",
    "project_id",
    "clip_id",
    "source_set_sha256",
    "layer_manifest_sha256",
    "p3_rig_sha256",
    "p3_bundle_sha256",
    "body_sway_continuous_preview_proof_v2_sha256",
    "body_sway_continuous_preview_proof_v2",
    "seam_anchor_candidates_v1_sha256",
    "seam_anchor_candidates_v1",
    "seam_anchor_review_decision_v1_sha256",
    "seam_anchor_review_decision_v1",
    "review_revision",
    "reviewed_seam_anchor_set_v1_sha256",
    "reviewed_seam_anchor_set_v1_bundle_sha256",
    "reviewed_seam_anchor_set_v1",
}


def body_sway_dynamic_seam_source_sha256_v2(
    source: Mapping[str, Any],
) -> str:
    """Hash a strict source closure without its self-address."""

    if type(source) is not dict:
        raise ValueError("Dynamic seam source v2 must be an exact JSON object")
    payload = {
        key: value for key, value in source.items()
        if key != "source_set_sha256"
    }
    return canonical_sha256({
        "domain": SOURCE_HASH_DOMAIN,
        "source": payload,
    })


__all__ = [
    "FORMAT",
    "FORMAT_VERSION",
    "MAX_CONTINUOUS_PROOF_V2_BYTES",
    "MAX_REVIEWED_SET_V1_BYTES",
    "MAX_SEAM_CANDIDATE_V1_BYTES",
    "MAX_SEAM_DECISION_V1_BYTES",
    "MAX_SOURCE_BYTES",
    "MAX_SOURCE_JSON_DEPTH",
    "MAX_SOURCE_JSON_NODES",
    "SOURCE_FIELDS",
    "SOURCE_HASH_DOMAIN",
    "body_sway_dynamic_seam_source_sha256_v2",
]
