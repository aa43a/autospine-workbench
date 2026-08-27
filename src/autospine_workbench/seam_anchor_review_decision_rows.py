"""Bounded row and anchor-shape validation for P10.5b decisions."""

from __future__ import annotations

from typing import Any

from .limb_contact_roles import CONTACT_RELATIONS, SIDES
from .manifest_artifacts import require_safe_token, require_sha256
from .seam_anchor_candidate_fields import locator as require_locator
from .seam_anchor_review_profile import MAX_RELATIONSHIP_NOTES_LENGTH


def require_seam_anchor_review_decision_rows(
    value: Any,
) -> dict[str, int]:
    """Validate the exhaustive six-row decision matrix and return counts."""

    if type(value) is not list or len(value) != 6:
        raise ValueError("Seam-review decisions must contain six rows")
    if any(type(raw) is not dict for raw in value) \
            or tuple(raw.get("relationship_id") for raw in value) \
                != _RELATIONSHIP_IDS:
        raise ValueError(
            "Seam-review decisions must follow the fixed relationship order"
        )
    counts = {name: 0 for name in (
        "accept", "adjust", "reject", "unobservable"
    )}
    anchor_count = 0
    identifiers = set()
    for raw in value:
        identifier, action, row_anchors = _decision_row(raw, counts)
        counts[action] += 1
        anchor_count += row_anchors
        identifiers.add(identifier)
    if len(identifiers) != 6:
        raise ValueError("Seam-review relationship ids must be unique")
    counts["decision"] = 6
    counts["anchors"] = anchor_count
    return counts


def _decision_row(raw: Any, actions: dict[str, int]) -> tuple[str, str, int]:
    if type(raw) is not dict or set(raw) != _DECISION_FIELDS:
        raise ValueError("Seam-review decision row fields are unsupported")
    identifier = require_safe_token(
        raw.get("relationship_id"), "Seam relationship id"
    )
    require_sha256(
        raw.get("relationship_evidence_sha256"),
        "Seam relationship evidence digest",
    )
    action, notes = raw.get("action"), raw.get("notes")
    if action not in actions or type(notes) is not str \
            or len(notes) > MAX_RELATIONSHIP_NOTES_LENGTH \
            or action != "accept" and not notes.strip():
        raise ValueError("Seam-review relationship action or notes are invalid")
    option_id = raw.get("option_id")
    option_sha = raw.get("option_evidence_sha256")
    if (option_id is None) != (option_sha is None):
        raise ValueError("Seam-review option identity is incomplete")
    if option_id is not None:
        require_safe_token(option_id, "Seam option id")
        require_sha256(option_sha, "Seam option evidence digest")
    anchor_count = _anchors(raw.get("anchors"), action)
    if action in {"accept", "adjust"} and option_id is None:
        raise ValueError("Resolved seam choice requires option evidence")
    return identifier, action, anchor_count


def _anchors(value: Any, action: str) -> int:
    if type(value) is not list \
            or (action in {"accept", "adjust"} and not 2 <= len(value) <= 8) \
            or (action not in {"accept", "adjust"} and value):
        raise ValueError("Seam-review anchors differ from relationship action")
    for index, raw in enumerate(value):
        if type(raw) is not dict or set(raw) != {"pair_id", "parent", "child"} \
                or raw.get("pair_id") != f"anchor.{index:03d}":
            raise ValueError("Seam-review anchor pair fields are invalid")
        for endpoint in ("parent", "child"):
            locator = raw[endpoint]
            if type(locator) is not dict:
                raise ValueError("Seam-review locator must be an object")
            require_locator(
                locator, locator.get("attachment_id"),
                locator.get("attachment_type"),
            )
    return len(value)


_DECISION_FIELDS = {
    "relationship_id", "relationship_evidence_sha256", "action",
    "option_id", "option_evidence_sha256", "notes", "anchors",
}
_RELATIONSHIP_IDS = tuple(
    f"seam.{relation}.{side}"
    for relation, _parent, _child, _joint in CONTACT_RELATIONS
    for side in SIDES
)
