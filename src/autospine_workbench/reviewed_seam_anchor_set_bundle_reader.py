"""Exact historical reader for reviewed seam-anchor set bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .immutable_bundle_fs import ImmutableBundleFSError
from .reviewed_seam_anchor_set_bundle_contract import DOCUMENT_NAMES
from .reviewed_seam_anchor_set_bundle_fs import (
    ReviewedSeamAnchorSetBundleFSError,
    reviewed_seam_anchor_set_bundle_fs,
)
from .reviewed_seam_anchor_set_bundle_integrity import (
    ReviewedSeamAnchorSetBundleIntegrityError,
    VerifiedReviewedSeamAnchorSetBundle,
    reviewed_seam_anchor_set_bundle_documents,
    verify_reviewed_seam_anchor_set_bundle_snapshot,
)
from .reviewed_seam_anchor_set_compiler import (
    ReviewedSeamAnchorSetCompilerError,
    compile_reviewed_seam_anchor_set,
)
from .seam_anchor_candidate_validation import (
    SeamAnchorCandidateValidationError,
    seam_anchor_candidates_sha256,
)
from .seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
    ExactSeamAnchorReviewAddressError,
)
from .seam_anchor_review_candidate_binding import (
    SeamAnchorReviewCandidateBindingError,
    load_bound_seam_anchor_review_candidate,
)
from .seam_anchor_review_decision_validation import (
    SeamAnchorReviewDecisionValidationError,
    seam_anchor_review_decision_sha256,
)
from .seam_anchor_review_errors import (
    SeamAnchorReviewHistoryError,
    SeamAnchorReviewStoreError,
)
from .seam_anchor_review_history import load_seam_anchor_review_decision


class VerifiedReviewedSeamAnchorSetBundleReaderError(RuntimeError):
    """Raised when an exact reviewed seam-anchor bundle cannot be replayed."""


@dataclass(frozen=True, slots=True)
class VerifiedReviewedSeamAnchorSetBundleReader:
    """Load only explicit set/bundle SHAs; never scan or use a latest alias."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self,
        project_id: str,
        set_sha256: str,
        bundle_sha256: str,
    ) -> VerifiedReviewedSeamAnchorSetBundle:
        """Replay P3, candidates, one historical decision, and the set."""

        try:
            snapshot = reviewed_seam_anchor_set_bundle_fs(
                self.state_root, project_id
            ).read(set_sha256, bundle_sha256)
            documents = reviewed_seam_anchor_set_bundle_documents(snapshot)
            candidates = documents[DOCUMENT_NAMES[0]]
            decision = documents[DOCUMENT_NAMES[1]]
            reviewed_set = documents[DOCUMENT_NAMES[2]]
            if candidates["project_id"] != project_id \
                    or reviewed_set["project_id"] != project_id:
                raise VerifiedReviewedSeamAnchorSetBundleReaderError(
                    "Reviewed seam-anchor project differs from address"
                )
            source = candidates["source"]
            address = ExactSeamAnchorReviewAddress(
                project_id,
                source["layer_manifest_sha256"],
                source["rig_sha256"],
                source["bundle_sha256"],
            )
            bound = load_bound_seam_anchor_review_candidate(
                self.state_root, address
            )
            candidate_sha = seam_anchor_candidates_sha256(candidates)
            if bound.candidates.sha256 != candidate_sha \
                    or bound.candidates.canonical_bytes \
                    != snapshot.file_bytes(DOCUMENT_NAMES[0]):
                raise VerifiedReviewedSeamAnchorSetBundleReaderError(
                    "Stored candidates differ from exact P3 replay"
                )
            decision_sha = seam_anchor_review_decision_sha256(decision)
            set_source = reviewed_set["source"]
            if set_source["seam_anchor_candidate_sha256"] != candidate_sha \
                    or set_source["seam_anchor_review_decision_sha256"] \
                    != decision_sha \
                    or set_source["review_revision"] \
                    != decision["review"]["revision"]:
                raise VerifiedReviewedSeamAnchorSetBundleReaderError(
                    "Reviewed set points to different review evidence"
                )
            historical = load_seam_anchor_review_decision(
                self.state_root,
                address,
                candidate_sha,
                decision_sha,
                candidates=bound.candidates,
                rig=bound.rig,
            )
            if historical.canonical_bytes \
                    != snapshot.file_bytes(DOCUMENT_NAMES[1]):
                raise VerifiedReviewedSeamAnchorSetBundleReaderError(
                    "Stored decision differs from authoritative revision"
                )
            rebuilt = compile_reviewed_seam_anchor_set(
                bound.candidates.document, historical.document, bound.rig
            )
            if rebuilt.canonical_bytes \
                    != snapshot.file_bytes(DOCUMENT_NAMES[2]):
                raise VerifiedReviewedSeamAnchorSetBundleReaderError(
                    "Stored reviewed set differs from exact recompilation"
                )
            return verify_reviewed_seam_anchor_set_bundle_snapshot(
                snapshot,
                expected_project_id=project_id,
                expected_set_sha256=set_sha256,
                expected_bundle_sha256=bundle_sha256,
                candidates=bound.candidates.document,
                decision=historical.document,
                rig=bound.rig,
            )
        except VerifiedReviewedSeamAnchorSetBundleReaderError:
            raise
        except _READER_ERRORS as exc:
            raise VerifiedReviewedSeamAnchorSetBundleReaderError(
                "Verified reviewed seam-anchor bundle load failed"
            ) from exc


_READER_ERRORS = (
    AttributeError,
    ExactSeamAnchorReviewAddressError,
    ImmutableBundleFSError,
    KeyError,
    OSError,
    OverflowError,
    RecursionError,
    ReviewedSeamAnchorSetBundleFSError,
    ReviewedSeamAnchorSetBundleIntegrityError,
    ReviewedSeamAnchorSetCompilerError,
    RuntimeError,
    SeamAnchorCandidateValidationError,
    SeamAnchorReviewCandidateBindingError,
    SeamAnchorReviewDecisionValidationError,
    SeamAnchorReviewHistoryError,
    SeamAnchorReviewStoreError,
    TypeError,
    UnicodeError,
    ValueError,
)
