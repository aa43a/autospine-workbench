"""Exact application services for P10.5c reviewed seam-anchor sets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .reviewed_seam_anchor_set_bundle_reader import (
    VerifiedReviewedSeamAnchorSetBundleReader,
    VerifiedReviewedSeamAnchorSetBundleReaderError,
)
from .reviewed_seam_anchor_set_bundle_store import (
    ReviewedSeamAnchorSetBundleStore,
    ReviewedSeamAnchorSetBundleStoreError,
)
from .reviewed_seam_anchor_set_compiler import ReviewedSeamAnchorSet
from .reviewed_seam_anchor_set_inputs import (
    ReviewedSeamAnchorSetInputsError,
    prepare_current_head_reviewed_seam_anchor_set,
)
from .seam_anchor_candidates import SeamAnchorCandidates
from .seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
    ExactSeamAnchorReviewAddressError,
)
from .seam_anchor_review_decision import SeamAnchorReviewDecision
from .seam_anchor_review_json import canonical_json_bytes


class ReviewedSeamAnchorSetCommandError(RuntimeError):
    """Raised when an exact P10.5c command cannot prove its result."""


@dataclass(frozen=True, slots=True)
class ReviewedSeamAnchorSetCommandResult:
    """Path-free identity and claims for one verified P10.5c bundle."""

    mode: str
    project_id: str
    layer_manifest_sha256: str
    p3_rig_sha256: str
    p3_bundle_sha256: str
    candidate_sha256: str
    decision_sha256: str
    review_revision: int
    reviewed_set_sha256: str
    bundle_sha256: str
    artifact_status: str
    release_gate_status: str
    release_gate_reason_codes: tuple[str, ...]
    relationship_count: int
    anchor_pair_count: int
    head_observation_method: str | None = None
    head_observation_scope: str | None = None
    permanent_authority_claimed: bool | None = None

    @property
    def source(self) -> dict[str, str | int]:
        return {
            "layer_manifest_sha256": self.layer_manifest_sha256,
            "p3_rig_sha256": self.p3_rig_sha256,
            "p3_bundle_sha256": self.p3_bundle_sha256,
            "seam_anchor_candidate_sha256": self.candidate_sha256,
            "review_revision": self.review_revision,
            "seam_anchor_review_decision_sha256": self.decision_sha256,
        }

    @property
    def output(self) -> dict[str, str]:
        return {
            "reviewed_set_sha256": self.reviewed_set_sha256,
            "bundle_sha256": self.bundle_sha256,
        }

    @property
    def head_observation(self) -> dict[str, Any] | None:
        if self.head_observation_method is None:
            return None
        return {
            "method": self.head_observation_method,
            "scope": self.head_observation_scope,
            "revision": self.review_revision,
            "head_decision_sha256": self.decision_sha256,
            "permanent_authority_claimed": self.permanent_authority_claimed,
        }


def compile_reviewed_seam_anchor_set_command(
    state_root: Path,
    project_id: str,
    *,
    layer_manifest_sha256: str,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    candidate_sha256: str,
    review_revision: int,
    decision_sha256: str,
) -> ReviewedSeamAnchorSetCommandResult:
    """Observe current head, publish frozen exact values, then read back."""

    try:
        address = ExactSeamAnchorReviewAddress(
            project_id,
            layer_manifest_sha256,
            p3_rig_sha256,
            p3_bundle_sha256,
        )
        prepared = prepare_current_head_reviewed_seam_anchor_set(
            state_root,
            address,
            candidate_sha256=candidate_sha256,
            revision=review_revision,
            decision_sha256=decision_sha256,
        )
        candidates = SeamAnchorCandidates(_canonical(
            prepared.inputs.candidate_document
        ))
        decision = SeamAnchorReviewDecision(_canonical(
            prepared.inputs.decision_document
        ))
        reviewed_set = ReviewedSeamAnchorSet(
            prepared.canonical_bytes.decode("utf-8")
        )
        published = ReviewedSeamAnchorSetBundleStore(state_root).publish(
            candidates,
            decision,
            prepared.inputs.rig_document,
            reviewed_set,
        )
        if (
            published.project_id != project_id
            or published.candidate_sha256 != candidate_sha256
            or published.decision_sha256 != decision_sha256
            or published.review_revision != review_revision
            or published.set_sha256
            != prepared.reviewed_seam_anchor_set_sha256
        ):
            raise ReviewedSeamAnchorSetCommandError(
                "Published reviewed seam-anchor identity differs"
            )
        verified = VerifiedReviewedSeamAnchorSetBundleReader(
            state_root
        ).load(project_id, published.set_sha256, published.bundle_sha256)
        return _result(
            "compiled",
            verified,
            head_observation=prepared.head_observation,
        )
    except ReviewedSeamAnchorSetCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise ReviewedSeamAnchorSetCommandError(
            "Reviewed seam-anchor set compilation failed"
        ) from exc


def verify_reviewed_seam_anchor_set_command(
    state_root: Path,
    project_id: str,
    *,
    reviewed_set_sha256: str,
    bundle_sha256: str,
) -> ReviewedSeamAnchorSetCommandResult:
    """Read and replay one explicit historical P10.5c address."""

    try:
        verified = VerifiedReviewedSeamAnchorSetBundleReader(
            state_root
        ).load(project_id, reviewed_set_sha256, bundle_sha256)
        return _result("verified", verified)
    except ReviewedSeamAnchorSetCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise ReviewedSeamAnchorSetCommandError(
            "Reviewed seam-anchor set verification failed"
        ) from exc


def _result(mode: str, verified, *, head_observation=None):
    document = verified.reviewed_set
    source = document["source"]
    release_gate = document["release_gate"]
    summary = document["summary"]
    return ReviewedSeamAnchorSetCommandResult(
        mode=mode,
        project_id=verified.project_id,
        layer_manifest_sha256=source["layer_manifest_sha256"],
        p3_rig_sha256=source["p3_rig_sha256"],
        p3_bundle_sha256=source["p3_bundle_sha256"],
        candidate_sha256=verified.candidate_sha256,
        decision_sha256=verified.decision_sha256,
        review_revision=verified.review_revision,
        reviewed_set_sha256=verified.set_sha256,
        bundle_sha256=verified.bundle_sha256,
        artifact_status=document["status"],
        release_gate_status=release_gate["status"],
        release_gate_reason_codes=tuple(release_gate["reason_codes"]),
        relationship_count=summary["relationship_count"],
        anchor_pair_count=summary["anchor_pair_count"],
        head_observation_method=(
            None if head_observation is None else head_observation["method"]
        ),
        head_observation_scope=(
            None if head_observation is None else head_observation["scope"]
        ),
        permanent_authority_claimed=(
            None if head_observation is None
            else head_observation["permanent_authority_claimed"]
        ),
    )


def _canonical(value: dict) -> str:
    return canonical_json_bytes(value).decode("utf-8")


_DOMAIN_ERRORS = (
    AttributeError,
    ExactSeamAnchorReviewAddressError,
    KeyError,
    OSError,
    OverflowError,
    RecursionError,
    ReviewedSeamAnchorSetBundleStoreError,
    ReviewedSeamAnchorSetInputsError,
    TypeError,
    UnicodeError,
    ValueError,
    VerifiedReviewedSeamAnchorSetBundleReaderError,
)
