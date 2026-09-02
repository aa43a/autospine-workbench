"""Compile-time current-head observations for P10.5d v2 inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json

from .body_sway_dynamic_seam_validation_v2 import (
    BodySwayDynamicSeamSourceV2ValidationError,
    require_body_sway_dynamic_seam_source_v2,
)
from .body_sway_review_admission_consumer_v2 import (
    BodySwayReviewAdmissionV2ConsumerError,
    require_current_body_sway_review_admission_v2,
)
from .project_store import ProjectStore, ProjectStoreError
from .reviewed_seam_anchor_set_inputs import (
    PreparedReviewedSeamAnchorSet,
    ReviewedSeamAnchorSetInputsError,
    prepare_current_head_reviewed_seam_anchor_set,
)
from .seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
    ExactSeamAnchorReviewAddressError,
)
from .seam_anchor_review_json import canonical_json_bytes


class BodySwayDynamicSeamHeadCheckV2Error(RuntimeError):
    """Raised when either current review head differs from exact source."""


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamHeadObservationV2:
    identity_sha256: str
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")


def require_current_body_sway_dynamic_seam_heads_v2(
    capture_job_reader,
    project_store: ProjectStore,
    source,
) -> BodySwayDynamicSeamHeadObservationV2:
    """Validate source, then observe both current review heads exactly."""

    try:
        admitted = require_body_sway_dynamic_seam_source_v2(source)
        return _observe_admitted_body_sway_dynamic_seam_heads_v2(
            capture_job_reader, project_store, admitted,
        )
    except BodySwayDynamicSeamHeadCheckV2Error:
        raise
    except _FAILURES as exc:
        raise BodySwayDynamicSeamHeadCheckV2Error(
            "Dynamic seam v2 current-head verification failed"
        ) from exc


def _observe_admitted_body_sway_dynamic_seam_heads_v2(
    capture_job_reader,
    project_store: ProjectStore,
    source,
) -> BodySwayDynamicSeamHeadObservationV2:
    if type(project_store) is not ProjectStore \
            or not callable(getattr(capture_job_reader, "get", None)):
        raise BodySwayDynamicSeamHeadCheckV2Error(
            "Dynamic seam v2 head check requires read-only stores"
        )
    proof = source["body_sway_continuous_preview_proof_v2"]
    amplitude = proof["source"]["amplitude_envelope_candidate_v2"]
    amplitude_source = amplitude["source"]
    admission = amplitude_source["review_admission_v2"]
    current_visual = require_current_body_sway_review_admission_v2(
        capture_job_reader, project_store, admission,
    )
    if current_visual.admission_sha256 \
            != amplitude_source["review_admission_v2_sha256"]:
        raise BodySwayDynamicSeamHeadCheckV2Error(
            "Dynamic seam v2 visual admission identity changed"
        )
    reviewed_set = source["reviewed_seam_anchor_set_v1"]
    seam = reviewed_set["source"]
    address = ExactSeamAnchorReviewAddress(
        source["project_id"], seam["layer_manifest_sha256"],
        seam["p3_rig_sha256"], seam["p3_bundle_sha256"],
    )
    prepared = prepare_current_head_reviewed_seam_anchor_set(
        project_store.state_root, address,
        candidate_sha256=seam["seam_anchor_candidate_sha256"],
        revision=seam["review_revision"],
        decision_sha256=seam["seam_anchor_review_decision_sha256"],
    )
    if type(prepared) is not PreparedReviewedSeamAnchorSet \
            or prepared.reviewed_seam_anchor_set_sha256 \
                != source["reviewed_seam_anchor_set_v1_sha256"] \
            or prepared.canonical_bytes != canonical_json_bytes(reviewed_set):
        raise BodySwayDynamicSeamHeadCheckV2Error(
            "Dynamic seam v2 seam head compiled different reviewed anchors"
        )
    identity = {
        "source_set_sha256": source["source_set_sha256"],
        "project_id": source["project_id"],
        "visual_review_v2": {
            "admission_sha256": current_visual.admission_sha256,
            "candidate_sha256": admission["source"]["visual_review"]
                ["candidate_v2_sha256"],
            "revision": admission["source"]["visual_review"]["revision"],
            "decision_sha256": admission["source"]["visual_review"]
                ["decision_v2_sha256"],
        },
        "seam_anchor_review_v1": {
            "candidate_sha256": seam["seam_anchor_candidate_sha256"],
            "revision": seam["review_revision"],
            "decision_sha256": seam[
                "seam_anchor_review_decision_sha256"
            ],
            "reviewed_set_sha256":
                source["reviewed_seam_anchor_set_v1_sha256"],
        },
    }
    from .resolved_project import canonical_sha256
    identity_sha = canonical_sha256(identity)
    document = {
        "method": "visual-v2-recompile-plus-seam-v1-history-replay",
        "scope": "compile_time",
        "identity_sha256": identity_sha,
        "identity": identity,
        "checks": {
            "visual_review_v2_head": "observed_current",
            "seam_anchor_review_v1_head": "observed_current",
            "reviewed_seam_anchor_set_v1": "canonical_replay_matched",
        },
        "permanent_authority_claimed": False,
    }
    return BodySwayDynamicSeamHeadObservationV2(
        identity_sha, canonical_json_bytes(document).decode("utf-8"),
    )


_FAILURES = (
    AttributeError, BodySwayDynamicSeamSourceV2ValidationError,
    BodySwayReviewAdmissionV2ConsumerError, ExactSeamAnchorReviewAddressError,
    KeyError, OSError, OverflowError, ProjectStoreError, RecursionError,
    ReviewedSeamAnchorSetInputsError, RuntimeError, TypeError,
    UnicodeError, ValueError,
)


__all__ = [
    "BodySwayDynamicSeamHeadCheckV2Error",
    "BodySwayDynamicSeamHeadObservationV2",
    "require_current_body_sway_dynamic_seam_heads_v2",
]
