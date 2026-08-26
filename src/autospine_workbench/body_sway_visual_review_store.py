"""Authoritative write-once facade for P10.3c candidates and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .body_sway_runtime_capture_binding import (
    BodySwayRuntimeCaptureBindingError,
    reload_authoritative_runtime_capture,
)
from .body_sway_runtime_capture_reader import VerifiedBodySwayRuntimeCapture
from .body_sway_visual_review_candidate import BodySwayVisualReviewCandidate
from .body_sway_visual_review_candidate_validation import (
    BodySwayVisualReviewCandidateValidationError,
    body_sway_visual_review_candidate_sha256,
    require_body_sway_visual_review_candidate,
)
from .body_sway_visual_review_decision import BodySwayVisualReviewDecision
from .body_sway_visual_review_errors import (
    BodySwayVisualReviewHistoryError,
    BodySwayVisualReviewRevisionConflict,
    BodySwayVisualReviewStoreError,
)
from .body_sway_visual_review_history import (
    load_visual_review_decision,
    publish_visual_review_decision,
)
from .body_sway_visual_review_history_snapshot import (
    BodySwayVisualReviewHistorySnapshot,
    snapshot_visual_review_history,
)
from .body_sway_visual_review_profile import (
    CANDIDATE_NAMESPACE,
    DECISION_NAMESPACE,
)
from .body_sway_visual_review_store_files import (
    BodySwayVisualReviewFilesError,
    exact_payload,
    publication_parent,
    publish_document,
    read_document,
)
from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_bundle_files import Spine42BundleFilesError


@dataclass(frozen=True, slots=True)
class PublishedBodySwayVisualReviewDocument:
    path: Path
    sha256: str
    reused: bool


class BodySwayVisualReviewStore:
    """Replay stored capture/candidate evidence at every authority boundary."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish_candidate(
        self,
        candidate: BodySwayVisualReviewCandidate,
        capture: VerifiedBodySwayRuntimeCapture,
    ) -> PublishedBodySwayVisualReviewDocument:
        """Publish only after authoritative four-part capture replay."""
        try:
            if type(candidate) is not BodySwayVisualReviewCandidate:
                raise BodySwayVisualReviewStoreError(
                    "Candidate publication requires an exact value object"
                )
            loaded_capture = reload_authoritative_runtime_capture(
                self.state_root, capture
            )
            document = candidate.document
            require_body_sway_visual_review_candidate(
                document, capture=loaded_capture
            )
            digest = body_sway_visual_review_candidate_sha256(document)
            payload = exact_payload(candidate.canonical_bytes, document, digest)
            parent = publication_parent(
                self.state_root,
                document["project_id"],
                CANDIDATE_NAMESPACE,
                loaded_capture.bundle_sha256,
            )
            path, reused = publish_document(parent, digest, payload)
            return PublishedBodySwayVisualReviewDocument(path, digest, reused)
        except BodySwayVisualReviewStoreError:
            raise
        except _FAILURES as exc:
            raise BodySwayVisualReviewStoreError(
                f"Visual review candidate publication failed: {exc}"
            ) from exc

    def load_candidate(
        self,
        project_id: str,
        runtime_capture_bundle_sha256: str,
        candidate_sha256: str,
        *,
        capture: VerifiedBodySwayRuntimeCapture,
    ) -> BodySwayVisualReviewCandidate:
        """Load one candidate only after authoritative capture replay."""
        try:
            loaded_capture = reload_authoritative_runtime_capture(
                self.state_root, capture
            )
            project = require_safe_token(project_id, "Visual review project id")
            bundle_sha = require_sha256(
                runtime_capture_bundle_sha256, "Runtime capture bundle digest"
            )
            digest = require_sha256(candidate_sha256, "Visual candidate digest")
            if loaded_capture.project_id != project \
                    or loaded_capture.bundle_sha256 != bundle_sha:
                raise BodySwayVisualReviewStoreError(
                    "Candidate address differs from its stored capture"
                )
            payload = read_document(
                self.state_root, project, CANDIDATE_NAMESPACE, bundle_sha, digest
            )
            document = strict_json_object(payload, "Visual review candidate")
            require_body_sway_visual_review_candidate(
                document, capture=loaded_capture
            )
            if body_sway_visual_review_candidate_sha256(document) != digest:
                raise BodySwayVisualReviewStoreError(
                    "Visual review candidate bytes differ from their address"
                )
            return BodySwayVisualReviewCandidate(payload.decode("utf-8"))
        except BodySwayVisualReviewStoreError:
            raise
        except _FAILURES as exc:
            raise BodySwayVisualReviewStoreError(
                f"Visual review candidate load failed: {exc}"
            ) from exc

    def publish_decision(
        self,
        decision: BodySwayVisualReviewDecision,
        *,
        candidates: BodySwayVisualReviewCandidate,
        capture: VerifiedBodySwayRuntimeCapture,
    ) -> PublishedBodySwayVisualReviewDocument:
        """Append through the strict linear revision-slot authority."""
        try:
            result = publish_visual_review_decision(
                self.state_root, decision, candidates, capture
            )
            return PublishedBodySwayVisualReviewDocument(
                result.path, result.sha256, result.reused
            )
        except BodySwayVisualReviewRevisionConflict:
            raise
        except BodySwayVisualReviewHistoryError as exc:
            raise BodySwayVisualReviewStoreError(
                f"Visual review decision publication failed: {exc}"
            ) from exc

    def snapshot_history(
        self,
        *,
        candidates: BodySwayVisualReviewCandidate,
        capture: VerifiedBodySwayRuntimeCapture,
    ) -> BodySwayVisualReviewHistorySnapshot:
        """Read the exact linear head and rows without mutating state."""
        try:
            return snapshot_visual_review_history(
                self.state_root, candidates, capture
            )
        except BodySwayVisualReviewHistoryError as exc:
            raise BodySwayVisualReviewStoreError(
                f"Visual review history snapshot failed: {exc}"
            ) from exc

    def load_decision(
        self,
        project_id: str,
        candidate_sha256: str,
        decision_sha256: str,
        *,
        candidates: BodySwayVisualReviewCandidate,
        capture: VerifiedBodySwayRuntimeCapture,
    ) -> BodySwayVisualReviewDecision:
        """Replay the full linear history before returning one revision."""
        try:
            return load_visual_review_decision(
                self.state_root,
                project_id,
                candidate_sha256,
                decision_sha256,
                candidates=candidates,
                capture=capture,
            )
        except BodySwayVisualReviewHistoryError as exc:
            raise BodySwayVisualReviewStoreError(
                f"Visual review decision load failed: {exc}"
            ) from exc


_FAILURES = (
    BodySwayRuntimeCaptureBindingError,
    BodySwayVisualReviewCandidateValidationError,
    BodySwayVisualReviewFilesError,
    LayerManifestError,
    SafeInputFileError,
    Spine42BundleFilesError,
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    UnicodeError,
    ValueError,
)
