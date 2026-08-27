"""Compile-time current-head observations for P10.5d inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .body_sway_dynamic_seam_source import (
    BodySwayDynamicSeamSourceError,
    require_body_sway_dynamic_seam_source,
)
from .body_sway_visual_review_address import (
    ExactVisualReviewAddress,
    ExactVisualReviewAddressError,
)
from .p10_amplitude_envelope_commands import (
    P10AmplitudeEnvelopeCommandError,
    require_unchanged_visual_review_head,
)
from .reviewed_seam_anchor_set_inputs import (
    PreparedReviewedSeamAnchorSet,
    ReviewedSeamAnchorSetInputsError,
    prepare_current_head_reviewed_seam_anchor_set,
)
from .reviewed_seam_anchor_set_validation import (
    ReviewedSeamAnchorSetValidationError,
    reviewed_seam_anchor_set_sha256,
)
from .seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
    ExactSeamAnchorReviewAddressError,
)
from .seam_anchor_review_json import canonical_json_bytes


class BodySwayDynamicSeamHeadCheckError(RuntimeError):
    """Raised when either exact review identity is no longer current."""


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamHeadIdentity:
    """Frozen path-free addresses and heads extracted from one exact source."""

    source_set_sha256: str
    project_id: str
    visual_address: ExactVisualReviewAddress
    visual_candidate_sha256: str
    visual_revision: int
    visual_decision_sha256: str
    seam_address: ExactSeamAnchorReviewAddress
    seam_candidate_sha256: str
    seam_revision: int
    seam_decision_sha256: str
    reviewed_seam_anchor_set_sha256: str

    def public_document(self) -> dict[str, Any]:
        return {
            "source_set_sha256": self.source_set_sha256,
            "project_id": self.project_id,
            "visual_review": {
                "address": self.visual_address.public_document(),
                "candidate_sha256": self.visual_candidate_sha256,
                "revision": self.visual_revision,
                "decision_sha256": self.visual_decision_sha256,
            },
            "seam_anchor_review": {
                "address": self.seam_address.public_document(),
                "candidate_sha256": self.seam_candidate_sha256,
                "revision": self.seam_revision,
                "decision_sha256": self.seam_decision_sha256,
            },
            "reviewed_seam_anchor_set_sha256":
                self.reviewed_seam_anchor_set_sha256,
        }


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamHeadObservation:
    """Frozen statement of two heads observed only at compile time."""

    identity: BodySwayDynamicSeamHeadIdentity = field(repr=False)
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")


def extract_body_sway_dynamic_seam_head_identity(
    source: Mapping[str, Any],
) -> BodySwayDynamicSeamHeadIdentity:
    """Fully replay one source before extracting its two exact heads."""

    try:
        admitted = require_body_sway_dynamic_seam_source(source)
        return _extract_identity(admitted)
    except BodySwayDynamicSeamHeadCheckError:
        raise
    except _FAILURES as exc:
        raise BodySwayDynamicSeamHeadCheckError(
            f"Dynamic seam head identity extraction failed: {exc}"
        ) from exc


def require_current_body_sway_dynamic_seam_heads(
    state_root: Path,
    source: Mapping[str, Any],
) -> BodySwayDynamicSeamHeadObservation:
    """Observe both current heads and replay the exact reviewed set once."""

    try:
        admitted = require_body_sway_dynamic_seam_source(source)
        identity = _extract_identity(admitted)
        state = Path(state_root)
        require_unchanged_visual_review_head(
            state,
            *identity.visual_address.reader_arguments,
            identity.visual_candidate_sha256,
            identity.visual_revision,
            identity.visual_decision_sha256,
        )
        prepared = prepare_current_head_reviewed_seam_anchor_set(
            state,
            identity.seam_address,
            candidate_sha256=identity.seam_candidate_sha256,
            revision=identity.seam_revision,
            decision_sha256=identity.seam_decision_sha256,
        )
        _require_exact_prepared_set(prepared, admitted, identity)
        document = {
            "method": (
                "visual-review-double-snapshot-plus-seam-review-history-a-b"
            ),
            "scope": "compile_time",
            "identity": identity.public_document(),
            "checks": {
                "visual_review_head": "observed_current",
                "seam_anchor_review_head": "observed_current",
                "reviewed_seam_anchor_set": "canonical_replay_matched",
            },
            "permanent_authority_claimed": False,
        }
        return BodySwayDynamicSeamHeadObservation(
            identity,
            canonical_json_bytes(document).decode("utf-8"),
        )
    except BodySwayDynamicSeamHeadCheckError:
        raise
    except _FAILURES as exc:
        raise BodySwayDynamicSeamHeadCheckError(
            f"Dynamic seam current-head observation failed: {exc}"
        ) from exc


def _extract_identity(source: dict[str, Any]) \
        -> BodySwayDynamicSeamHeadIdentity:
    proof = source["body_sway_continuous_preview_proof"]
    admission = proof["source"]["amplitude_envelope_candidate"]["source"] \
        ["review_admission"]
    capture = admission["source"]["capture"]
    visual = admission["source"]["visual_review"]
    reviewed_set = source["reviewed_seam_anchor_set"]
    seam = reviewed_set["source"]
    project_id = proof["project_id"]
    if capture["project_id"] != project_id \
            or admission["project_id"] != project_id \
            or reviewed_set["project_id"] != project_id:
        raise BodySwayDynamicSeamHeadCheckError(
            "Dynamic seam review projects are cross-wired"
        )
    reviewed_sha = reviewed_seam_anchor_set_sha256(reviewed_set)
    if reviewed_sha != source["reviewed_seam_anchor_set_sha256"] \
            or visual["decision_sha256"] \
                != visual["head_decision_sha256"]:
        raise BodySwayDynamicSeamHeadCheckError(
            "Dynamic seam embedded head identity is inconsistent"
        )
    return BodySwayDynamicSeamHeadIdentity(
        source["source_set_sha256"], project_id,
        ExactVisualReviewAddress(
            project_id, capture["temporary_preview_sha256"],
            capture["runtime_capture_bundle_sha256"],
            capture["capture_artifact_set_sha256"],
        ),
        visual["candidate_sha256"], visual["revision"],
        visual["decision_sha256"],
        ExactSeamAnchorReviewAddress(
            project_id, seam["layer_manifest_sha256"],
            seam["p3_rig_sha256"], seam["p3_bundle_sha256"],
        ),
        seam["seam_anchor_candidate_sha256"], seam["review_revision"],
        seam["seam_anchor_review_decision_sha256"], reviewed_sha,
    )


def _require_exact_prepared_set(prepared, source, identity) -> None:
    expected = canonical_json_bytes(source["reviewed_seam_anchor_set"])
    if type(prepared) is not PreparedReviewedSeamAnchorSet \
            or prepared.reviewed_seam_anchor_set_sha256 \
                != identity.reviewed_seam_anchor_set_sha256 \
            or prepared.canonical_bytes != expected:
        raise BodySwayDynamicSeamHeadCheckError(
            "Current seam head compiled a different reviewed anchor set"
        )


_FAILURES = (
    AttributeError,
    BodySwayDynamicSeamSourceError,
    ExactSeamAnchorReviewAddressError,
    ExactVisualReviewAddressError,
    KeyError,
    OSError,
    OverflowError,
    P10AmplitudeEnvelopeCommandError,
    RecursionError,
    ReviewedSeamAnchorSetInputsError,
    ReviewedSeamAnchorSetValidationError,
    RuntimeError,
    TypeError,
    UnicodeError,
    ValueError,
)
