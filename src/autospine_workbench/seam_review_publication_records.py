"""Immutable idempotency records for successful P10.5c publications."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .safe_input_files import SafeInputFileError, strict_json_object
from .seam_anchor_review_json import canonical_json_bytes
from .seam_anchor_review_store_files import (
    SeamAnchorReviewFilesError,
    optional_existing_parent,
    publication_parent,
    publish_named_document,
    read_named_document,
)
from .spine42_bundle_files import (
    Spine42BundleFilesError,
    existing_exact_child,
)


NAMESPACE = "seam-review-publication-records"
RECORD_FORMAT = "autospine-seam-review-publication-record"
FORMAT_VERSION = 1
_FIELDS = {
    "format", "format_version", "request_sha256", "request", "receipt",
}


class SeamReviewPublicationRecordError(RuntimeError):
    """Raised when an immutable publication record cannot be trusted."""


def load_seam_review_publication_record(
    state_root: Path,
    project_id: str,
    package_id: str,
    request: dict[str, Any],
) -> dict[str, Any] | None:
    """Read one exact request record without scanning for a latest result."""

    try:
        request_sha = _request_sha256(request)
        parent = optional_existing_parent(
            state_root, project_id, NAMESPACE, package_id,
        )
        name = f"{request_sha}.json"
        if parent is None or existing_exact_child(parent, name) is None:
            return None
        document = strict_json_object(
            read_named_document(parent, name), "Seam publication record",
        )
        return _require_record(document, request, request_sha)
    except SeamReviewPublicationRecordError:
        raise
    except _FILESYSTEM_ERRORS as exc:
        raise SeamReviewPublicationRecordError(
            "Seam publication record could not be read safely"
        ) from exc


def publish_seam_review_publication_record(
    state_root: Path,
    project_id: str,
    package_id: str,
    request: dict[str, Any],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Atomically append and read back one successful exact request receipt."""

    try:
        request_sha = _request_sha256(request)
        document = {
            "format": RECORD_FORMAT,
            "format_version": FORMAT_VERSION,
            "request_sha256": request_sha,
            "request": request,
            "receipt": receipt,
        }
        _require_record(document, request, request_sha)
        payload = canonical_json_bytes(document)
        parent = publication_parent(
            state_root, project_id, NAMESPACE, package_id,
        )
        publish_named_document(parent, f"{request_sha}.json", payload)
        loaded = load_seam_review_publication_record(
            state_root, project_id, package_id, request,
        )
        if loaded != receipt:
            raise SeamReviewPublicationRecordError(
                "Published seam publication record differs on readback"
            )
        return loaded
    except SeamReviewPublicationRecordError:
        raise
    except _FILESYSTEM_ERRORS as exc:
        raise SeamReviewPublicationRecordError(
            "Seam publication record could not be published safely"
        ) from exc


def _request_sha256(request: dict[str, Any]) -> str:
    if type(request) is not dict:
        raise SeamReviewPublicationRecordError(
            "Seam publication record request is invalid"
        )
    try:
        return hashlib.sha256(canonical_json_bytes(request)).hexdigest()
    except (OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise SeamReviewPublicationRecordError(
            "Seam publication record request is invalid"
        ) from exc


def _require_record(document, request, request_sha):
    if type(document) is not dict or set(document) != _FIELDS \
            or document.get("format") != RECORD_FORMAT \
            or type(document.get("format_version")) is not int \
            or document.get("format_version") != FORMAT_VERSION \
            or document.get("request_sha256") != request_sha \
            or document.get("request") != request \
            or type(document.get("receipt")) is not dict:
        raise SeamReviewPublicationRecordError(
            "Seam publication record identity is invalid"
        )
    return document["receipt"]


_FILESYSTEM_ERRORS = (
    OSError,
    OverflowError,
    RecursionError,
    RuntimeError,
    SafeInputFileError,
    SeamAnchorReviewFilesError,
    Spine42BundleFilesError,
    TypeError,
    UnicodeError,
    ValueError,
)
