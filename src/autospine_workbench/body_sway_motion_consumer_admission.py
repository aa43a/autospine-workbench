"""Seal a frozen P10.6a core with equal before/after head observations."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_head_checks import (
    BodySwayDynamicSeamHeadIdentity,
    BodySwayDynamicSeamHeadObservation,
)
from .body_sway_motion_consumer_core import (
    BodySwayMotionConsumerAdmissionCore,
    BodySwayMotionConsumerAdmissionError,
    compile_body_sway_motion_consumer_admission_core,
)
from .body_sway_motion_consumer_profile import (
    FORMAT,
    FORMAT_VERSION,
    MAX_DOCUMENT_BYTES,
    body_sway_head_observations_sha256,
    body_sway_motion_consumer_claims,
    body_sway_motion_consumer_release_gate,
)
from .seam_anchor_review_json import canonical_json_bytes


TOP_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "core_sha256",
    "source", "motion_domain", "profile", "head_observations", "claims",
    "status", "release_gate", "summary",
}
OBSERVATION_DOCUMENT_FIELDS = {
    "method", "scope", "identity", "checks", "permanent_authority_claimed",
}
HEAD_OBSERVATION_FIELDS = {
    "method", "scope", "before", "after", "observations_match",
    "permanent_authority_claimed", "head_observations_sha256",
}


@dataclass(frozen=True, slots=True)
class BodySwayMotionConsumerAdmission:
    """Frozen path-free consumer admission and canonical identity."""

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


def seal_body_sway_motion_consumer_admission(
    core: BodySwayMotionConsumerAdmissionCore,
    before: BodySwayDynamicSeamHeadObservation,
    after: BodySwayDynamicSeamHeadObservation,
) -> BodySwayMotionConsumerAdmission:
    """Require unchanged current heads around the frozen pure compilation."""

    try:
        if type(core) is not BodySwayMotionConsumerAdmissionCore:
            raise BodySwayMotionConsumerAdmissionError(
                "Motion consumer seal requires an exact frozen core"
            )
        before_document = _require_observation(
            before, core.head_identity, "before"
        )
        after_document = _require_observation(
            after, core.head_identity, "after"
        )
        if before.identity != after.identity \
                or before.canonical_bytes != after.canonical_bytes:
            raise BodySwayMotionConsumerAdmissionError(
                "Motion consumer heads changed during compilation"
            )
        head_evidence = _head_evidence(
            before_document, after_document,
            before.canonical_bytes, after.canonical_bytes,
        )
        core_document = core.document
        summary = {
            **core_document["summary"],
            "head_observation_count": 2,
        }
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
            "claims": body_sway_motion_consumer_claims(),
            "status": "setup_local_timeline_compilation_admitted",
            "release_gate": body_sway_motion_consumer_release_gate(),
            "summary": summary,
        }
        encoded = canonical_json_bytes(document)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise BodySwayMotionConsumerAdmissionError(
                "Motion consumer admission exceeds its byte limit"
            )
        return BodySwayMotionConsumerAdmission(encoded.decode("utf-8"))
    except BodySwayMotionConsumerAdmissionError:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerAdmissionError(
            f"Motion consumer admission seal failed: {exc}"
        ) from exc


def observation_from_document(
    identity: BodySwayDynamicSeamHeadIdentity,
    document: Any,
) -> BodySwayDynamicSeamHeadObservation:
    """Rebuild a typed observation for strict public semantic replay."""

    if type(identity) is not BodySwayDynamicSeamHeadIdentity \
            or type(document) is not dict:
        raise BodySwayMotionConsumerAdmissionError(
            "Motion consumer observation replay input is invalid"
        )
    encoded = canonical_json_bytes(document)
    observation = BodySwayDynamicSeamHeadObservation(
        identity, encoded.decode("utf-8")
    )
    _require_observation(observation, identity, "replayed")
    return observation


def _require_observation(observation, expected_identity, label):
    if type(observation) is not BodySwayDynamicSeamHeadObservation \
            or type(observation.identity) is not BodySwayDynamicSeamHeadIdentity \
            or observation.identity != expected_identity:
        raise BodySwayMotionConsumerAdmissionError(
            f"Motion consumer {label} head identity differs from the probe"
        )
    document = observation.document
    expected = _expected_observation_document(expected_identity)
    if type(document) is not dict or set(document) != OBSERVATION_DOCUMENT_FIELDS \
            or observation.canonical_bytes != canonical_json_bytes(expected):
        raise BodySwayMotionConsumerAdmissionError(
            f"Motion consumer {label} head observation is unsupported"
        )
    return document


def _expected_observation_document(identity):
    return {
        "method": "visual-review-double-snapshot-plus-seam-review-history-a-b",
        "scope": "compile_time",
        "identity": identity.public_document(),
        "checks": {
            "visual_review_head": "observed_current",
            "seam_anchor_review_head": "observed_current",
            "reviewed_seam_anchor_set": "canonical_replay_matched",
        },
        "permanent_authority_claimed": False,
    }


def _head_evidence(before, after, before_bytes, after_bytes):
    evidence = {
        "method": "before-after-current-head-recheck",
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
        body_sway_head_observations_sha256(evidence)
    )
    return evidence


__all__ = [
    "BodySwayMotionConsumerAdmission",
    "BodySwayMotionConsumerAdmissionCore",
    "BodySwayMotionConsumerAdmissionError",
    "compile_body_sway_motion_consumer_admission_core",
    "observation_from_document",
    "seal_body_sway_motion_consumer_admission",
]
