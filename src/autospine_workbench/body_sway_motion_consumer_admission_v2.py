"""Seal a P10.6a v2 core with equal before/after v2 head observations."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_head_checks_v2 import (
    BodySwayDynamicSeamHeadObservationV2,
)
from .body_sway_motion_consumer_core_v2 import (
    BodySwayMotionConsumerAdmissionCoreV2,
    BodySwayMotionConsumerAdmissionV2Error,
    compile_body_sway_motion_consumer_admission_core_v2,
)
from .body_sway_motion_consumer_profile_v2 import (
    FORMAT,
    FORMAT_VERSION,
    MAX_DOCUMENT_BYTES,
    body_sway_head_observations_sha256_v2,
    body_sway_motion_consumer_claims_v2,
    body_sway_motion_consumer_release_gate_v2,
)
from .seam_anchor_review_json import canonical_json_bytes


TOP_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "core_sha256",
    "source", "motion_domain", "profile", "head_observations", "claims",
    "status", "release_gate", "summary",
}
OBSERVATION_DOCUMENT_FIELDS = {
    "method", "scope", "identity_sha256", "identity", "checks",
    "permanent_authority_claimed",
}
HEAD_OBSERVATION_FIELDS = {
    "method", "scope", "before", "after", "observations_match",
    "permanent_authority_claimed", "head_observations_sha256",
}


@dataclass(frozen=True, slots=True)
class BodySwayMotionConsumerAdmissionV2:
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def seal_body_sway_motion_consumer_admission_v2(
    core: BodySwayMotionConsumerAdmissionCoreV2,
    before: BodySwayDynamicSeamHeadObservationV2,
    after: BodySwayDynamicSeamHeadObservationV2,
) -> BodySwayMotionConsumerAdmissionV2:
    """Require unchanged current v2 heads around frozen pure compilation."""

    try:
        if type(core) is not BodySwayMotionConsumerAdmissionCoreV2:
            raise BodySwayMotionConsumerAdmissionV2Error(
                "Motion consumer v2 seal requires an exact frozen core"
            )
        before_document = _require_observation(before, core, "before")
        after_document = _require_observation(after, core, "after")
        if before.identity_sha256 != after.identity_sha256 \
                or before.canonical_bytes != after.canonical_bytes:
            raise BodySwayMotionConsumerAdmissionV2Error(
                "Motion consumer v2 heads changed during compilation"
            )
        head_evidence = _head_evidence(
            before_document, after_document,
            before.canonical_bytes, after.canonical_bytes,
        )
        core_document = core.document
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": core_document["project_id"],
            "clip_id": core_document["clip_id"],
            "core_sha256": core.sha256,
            "source": core_document["source"],
            "motion_domain": core_document["motion_domain"],
            "profile": core_document["profile"],
            "head_observations": head_evidence,
            "claims": body_sway_motion_consumer_claims_v2(),
            "status": "setup_local_timeline_compilation_admitted",
            "release_gate": body_sway_motion_consumer_release_gate_v2(),
            "summary": {
                **core_document["summary"],
                "head_observation_count": 2,
            },
        }
        encoded = canonical_json_bytes(document)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise BodySwayMotionConsumerAdmissionV2Error(
                "Motion consumer v2 admission exceeds its byte limit"
            )
        return BodySwayMotionConsumerAdmissionV2(encoded.decode("utf-8"))
    except BodySwayMotionConsumerAdmissionV2Error:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerAdmissionV2Error(
            f"Motion consumer v2 admission seal failed: {exc}"
        ) from exc


def observation_from_document_v2(
    core: BodySwayMotionConsumerAdmissionCoreV2,
    document: Any,
) -> BodySwayDynamicSeamHeadObservationV2:
    """Rebuild one typed compile-time observation for semantic replay."""

    if type(core) is not BodySwayMotionConsumerAdmissionCoreV2 \
            or type(document) is not dict:
        raise BodySwayMotionConsumerAdmissionV2Error(
            "Motion consumer v2 observation replay input is invalid"
        )
    encoded = canonical_json_bytes(document)
    observation = BodySwayDynamicSeamHeadObservationV2(
        document.get("identity_sha256"), encoded.decode("utf-8"),
    )
    _require_observation(observation, core, "replayed")
    return observation


def _require_observation(observation, core, label):
    if type(observation) is not BodySwayDynamicSeamHeadObservationV2 \
            or observation.identity_sha256 != core.head_identity_sha256:
        raise BodySwayMotionConsumerAdmissionV2Error(
            f"Motion consumer v2 {label} head identity differs from source"
        )
    document = observation.document
    if type(document) is not dict \
            or set(document) != OBSERVATION_DOCUMENT_FIELDS \
            or observation.canonical_bytes != canonical_json_bytes(
                core.expected_head_observation
            ):
        raise BodySwayMotionConsumerAdmissionV2Error(
            f"Motion consumer v2 {label} head observation is unsupported"
        )
    return document


def _head_evidence(before, after, before_bytes, after_bytes):
    evidence = {
        "method": "before-after-current-v2-head-recheck",
        "scope": "compile_time",
        "before": {
            "observation": before,
            "canonical_sha256": hashlib.sha256(before_bytes).hexdigest(),
        },
        "after": {
            "observation": after,
            "canonical_sha256": hashlib.sha256(after_bytes).hexdigest(),
        },
        "observations_match": True,
        "permanent_authority_claimed": False,
    }
    evidence["head_observations_sha256"] = (
        body_sway_head_observations_sha256_v2(evidence)
    )
    return evidence


__all__ = [
    "BodySwayMotionConsumerAdmissionCoreV2",
    "BodySwayMotionConsumerAdmissionV2",
    "BodySwayMotionConsumerAdmissionV2Error", "HEAD_OBSERVATION_FIELDS",
    "OBSERVATION_DOCUMENT_FIELDS", "TOP_FIELDS",
    "compile_body_sway_motion_consumer_admission_core_v2",
    "observation_from_document_v2",
    "seal_body_sway_motion_consumer_admission_v2",
]
