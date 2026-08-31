"""Linear write-once revision slots for authoritative P10.3c v2 decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import stat

from .body_sway_runtime_execution_reader import VerifiedBodySwayRuntimeExecution
from .body_sway_visual_review_binding_v2 import (
    reload_authoritative_visual_review_candidate_v2,
)
from .body_sway_visual_review_candidate_v2 import BodySwayVisualReviewCandidateV2
from .body_sway_visual_review_decision_v2 import BodySwayVisualReviewDecisionV2
from .body_sway_visual_review_decision_validation_v2 import (
    body_sway_visual_review_decision_sha256_v2,
    require_body_sway_visual_review_decision_v2,
)
from .body_sway_visual_review_errors_v2 import (
    BodySwayVisualReviewHistoryV2Error,
    BodySwayVisualReviewRevisionV2Conflict,
)
from .body_sway_visual_review_profile_v2 import (
    DECISION_NAMESPACE, MAX_VISUAL_REVIEW_REVISIONS,
)
from .body_sway_visual_review_store_files import (
    BodySwayVisualReviewFilesError, exact_payload, exact_subdirectory,
    existing_parent, optional_existing_parent, publication_parent,
    publish_document, publish_named_document, read_named_document,
)
from .manifest_artifacts import require_safe_token, require_sha256
from .safe_input_files import strict_json_object
from .spine42_bundle_files import is_alias
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


_REVISION_NAME = re.compile(r"^r([0-9]{6,10})\.json$")


@dataclass(frozen=True, slots=True)
class PublishedBodySwayVisualReviewDecisionV2:
    path: Path
    sha256: str
    reused: bool


def publish_visual_review_decision_v2(
    state_root: Path, decision: BodySwayVisualReviewDecisionV2,
    candidates: BodySwayVisualReviewCandidateV2,
    execution: VerifiedBodySwayRuntimeExecution,
    preview: TemporaryBodySwayPreviewV2,
) -> PublishedBodySwayVisualReviewDecisionV2:
    """Append revision N only after replaying exact slots 1 through N-1."""

    try:
        if type(decision) is not BodySwayVisualReviewDecisionV2:
            raise BodySwayVisualReviewHistoryV2Error(
                "Decision v2 publication requires an exact value object"
            )
        candidate, _execution = reload_authoritative_visual_review_candidate_v2(
            state_root, candidates, execution, preview,
        )
        document = decision.document
        revision = document["review"]["revision"]
        digest = body_sway_visual_review_decision_sha256_v2(document)
        payload = exact_payload(decision.canonical_bytes, document, digest)
        parent = optional_existing_parent(
            state_root, document["project_id"], DECISION_NAMESPACE,
            candidate.sha256,
        )
        chain = []
        if parent is not None:
            try:
                revisions = exact_subdirectory(parent, "revisions", create=False)
            except BodySwayVisualReviewFilesError:
                if revision != 1:
                    raise
                revisions = exact_subdirectory(parent, "revisions", create=True)
            chain = load_visual_review_chain_v2(parent, revisions, candidate)
        require_body_sway_visual_review_decision_v2(
            document, candidates=candidate.document,
        )
        if revision <= len(chain):
            if chain[revision - 1].canonical_bytes != payload:
                raise _conflict(
                    "Visual review v2 revision slot is already owned",
                    document, chain,
                )
            path, _reused = publish_document(parent, digest, payload)
            return PublishedBodySwayVisualReviewDecisionV2(path, digest, True)
        if revision != len(chain) + 1:
            raise _conflict(
                "Visual review v2 revisions must be contiguous", document, chain,
            )
        head = chain[-1].sha256 if chain else None
        if document["review"]["supersedes_decision_sha256"] != head:
            raise _conflict(
                "Visual review v2 predecessor is stale", document, chain,
            )
        previous = chain[-1].document if chain else None
        require_body_sway_visual_review_decision_v2(
            document, candidates=candidate.document,
            previous_decision=previous,
        )
        if parent is None:
            parent = publication_parent(
                state_root, document["project_id"], DECISION_NAMESPACE,
                candidate.sha256,
            )
            revisions = exact_subdirectory(parent, "revisions", create=True)
        path, _content_reused = publish_document(parent, digest, payload)
        try:
            _slot, slot_reused = publish_named_document(
                revisions, _revision_name(revision), payload,
                staging_parent=parent,
            )
        except BodySwayVisualReviewFilesError as exc:
            current = load_visual_review_chain_v2(parent, revisions, candidate)
            raise _conflict(
                "Visual review v2 revision lost its concurrent slot",
                document, current,
            ) from exc
        verified = load_visual_review_chain_v2(parent, revisions, candidate)
        if len(verified) != revision \
                or verified[-1].canonical_bytes != payload:
            raise BodySwayVisualReviewHistoryV2Error(
                "Visual review v2 revision failed authoritative readback"
            )
        return PublishedBodySwayVisualReviewDecisionV2(
            path, digest, slot_reused,
        )
    except BodySwayVisualReviewHistoryV2Error:
        raise
    except (AttributeError, KeyError, OSError, RuntimeError,
            TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayVisualReviewHistoryV2Error(
            f"Visual review v2 history publication failed: {exc}"
        ) from exc


def load_visual_review_decision_v2(
    state_root: Path, project_id: str, candidate_sha256: str,
    decision_sha256: str, *, candidates: BodySwayVisualReviewCandidateV2,
    execution: VerifiedBodySwayRuntimeExecution,
    preview: TemporaryBodySwayPreviewV2,
) -> BodySwayVisualReviewDecisionV2:
    try:
        project = require_safe_token(project_id, "Visual review v2 project")
        candidate_address = require_sha256(
            candidate_sha256, "Visual review candidate v2",
        )
        decision_address = require_sha256(
            decision_sha256, "Visual review decision v2",
        )
        candidate, _execution = reload_authoritative_visual_review_candidate_v2(
            state_root, candidates, execution, preview,
        )
        if candidate.document["project_id"] != project \
                or candidate.sha256 != candidate_address:
            raise BodySwayVisualReviewHistoryV2Error(
                "Visual review v2 decision address differs from candidate"
            )
        parent = existing_parent(
            state_root, project, DECISION_NAMESPACE, candidate_address,
        )
        revisions = exact_subdirectory(parent, "revisions", create=False)
        chain = load_visual_review_chain_v2(parent, revisions, candidate)
        matches = [item for item in chain if item.sha256 == decision_address]
        if len(matches) != 1:
            raise BodySwayVisualReviewHistoryV2Error(
                "Decision v2 address is not an authoritative revision"
            )
        return matches[0]
    except BodySwayVisualReviewHistoryV2Error:
        raise
    except (AttributeError, KeyError, OSError, RuntimeError,
            TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayVisualReviewHistoryV2Error(
            f"Visual review v2 history load failed: {exc}"
        ) from exc


def load_visual_review_chain_v2(parent, revisions, candidate):
    names = _revision_inventory(revisions)
    chain, previous = [], None
    for revision, name in enumerate(names, start=1):
        payload = read_named_document(revisions, name)
        document = strict_json_object(payload, name)
        if document.get("review", {}).get("revision") != revision:
            raise BodySwayVisualReviewHistoryV2Error(
                "Visual review v2 slot revision is inconsistent"
            )
        require_body_sway_visual_review_decision_v2(
            document, candidates=candidate.document,
            previous_decision=(previous.document if previous else None),
        )
        digest = body_sway_visual_review_decision_sha256_v2(document)
        if read_named_document(parent, f"{digest}.json", digest=digest) \
                != payload:
            raise BodySwayVisualReviewHistoryV2Error(
                "Visual review v2 slot differs from addressed decision"
            )
        previous = BodySwayVisualReviewDecisionV2(payload.decode("utf-8"))
        chain.append(previous)
    return chain


def _revision_inventory(directory):
    try:
        children = list(directory.iterdir())
        if len(children) > MAX_VISUAL_REVIEW_REVISIONS:
            raise BodySwayVisualReviewHistoryV2Error(
                "Visual review v2 history exceeds its revision limit"
            )
        revisions = {}
        for child in children:
            match = _REVISION_NAME.fullmatch(child.name)
            if match is None or is_alias(child) \
                    or not stat.S_ISREG(child.lstat().st_mode):
                raise BodySwayVisualReviewHistoryV2Error(
                    "Visual review v2 revision inventory is unsafe"
                )
            number = int(match.group(1))
            if number in revisions or _revision_name(number) != child.name:
                raise BodySwayVisualReviewHistoryV2Error(
                    "Visual review v2 revision inventory is aliased"
                )
            revisions[number] = child.name
        expected = list(range(1, len(revisions) + 1))
        if sorted(revisions) != expected:
            raise BodySwayVisualReviewHistoryV2Error(
                "Visual review v2 revision inventory is not contiguous"
            )
        return tuple(revisions[number] for number in expected)
    except BodySwayVisualReviewHistoryV2Error:
        raise
    except OSError as exc:
        raise BodySwayVisualReviewHistoryV2Error(
            "Visual review v2 revision inventory cannot be inspected"
        ) from exc


def _revision_name(revision):
    if type(revision) is not int \
            or not 1 <= revision <= MAX_VISUAL_REVIEW_REVISIONS:
        raise BodySwayVisualReviewHistoryV2Error(
            "Visual review v2 revision is outside its bounded history"
        )
    return f"r{revision:06d}.json"


def _conflict(message, document, chain):
    review = document.get("review", {})
    return BodySwayVisualReviewRevisionV2Conflict(
        message, requested_revision=review.get("revision"),
        current_revision=len(chain),
        requested_head=review.get("supersedes_decision_sha256"),
        current_head=chain[-1].sha256 if chain else None,
    )
