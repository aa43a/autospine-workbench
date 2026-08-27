"""Linear write-once revision slots for authoritative P10.5b decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import stat

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .safe_input_files import SafeInputFileError, strict_json_object
from .seam_anchor_candidates import SeamAnchorCandidates
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_candidate_store import (
    reload_authoritative_seam_anchor_review_candidate,
)
from .seam_anchor_review_decision import SeamAnchorReviewDecision
from .seam_anchor_review_decision_validation import (
    SeamAnchorReviewDecisionValidationError,
    require_seam_anchor_review_decision,
    seam_anchor_review_decision_sha256,
)
from .seam_anchor_review_errors import (
    SeamAnchorReviewHistoryError,
    SeamAnchorReviewRevisionConflict,
)
from .seam_anchor_review_profile import (
    DECISION_NAMESPACE,
    MAX_SEAM_ANCHOR_REVIEW_REVISIONS,
)
from .seam_anchor_review_store_files import (
    SeamAnchorReviewFilesError,
    exact_payload,
    exact_subdirectory,
    existing_parent,
    optional_existing_parent,
    publication_parent,
    publish_document,
    publish_named_document,
    read_named_document,
)
from .spine42_bundle_files import is_alias


_REVISION_NAME = re.compile(r"^r([0-9]{6,10})\.json$")


@dataclass(frozen=True, slots=True)
class PublishedSeamAnchorReviewDecision:
    path: Path
    sha256: str
    reused: bool


def publish_seam_anchor_review_decision(
    state_root: Path,
    address: ExactSeamAnchorReviewAddress,
    decision: SeamAnchorReviewDecision,
    candidates: SeamAnchorCandidates,
    rig: dict,
) -> PublishedSeamAnchorReviewDecision:
    """Append revision N only after replay of candidate and slots 1..N-1."""

    try:
        if type(decision) is not SeamAnchorReviewDecision:
            raise SeamAnchorReviewHistoryError(
                "Seam decision publication requires an exact value object"
            )
        candidate = reload_authoritative_seam_anchor_review_candidate(
            state_root, address, candidates
        )
        document = decision.document
        revision = document["review"]["revision"]
        digest = seam_anchor_review_decision_sha256(document)
        payload = exact_payload(decision.canonical_bytes, document, digest)
        parent = optional_existing_parent(
            state_root, address.project_id, DECISION_NAMESPACE,
            candidate.sha256,
        )
        chain = []
        if parent is not None:
            revisions = exact_subdirectory(parent, "revisions", create=False)
            chain = load_seam_anchor_review_chain(
                parent, revisions, candidate, rig
            )
        require_seam_anchor_review_decision(
            document, candidates=candidate.document, rig=rig
        )
        if revision <= len(chain):
            if chain[revision - 1].canonical_bytes != payload:
                raise _conflict(
                    "Seam-review revision slot is already owned",
                    document, chain,
                )
            path, _reused = publish_document(parent, digest, payload)
            return PublishedSeamAnchorReviewDecision(path, digest, True)
        if revision != len(chain) + 1:
            raise _conflict(
                "Seam-review revisions must be contiguous", document, chain
            )
        current_head = chain[-1].sha256 if chain else None
        if document["review"]["supersedes_decision_sha256"] != current_head:
            raise _conflict(
                "Seam-review predecessor is stale", document, chain
            )
        previous = chain[-1].document if chain else None
        require_seam_anchor_review_decision(
            document, candidates=candidate.document, rig=rig,
            previous_decision=previous,
        )
        if parent is None:
            parent = publication_parent(
                state_root, address.project_id, DECISION_NAMESPACE,
                candidate.sha256,
            )
            revisions = exact_subdirectory(parent, "revisions", create=True)
        path, _content_reused = publish_document(parent, digest, payload)
        try:
            _slot, slot_reused = publish_named_document(
                revisions, _revision_name(revision), payload,
                staging_parent=parent,
            )
        except SeamAnchorReviewFilesError as exc:
            current = load_seam_anchor_review_chain(
                parent, revisions, candidate, rig
            )
            raise _conflict(
                "Seam-review revision lost its concurrent slot",
                document, current,
            ) from exc
        verified = load_seam_anchor_review_chain(
            parent, revisions, candidate, rig
        )
        if len(verified) != revision \
                or verified[-1].canonical_bytes != payload:
            raise SeamAnchorReviewHistoryError(
                "Seam-review revision failed authoritative readback"
            )
        return PublishedSeamAnchorReviewDecision(path, digest, slot_reused)
    except (SeamAnchorReviewHistoryError, SeamAnchorReviewRevisionConflict):
        raise
    except _FAILURES as exc:
        raise SeamAnchorReviewHistoryError(
            "Seam-review history publication failed"
        ) from exc


def load_seam_anchor_review_decision(
    state_root: Path,
    address: ExactSeamAnchorReviewAddress,
    candidate_sha256: str,
    decision_sha256: str, *,
    candidates: SeamAnchorCandidates,
    rig: dict,
) -> SeamAnchorReviewDecision:
    """Replay the full chain and return one exact addressed revision."""

    try:
        candidate_address = require_sha256(
            candidate_sha256, "Seam-review candidate digest"
        )
        decision_address = require_sha256(
            decision_sha256, "Seam-review decision digest"
        )
        candidate = reload_authoritative_seam_anchor_review_candidate(
            state_root, address, candidates
        )
        if candidate.sha256 != candidate_address:
            raise SeamAnchorReviewHistoryError(
                "Seam decision address differs from exact candidate"
            )
        parent = existing_parent(
            state_root, address.project_id, DECISION_NAMESPACE,
            candidate_address,
        )
        revisions = exact_subdirectory(parent, "revisions", create=False)
        chain = load_seam_anchor_review_chain(
            parent, revisions, candidate, rig
        )
        matches = [item for item in chain if item.sha256 == decision_address]
        if len(matches) != 1:
            raise SeamAnchorReviewHistoryError(
                "Seam decision is not an authoritative revision slot"
            )
        return matches[0]
    except SeamAnchorReviewHistoryError:
        raise
    except _FAILURES as exc:
        raise SeamAnchorReviewHistoryError(
            "Seam-review history load failed"
        ) from exc


def load_seam_anchor_review_chain(
    parent: Path,
    revisions: Path,
    candidate: SeamAnchorCandidates,
    rig: dict,
) -> list[SeamAnchorReviewDecision]:
    names = _revision_inventory(revisions)
    chain, previous = [], None
    for revision, name in enumerate(names, start=1):
        payload = read_named_document(revisions, name)
        document = strict_json_object(payload, name)
        if document.get("review", {}).get("revision") != revision:
            raise SeamAnchorReviewHistoryError(
                "Seam-review slot revision is inconsistent"
            )
        require_seam_anchor_review_decision(
            document, candidates=candidate.document, rig=rig,
            previous_decision=previous.document if previous else None,
        )
        digest = seam_anchor_review_decision_sha256(document)
        if read_named_document(
            parent, f"{digest}.json", digest=digest
        ) != payload:
            raise SeamAnchorReviewHistoryError(
                "Seam revision differs from content-addressed decision"
            )
        previous = SeamAnchorReviewDecision(payload.decode("utf-8"))
        chain.append(previous)
    return chain


def _revision_inventory(directory: Path) -> tuple[str, ...]:
    try:
        children = list(directory.iterdir())
        if len(children) > MAX_SEAM_ANCHOR_REVIEW_REVISIONS:
            raise SeamAnchorReviewHistoryError(
                "Seam-review revision count exceeds its limit"
            )
        revisions = {}
        for child in children:
            match = _REVISION_NAME.fullmatch(child.name)
            if match is None or is_alias(child) \
                    or not stat.S_ISREG(child.lstat().st_mode):
                raise SeamAnchorReviewHistoryError(
                    "Seam-review revision inventory is unsafe"
                )
            number = int(match.group(1))
            if number in revisions or _revision_name(number) != child.name:
                raise SeamAnchorReviewHistoryError(
                    "Seam-review revision inventory is aliased"
                )
            revisions[number] = child.name
        expected = list(range(1, len(revisions) + 1))
        if sorted(revisions) != expected:
            raise SeamAnchorReviewHistoryError(
                "Seam-review revision inventory is not contiguous"
            )
        return tuple(revisions[number] for number in expected)
    except SeamAnchorReviewHistoryError:
        raise
    except OSError as exc:
        raise SeamAnchorReviewHistoryError(
            "Seam-review revision inventory cannot be inspected"
        ) from exc


def _revision_name(revision: int) -> str:
    if type(revision) is not int \
            or not 1 <= revision <= MAX_SEAM_ANCHOR_REVIEW_REVISIONS:
        raise SeamAnchorReviewHistoryError(
            "Seam-review revision is outside bounded history"
        )
    return f"r{revision:06d}.json"


def _conflict(message, document, chain):
    review = document.get("review", {})
    return SeamAnchorReviewRevisionConflict(
        message,
        requested_revision=review.get("revision"),
        current_revision=len(chain),
        requested_head=review.get("supersedes_decision_sha256"),
        current_head=chain[-1].sha256 if chain else None,
    )


_FAILURES = (
    AttributeError, KeyError, LayerManifestError, OSError, OverflowError,
    RuntimeError, SafeInputFileError,
    SeamAnchorReviewDecisionValidationError, SeamAnchorReviewFilesError,
    TypeError, UnicodeError, ValueError,
)
