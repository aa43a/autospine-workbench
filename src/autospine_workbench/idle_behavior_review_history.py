"""Alias-safe, write-once linear history for P10.1 human decisions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import stat
from typing import Any, Mapping

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
from .idle_behavior_candidate_validation import (
    idle_behavior_candidates_sha256,
    require_idle_behavior_candidates,
)
from .idle_behavior_decision import IdleBehaviorDecision
from .idle_behavior_decision_validation import (
    idle_behavior_decision_sha256,
    require_idle_behavior_decision,
)
from .idle_behavior_review_profile import DECISION_NAMESPACE, MAX_REVISIONS
from .safe_input_files import strict_json_object
from .spine42_bundle_files import is_alias


class IdleBehaviorReviewHistoryError(RuntimeError):
    """Raised when a decision history cannot be replayed exactly."""


class IdleBehaviorReviewRevisionConflict(IdleBehaviorReviewHistoryError):
    """Raised when a submission no longer names the exact linear head."""

    def __init__(
        self, message: str, *, requested_revision: int,
        current_revision: int, requested_head: str | None,
        current_head: str | None,
    ) -> None:
        super().__init__(message)
        self.requested_revision = requested_revision
        self.current_revision = current_revision
        self.requested_head = requested_head
        self.current_head = current_head


@dataclass(frozen=True, slots=True)
class IdleBehaviorReviewHistoryRow:
    revision: int
    decision_sha256: str
    action: str
    probe_status: str
    _parameters_json: str | None

    @property
    def parameters(self) -> dict[str, Any] | None:
        """Return a detached copy of the exact reviewed parameters."""
        return json.loads(self._parameters_json) \
            if self._parameters_json is not None else None


@dataclass(frozen=True, slots=True)
class IdleBehaviorReviewHistorySnapshot:
    current_revision: int
    head_decision_sha256: str | None
    rows: tuple[IdleBehaviorReviewHistoryRow, ...]


@dataclass(frozen=True, slots=True)
class PublishedIdleBehaviorReviewDecision:
    path: Path
    sha256: str
    revision: int
    reused: bool


def snapshot_idle_behavior_review_history(
    state_root: Path, candidates: Mapping[str, Any],
) -> IdleBehaviorReviewHistorySnapshot:
    """Replay the exact candidate-bound chain without creating state."""

    try:
        candidate_sha = idle_behavior_candidates_sha256(candidates)
        parent = optional_existing_parent(
            state_root, candidates["project_id"],
            DECISION_NAMESPACE, candidate_sha,
        )
        if parent is None:
            return IdleBehaviorReviewHistorySnapshot(0, None, ())
        revisions = exact_subdirectory(parent, "revisions", create=False)
        chain = _load_chain(parent, revisions, candidates)
        rows = tuple(_row(item) for item in chain)
        return IdleBehaviorReviewHistorySnapshot(
            len(rows), rows[-1].decision_sha256 if rows else None, rows,
        )
    except IdleBehaviorReviewHistoryError:
        raise
    except _FAILURES as exc:
        raise IdleBehaviorReviewHistoryError(
            "Idle behavior review history could not be replayed"
        ) from exc


def publish_idle_behavior_review_decision(
    state_root: Path,
    decision: IdleBehaviorDecision,
    candidates: Mapping[str, Any],
    *,
    base_revision: int,
    previous_decision_sha256: str | None,
) -> PublishedIdleBehaviorReviewDecision:
    """CAS append revision base+1, allowing only byte-identical retries."""

    try:
        if type(decision) is not IdleBehaviorDecision:
            raise IdleBehaviorReviewHistoryError(
                "Idle behavior decision publication requires an exact value"
            )
        require_idle_behavior_candidates(candidates)
        document = decision.document
        require_idle_behavior_decision(document, candidates=candidates)
        revision = document["review"]["revision"]
        if type(base_revision) is not int or revision != base_revision + 1 \
                or not 1 <= revision <= MAX_REVISIONS:
            raise IdleBehaviorReviewHistoryError(
                "Idle behavior decision revision is inconsistent"
            )
        digest = idle_behavior_decision_sha256(document)
        payload = exact_payload(decision.canonical_bytes, document, digest)
        candidate_sha = idle_behavior_candidates_sha256(candidates)
        project_id = candidates["project_id"]
        parent = optional_existing_parent(
            state_root, project_id, DECISION_NAMESPACE, candidate_sha,
        )
        chain: list[IdleBehaviorDecision] = []
        if parent is not None:
            revisions = exact_subdirectory(parent, "revisions", create=False)
            chain = _load_chain(parent, revisions, candidates)
        if len(chain) >= revision \
                and chain[revision - 1].canonical_bytes == payload:
            expected_previous = (
                chain[revision - 2].sha256 if revision > 1 else None
            )
            if len(chain) != revision \
                    or previous_decision_sha256 != expected_previous:
                raise _conflict(
                    "Idle behavior review retry is no longer the current head",
                    revision, previous_decision_sha256, chain,
                )
            path, _ = publish_document(parent, digest, payload)
            return PublishedIdleBehaviorReviewDecision(
                path, digest, revision, True,
            )
        current_head = chain[-1].sha256 if chain else None
        if len(chain) != base_revision \
                or previous_decision_sha256 != current_head:
            raise _conflict(
                "Idle behavior review predecessor is stale",
                revision, previous_decision_sha256, chain,
            )
        if parent is None:
            parent = publication_parent(
                state_root, project_id, DECISION_NAMESPACE, candidate_sha,
            )
            revisions = exact_subdirectory(parent, "revisions", create=True)
        path, _ = publish_document(parent, digest, payload)
        try:
            _slot, reused = publish_named_document(
                revisions, _revision_name(revision), payload,
                staging_parent=parent,
            )
        except BodySwayVisualReviewFilesError as exc:
            current = _load_chain(parent, revisions, candidates)
            raise _conflict(
                "Idle behavior review lost its revision slot",
                revision, previous_decision_sha256, current,
            ) from exc
        verified = _load_chain(parent, revisions, candidates)
        if len(verified) < revision \
                or verified[revision - 1].canonical_bytes != payload:
            raise IdleBehaviorReviewHistoryError(
                "Idle behavior review decision failed exact readback"
            )
        return PublishedIdleBehaviorReviewDecision(
            path, digest, revision, reused,
        )
    except IdleBehaviorReviewRevisionConflict:
        raise
    except IdleBehaviorReviewHistoryError:
        raise
    except _FAILURES as exc:
        raise IdleBehaviorReviewHistoryError(
            "Idle behavior review decision could not be published"
        ) from exc


def _load_chain(
    parent: Path, revisions: Path, candidates: Mapping[str, Any],
) -> list[IdleBehaviorDecision]:
    chain = []
    for revision, name in enumerate(_revision_inventory(revisions), start=1):
        payload = read_named_document(revisions, name)
        document = strict_json_object(payload, "Idle behavior review decision")
        require_idle_behavior_decision(document, candidates=candidates)
        if document["review"]["revision"] != revision:
            raise IdleBehaviorReviewHistoryError(
                "Idle behavior revision slot is inconsistent"
            )
        digest = idle_behavior_decision_sha256(document)
        if read_named_document(parent, f"{digest}.json", digest=digest) \
                != payload:
            raise IdleBehaviorReviewHistoryError(
                "Idle behavior slot differs from its addressed decision"
            )
        chain.append(IdleBehaviorDecision(payload.decode("utf-8")))
    return chain


def _revision_inventory(directory: Path) -> tuple[str, ...]:
    try:
        children = list(directory.iterdir())
        if len(children) > MAX_REVISIONS:
            raise IdleBehaviorReviewHistoryError(
                "Idle behavior review history exceeds its limit"
            )
        revisions = {}
        for child in children:
            match = _REVISION_NAME.fullmatch(child.name)
            if match is None or is_alias(child) \
                    or not stat.S_ISREG(child.lstat().st_mode):
                raise IdleBehaviorReviewHistoryError(
                    "Idle behavior revision inventory is unsafe"
                )
            number = int(match.group(1))
            if number in revisions or _revision_name(number) != child.name:
                raise IdleBehaviorReviewHistoryError(
                    "Idle behavior revision inventory is aliased"
                )
            revisions[number] = child.name
        expected = list(range(1, len(revisions) + 1))
        if sorted(revisions) != expected:
            raise IdleBehaviorReviewHistoryError(
                "Idle behavior revision inventory is not contiguous"
            )
        return tuple(revisions[number] for number in expected)
    except IdleBehaviorReviewHistoryError:
        raise
    except OSError as exc:
        raise IdleBehaviorReviewHistoryError(
            "Idle behavior revision inventory cannot be inspected"
        ) from exc


def _row(value: IdleBehaviorDecision) -> IdleBehaviorReviewHistoryRow:
    document = value.document
    decision = document["decisions"][0]
    return IdleBehaviorReviewHistoryRow(
        document["review"]["revision"], value.sha256,
        decision["action"], decision["probe_status"],
        (
            json.dumps(
                decision["payload"], ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            )
            if decision["action"] == "adjust" else None
        ),
    )


def _revision_name(revision: int) -> str:
    if type(revision) is not int or not 1 <= revision <= MAX_REVISIONS:
        raise IdleBehaviorReviewHistoryError(
            "Idle behavior review revision is outside its limit"
        )
    return f"r{revision:06d}.json"


def _conflict(message, revision, requested_head, chain):
    return IdleBehaviorReviewRevisionConflict(
        message, requested_revision=revision,
        current_revision=len(chain), requested_head=requested_head,
        current_head=chain[-1].sha256 if chain else None,
    )


_REVISION_NAME = re.compile(r"^r([0-9]{6,10})\.json$")
_FAILURES = (
    AttributeError, BodySwayVisualReviewFilesError, KeyError, OSError,
    OverflowError, RuntimeError, TypeError, UnicodeError, ValueError,
)
