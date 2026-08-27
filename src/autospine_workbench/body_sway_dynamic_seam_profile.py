"""Pinned identity and resource limits for the P10.5d source closure."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .body_sway_continuous_proof_profile import (
    MAX_DOCUMENT_BYTES as MAX_CONTINUOUS_PROOF_BYTES,
)
from .resolved_project import canonical_sha256
from .reviewed_seam_anchor_set_profile import (
    MAX_DOCUMENT_BYTES as MAX_REVIEWED_SET_BYTES,
)
from .seam_anchor_candidate_profile import (
    MAX_DOCUMENT_BYTES as MAX_SEAM_CANDIDATE_BYTES,
)
from .seam_anchor_review_profile import (
    MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES as MAX_SEAM_DECISION_BYTES,
)


SOURCE_HASH_DOMAIN = "autospine-body-sway-dynamic-seam-source/v1"
MAX_SOURCE_OWN_BYTES = 64 * 1024
MAX_SOURCE_BYTES = (
    MAX_CONTINUOUS_PROOF_BYTES
    + MAX_SEAM_CANDIDATE_BYTES
    + MAX_SEAM_DECISION_BYTES
    + MAX_REVIEWED_SET_BYTES
    + MAX_SOURCE_OWN_BYTES
)
MAX_SOURCE_JSON_NODES = 1_000_000
MAX_SOURCE_JSON_DEPTH = 160
SOURCE_FIELDS = {
    "source_set_sha256",
    "body_sway_continuous_proof_sha256",
    "body_sway_continuous_preview_proof",
    "seam_anchor_candidate_sha256",
    "seam_anchor_candidates",
    "seam_anchor_review_decision_sha256",
    "seam_anchor_review_decision",
    "review_revision",
    "reviewed_seam_anchor_set_sha256",
    "reviewed_seam_anchor_set_bundle_sha256",
    "reviewed_seam_anchor_set",
}


def body_sway_dynamic_seam_source_sha256(
    source: Mapping[str, Any],
) -> str:
    """Hash one source closure with an explicit P10.5d domain separator."""

    if type(source) is not dict:
        raise ValueError("Dynamic seam source must be an exact JSON object")
    payload = {key: value for key, value in source.items()
               if key != "source_set_sha256"}
    return canonical_sha256({
        "domain": SOURCE_HASH_DOMAIN,
        "source": payload,
    })
