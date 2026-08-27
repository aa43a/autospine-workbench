"""Exact P10.6a source admission from a seam probe and verified P9."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_head_checks import (
    BodySwayDynamicSeamHeadCheckError,
    BodySwayDynamicSeamHeadIdentity,
    extract_body_sway_dynamic_seam_head_identity,
)
from .body_sway_dynamic_seam_validation import (
    BodySwayDynamicSeamProbeValidationError,
    body_sway_dynamic_seam_probe_canonical_bytes,
)
from .body_sway_motion_consumer_profile import (
    MAX_SOURCE_BYTES,
    MAX_SOURCE_JSON_DEPTH,
    MAX_SOURCE_JSON_NODES,
    body_sway_motion_consumer_source_sha256,
)
from .body_sway_motion_consumer_p9 import (
    require_verified_reviewed_motion_bundle,
)
from .motion_instance_v2_validation import (
    motion_instance_v2_sha256,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


SOURCE_FIELDS = {
    "source_set_sha256", "dynamic_seam_probe_sha256",
    "body_sway_dynamic_seam_probe",
    "dynamic_seam_source_set_sha256", "continuous_preview_proof_sha256",
    "continuous_source_set_sha256", "reviewed_seam_anchor_set_sha256",
    "reviewed_seam_anchor_set_bundle_sha256", "rig_ir_sha256",
    "target_profile_sha256", "preview_projection_sha256", "p9",
}


class BodySwayMotionConsumerSourceError(ValueError):
    """Raised when P10.5d and verified P9 do not form one exact chain."""


@dataclass(frozen=True, slots=True)
class AdmittedBodySwayMotionConsumerSource:
    """Detached documents needed by the pure core compiler."""

    project_id: str
    clip_id: str
    head_identity: BodySwayDynamicSeamHeadIdentity = field(repr=False)
    _source_json: str = field(repr=False)
    _motion_json: str = field(repr=False)
    _projection_json: str = field(repr=False)

    @property
    def source(self) -> dict[str, Any]:
        return json.loads(self._source_json)

    @property
    def motion_instance_v2(self) -> dict[str, Any]:
        return json.loads(self._motion_json)

    @property
    def preview_projection(self) -> dict[str, Any]:
        return json.loads(self._projection_json)


def admit_body_sway_motion_consumer_source(
    dynamic_seam_probe: Any,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> AdmittedBodySwayMotionConsumerSource:
    """Fully replay the probe, then bind its exact embedded MIv2 to P9."""

    try:
        probe_bytes = body_sway_dynamic_seam_probe_canonical_bytes(
            dynamic_seam_probe
        )
        probe = json.loads(probe_bytes)
        if probe["status"] != (
            "continuous_preview_model_reviewed_anchor_proximity_certified"
        ):
            raise BodySwayMotionConsumerSourceError(
                "Dynamic seam proximity is not certified"
            )
        proof = probe["source"]["body_sway_continuous_preview_proof"]
        if proof["status"] != "continuous_preview_model_structural_certified":
            raise BodySwayMotionConsumerSourceError(
                "Upstream continuous preview structure is not certified"
            )
        if proof["claims"].get(
            "continuous_preview_model_structural_safety"
        ) is not True or probe["claims"].get(
            "continuous_preview_model_reviewed_anchor_proximity_within_"
            "engineering_tolerance"
        ) is not True:
            raise BodySwayMotionConsumerSourceError(
                "Certified probe claims are internally inconsistent"
            )
        continuous = proof["source"]
        motion = continuous["motion_instance_v2"]
        projection = continuous["preview_projection"]
        p9 = proof["source"]["amplitude_envelope_candidate"]["source"] \
            ["reviewed_probe_report"]["source"]["p9"]
        bundle_motion = require_verified_reviewed_motion_bundle(
            reviewed_bundle, p9
        )
        _require_cross_chain(probe, continuous, motion, projection,
                             bundle_motion, reviewed_bundle)
        head = extract_body_sway_dynamic_seam_head_identity(probe["source"])
        source = _build_source(probe, continuous, p9, probe_bytes)
        _require_source_budget(source)
        return AdmittedBodySwayMotionConsumerSource(
            probe["project_id"], probe["clip_id"], head,
            _canonical(source), _canonical(motion), _canonical(projection),
        )
    except BodySwayMotionConsumerSourceError:
        raise
    except (
        AttributeError, BodySwayDynamicSeamHeadCheckError,
        BodySwayDynamicSeamProbeValidationError, KeyError, OverflowError,
        RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerSourceError(
            f"Motion consumer source admission failed: {exc}"
        ) from exc

def _require_cross_chain(probe, continuous, motion, projection,
                         bundle_motion, bundle) -> None:
    if bundle.project_id != probe["project_id"] \
            or bundle.clip_id != probe["clip_id"] \
            or motion["clip_id"] != probe["clip_id"]:
        raise BodySwayMotionConsumerSourceError(
            "Motion consumer project or clip identities are cross-wired"
        )
    motion_bytes = canonical_json_bytes(motion)
    if motion_bytes != canonical_json_bytes(bundle_motion) \
            or motion_instance_v2_sha256(motion) \
                != bundle.motion_instance_v2_sha256 \
            or continuous["motion_instance_v2_sha256"] \
                != bundle.motion_instance_v2_sha256:
        raise BodySwayMotionConsumerSourceError(
            "Embedded MotionInstance v2 differs from verified P9 bytes"
        )
    if motion["timing"] != projection["timing"] \
            or projection["project_id"] != probe["project_id"] \
            or projection["clip_id"] != probe["clip_id"]:
        raise BodySwayMotionConsumerSourceError(
            "Motion consumer timing or projection identity is cross-wired"
        )


def _build_source(probe, continuous, p9, probe_bytes):
    dynamic = probe["source"]
    source = {
        "dynamic_seam_probe_sha256": hashlib.sha256(probe_bytes).hexdigest(),
        "body_sway_dynamic_seam_probe": json.loads(probe_bytes),
        "dynamic_seam_source_set_sha256": dynamic["source_set_sha256"],
        "continuous_preview_proof_sha256": dynamic[
            "body_sway_continuous_proof_sha256"
        ],
        "continuous_source_set_sha256": continuous["source_set_sha256"],
        "reviewed_seam_anchor_set_sha256": dynamic[
            "reviewed_seam_anchor_set_sha256"
        ],
        "reviewed_seam_anchor_set_bundle_sha256": dynamic[
            "reviewed_seam_anchor_set_bundle_sha256"
        ],
        "rig_ir_sha256": continuous["rig_ir_sha256"],
        "target_profile_sha256": continuous["target_profile_sha256"],
        "preview_projection_sha256": continuous["preview_projection_sha256"],
        "p9": json.loads(_canonical(p9)),
    }
    source["source_set_sha256"] = body_sway_motion_consumer_source_sha256(
        source
    )
    return source


def _require_source_budget(source) -> None:
    if set(source) != SOURCE_FIELDS:
        raise BodySwayMotionConsumerSourceError(
            "Motion consumer source fields are unsupported"
        )
    require_bounded_json_tree(
        source, max_nodes=MAX_SOURCE_JSON_NODES,
        max_depth=MAX_SOURCE_JSON_DEPTH,
    )
    if len(canonical_json_bytes(source)) > MAX_SOURCE_BYTES:
        raise BodySwayMotionConsumerSourceError(
            "Motion consumer source exceeds its byte limit"
        )


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
