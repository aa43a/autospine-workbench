"""Exact P9 reviewed-motion replay for the P10.6a consumer boundary."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .depth_order_candidate_validation import depth_order_candidates_sha256
from .foot_lock_candidate_validation import foot_lock_candidates_sha256
from .motion_instance_v2_validation import (
    motion_instance_v2_sha256,
    require_motion_instance_v2,
)
from .motion_policy_decision_validation import motion_policy_decision_sha256
from .reviewed_motion_bundle_contract import (
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    MAX_TOTAL_DOCUMENT_BYTES,
    reviewed_motion_bundle_address_sha256,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .reviewed_motion_bundle_run import require_reviewed_motion_bundle_run
from .reviewed_motion_policy_validation import reviewed_motion_policy_sha256
from .seam_anchor_review_json import canonical_json_bytes


P9_FIELDS = {
    "foot_lock_candidates_sha256",
    "depth_order_candidates_sha256",
    "motion_policy_decision_sha256",
    "reviewed_motion_policy_sha256",
    "motion_instance_v2_sha256",
    "run_sha256",
    "bundle_sha256",
}


class BodySwayMotionConsumerP9Error(ValueError):
    """Raised when verified P9 bytes differ from their exact address."""


def require_verified_reviewed_motion_bundle(
    bundle: Any,
    p9: Any,
) -> dict[str, Any]:
    """Revalidate all six canonical P9 documents and their provenance."""

    if type(bundle) is not VerifiedReviewedMotionBundle:
        raise BodySwayMotionConsumerP9Error(
            "Motion consumer requires an exact verified reviewed-motion bundle"
        )
    if type(p9) is not dict or set(p9) != P9_FIELDS \
            or bundle.identities != p9:
        raise BodySwayMotionConsumerP9Error(
            "Verified reviewed-motion identities differ from exact P9"
        )
    documents, items = _canonical_documents(bundle)
    identities = _require_identities(bundle, documents, items)
    _require_run_provenance(bundle, documents, identities)
    return documents["motion-instance-v2.json"]


def _canonical_documents(bundle):
    raw = bundle.document_bytes
    if tuple(raw) != DOCUMENT_NAMES:
        raise BodySwayMotionConsumerP9Error(
            "Verified reviewed-motion inventory differs from P9"
        )
    documents, items, total = {}, [], 0
    for index, name in enumerate(DOCUMENT_NAMES):
        data = raw[name]
        if type(data) is not bytes or len(data) > DOCUMENT_LIMITS[index]:
            raise BodySwayMotionConsumerP9Error(
                f"Verified reviewed-motion bytes are invalid: {name}"
            )
        total += len(data)
        value = json.loads(data)
        if type(value) is not dict or canonical_json_bytes(value) != data:
            raise BodySwayMotionConsumerP9Error(
                f"Verified reviewed-motion bytes are not canonical: {name}"
            )
        documents[name] = value
        items.append((name, data))
    if total > MAX_TOTAL_DOCUMENT_BYTES:
        raise BodySwayMotionConsumerP9Error(
            "Verified reviewed-motion bundle exceeds its byte limit"
        )
    return documents, tuple(items)


def _require_identities(bundle, documents, items):
    foot, depth = (documents[name] for name in DOCUMENT_NAMES[:2])
    decision, policy, motion, run = (
        documents[name] for name in DOCUMENT_NAMES[2:]
    )
    require_motion_instance_v2(
        motion,
        reviewed_motion_policy=policy,
    )
    require_reviewed_motion_bundle_run(run)
    identities = {
        "foot_lock_candidates_sha256": foot_lock_candidates_sha256(foot),
        "depth_order_candidates_sha256": depth_order_candidates_sha256(depth),
        "motion_policy_decision_sha256": motion_policy_decision_sha256(
            decision,
            foot_candidates=foot,
            depth_candidates=depth,
        ),
        "reviewed_motion_policy_sha256": reviewed_motion_policy_sha256(policy),
        "motion_instance_v2_sha256": motion_instance_v2_sha256(motion),
        "run_sha256": hashlib.sha256(items[5][1]).hexdigest(),
        "bundle_sha256": reviewed_motion_bundle_address_sha256(
            bundle.project_id,
            bundle.motion_instance_v2_sha256,
            items,
        ),
    }
    if identities != bundle.identities:
        raise BodySwayMotionConsumerP9Error(
            "Verified reviewed-motion documents differ from their identities"
        )
    _require_cross_document_sources(
        bundle,
        foot,
        depth,
        decision,
        policy,
        identities,
    )
    return identities


def _require_cross_document_sources(
    bundle,
    foot,
    depth,
    decision,
    policy,
    identities,
):
    documents = (foot, depth, decision, policy)
    if any(
        document["project_id"] != bundle.project_id
        or document["clip_id"] != bundle.clip_id
        for document in documents
    ):
        raise BodySwayMotionConsumerP9Error(
            "Reviewed-motion project or clip provenance is cross-wired"
        )
    source = policy["source"]
    expected = {
        "foot_lock_candidates_sha256": identities[
            "foot_lock_candidates_sha256"
        ],
        "depth_order_candidates_sha256": identities[
            "depth_order_candidates_sha256"
        ],
        "motion_policy_decision_sha256": identities[
            "motion_policy_decision_sha256"
        ],
    }
    if any(source[field] != value for field, value in expected.items()):
        raise BodySwayMotionConsumerP9Error(
            "Reviewed-motion policy source identities are cross-wired"
        )


def _require_run_provenance(bundle, documents, identities):
    motion = documents["motion-instance-v2.json"]
    run = documents["run-manifest.json"]
    source = motion["source"]
    expected = {
        "project_id": bundle.project_id,
        "clip_id": bundle.clip_id,
        "inputs": {
            "p3": {
                "rig_sha256": source["p3_rig_sha256"],
                "bundle_sha256": source["p3_bundle_sha256"],
            },
            "p5": {
                "instance_sha256": source["base_motion_instance_sha256"],
                "bundle_sha256": source["base_retarget_bundle_sha256"],
                "target_profile_sha256": source["target_profile_sha256"],
            },
            "foot_lock_candidates_sha256": identities[
                "foot_lock_candidates_sha256"
            ],
            "depth_order_candidates_sha256": identities[
                "depth_order_candidates_sha256"
            ],
            "motion_policy_decision_sha256": identities[
                "motion_policy_decision_sha256"
            ],
        },
        "outputs": {
            "reviewed_motion_policy_sha256": identities[
                "reviewed_motion_policy_sha256"
            ],
            "motion_instance_v2_sha256": identities[
                "motion_instance_v2_sha256"
            ],
        },
    }
    if any(run[field] != value for field, value in expected.items()):
        raise BodySwayMotionConsumerP9Error(
            "Reviewed-motion run provenance is cross-wired"
        )


__all__ = [
    "BodySwayMotionConsumerP9Error",
    "P9_FIELDS",
    "require_verified_reviewed_motion_bundle",
]
