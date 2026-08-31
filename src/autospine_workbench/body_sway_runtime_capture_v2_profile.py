"""Pinned identities and claims for capture-framed P10.3 runtime evidence."""

from __future__ import annotations

from typing import Any


FORMAT = "autospine-body-sway-runtime-capture"
FORMAT_VERSION = 2
MANIFEST_NAME = "body-sway-runtime-capture-v2.json"
NAMESPACE = "body-sway-runtime-captures-v2"
COMPILER_ID = "body-sway-runtime-capture-payload-validator-v2"
COMPILER_VERSION = "2.1.0"
ARTIFACT_SET_DIGEST_DOMAIN = (
    "autospine-body-sway-runtime-capture-artifacts/v2"
)
CASE_STREAM_DIGEST_DOMAIN = "autospine-body-sway-runtime-capture-cases/v2"
BUNDLE_ADDRESS_DOMAIN = b"autospine.body-sway-runtime-capture-bundle/v2\x00"
MAX_CAPTURE_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_CAPTURE_ARTIFACTS = 55
CAPTURE_VIEWPORT = {"width": 640, "height": 640}
CAPTURE_DEVICE_PIXEL_RATIO = 1


SEMANTICS = {
    "scope": "capture-framed-validated-capture-payload",
    "capture_payload_validated": True,
    "ready_for_official_runtime_execution": True,
    "official_runtime_execution_claimed": False,
    "official_runtime_execution_evidence_emitted": False,
    "browser_identity_is_execution_evidence": False,
    "human_capture_framing_decision_bound": True,
    "human_visual_review_claimed": False,
    "visual_quality_claimed": False,
    "safe_range_claimed": False,
    "continuous_time_safety_claimed": False,
    "inter_attachment_seam_safety_claimed": False,
    "publishable": False,
    "release_authority": False,
    "content_digests_are_compiler_seals": True,
    "detached_validation_scope": "structure-and-internal-consistency",
    "detached_currentness_claimed": False,
    "currentness_requires_exact_preview_v2_replay": True,
}

RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": sorted([
        "continuous_time_safety_unproven",
        "manual_visual_review_required",
        "official_runtime_execution_required",
        "preview_only_timeline",
        "reviewed_seam_anchors_missing",
        "safe_range_unproven",
    ]),
}


def body_sway_runtime_capture_v2_compiler_profile() -> dict[str, Any]:
    """Return the only supported capture-framed evidence profile."""

    return {
        "id": COMPILER_ID,
        "version": COMPILER_VERSION,
        "artifact_set_digest_domain": ARTIFACT_SET_DIGEST_DOMAIN,
        "case_stream_digest_domain": CASE_STREAM_DIGEST_DOMAIN,
        "capture_viewport": dict(CAPTURE_VIEWPORT),
        "device_pixel_ratio": CAPTURE_DEVICE_PIXEL_RATIO,
        "world_viewport_source": "capture-framing-human-decision-v1",
        "output_status":
            "validated-capture-payload-ready-for-official-runtime-execution",
        "limits": {
            "max_capture_document_bytes": MAX_CAPTURE_DOCUMENT_BYTES,
            "max_capture_artifacts": MAX_CAPTURE_ARTIFACTS,
        },
    }
