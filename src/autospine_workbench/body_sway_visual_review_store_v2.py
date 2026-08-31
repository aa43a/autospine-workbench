"""Write-once facade for P10.3c v2 candidates and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .body_sway_runtime_execution_reader import VerifiedBodySwayRuntimeExecution
from .body_sway_visual_review_binding_v2 import (
    reload_authoritative_runtime_execution_v2,
)
from .body_sway_visual_review_candidate_v2 import BodySwayVisualReviewCandidateV2
from .body_sway_visual_review_candidate_validation_v2 import (
    body_sway_visual_review_candidate_sha256_v2,
    require_body_sway_visual_review_candidate_v2,
)
from .body_sway_visual_review_decision_v2 import BodySwayVisualReviewDecisionV2
from .body_sway_visual_review_errors_v2 import (
    BodySwayVisualReviewHistoryV2Error,
    BodySwayVisualReviewRevisionV2Conflict,
    BodySwayVisualReviewStoreV2Error,
)
from .body_sway_visual_review_history_snapshot_v2 import (
    BodySwayVisualReviewHistorySnapshotV2,
    snapshot_visual_review_history_v2,
)
from .body_sway_visual_review_history_v2 import (
    load_visual_review_decision_v2, publish_visual_review_decision_v2,
)
from .body_sway_visual_review_profile_v2 import CANDIDATE_NAMESPACE
from .body_sway_visual_review_store_files import (
    exact_payload, publication_parent, publish_document, read_document,
)
from .manifest_artifacts import require_safe_token, require_sha256
from .safe_input_files import strict_json_object
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


@dataclass(frozen=True, slots=True)
class PublishedBodySwayVisualReviewDocumentV2:
    path: Path
    sha256: str
    reused: bool


class BodySwayVisualReviewStoreV2:
    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish_candidate(
        self, candidate: BodySwayVisualReviewCandidateV2,
        execution: VerifiedBodySwayRuntimeExecution,
        preview: TemporaryBodySwayPreviewV2,
    ) -> PublishedBodySwayVisualReviewDocumentV2:
        try:
            if type(candidate) is not BodySwayVisualReviewCandidateV2:
                raise BodySwayVisualReviewStoreV2Error(
                    "Candidate v2 publication requires an exact value object"
                )
            loaded = reload_authoritative_runtime_execution_v2(
                self.state_root, execution,
            )
            document = candidate.document
            require_body_sway_visual_review_candidate_v2(
                document, execution=loaded, preview=preview,
            )
            digest = body_sway_visual_review_candidate_sha256_v2(document)
            payload = exact_payload(candidate.canonical_bytes, document, digest)
            parent = publication_parent(
                self.state_root, document["project_id"], CANDIDATE_NAMESPACE,
                loaded.bundle_sha256,
            )
            path, reused = publish_document(parent, digest, payload)
            return PublishedBodySwayVisualReviewDocumentV2(
                path, digest, reused,
            )
        except BodySwayVisualReviewStoreV2Error:
            raise
        except (AttributeError, KeyError, OSError, RuntimeError,
                TypeError, UnicodeError, ValueError) as exc:
            raise BodySwayVisualReviewStoreV2Error(
                f"Visual review candidate v2 publication failed: {exc}"
            ) from exc

    def load_candidate(
        self, project_id: str, runtime_execution_bundle_sha256: str,
        candidate_sha256: str, *,
        execution: VerifiedBodySwayRuntimeExecution,
        preview: TemporaryBodySwayPreviewV2,
    ) -> BodySwayVisualReviewCandidateV2:
        try:
            loaded = reload_authoritative_runtime_execution_v2(
                self.state_root, execution,
            )
            project = require_safe_token(project_id, "Visual review v2 project")
            bundle_sha = require_sha256(
                runtime_execution_bundle_sha256, "Runtime execution bundle",
            )
            digest = require_sha256(candidate_sha256, "Visual candidate v2")
            if loaded.project_id != project \
                    or loaded.bundle_sha256 != bundle_sha:
                raise BodySwayVisualReviewStoreV2Error(
                    "Candidate v2 address differs from its execution"
                )
            payload = read_document(
                self.state_root, project, CANDIDATE_NAMESPACE,
                bundle_sha, digest,
            )
            document = strict_json_object(payload, "Visual review candidate v2")
            require_body_sway_visual_review_candidate_v2(
                document, execution=loaded, preview=preview,
            )
            if body_sway_visual_review_candidate_sha256_v2(document) != digest:
                raise BodySwayVisualReviewStoreV2Error(
                    "Candidate v2 bytes differ from their address"
                )
            return BodySwayVisualReviewCandidateV2(payload.decode("utf-8"))
        except BodySwayVisualReviewStoreV2Error:
            raise
        except (AttributeError, KeyError, OSError, RuntimeError,
                TypeError, UnicodeError, ValueError) as exc:
            raise BodySwayVisualReviewStoreV2Error(
                f"Visual review candidate v2 load failed: {exc}"
            ) from exc

    def publish_decision(
        self, decision: BodySwayVisualReviewDecisionV2, *,
        candidates: BodySwayVisualReviewCandidateV2,
        execution: VerifiedBodySwayRuntimeExecution,
        preview: TemporaryBodySwayPreviewV2,
    ) -> PublishedBodySwayVisualReviewDocumentV2:
        try:
            result = publish_visual_review_decision_v2(
                self.state_root, decision, candidates, execution, preview,
            )
            return PublishedBodySwayVisualReviewDocumentV2(
                result.path, result.sha256, result.reused,
            )
        except BodySwayVisualReviewRevisionV2Conflict:
            raise
        except BodySwayVisualReviewHistoryV2Error as exc:
            raise BodySwayVisualReviewStoreV2Error(
                f"Visual review decision v2 publication failed: {exc}"
            ) from exc

    def snapshot_history(
        self, *, candidates: BodySwayVisualReviewCandidateV2,
        execution: VerifiedBodySwayRuntimeExecution,
        preview: TemporaryBodySwayPreviewV2,
    ) -> BodySwayVisualReviewHistorySnapshotV2:
        try:
            return snapshot_visual_review_history_v2(
                self.state_root, candidates, execution, preview,
            )
        except BodySwayVisualReviewHistoryV2Error as exc:
            raise BodySwayVisualReviewStoreV2Error(
                f"Visual review history v2 snapshot failed: {exc}"
            ) from exc

    def load_decision(
        self, project_id: str, candidate_sha256: str,
        decision_sha256: str, *,
        candidates: BodySwayVisualReviewCandidateV2,
        execution: VerifiedBodySwayRuntimeExecution,
        preview: TemporaryBodySwayPreviewV2,
    ) -> BodySwayVisualReviewDecisionV2:
        try:
            return load_visual_review_decision_v2(
                self.state_root, project_id, candidate_sha256,
                decision_sha256, candidates=candidates,
                execution=execution, preview=preview,
            )
        except BodySwayVisualReviewHistoryV2Error as exc:
            raise BodySwayVisualReviewStoreV2Error(
                f"Visual review decision v2 load failed: {exc}"
            ) from exc
