"""Strict standalone validation for ReviewedSeamAnchorSet v1."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .resolved_project import canonical_sha256
from .seam_anchor_candidate_fields import (
    SeamAnchorCandidateFieldError,
    locator as require_locator,
)
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)
from .seam_anchor_review_profile import MAX_SEAM_ANCHOR_REVIEW_REVISIONS
from .reviewed_seam_anchor_set_profile import (
    CLAIMS,
    FORMAT,
    FORMAT_VERSION,
    MAX_DOCUMENT_BYTES,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    RELEASE_GATE,
    RELATIONSHIP_IDS,
    SEMANTICS,
    SOURCE_FIELDS,
    reviewed_seam_anchor_set_compiler_profile,
)


class ReviewedSeamAnchorSetValidationError(ValueError):
    """Raised when a reviewed static anchor set is ambiguous or overclaims."""


def require_reviewed_seam_anchor_set(document: Mapping[str, Any]) -> None:
    """Require the complete path-free ReviewedSeamAnchorSet v1 contract."""

    try:
        root = _object(document, "Reviewed seam anchor set")
        require_bounded_json_tree(
            root, max_nodes=MAX_JSON_NODES, max_depth=MAX_JSON_DEPTH
        )
        _exact(root, _TOP, "Reviewed seam anchor set")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise ReviewedSeamAnchorSetValidationError(
                "Reviewed seam anchor set format is unsupported"
            )
        require_safe_token(root.get("project_id"), "Reviewed seam project id")
        _source(root.get("source"))
        _fixed(
            root.get("compiler"),
            reviewed_seam_anchor_set_compiler_profile(),
            "compiler profile",
        )
        _fixed(root.get("semantics"), SEMANTICS, "semantics")
        anchor_count = _relationships(root.get("relationships"))
        if root.get("status") != "reviewed_static_anchor_set_compiled":
            raise ReviewedSeamAnchorSetValidationError(
                "Reviewed seam anchor set status is unsupported"
            )
        _fixed(root.get("claims"), CLAIMS, "claims")
        _fixed(root.get("release_gate"), RELEASE_GATE, "release gate")
        expected_summary = {
            "relationship_count": len(RELATIONSHIP_IDS),
            "anchor_pair_count": anchor_count,
        }
        if root.get("summary") != expected_summary:
            raise ReviewedSeamAnchorSetValidationError(
                "Reviewed seam anchor set summary is inconsistent"
            )
        if len(canonical_json_bytes(root)) > MAX_DOCUMENT_BYTES:
            raise ReviewedSeamAnchorSetValidationError(
                "Reviewed seam anchor set exceeds its byte limit"
            )
    except ReviewedSeamAnchorSetValidationError:
        raise
    except (
        KeyError, LayerManifestError, OverflowError, RecursionError,
        SeamAnchorCandidateFieldError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise ReviewedSeamAnchorSetValidationError(
            f"Reviewed seam anchor set validation failed: {exc}"
        ) from exc


def reviewed_seam_anchor_set_sha256(document: Mapping[str, Any]) -> str:
    """Return canonical identity only after standalone validation."""

    require_reviewed_seam_anchor_set(document)
    return canonical_sha256(document)


def _source(value: Any) -> None:
    source = _object(value, "Reviewed seam anchor source")
    _exact(source, set(SOURCE_FIELDS), "Reviewed seam anchor source")
    for field in SOURCE_FIELDS:
        if field == "review_revision":
            revision = source.get(field)
            if type(revision) is not int \
                    or not 1 <= revision <= MAX_SEAM_ANCHOR_REVIEW_REVISIONS:
                raise ReviewedSeamAnchorSetValidationError(
                    "Reviewed seam revision is invalid"
                )
        else:
            require_sha256(source.get(field), field)


def _relationships(value: Any) -> int:
    rows = [
        _object(row, "Reviewed seam relationship")
        for row in _array(value, "Reviewed seam relationships")
    ]
    if len(rows) != len(RELATIONSHIP_IDS) \
            or tuple(row.get("relationship_id") for row in rows) \
                != RELATIONSHIP_IDS:
        raise ReviewedSeamAnchorSetValidationError(
            "Reviewed seam relationships must use the fixed canonical order"
        )
    total = 0
    for row in rows:
        _exact(row, _RELATIONSHIP, "Reviewed seam relationship")
        require_safe_token(
            row.get("relationship_id"), "Reviewed seam relationship id"
        )
        total += _anchors(row.get("anchors"))
    return total


def _anchors(value: Any) -> int:
    rows = _array(value, "Reviewed seam anchors")
    if not 2 <= len(rows) <= 8:
        raise ReviewedSeamAnchorSetValidationError(
            "Reviewed seam anchors must contain two to eight pairs"
        )
    parent_identity = child_identity = None
    parent_keys, child_keys = set(), set()
    for index, row in enumerate(rows):
        _exact(row, _ANCHOR, "Reviewed seam anchor pair")
        if row.get("pair_id") != f"anchor.{index:03d}":
            raise ReviewedSeamAnchorSetValidationError(
                "Reviewed seam pair ids differ from canonical order"
            )
        parent_identity = _endpoint(
            row.get("parent"), parent_identity, "parent", parent_keys
        )
        child_identity = _endpoint(
            row.get("child"), child_identity, "child", child_keys
        )
    if parent_identity == child_identity:
        raise ReviewedSeamAnchorSetValidationError(
            "Reviewed seam endpoints must bind different attachments"
        )
    return len(rows)


def _endpoint(value, expected, label, seen):
    locator = _object(value, f"Reviewed seam {label} locator")
    identifier = locator.get("attachment_id")
    kind = locator.get("attachment_type")
    require_locator(locator, identifier, kind)
    identity = identifier, kind
    if expected is not None and identity != expected:
        raise ReviewedSeamAnchorSetValidationError(
            f"Reviewed seam {label} attachment identity changes within a row"
        )
    digest = canonical_sha256(locator)
    if digest in seen:
        raise ReviewedSeamAnchorSetValidationError(
            f"Reviewed seam {label} locators must be unique"
        )
    seen.add(digest)
    return identity


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ReviewedSeamAnchorSetValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ReviewedSeamAnchorSetValidationError(f"{label} must be an array")
    return value


def _exact(value: Any, fields: set[str], label: str) -> None:
    row = _object(value, label)
    if set(row) != fields:
        raise ReviewedSeamAnchorSetValidationError(
            f"{label} fields are unsupported"
        )


def _fixed(value: Any, expected: Any, label: str) -> None:
    if value != expected or type(value) is not type(expected):
        raise ReviewedSeamAnchorSetValidationError(
            f"Reviewed seam anchor set {label} is unsupported"
        )


_TOP = {
    "format", "format_version", "project_id", "source", "compiler",
    "semantics", "relationships", "status", "claims", "release_gate",
    "summary",
}
_RELATIONSHIP = {"relationship_id", "anchors"}
_ANCHOR = {"pair_id", "parent", "child"}
