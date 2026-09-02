"""Exact P10.6a v2 source admission from P10.5d v2 and P9."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .body_sway_dynamic_seam_bundle_reader_v2 import (
    VerifiedBodySwayDynamicSeamBundleV2,
)
from .body_sway_motion_consumer_dynamic_bundle_v2 import (
    BodySwayMotionConsumerDynamicBundleV2Error,
    require_exact_body_sway_dynamic_seam_bundle_v2,
)
from .body_sway_motion_consumer_p9 import (
    BodySwayMotionConsumerP9Error,
    require_verified_reviewed_motion_bundle,
)
from .body_sway_motion_consumer_profile_v2 import (
    MAX_SOURCE_BYTES,
    MAX_SOURCE_JSON_DEPTH,
    MAX_SOURCE_JSON_NODES,
    body_sway_motion_consumer_source_sha256_v2,
)
from .body_sway_motion_consumer_source_checks_v2 import (
    expected_body_sway_motion_consumer_v2_head_observation,
    require_body_sway_motion_consumer_v2_certified,
    require_body_sway_motion_consumer_v2_cross_chain,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


SOURCE_FIELDS = {
    "source_set_sha256", "dynamic_seam_source_set_sha256",
    "dynamic_seam_source_document_sha256", "dynamic_seam_probe_sha256",
    "dynamic_seam_bundle_sha256", "body_sway_dynamic_seam_probe_v2",
    "body_sway_continuous_preview_proof_v2_sha256",
    "reviewed_seam_anchor_set_v1_sha256",
    "reviewed_seam_anchor_set_v1_bundle_sha256", "layer_manifest_sha256",
    "p3_rig_sha256", "p3_bundle_sha256", "target_profile_sha256",
    "preview_projection_v2_sha256", "p9",
}


class BodySwayMotionConsumerSourceV2Error(ValueError):
    """Raised when exact P10.5d v2 and P9 bytes do not form one chain."""


@dataclass(frozen=True, slots=True)
class AdmittedBodySwayMotionConsumerSourceV2:
    project_id: str
    clip_id: str
    head_identity_sha256: str
    _expected_head_json: str = field(repr=False)
    _source_json: str = field(repr=False)
    _motion_json: str = field(repr=False)
    _projection_json: str = field(repr=False)

    @property
    def expected_head_observation(self) -> dict[str, Any]:
        return json.loads(self._expected_head_json)

    @property
    def source(self) -> dict[str, Any]:
        return json.loads(self._source_json)

    @property
    def motion_instance_v2(self) -> dict[str, Any]:
        return json.loads(self._motion_json)

    @property
    def preview_projection_v2(self) -> dict[str, Any]:
        return json.loads(self._projection_json)


def admit_body_sway_motion_consumer_source_v2(
    dynamic_bundle: VerifiedBodySwayDynamicSeamBundleV2,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> AdmittedBodySwayMotionConsumerSourceV2:
    """Rebuild both immutable bundles and bind their exact setup-local data."""

    try:
        source, probe = require_exact_body_sway_dynamic_seam_bundle_v2(
            dynamic_bundle
        )
        require_body_sway_motion_consumer_v2_certified(probe)
        proof = source["body_sway_continuous_preview_proof_v2"]
        continuous = proof["source"]
        candidate = continuous["amplitude_envelope_candidate_v2"]
        report = candidate["source"]["reviewed_probe_report"]
        p9 = report["source"]["p9"]
        motion = continuous["motion_instance_v2"]
        projection = continuous["preview_projection_v2"]
        bundle_motion = require_verified_reviewed_motion_bundle(
            reviewed_bundle, p9,
        )
        require_body_sway_motion_consumer_v2_cross_chain(
            source, probe, proof, candidate, report, motion, projection,
            bundle_motion, reviewed_bundle,
        )
        closure = _build_source(
            source, probe, dynamic_bundle, continuous, p9
        )
        _require_source_budget(closure)
        expected_head = expected_body_sway_motion_consumer_v2_head_observation(
            source
        )
        return AdmittedBodySwayMotionConsumerSourceV2(
            source["project_id"], source["clip_id"],
            expected_head["identity_sha256"], _canonical(expected_head),
            _canonical(closure), _canonical(motion), _canonical(projection),
        )
    except BodySwayMotionConsumerSourceV2Error:
        raise
    except (
        AttributeError, BodySwayMotionConsumerDynamicBundleV2Error,
        BodySwayMotionConsumerP9Error, KeyError, OverflowError,
        RecursionError, RuntimeError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerSourceV2Error(
            f"Motion consumer v2 source admission failed: {exc}"
        ) from exc


def _build_source(dynamic, probe, bundle, continuous, p9):
    closure = {
        "dynamic_seam_source_set_sha256": bundle.source_set_sha256,
        "dynamic_seam_source_document_sha256":
            bundle.source_document_sha256,
        "dynamic_seam_probe_sha256": bundle.probe_sha256,
        "dynamic_seam_bundle_sha256": bundle.bundle_sha256,
        "body_sway_dynamic_seam_probe_v2": probe,
        "body_sway_continuous_preview_proof_v2_sha256": dynamic[
            "body_sway_continuous_preview_proof_v2_sha256"
        ],
        "reviewed_seam_anchor_set_v1_sha256": dynamic[
            "reviewed_seam_anchor_set_v1_sha256"
        ],
        "reviewed_seam_anchor_set_v1_bundle_sha256": dynamic[
            "reviewed_seam_anchor_set_v1_bundle_sha256"
        ],
        "layer_manifest_sha256": dynamic["layer_manifest_sha256"],
        "p3_rig_sha256": dynamic["p3_rig_sha256"],
        "p3_bundle_sha256": dynamic["p3_bundle_sha256"],
        "target_profile_sha256": continuous["target_profile_sha256"],
        "preview_projection_v2_sha256": continuous[
            "preview_projection_v2_sha256"
        ],
        "p9": json.loads(_canonical(p9)),
    }
    closure["source_set_sha256"] = (
        body_sway_motion_consumer_source_sha256_v2(closure)
    )
    return closure


def _require_source_budget(source):
    if set(source) != SOURCE_FIELDS:
        raise BodySwayMotionConsumerSourceV2Error(
            "Motion consumer v2 source fields are unsupported"
        )
    require_bounded_json_tree(
        source, max_nodes=MAX_SOURCE_JSON_NODES,
        max_depth=MAX_SOURCE_JSON_DEPTH,
    )
    if len(canonical_json_bytes(source)) > MAX_SOURCE_BYTES:
        raise BodySwayMotionConsumerSourceV2Error(
            "Motion consumer v2 source exceeds its byte limit"
        )


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


__all__ = [
    "AdmittedBodySwayMotionConsumerSourceV2",
    "BodySwayMotionConsumerSourceV2Error", "SOURCE_FIELDS",
    "admit_body_sway_motion_consumer_source_v2",
]
