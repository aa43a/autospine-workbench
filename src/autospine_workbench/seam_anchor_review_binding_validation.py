"""Candidate/P3-bound materialization for human seam-anchor choices."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

from .resolved_project import canonical_sha256
from .seam_anchor_candidate_validation import (
    SeamAnchorCandidateValidationError,
    require_seam_anchor_candidates,
)
from .seam_anchor_pair_validation import (
    SeamAnchorLocatorError,
    validate_anchor_pairs,
)


class SeamAnchorReviewBindingValidationError(ValueError):
    """Raised when human choices cross-wire candidate or P3 evidence."""


def materialize_seam_anchor_review_rows(
    candidates: Mapping[str, Any],
    rig: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Bind exhaustive submitted rows and derive all authoritative anchors."""

    try:
        require_seam_anchor_candidates(candidates)
        attachments = _attachment_index(candidates, rig)
        if type(decisions) not in (list, tuple) or len(decisions) != 6:
            raise SeamAnchorReviewBindingValidationError(
                "Seam decisions must cover the fixed six relationships"
            )
        rows = []
        for relationship, submitted in zip(
            candidates["relationships"], decisions, strict=True
        ):
            rows.append(_materialize(relationship, submitted, attachments))
        return tuple(rows)
    except SeamAnchorReviewBindingValidationError:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        SeamAnchorCandidateValidationError, SeamAnchorLocatorError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise SeamAnchorReviewBindingValidationError(
            f"Seam-review candidate binding failed: {exc}"
        ) from exc


def require_materialized_seam_anchor_review_rows(
    candidates: Mapping[str, Any],
    rig: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
) -> None:
    """Rebuild stored rows from their human projection and compare exactly."""

    submitted = []
    for raw in decisions:
        if type(raw) is not dict:
            raise SeamAnchorReviewBindingValidationError(
                "Stored seam decision row must be an object"
            )
        row = {key: _copy(raw[key]) for key in _SUBMITTED_FIELDS}
        if raw.get("action") == "adjust":
            row["final_anchors"] = _copy(raw.get("anchors"))
        submitted.append(row)
    expected = materialize_seam_anchor_review_rows(
        candidates, rig, submitted
    )
    if list(expected) != decisions:
        raise SeamAnchorReviewBindingValidationError(
            "Stored seam decisions differ from candidate-bound materialization"
        )


def _materialize(relationship, submitted, attachments):
    if type(submitted) is not dict:
        raise SeamAnchorReviewBindingValidationError(
            "Submitted seam decision row must be an object"
        )
    identifier = relationship["relationship_id"]
    if submitted.get("relationship_id") != identifier \
            or submitted.get("relationship_evidence_sha256") \
                != relationship["evidence_sha256"]:
        raise SeamAnchorReviewBindingValidationError(
            "Seam decision relationship evidence is stale or reordered"
        )
    action = submitted.get("action")
    if relationship["status"] == "unobservable":
        if action != "unobservable" \
                or submitted.get("option_id") is not None \
                or submitted.get("option_evidence_sha256") is not None:
            raise SeamAnchorReviewBindingValidationError(
                "Unobservable candidate relationship cannot select an option"
            )
        option, anchors = None, []
    else:
        if action not in {"accept", "adjust", "reject", "unobservable"}:
            raise SeamAnchorReviewBindingValidationError(
                "Review-required seam relationship action is unsupported"
            )
        matches = [
            option for option in relationship["options"]
            if option["option_id"] == submitted.get("option_id")
            and option["evidence_sha256"]
                == submitted.get("option_evidence_sha256")
        ]
        if len(matches) != 1 or matches[0]["status"] != "candidate":
            raise SeamAnchorReviewBindingValidationError(
                "Seam decision option evidence is stale or unavailable"
            )
        option = matches[0]
        anchors = (
            _copy(option["anchors"]) if action == "accept"
            else _copy(submitted.get("final_anchors"))
            if action == "adjust" else []
        )
        if action in {"accept", "adjust"}:
            _validate_anchors(anchors, option, attachments)
    return {
        "relationship_id": identifier,
        "relationship_evidence_sha256": relationship["evidence_sha256"],
        "action": action,
        "option_id": None if option is None else option["option_id"],
        "option_evidence_sha256": (
            None if option is None else option["evidence_sha256"]
        ),
        "notes": submitted.get("notes"),
        "anchors": anchors,
    }


def _validate_anchors(anchors, option, attachments):
    if type(anchors) is not list or not 2 <= len(anchors) <= 8:
        raise SeamAnchorReviewBindingValidationError(
            "Resolved seam anchors must contain two to eight pairs"
        )
    converted = []
    for index, raw in enumerate(anchors):
        if type(raw) is not dict or set(raw) != {"pair_id", "parent", "child"} \
                or raw.get("pair_id") != f"anchor.{index:03d}":
            raise SeamAnchorReviewBindingValidationError(
                "Resolved seam anchor pair fields are invalid"
            )
        converted.append({
            "pair_id": raw["pair_id"],
            "a": raw["parent"],
            "b": raw["child"],
        })
    parent = attachments.get(option["parent_attachment_id"])
    child = attachments.get(option["child_attachment_id"])
    if parent is None or child is None \
            or parent.get("type") != option["parent_attachment_type"] \
            or child.get("type") != option["child_attachment_type"]:
        raise SeamAnchorReviewBindingValidationError(
            "Seam option attachment evidence differs from P3"
        )
    validate_anchor_pairs(
        converted, parent, child, principal_axis=option["principal_axis"]
    )


def _attachment_index(candidates, rig):
    if type(rig) is not dict or canonical_sha256(rig) \
            != candidates["source"]["rig_sha256"]:
        raise SeamAnchorReviewBindingValidationError(
            "Seam review P3 RigIR differs from candidate source"
        )
    rows = rig.get("attachments")
    if type(rows) is not list or len(rows) > 4096:
        raise SeamAnchorReviewBindingValidationError(
            "Seam review P3 attachment inventory is invalid"
        )
    result = {}
    for row in rows:
        if type(row) is not dict or type(row.get("id")) is not str \
                or row["id"] in result:
            raise SeamAnchorReviewBindingValidationError(
                "Seam review P3 attachment inventory is invalid"
            )
        result[row["id"]] = row
    return result


def _copy(value):
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_SUBMITTED_FIELDS = {
    "relationship_id", "relationship_evidence_sha256", "action",
    "option_id", "option_evidence_sha256", "notes",
}
