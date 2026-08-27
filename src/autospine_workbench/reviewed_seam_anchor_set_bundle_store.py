"""Atomic publication for reviewed seam-anchor set bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .immutable_bundle_fs import ImmutableBundleFSError
from .reviewed_seam_anchor_set_bundle_contract import (
    ReviewedSeamAnchorSetBundleContractError,
    build_reviewed_seam_anchor_set_bundle_contract,
)
from .reviewed_seam_anchor_set_bundle_fs import (
    ReviewedSeamAnchorSetBundleFSError,
    reviewed_seam_anchor_set_bundle_fs,
)
from .reviewed_seam_anchor_set_bundle_integrity import (
    ReviewedSeamAnchorSetBundleIntegrityError,
    verify_reviewed_seam_anchor_set_bundle_snapshot,
)
from .reviewed_seam_anchor_set_compiler import ReviewedSeamAnchorSet
from .seam_anchor_candidates import SeamAnchorCandidates
from .seam_anchor_review_decision import SeamAnchorReviewDecision
from .seam_anchor_review_json import canonical_json_copy


class ReviewedSeamAnchorSetBundleStoreError(RuntimeError):
    """Raised when a reviewed seam-anchor bundle cannot be published."""


@dataclass(frozen=True, slots=True)
class PublishedReviewedSeamAnchorSetBundle:
    path: Path
    project_id: str
    candidate_sha256: str
    decision_sha256: str
    review_revision: int
    set_sha256: str
    bundle_sha256: str
    reused: bool


class ReviewedSeamAnchorSetBundleStore:
    """Publish exact value objects without deciding current-head authority."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self,
        candidates: SeamAnchorCandidates,
        decision: SeamAnchorReviewDecision,
        rig: dict,
        reviewed_set: ReviewedSeamAnchorSet,
    ) -> PublishedReviewedSeamAnchorSetBundle:
        """Fully validate and recompile before creating any state path."""

        try:
            if type(candidates) is not SeamAnchorCandidates \
                    or type(decision) is not SeamAnchorReviewDecision \
                    or type(rig) is not dict \
                    or type(reviewed_set) is not ReviewedSeamAnchorSet:
                raise ReviewedSeamAnchorSetBundleStoreError(
                    "Publication requires exact reviewed seam-anchor values"
                )
            candidate_document = canonical_json_copy(candidates.document)
            decision_document = canonical_json_copy(decision.document)
            rig_document = canonical_json_copy(rig)
            reviewed_set_document = canonical_json_copy(
                reviewed_set.document
            )
            contract = build_reviewed_seam_anchor_set_bundle_contract(
                candidate_document,
                decision_document,
                rig_document,
                reviewed_set_document,
            )
        except ReviewedSeamAnchorSetBundleStoreError:
            raise
        except (
            OverflowError,
            RecursionError,
            ReviewedSeamAnchorSetBundleContractError,
            RuntimeError,
            TypeError,
            UnicodeError,
            ValueError,
        ) as exc:
            raise ReviewedSeamAnchorSetBundleStoreError(
                "Reviewed seam-anchor publication input is invalid"
            ) from exc
        try:
            filesystem = reviewed_seam_anchor_set_bundle_fs(
                self.state_root, contract.project_id
            )
            published = filesystem.publish(
                contract.set_sha256,
                contract.bundle_sha256,
                contract.document_bytes,
            )
            snapshot = filesystem.read(
                contract.set_sha256, contract.bundle_sha256
            )
            verified = verify_reviewed_seam_anchor_set_bundle_snapshot(
                snapshot,
                expected_project_id=contract.project_id,
                expected_set_sha256=contract.set_sha256,
                expected_bundle_sha256=contract.bundle_sha256,
                candidates=candidate_document,
                decision=decision_document,
                rig=rig_document,
            )
            if verified.document_bytes != contract.document_bytes:
                raise ReviewedSeamAnchorSetBundleStoreError(
                    "Published reviewed seam-anchor bytes differ"
                )
            return PublishedReviewedSeamAnchorSetBundle(
                path=published.path,
                project_id=contract.project_id,
                candidate_sha256=contract.candidate_sha256,
                decision_sha256=contract.decision_sha256,
                review_revision=contract.review_revision,
                set_sha256=contract.set_sha256,
                bundle_sha256=contract.bundle_sha256,
                reused=published.reused,
            )
        except ReviewedSeamAnchorSetBundleStoreError:
            raise
        except (
            ImmutableBundleFSError,
            OSError,
            ReviewedSeamAnchorSetBundleFSError,
            ReviewedSeamAnchorSetBundleIntegrityError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise ReviewedSeamAnchorSetBundleStoreError(
                "Could not publish reviewed seam-anchor bundle"
            ) from exc
