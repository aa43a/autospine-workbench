"""Write-once candidate-bound history for P10.2b framing decisions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import stat

from .body_sway_visual_review_store_files import (
    BodySwayVisualReviewFilesError,
    exact_payload,
    exact_subdirectory,
    optional_existing_parent,
    publication_parent,
    publish_document,
    publish_named_document,
    read_named_document,
)
from .capture_framing_candidate import CaptureFramingCandidate
from .capture_framing_decision import (
    CaptureFramingDecision,
    CaptureFramingDecisionError,
    capture_framing_decision_sha256,
    require_capture_framing_decision,
)
from .capture_framing_profile import DECISION_NAMESPACE, MAX_REVISIONS
from .safe_input_files import strict_json_object
from .spine42_bundle_files import is_alias


class CaptureFramingHistoryError(RuntimeError):
    """Raised when framing authority cannot be replayed exactly."""


class CaptureFramingRevisionConflict(CaptureFramingHistoryError):
    def __init__(self, message, *, requested_revision, current_revision,
                 requested_head, current_head):
        super().__init__(message)
        self.requested_revision = requested_revision
        self.current_revision = current_revision
        self.requested_head = requested_head
        self.current_head = current_head


@dataclass(frozen=True, slots=True)
class CaptureFramingHistorySnapshot:
    current_revision: int
    head_decision_sha256: str | None
    action: str | None
    status: str | None


@dataclass(frozen=True, slots=True)
class PublishedCaptureFramingDecision:
    path: Path
    sha256: str
    revision: int
    reused: bool


def snapshot_capture_framing_history(
    state_root: Path, candidate: CaptureFramingCandidate,
) -> CaptureFramingHistorySnapshot:
    try:
        _candidate(candidate)
        parent = optional_existing_parent(
            state_root, candidate.document["project_id"],
            DECISION_NAMESPACE, candidate.sha256,
        )
        if parent is None:
            return CaptureFramingHistorySnapshot(0, None, None, None)
        revisions = exact_subdirectory(parent, "revisions", create=False)
        chain = _load_chain(parent, revisions, candidate)
        if not chain:
            return CaptureFramingHistorySnapshot(0, None, None, None)
        head = chain[-1]
        return CaptureFramingHistorySnapshot(
            len(chain), head.sha256,
            head.document["decision"]["action"], head.document["status"],
        )
    except CaptureFramingHistoryError:
        raise
    except _FAILURES as exc:
        raise CaptureFramingHistoryError(
            "Capture framing history could not be replayed"
        ) from exc


def publish_capture_framing_decision(
    state_root: Path,
    decision: CaptureFramingDecision,
    candidate: CaptureFramingCandidate,
    *, base_revision: int,
    previous_decision_sha256: str | None,
) -> PublishedCaptureFramingDecision:
    """CAS append one revision, allowing only an exact current retry."""

    try:
        _candidate(candidate)
        if type(decision) is not CaptureFramingDecision:
            raise CaptureFramingHistoryError("Framing decision value is invalid")
        revision = decision.document["review"]["revision"]
        if type(base_revision) is not int or revision != base_revision + 1:
            raise CaptureFramingHistoryError("Framing base revision is invalid")
        parent = optional_existing_parent(
            state_root, candidate.document["project_id"],
            DECISION_NAMESPACE, candidate.sha256,
        )
        chain = []
        if parent is not None:
            revisions = exact_subdirectory(parent, "revisions", create=False)
            chain = _load_chain(parent, revisions, candidate)
        previous_document = chain[revision - 2].document \
            if revision > 1 and len(chain) >= revision - 1 else None
        require_capture_framing_decision(
            decision.document, candidate=candidate,
            previous_decision=previous_document,
        )
        digest = capture_framing_decision_sha256(
            decision.document, candidate=candidate,
            previous_decision=previous_document,
        )
        payload = exact_payload(decision.canonical_bytes, decision.document, digest)
        if len(chain) >= revision \
                and chain[revision - 1].canonical_bytes == payload:
            expected_previous = chain[revision - 2].sha256 if revision > 1 else None
            if len(chain) != revision \
                    or previous_decision_sha256 != expected_previous:
                raise _conflict(
                    "Framing retry is no longer current", decision, chain
                )
            path, _ = publish_document(parent, digest, payload)
            return PublishedCaptureFramingDecision(
                path, digest, revision, True,
            )
        current = chain[-1].sha256 if chain else None
        if len(chain) != base_revision or previous_decision_sha256 != current:
            raise _conflict("Framing predecessor is stale", decision, chain)
        if parent is None:
            parent = publication_parent(
                state_root, candidate.document["project_id"],
                DECISION_NAMESPACE, candidate.sha256,
            )
            revisions = exact_subdirectory(parent, "revisions", create=True)
        path, _ = publish_document(parent, digest, payload)
        try:
            _slot, reused = publish_named_document(
                revisions, _revision_name(revision), payload,
                staging_parent=parent,
            )
        except BodySwayVisualReviewFilesError as exc:
            current_chain = _load_chain(parent, revisions, candidate)
            raise _conflict(
                "Framing revision lost its slot", decision, current_chain
            ) from exc
        verified = _load_chain(parent, revisions, candidate)
        if len(verified) != revision \
                or verified[-1].canonical_bytes != payload:
            raise CaptureFramingHistoryError(
                "Framing decision failed exact readback"
            )
        return PublishedCaptureFramingDecision(
            path, digest, revision, reused,
        )
    except CaptureFramingRevisionConflict:
        raise
    except CaptureFramingHistoryError:
        raise
    except _FAILURES as exc:
        raise CaptureFramingHistoryError(
            "Capture framing decision could not be published"
        ) from exc


def load_capture_framing_head(
    state_root: Path, candidate: CaptureFramingCandidate,
) -> CaptureFramingDecision | None:
    _candidate(candidate)
    parent = optional_existing_parent(
        state_root, candidate.document["project_id"],
        DECISION_NAMESPACE, candidate.sha256,
    )
    if parent is None:
        return None
    revisions = exact_subdirectory(parent, "revisions", create=False)
    chain = _load_chain(parent, revisions, candidate)
    return chain[-1] if chain else None


def _load_chain(parent, revisions, candidate):
    chain, previous = [], None
    for revision, name in enumerate(_revision_inventory(revisions), start=1):
        payload = read_named_document(revisions, name)
        document = strict_json_object(payload, "Capture framing decision")
        require_capture_framing_decision(
            document, candidate=candidate,
            previous_decision=previous.document if previous else None,
        )
        if document["review"]["revision"] != revision:
            raise CaptureFramingHistoryError("Framing revision slot differs")
        digest = capture_framing_decision_sha256(
            document, candidate=candidate,
            previous_decision=previous.document if previous else None,
        )
        if read_named_document(parent, f"{digest}.json", digest=digest) != payload:
            raise CaptureFramingHistoryError(
                "Framing slot differs from addressed bytes"
            )
        previous = CaptureFramingDecision(payload.decode("utf-8"))
        chain.append(previous)
    return chain


def _revision_inventory(directory):
    try:
        children = list(directory.iterdir())
        if len(children) > MAX_REVISIONS:
            raise CaptureFramingHistoryError("Framing history is excessive")
        revisions = {}
        for child in children:
            match = _REVISION_NAME.fullmatch(child.name)
            if match is None or is_alias(child) \
                    or not stat.S_ISREG(child.lstat().st_mode):
                raise CaptureFramingHistoryError("Framing history is unsafe")
            number = int(match.group(1))
            if number in revisions or _revision_name(number) != child.name:
                raise CaptureFramingHistoryError("Framing history is aliased")
            revisions[number] = child.name
        expected = list(range(1, len(revisions) + 1))
        if sorted(revisions) != expected:
            raise CaptureFramingHistoryError("Framing history is not contiguous")
        return tuple(revisions[number] for number in expected)
    except CaptureFramingHistoryError:
        raise
    except OSError as exc:
        raise CaptureFramingHistoryError("Framing history is unavailable") from exc


def _revision_name(revision):
    if type(revision) is not int or not 1 <= revision <= MAX_REVISIONS:
        raise CaptureFramingHistoryError("Framing revision is outside its limit")
    return f"r{revision:06d}.json"


def _candidate(value):
    if type(value) is not CaptureFramingCandidate:
        raise CaptureFramingHistoryError("Framing candidate is invalid")


def _conflict(message, decision, chain):
    review = decision.document["review"]
    return CaptureFramingRevisionConflict(
        message, requested_revision=review["revision"],
        current_revision=len(chain),
        requested_head=review["supersedes_decision_sha256"],
        current_head=chain[-1].sha256 if chain else None,
    )


_REVISION_NAME = re.compile(r"^r([0-9]{6,10})\.json$")
_FAILURES = (
    AttributeError, BodySwayVisualReviewFilesError,
    CaptureFramingDecisionError, KeyError, OSError, OverflowError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)
