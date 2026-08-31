"""Pinned claims and runner identity for Preview v2 official execution."""

from __future__ import annotations

import hashlib
from typing import Any

from .body_sway_runtime_capture_page import (
    CAPTURE_CSS,
    CAPTURE_JS,
    body_sway_capture_case_html,
)
from .body_sway_runtime_capture_profile import (
    BROWSER_FIXED_ARGUMENTS as FROZEN_V1_BROWSER_FIXED_ARGUMENTS,
)


FORMAT = "autospine-body-sway-runtime-execution"
FORMAT_VERSION = 1
MANIFEST_NAME = "body-sway-runtime-execution.json"
PAYLOAD_NAME = "body-sway-runtime-capture-v2.json"
NAMESPACE = "body-sway-runtime-executions"
BUNDLE_ADDRESS_DOMAIN = b"autospine.body-sway-runtime-execution-bundle/v1\x00"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
RUNNER_VERSION = "1.1.0"
BROWSER_FIXED_ARGUMENTS = tuple(
    argument for argument in FROZEN_V1_BROWSER_FIXED_ARGUMENTS
    if not argument.startswith("--virtual-time-budget=")
)

AUTHORITY = {
    "scope": "bounded-capture-framed-official-runtime-still-execution",
    "official_runtime_execution_claimed": True,
    "official_runtime_execution_evidence_emitted": True,
    "official_runtime_loaded": True,
    "official_runtime_loaded_observation":
        "spine-player-success-draw-and-exact-collector-post",
    "capture_payload_v2_bound": True,
    "capture_bytes_recorded": True,
    "human_capture_framing_decision_bound": True,
    "standalone_license_authorization_attestation_claimed": False,
    "human_visual_review_claimed": False,
    "visual_quality_claimed": False,
    "safe_range_claimed": False,
    "continuous_time_safety_claimed": False,
    "inter_attachment_seam_safety_claimed": False,
    "publishable": False,
    "release_authority": False,
    "detached_currentness_claimed": False,
}

RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": sorted([
        "continuous_time_safety_unproven",
        "manual_visual_review_required",
        "preview_only_timeline",
        "reviewed_seam_anchors_missing",
        "safe_range_unproven",
    ]),
}


def body_sway_runtime_execution_compiler_profile() -> dict[str, Any]:
    return {
        "id": "body-sway-runtime-execution-evidence-compiler",
        "version": "1.0.0",
        "inner_capture_payload": {
            "format": "autospine-body-sway-runtime-capture",
            "format_version": 2,
            "authority": "none-unless-bound-by-this-execution-evidence",
        },
        "output_status": "captured-unreviewed",
    }


def body_sway_runtime_execution_runner_profile() -> dict[str, Any]:
    return {
        "id": "body-sway-capture-framed-official-runtime-runner",
        "version": RUNNER_VERSION,
        "supported_host_os": "windows",
        "host": "127.0.0.1",
        "transport": "loopback-http-post",
        "case_order": "exact-capture-plan-order",
        "case_isolation": "fresh-browser-profile",
        "completion_signal": "collector-terminal-capture",
        "page_lifetime": "collector-terminal",
        "network_dependency": "none",
        "input_trust": "pinned-runtime-and-exact-preview-v2-assets-only",
        "browser_executable_stability": {
            "mechanism": "windows-deny-write-delete-file-handle",
            "scope": "before-snapshot-through-final-exact-replay",
            "mapped_page_identity_claimed": False,
        },
        "process_tree_control": {
            "creation": "create-suspended",
            "assignment": "owned-inner-kill-on-close-job-before-resume",
            "cleanup": "close-job-then-bounded-root-wait",
        },
        "fixed_browser_arguments": list(BROWSER_FIXED_ARGUMENTS),
        "harness": {
            "javascript_sha256": hashlib.sha256(CAPTURE_JS).hexdigest(),
            "stylesheet_sha256": hashlib.sha256(CAPTURE_CSS).hexdigest(),
            "html_template_sha256": hashlib.sha256(
                body_sway_capture_case_html("capture-case-placeholder")
            ).hexdigest(),
        },
    }


__all__ = [
    "AUTHORITY", "BROWSER_FIXED_ARGUMENTS", "BUNDLE_ADDRESS_DOMAIN",
    "FORMAT", "FORMAT_VERSION", "MANIFEST_NAME", "MAX_MANIFEST_BYTES",
    "NAMESPACE", "PAYLOAD_NAME", "RELEASE_GATE", "RUNNER_VERSION",
    "body_sway_runtime_execution_compiler_profile",
    "body_sway_runtime_execution_runner_profile",
]
