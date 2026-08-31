"""Exact-current application service for P10.2b framing decisions."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_probe_application import (
    BodySwayProbeApplication,
    BodySwayProbeApplicationError,
    BodySwayProbeApplicationHeadChanged,
    BodySwayProbeApplicationNotFound,
)
from .capture_framing_candidate import CaptureFramingCandidate
from .capture_framing_decision import (
    CaptureFramingDecisionError,
    build_capture_framing_decision,
)
from .capture_framing_history import (
    CaptureFramingHistoryError,
    CaptureFramingRevisionConflict,
    load_capture_framing_head,
    publish_capture_framing_decision,
    snapshot_capture_framing_history,
)
from .capture_framing_profile import FORMAT_VERSION, RECEIPT_FORMAT
from .capture_framing_submission import (
    CaptureFramingSubmission,
    CaptureFramingSubmissionError,
    require_capture_framing_submission,
)
from .capture_framing_validation import (
    CaptureFramingValidationError,
    capture_framing_candidate_sha256,
)
from .current_project_chain import (
    rebuild_current_project_chains,
    require_unchanged_current_project_chains,
)
from .idle_behavior_review_packages import (
    IdleBehaviorReviewPackageError,
    IdleBehaviorReviewPackageStale,
    require_current_idle_behavior_review_address,
)
from .idle_behavior_review_transaction import idle_behavior_review_transaction
from .project_store import ProjectStore


class CaptureFramingApplicationError(RuntimeError):
    """Base class for a safe capture-framing submission failure."""


class CaptureFramingApplicationInvalid(CaptureFramingApplicationError):
    """The browser submission differs from exact server evidence."""


class CaptureFramingApplicationNotFound(CaptureFramingApplicationError):
    """The exact package or candidate is unavailable."""


class CaptureFramingApplicationHistorical(CaptureFramingApplicationError):
    """The package is valid history but not current authoring."""


class CaptureFramingApplicationHeadChanged(CaptureFramingApplicationError):
    """P10.1 or the current project chain changed before publication."""


class CaptureFramingApplicationUnavailable(CaptureFramingApplicationError):
    """Trusted evidence could not be replayed or published exactly."""


class CaptureFramingApplication:
    """Recheck one current chain, then CAS an explicit human decision."""

    def __init__(self, store: ProjectStore) -> None:
        if not isinstance(store, ProjectStore):
            raise CaptureFramingApplicationUnavailable("Project store is invalid")
        self.store = store

    def submit(self, package_id: str, payload: Any) -> dict[str, Any]:
        request = _request(package_id, payload)
        project_ids = self.store.discover_project_ids()
        before = rebuild_current_project_chains(self.store, project_ids)
        address = _current_address(
            self.store, package_id, project_ids, before,
        )
        scoped = (address.project_id,)
        candidate, head = _prepare(
            self.store.state_root, package_id, scoped, request,
            before[address.project_id],
        )
        after = rebuild_current_project_chains(self.store, project_ids)
        require_unchanged_current_project_chains(before, after)
        idle_candidate_sha = request.p10_1_head["candidate_sha256"]
        with idle_behavior_review_transaction(
            self.store.state_root, idle_candidate_sha,
        ):
            locked = rebuild_current_project_chains(self.store, project_ids)
            require_unchanged_current_project_chains(before, locked)
            confirmed_address = _current_address(
                self.store, package_id, project_ids, locked,
            )
            if confirmed_address != address:
                raise CaptureFramingApplicationHeadChanged(
                    "Framing package address changed before publication"
                )
            confirmed, confirmed_head = _prepare(
                self.store.state_root, package_id, scoped, request,
                locked[address.project_id],
            )
            if confirmed.canonical_bytes != candidate.canonical_bytes \
                    or confirmed_head != head:
                raise CaptureFramingApplicationHeadChanged(
                    "P10.1 head changed before framing publication"
                )
            final_chain = rebuild_current_project_chains(
                self.store, project_ids,
            )
            require_unchanged_current_project_chains(locked, final_chain)
            _current_address(
                self.store, package_id, project_ids, final_chain,
            )
            return _publish(
                self.store.state_root, package_id, confirmed, request,
            )


def _request(package_id, payload) -> CaptureFramingSubmission:
    try:
        request = require_capture_framing_submission(payload)
    except CaptureFramingSubmissionError as exc:
        raise CaptureFramingApplicationInvalid(str(exc)) from exc
    if request.package_id != package_id:
        raise CaptureFramingApplicationInvalid(
            "Capture framing package identity is stale"
        )
    return request


def _current_address(store, package_id, project_ids, chains):
    try:
        return require_current_idle_behavior_review_address(
            store.state_root, package_id,
            project_ids=project_ids, current_project_chains=chains,
        )
    except IdleBehaviorReviewPackageStale as exc:
        raise CaptureFramingApplicationHistorical(
            "Historical structural-probe packages are read-only"
        ) from exc
    except IdleBehaviorReviewPackageError as exc:
        raise CaptureFramingApplicationNotFound(
            "Structural-probe package is unavailable"
        ) from exc


def _prepare(state_root, package_id, project_ids, request, chain):
    try:
        detail = BodySwayProbeApplication(state_root).prepare(
            package_id, project_ids=project_ids,
        )
    except BodySwayProbeApplicationNotFound as exc:
        raise CaptureFramingApplicationNotFound(
            "Structural-probe package is unavailable"
        ) from exc
    except BodySwayProbeApplicationHeadChanged as exc:
        raise CaptureFramingApplicationHeadChanged(
            "P10.1 changed during framing replay"
        ) from exc
    except BodySwayProbeApplicationError as exc:
        raise CaptureFramingApplicationUnavailable(
            "Capture framing evidence is unavailable"
        ) from exc
    return _candidate(detail, request, chain)


def _candidate(detail, request, chain):
    try:
        projection = detail["capture_framing"]
        if not isinstance(projection, Mapping) \
                or projection.get("candidate_sha256") \
                != request.candidate_sha256:
            raise CaptureFramingApplicationNotFound(
                "Capture framing candidate is unavailable"
            )
        document = projection["document"]
        canonical = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        candidate = CaptureFramingCandidate(canonical)
        if capture_framing_candidate_sha256(document) \
                != request.candidate_sha256 \
                or candidate.sha256 != request.candidate_sha256:
            raise CaptureFramingApplicationUnavailable(
                "Capture framing candidate digest differs"
            )
        source = document["source"]
        history = detail["history"]
        head = {
            "candidate_sha256": detail["candidate_sha256"],
            "decision_sha256": history["head_decision_sha256"],
            "revision": history["current_revision"],
        }
        package = detail["package"]
        if package["package_id"] != request.package_id \
                or package["project_id"] != document["project_id"] \
                or package["clip_id"] != document["clip_id"] \
                or source["package_id"] != request.package_id \
                or source["current_p10_1_head"] != request.p10_1_head \
                or head != request.p10_1_head \
                or history["action"] != "adjust" \
                or history["probe_status"] != "pending_probe" \
                or source["p3"]["resolved_project_sha256"] \
                != chain.resolved_project_sha256 \
                or source["p3"]["layer_manifest_sha256"] \
                != chain.layer_manifest_sha256:
            raise CaptureFramingApplicationHeadChanged(
                "Capture framing current source differs"
            )
        return candidate, head
    except CaptureFramingApplicationError:
        raise
    except (
        CaptureFramingValidationError, KeyError, OverflowError,
        RecursionError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise CaptureFramingApplicationUnavailable(
            "Capture framing projection is invalid"
        ) from exc


def _publish(state_root, package_id, candidate, request):
    try:
        snapshot = snapshot_capture_framing_history(state_root, candidate)
        if snapshot.current_revision != request.base_revision \
                or snapshot.head_decision_sha256 \
                != request.previous_decision_sha256:
            raise CaptureFramingRevisionConflict(
                "Capture framing predecessor is stale",
                requested_revision=request.base_revision + 1,
                current_revision=snapshot.current_revision,
                requested_head=request.previous_decision_sha256,
                current_head=snapshot.head_decision_sha256,
            )
        previous = load_capture_framing_head(state_root, candidate)
        if (previous.sha256 if previous else None) \
                != snapshot.head_decision_sha256:
            raise CaptureFramingApplicationUnavailable(
                "Capture framing history changed during replay"
            )
        decision = build_capture_framing_decision(
            candidate, action=request.action,
            world_viewport=request.world_viewport,
            reason_code=request.reason_code,
            revision=request.base_revision + 1,
            supersedes_decision_sha256=request.previous_decision_sha256,
            previous_decision=previous,
        )
        published = publish_capture_framing_decision(
            state_root, decision, candidate,
            base_revision=request.base_revision,
            previous_decision_sha256=request.previous_decision_sha256,
        )
    except CaptureFramingRevisionConflict:
        raise
    except CaptureFramingDecisionError as exc:
        raise CaptureFramingApplicationInvalid(
            "Capture framing decision parameters are invalid"
        ) from exc
    except CaptureFramingHistoryError as exc:
        raise CaptureFramingApplicationUnavailable(
            "Capture framing decision could not be published"
        ) from exc
    return {
        "format": RECEIPT_FORMAT,
        "format_version": FORMAT_VERSION,
        "status": "recorded",
        "project_id": candidate.document["project_id"],
        "package_id": package_id,
        "candidate_sha256": candidate.sha256,
        "decision_sha256": published.sha256,
        "revision": published.revision,
        "action": decision.document["decision"]["action"],
        "decision_status": decision.document["status"],
        "reused": published.reused,
        "history": {
            "current_revision": published.revision,
            "head_decision_sha256": published.sha256,
        },
    }
