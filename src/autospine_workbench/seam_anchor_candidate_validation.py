"""Strict standalone validator for review-only static seam candidates."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .resolved_project import canonical_sha256
from .seam_anchor_candidate_fields import (
    SeamAnchorCandidateFieldError,
    array_value as _array,
    contact_evidence as _contact,
    digest as _digest,
    evidence_seal as _sealed,
    exact_fields as _exact,
    fixed_object as _fixed,
    identifier as _identifier,
    locator as _locator,
    object_value as _object,
    reasons as _reasons,
)
from .seam_anchor_candidate_profile import (
    CLAIMS,
    CONTACT_MAX_GAP_PX,
    FORMAT,
    FORMAT_VERSION,
    MAX_DOCUMENT_BYTES,
    MAX_OPTIONS_PER_RELATION,
    MAX_TOTAL_OPTIONS,
    RELEASE_GATE,
    SEMANTICS,
    RELATIONSHIP_PROFILE,
    candidate_generator_profile,
    option_evidence_sha256,
    relationship_evidence_sha256,
)
from .seam_anchor_candidate_policy import (
    SeamAnchorCandidatePolicyError,
    require_option_policy,
    require_relationship_policy,
)
from .seam_anchor_profile import SEAM_SOURCE_IDENTITY_FIELDS
from .seam_anchor_sampling import MAX_ANCHOR_PAIRS


_TOP = {
    "format", "format_version", "project_id", "source", "generator",
    "semantics", "relationships", "claims", "release_gate", "summary",
}
_RELATIONSHIP = {
    "relationship_id", "relation", "joint", "side", "status",
    "reason_codes", "options", "evidence_sha256",
}
_OPTION = {
    "option_id", "parent_attachment_id", "child_attachment_id",
    "parent_attachment_type", "child_attachment_type", "status",
    "reason_codes", "contact_evidence", "principal_axis",
    "sampling_profile", "anchors", "evidence_sha256",
}
_ANCHOR = {"pair_id", "parent", "child"}
_SUMMARY = {
    "status", "relationship_count", "review_required_count",
    "unobservable_count", "option_count", "candidate_option_count",
    "unavailable_option_count", "anchor_pair_count",
}


class SeamAnchorCandidateValidationError(ValueError):
    """Raised when a SeamAnchorCandidates v1 document is not canonical."""


def require_seam_anchor_candidates(document: Mapping[str, Any]) -> None:
    """Require the complete path-free SeamAnchorCandidates v1 contract."""

    try:
        root = _object(document, "Seam anchor candidates")
        _exact(root, _TOP, "Seam anchor candidates")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise SeamAnchorCandidateValidationError(
                "Seam anchor candidate format is unsupported"
            )
        _identifier(root.get("project_id"), "project_id")
        _source(root.get("source"))
        _fixed(
            root.get("generator"), candidate_generator_profile(),
            "generator",
        )
        _fixed(root.get("semantics"), SEMANTICS, "semantics")
        counts = _relationships(root.get("relationships"))
        _fixed(root.get("claims"), CLAIMS, "claims")
        _fixed(root.get("release_gate"), RELEASE_GATE, "release gate")
        _summary(root.get("summary"), counts)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise SeamAnchorCandidateValidationError(
                "Seam anchor candidate byte limit exceeded"
            )
    except SeamAnchorCandidateValidationError:
        raise
    except (
        KeyError, OverflowError, RecursionError,
        SeamAnchorCandidateFieldError, SeamAnchorCandidatePolicyError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise SeamAnchorCandidateValidationError(
            f"Seam anchor candidate validation failed: {exc}"
        ) from exc


def seam_anchor_candidates_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical digest only after standalone validation."""

    require_seam_anchor_candidates(document)
    return canonical_sha256(document)


def _source(value: Any) -> None:
    source = _object(value, "Seam anchor candidate source")
    expected = set(SEAM_SOURCE_IDENTITY_FIELDS)
    _exact(source, expected, "Seam anchor candidate source")
    for field in SEAM_SOURCE_IDENTITY_FIELDS:
        _digest(source.get(field), field)


def _relationships(value: Any) -> dict[str, int]:
    rows = _array(value, "Seam relationships", maximum=len(RELATIONSHIP_PROFILE))
    if len(rows) != len(RELATIONSHIP_PROFILE):
        raise SeamAnchorCandidateValidationError(
            "Seam relationships must contain the fixed six rows"
        )
    totals = {
        "review_required_count": 0, "unobservable_count": 0,
        "option_count": 0, "candidate_option_count": 0,
        "unavailable_option_count": 0, "anchor_pair_count": 0,
    }
    for expected, raw in zip(RELATIONSHIP_PROFILE, rows, strict=True):
        row = _object(raw, "Seam relationship")
        _exact(row, _RELATIONSHIP, "Seam relationship")
        if tuple(row.get(field) for field in (
            "relationship_id", "relation", "joint", "side",
        )) != expected:
            raise SeamAnchorCandidateValidationError(
                "Seam relationships are not the fixed canonical rows"
            )
        reasons = _reasons(row.get("reason_codes"), "relationship reasons")
        option_counts, option_reasons, option_pairs = _options(
            row.get("options"), expected[0]
        )
        expected_status = (
            "review_required" if option_counts["candidate_option_count"]
            else "unobservable"
        )
        if row.get("status") != expected_status \
                or (expected_status == "unobservable" and not reasons):
            raise SeamAnchorCandidateValidationError(
                "Seam relationship status or reasons differ from its options"
            )
        require_relationship_policy(reasons, option_reasons, option_pairs)
        _sealed(row, "evidence_sha256", relationship_evidence_sha256,
                "relationship")
        totals[f"{expected_status}_count"] += 1
        for field, count in option_counts.items():
            totals[field] += count
    if totals["option_count"] > MAX_TOTAL_OPTIONS:
        raise SeamAnchorCandidateValidationError(
            "Seam anchor candidate total option limit exceeded"
        )
    return totals


def _options(value: Any, relationship_id: str):
    rows = _array(value, "Seam options", maximum=MAX_OPTIONS_PER_RELATION)
    counts = {
        "option_count": len(rows), "candidate_option_count": 0,
        "unavailable_option_count": 0, "anchor_pair_count": 0,
    }
    keys, option_reasons, option_pairs = [], set(), set()
    for index, raw in enumerate(rows):
        row = _object(raw, "Seam option")
        _exact(row, _OPTION, "Seam option")
        expected_id = f"{relationship_id}.option.{index:03d}"
        if row.get("option_id") != expected_id:
            raise SeamAnchorCandidateValidationError(
                "Seam option ids do not match canonical array order"
            )
        parent = _identifier(row.get("parent_attachment_id"),
                             "parent attachment id")
        child = _identifier(row.get("child_attachment_id"),
                            "child attachment id")
        if parent == child:
            raise SeamAnchorCandidateValidationError(
                "A seam option must bind two different attachments"
            )
        kinds = row.get("parent_attachment_type"), row.get("child_attachment_type")
        if any(kind not in ("region", "mesh") for kind in kinds):
            raise SeamAnchorCandidateValidationError(
                "Seam option attachment type is unsupported"
            )
        mode = None if row.get("contact_evidence") is None else _contact(
            row["contact_evidence"], max_gap=CONTACT_MAX_GAP_PX
        )
        keys.append((parent, child, "" if mode is None else
                     row["contact_evidence"]["contact_id"]))
        anchors = _anchors(row.get("anchors"), parent, child, kinds)
        option_reasons.update(require_option_policy(
            row, kinds, mode, len(anchors)
        ))
        option_pairs.add((parent, child))
        _sealed(row, "evidence_sha256", option_evidence_sha256, "option")
        counts[f"{row['status']}_option_count"] += 1
        counts["anchor_pair_count"] += len(anchors)
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise SeamAnchorCandidateValidationError(
            "Seam options are not in unique canonical evidence order"
        )
    return counts, option_reasons, option_pairs


def _anchors(value, parent, child, kinds) -> tuple[Mapping[str, Any], ...]:
    rows = _array(value, "Seam anchors", maximum=MAX_ANCHOR_PAIRS)
    parent_keys, child_keys = set(), set()
    for index, raw in enumerate(rows):
        row = _object(raw, "Seam anchor pair")
        _exact(row, _ANCHOR, "Seam anchor pair")
        if row.get("pair_id") != f"anchor.{index:03d}":
            raise SeamAnchorCandidateValidationError(
                "Seam anchor pair ids do not match canonical array order"
            )
        _locator(row.get("parent"), parent, kinds[0])
        _locator(row.get("child"), child, kinds[1])
        parent_key = canonical_sha256(row["parent"])
        child_key = canonical_sha256(row["child"])
        if parent_key in parent_keys or child_key in child_keys:
            raise SeamAnchorCandidateValidationError(
                "Seam anchor endpoints must be unique on both attachments"
            )
        parent_keys.add(parent_key)
        child_keys.add(child_key)
    return tuple(rows)


def _summary(value: Any, counts: Mapping[str, int]) -> None:
    row = _object(value, "Seam anchor candidate summary")
    _exact(row, _SUMMARY, "Seam anchor candidate summary")
    expected = {
        "status": "manual_review_required",
        "relationship_count": len(RELATIONSHIP_PROFILE), **dict(counts),
    }
    if row != expected or any(
        type(row.get(field)) is not int for field in _SUMMARY - {"status"}
    ):
        raise SeamAnchorCandidateValidationError(
            "Seam anchor candidate summary differs from its rows"
        )
