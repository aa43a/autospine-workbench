"""Linear write-once revision slots for authoritative P10.3c decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import stat

from .body_sway_runtime_capture_reader import VerifiedBodySwayRuntimeCapture
from .body_sway_visual_review_binding import (
    BodySwayVisualReviewBindingError,
    reload_authoritative_visual_review_candidate,
)
from .body_sway_visual_review_candidate import BodySwayVisualReviewCandidate
from .body_sway_visual_review_decision import BodySwayVisualReviewDecision
from .body_sway_visual_review_decision_validation import (
    BodySwayVisualReviewDecisionValidationError,
    body_sway_visual_review_decision_sha256,
    require_body_sway_visual_review_decision,
)
from .body_sway_visual_review_profile import (
    DECISION_NAMESPACE,
    MAX_VISUAL_REVIEW_REVISIONS,
)
from .body_sway_visual_review_store_files import (
    BodySwayVisualReviewFilesError,
    exact_payload,
    exact_subdirectory,
    existing_parent,
    publication_parent,
    publish_document,
    publish_named_document,
    read_named_document,
)
from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_bundle_files import is_alias


_REVISION_NAME = re.compile(r"^r([0-9]{6,10})\.json$")


class BodySwayVisualReviewHistoryError(RuntimeError):
    """Raised when the linear human-decision history is unsafe or stale."""


@dataclass(frozen=True, slots=True)
class PublishedBodySwayVisualReviewDecision:
    path: Path
    sha256: str
    reused: bool


def publish_visual_review_decision(
    state_root: Path,
    decision: BodySwayVisualReviewDecision,
    candidates: BodySwayVisualReviewCandidate,
    capture: VerifiedBodySwayRuntimeCapture,
) -> PublishedBodySwayVisualReviewDecision:
    """Append revision N only after exact replay of slots 1 through N-1."""

    try:
        if type(decision) is not BodySwayVisualReviewDecision:
            raise BodySwayVisualReviewHistoryError(
                "Decision publication requires an exact value object"
            )
        candidate, _capture = reload_authoritative_visual_review_candidate(
            state_root, candidates, capture
        )
        document = decision.document
        revision = document["review"]["revision"]
        parent = publication_parent(
            state_root, document["project_id"],
            DECISION_NAMESPACE, candidate.sha256,
        )
        revisions = exact_subdirectory(parent, "revisions", create=True)
        chain = _load_chain(parent, revisions, candidate)
        digest = body_sway_visual_review_decision_sha256(document)
        payload = exact_payload(decision.canonical_bytes, document, digest)
        if revision <= len(chain):
            if chain[revision - 1].canonical_bytes != payload:
                raise BodySwayVisualReviewHistoryError(
                    "Visual review revision slot is already owned"
                )
            path, _reused = publish_document(parent, digest, payload)
            return PublishedBodySwayVisualReviewDecision(path, digest, True)
        if revision != len(chain) + 1:
            raise BodySwayVisualReviewHistoryError(
                "Visual review revisions must be contiguous"
            )
        previous = chain[-1].document if chain else None
        require_body_sway_visual_review_decision(
            document,
            candidates=candidate.document,
            previous_decision=previous,
        )
        path, content_reused = publish_document(parent, digest, payload)
        _slot_path, slot_reused = publish_named_document(
            revisions,
            _revision_name(revision),
            payload,
            staging_parent=parent,
        )
        verified = _load_chain(parent, revisions, candidate)
        if len(verified) != revision \
                or verified[-1].canonical_bytes != payload:
            raise BodySwayVisualReviewHistoryError(
                "Visual review revision failed authoritative readback"
            )
        return PublishedBodySwayVisualReviewDecision(
            path, digest, content_reused and slot_reused
        )
    except BodySwayVisualReviewHistoryError:
        raise
    except _FAILURES as exc:
        raise BodySwayVisualReviewHistoryError(
            f"Visual review history publication failed: {exc}"
        ) from exc


def load_visual_review_decision(
    state_root: Path,
    project_id: str,
    candidate_sha256: str,
    decision_sha256: str,
    *,
    candidates: BodySwayVisualReviewCandidate,
    capture: VerifiedBodySwayRuntimeCapture,
) -> BodySwayVisualReviewDecision:
    """Replay the full slot chain and return one exact addressed revision."""

    try:
        project = require_safe_token(project_id, "Visual review project id")
        candidate_address = require_sha256(
            candidate_sha256, "Visual review candidate digest"
        )
        decision_address = require_sha256(
            decision_sha256, "Visual review decision digest"
        )
        candidate, _capture = reload_authoritative_visual_review_candidate(
            state_root, candidates, capture
        )
        if candidate.document["project_id"] != project \
                or candidate.sha256 != candidate_address:
            raise BodySwayVisualReviewHistoryError(
                "Visual review decision address differs from its candidate"
            )
        parent = existing_parent(
            state_root, project, DECISION_NAMESPACE, candidate_address
        )
        revisions = exact_subdirectory(parent, "revisions", create=False)
        chain = _load_chain(parent, revisions, candidate)
        matches = [
            item for item in chain if item.sha256 == decision_address
        ]
        if len(matches) != 1:
            raise BodySwayVisualReviewHistoryError(
                "Decision address is not an authoritative revision slot"
            )
        return matches[0]
    except BodySwayVisualReviewHistoryError:
        raise
    except _FAILURES as exc:
        raise BodySwayVisualReviewHistoryError(
            f"Visual review history load failed: {exc}"
        ) from exc


def _load_chain(
    parent: Path,
    revisions: Path,
    candidate: BodySwayVisualReviewCandidate,
) -> list[BodySwayVisualReviewDecision]:
    names = _revision_inventory(revisions)
    chain = []
    previous = None
    for revision, name in enumerate(names, start=1):
        payload = read_named_document(revisions, name)
        document = strict_json_object(payload, name)
        if document.get("review", {}).get("revision") != revision:
            raise BodySwayVisualReviewHistoryError(
                "Visual review slot revision is inconsistent"
            )
        require_body_sway_visual_review_decision(
            document,
            candidates=candidate.document,
            previous_decision=(previous.document if previous else None),
        )
        digest = body_sway_visual_review_decision_sha256(document)
        if read_named_document(parent, f"{digest}.json", digest=digest) != payload:
            raise BodySwayVisualReviewHistoryError(
                "Revision slot differs from its content-addressed decision"
            )
        previous = BodySwayVisualReviewDecision(payload.decode("utf-8"))
        chain.append(previous)
    return chain


def _revision_inventory(directory: Path) -> tuple[str, ...]:
    try:
        children = list(directory.iterdir())
        if len(children) > MAX_VISUAL_REVIEW_REVISIONS:
            raise BodySwayVisualReviewHistoryError(
                "Visual review revision count exceeds its limit"
            )
        revisions = {}
        for child in children:
            match = _REVISION_NAME.fullmatch(child.name)
            if match is None or is_alias(child) \
                    or not stat.S_ISREG(child.lstat().st_mode):
                raise BodySwayVisualReviewHistoryError(
                    "Visual review revision inventory is unsafe"
                )
            number = int(match.group(1))
            if number in revisions or _revision_name(number) != child.name:
                raise BodySwayVisualReviewHistoryError(
                    "Visual review revision inventory is aliased"
                )
            revisions[number] = child.name
        expected = list(range(1, len(revisions) + 1))
        if sorted(revisions) != expected:
            raise BodySwayVisualReviewHistoryError(
                "Visual review revision inventory is not contiguous"
            )
        return tuple(revisions[number] for number in expected)
    except BodySwayVisualReviewHistoryError:
        raise
    except OSError as exc:
        raise BodySwayVisualReviewHistoryError(
            "Visual review revision inventory cannot be inspected"
        ) from exc


def _revision_name(revision: int) -> str:
    if type(revision) is not int \
            or not 1 <= revision <= MAX_VISUAL_REVIEW_REVISIONS:
        raise BodySwayVisualReviewHistoryError(
            "Visual review revision is outside its bounded history"
        )
    return f"r{revision:06d}.json"


_FAILURES = (
    BodySwayVisualReviewBindingError,
    BodySwayVisualReviewDecisionValidationError,
    BodySwayVisualReviewFilesError,
    LayerManifestError,
    SafeInputFileError,
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    UnicodeError,
    ValueError,
)
