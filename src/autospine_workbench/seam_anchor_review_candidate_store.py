"""Write-once persistence for exact P10.5a candidates used by review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .safe_input_files import SafeInputFileError, strict_json_object
from .seam_anchor_candidate_validation import (
    SeamAnchorCandidateValidationError,
    require_seam_anchor_candidates,
    seam_anchor_candidates_sha256,
)
from .seam_anchor_candidates import SeamAnchorCandidates
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_errors import SeamAnchorReviewStoreError
from .seam_anchor_review_profile import CANDIDATE_NAMESPACE
from .seam_anchor_review_store_files import (
    SeamAnchorReviewFilesError,
    exact_payload,
    publication_parent,
    publish_document,
    read_document,
)


@dataclass(frozen=True, slots=True)
class PublishedSeamAnchorReviewCandidate:
    path: Path
    sha256: str
    reused: bool


def publish_seam_anchor_review_candidate(
    state_root: Path,
    address: ExactSeamAnchorReviewAddress,
    candidates: SeamAnchorCandidates,
) -> PublishedSeamAnchorReviewCandidate:
    """Publish only the candidate recompiled from this exact source address."""

    try:
        _require_value(address, candidates)
        document = candidates.document
        digest = seam_anchor_candidates_sha256(document)
        payload = exact_payload(candidates.canonical_bytes, document, digest)
        parent = publication_parent(
            state_root, address.project_id, CANDIDATE_NAMESPACE,
            address.p3_bundle_sha256,
        )
        path, reused = publish_document(parent, digest, payload)
        return PublishedSeamAnchorReviewCandidate(path, digest, reused)
    except SeamAnchorReviewStoreError:
        raise
    except _FAILURES as exc:
        raise SeamAnchorReviewStoreError(
            "Seam-review candidate publication failed"
        ) from exc


def reload_authoritative_seam_anchor_review_candidate(
    state_root: Path,
    address: ExactSeamAnchorReviewAddress,
    candidates: SeamAnchorCandidates,
) -> SeamAnchorCandidates:
    """Require stored bytes to equal a fresh exact-source compilation."""

    try:
        _require_value(address, candidates)
        digest = candidates.sha256
        payload = read_document(
            state_root, address.project_id, CANDIDATE_NAMESPACE,
            address.p3_bundle_sha256, digest,
        )
        document = strict_json_object(payload, "Seam-review candidate")
        require_seam_anchor_candidates(document)
        if seam_anchor_candidates_sha256(document) != digest \
                or payload != candidates.canonical_bytes:
            raise SeamAnchorReviewStoreError(
                "Stored seam-review candidate differs from exact replay"
            )
        return SeamAnchorCandidates(payload.decode("utf-8"))
    except SeamAnchorReviewStoreError:
        raise
    except _FAILURES as exc:
        raise SeamAnchorReviewStoreError(
            "Seam-review candidate reload failed"
        ) from exc


def _require_value(address, candidates) -> None:
    if type(address) is not ExactSeamAnchorReviewAddress \
            or type(candidates) is not SeamAnchorCandidates:
        raise SeamAnchorReviewStoreError(
            "Seam-review candidate storage requires exact value objects"
        )
    document = candidates.document
    require_seam_anchor_candidates(document)
    source = document["source"]
    if document["project_id"] != address.project_id \
            or source["layer_manifest_sha256"] \
                != address.layer_manifest_sha256 \
            or source["rig_sha256"] != address.p3_rig_sha256 \
            or source["bundle_sha256"] != address.p3_bundle_sha256:
        raise SeamAnchorReviewStoreError(
            "Seam-review candidate differs from its source address"
        )


_FAILURES = (
    AttributeError, KeyError, OSError, OverflowError, RecursionError,
    RuntimeError, SafeInputFileError, SeamAnchorCandidateValidationError,
    SeamAnchorReviewFilesError, TypeError, UnicodeError, ValueError,
)
