"""Detached exact-identity and compile-time head checks for P10.5c."""

from __future__ import annotations

from .manifest_artifacts import LayerManifestError, require_sha256
from .resolved_project import canonical_sha256
from .reviewed_seam_anchor_set_binding_validation import (
    ReviewedSeamAnchorSetBindingValidationError,
    require_ready_seam_anchor_review,
)
from .reviewed_seam_anchor_set_profile import REQUIRED_DECISION_STATUS
from .seam_anchor_candidate_validation import (
    SeamAnchorCandidateValidationError,
    require_seam_anchor_candidates,
    seam_anchor_candidates_sha256,
)
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_application_models import (
    ExactSeamAnchorReviewDecision,
    PreparedSeamAnchorReview,
)
from .seam_anchor_review_decision_validation import (
    SeamAnchorReviewDecisionValidationError,
    require_seam_anchor_review_decision,
    seam_anchor_review_decision_sha256,
)
from .seam_anchor_review_history_models import (
    SeamAnchorReviewHistoryRow,
    SeamAnchorReviewHistorySnapshot,
)
from .seam_anchor_review_json import canonical_json_bytes
from .seam_anchor_review_profile import MAX_SEAM_ANCHOR_REVIEW_REVISIONS


class ReviewedSeamAnchorSetInputCheckError(ValueError):
    """Raised when detached review inputs are stale or cross-wired."""


def require_current_ready_seam_anchor_snapshot(
    prepared: PreparedSeamAnchorReview,
    address: ExactSeamAnchorReviewAddress,
    candidate_sha256: str,
    revision: int,
    decision_sha256: str,
) -> None:
    """Require the requested ready decision to be this snapshot's head."""

    candidate_sha, decision_sha = _explicit_identity(
        candidate_sha256, revision, decision_sha256
    )
    if type(prepared) is not PreparedSeamAnchorReview \
            or prepared.address != address \
            or prepared.candidate_sha256 != candidate_sha:
        raise ReviewedSeamAnchorSetInputCheckError(
            "Seam-review snapshot differs from its exact address"
        )
    candidate = prepared.candidate_document
    require_seam_anchor_candidates(candidate)
    if seam_anchor_candidates_sha256(candidate) != candidate_sha \
            or canonical_json_bytes(candidate).decode("utf-8") \
                != prepared._candidate_json \
            or not _candidate_matches_address(candidate, address):
        raise ReviewedSeamAnchorSetInputCheckError(
            "Seam-review snapshot candidate is cross-wired"
        )
    _require_ready_head(
        prepared.history, address, candidate_sha, revision, decision_sha
    )


def require_exact_seam_anchor_decision(
    exact: ExactSeamAnchorReviewDecision,
    address: ExactSeamAnchorReviewAddress,
    candidate_sha256: str,
    revision: int,
    decision_sha256: str,
    *,
    history: SeamAnchorReviewHistorySnapshot | None = None,
) -> None:
    """Validate the path-free exact-decision application value."""

    candidate_sha, decision_sha = _explicit_identity(
        candidate_sha256, revision, decision_sha256
    )
    if type(exact) is not ExactSeamAnchorReviewDecision \
            or exact.address != address \
            or exact.candidate_sha256 != candidate_sha \
            or exact.revision != revision \
            or exact.decision_sha256 != decision_sha:
        raise ReviewedSeamAnchorSetInputCheckError(
            "Exact seam decision differs from its requested address"
        )
    decision = exact.decision_document
    require_seam_anchor_review_decision(decision)
    if seam_anchor_review_decision_sha256(decision) != decision_sha \
            or canonical_json_bytes(decision).decode("utf-8") \
                != exact._decision_json \
            or decision["review"]["revision"] != revision \
            or decision["status"] != REQUIRED_DECISION_STATUS:
        raise ReviewedSeamAnchorSetInputCheckError(
            "Exact seam decision is not the requested ready decision"
        )
    if history is not None:
        _require_ready_head(
            history, address, candidate_sha, revision, decision_sha,
            decision=decision,
        )


def require_reviewed_seam_anchor_set_input_content(value) -> None:
    """Revalidate frozen candidate, decision, rig, and stable snapshots."""

    candidate_sha, decision_sha = _explicit_identity(
        value.candidate_sha256, value.review_revision,
        value.decision_sha256,
    )
    candidate = value.candidate_document
    decision = value.decision_document
    rig = value.rig_document
    require_seam_anchor_candidates(candidate)
    require_seam_anchor_review_decision(
        decision, candidates=candidate, rig=rig
    )
    require_ready_seam_anchor_review(candidate, decision, rig)
    if canonical_json_bytes(candidate).decode("utf-8") \
            != value._candidate_json \
            or canonical_json_bytes(decision).decode("utf-8") \
                != value._decision_json \
            or canonical_json_bytes(rig).decode("utf-8") != value._rig_json:
        raise ReviewedSeamAnchorSetInputCheckError(
            "Reviewed seam input bytes are not canonical"
        )
    if seam_anchor_candidates_sha256(candidate) != candidate_sha \
            or seam_anchor_review_decision_sha256(decision) != decision_sha \
            or canonical_sha256(rig) != value.address.p3_rig_sha256 \
            or not _candidate_matches_address(candidate, value.address) \
            or decision["review"]["revision"] != value.review_revision:
        raise ReviewedSeamAnchorSetInputCheckError(
            "Reviewed seam input identities are cross-wired"
        )
    before, after = value.history_before, value.history_after
    if before != after:
        raise ReviewedSeamAnchorSetInputCheckError(
            "Seam-review head changed during compile-time observation"
        )
    _require_ready_head(
        before, value.address, candidate_sha,
        value.review_revision, decision_sha, decision=decision,
    )


def _explicit_identity(candidate_sha, revision, decision_sha):
    try:
        candidate = require_sha256(candidate_sha, "Seam candidate digest")
        decision = require_sha256(decision_sha, "Seam decision digest")
        if type(revision) is not int \
                or not 1 <= revision <= MAX_SEAM_ANCHOR_REVIEW_REVISIONS:
            raise ReviewedSeamAnchorSetInputCheckError(
                "Seam decision revision is invalid"
            )
        return candidate, decision
    except ReviewedSeamAnchorSetInputCheckError:
        raise
    except LayerManifestError as exc:
        raise ReviewedSeamAnchorSetInputCheckError(
            "Seam review identity is invalid"
        ) from exc


def _candidate_matches_address(candidate, address) -> bool:
    source = candidate["source"]
    return type(address) is ExactSeamAnchorReviewAddress \
        and candidate["project_id"] == address.project_id \
        and source["layer_manifest_sha256"] \
            == address.layer_manifest_sha256 \
        and source["rig_sha256"] == address.p3_rig_sha256 \
        and source["bundle_sha256"] == address.p3_bundle_sha256


def _require_ready_head(
    history, address, candidate_sha, revision, decision_sha, *, decision=None,
):
    rows = history.rows if type(history) is SeamAnchorReviewHistorySnapshot \
        and type(history.rows) is tuple else ()
    ordered = _valid_history_rows(rows)
    expected_predecessor = None if revision == 1 \
        else rows[-2].decision_sha256 if len(rows) >= 2 else object()
    predecessor_matches = decision is None or (
        type(decision) is dict
        and decision.get("review", {}).get("supersedes_decision_sha256")
            == expected_predecessor
    )
    if type(history) is not SeamAnchorReviewHistorySnapshot \
            or history.project_id != address.project_id \
            or history.candidate_sha256 != candidate_sha \
            or type(history.revision_count) is not int \
            or type(history.current_revision) is not int \
            or history.revision_count != len(rows) \
            or history.current_revision != revision \
            or history.revision_count != revision \
            or history.head_decision_sha256 != decision_sha \
            or not ordered or not rows \
            or rows[-1].decision_sha256 != decision_sha \
            or rows[-1].status != REQUIRED_DECISION_STATUS \
            or not predecessor_matches:
        raise ReviewedSeamAnchorSetInputCheckError(
            "Only the current ready seam-review head is admissible"
        )


def _valid_history_rows(rows) -> bool:
    statuses = {
        REQUIRED_DECISION_STATUS, "reviewed_anchor_set_blocked",
    }
    for index, row in enumerate(rows, 1):
        if type(row) is not SeamAnchorReviewHistoryRow \
                or type(row.revision) is not int \
                or row.revision != index \
                or type(row.status) is not str \
                or row.status not in statuses:
            return False
        try:
            require_sha256(row.decision_sha256, "Seam history decision digest")
        except LayerManifestError:
            return False
    return True


INPUT_CHECK_FAILURES = (
    AttributeError, KeyError, LayerManifestError, OverflowError,
    RecursionError, ReviewedSeamAnchorSetBindingValidationError,
    SeamAnchorCandidateValidationError,
    SeamAnchorReviewDecisionValidationError, TypeError, UnicodeError,
    ValueError,
)
