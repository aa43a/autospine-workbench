"""Pinned compiler semantics for unreviewed P10 official-runtime captures."""

from __future__ import annotations

import hashlib
from typing import Any

from .body_sway_runtime_capture_page import (
    CAPTURE_CSS,
    CAPTURE_JS,
    body_sway_capture_case_html,
)


COMPILER_ID = "body-sway-official-runtime-capture-compiler"
COMPILER_VERSION = "1.0.0"
RUNNER_ID = "body-sway-official-runtime-headless-runner"
RUNNER_VERSION = "1.1.0"
ARTIFACT_SET_DIGEST_DOMAIN = "autospine-body-sway-runtime-capture-artifacts/v1"
CASE_STREAM_DIGEST_DOMAIN = "autospine-body-sway-runtime-capture-cases/v1"
MAX_CAPTURE_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_CAPTURE_ARTIFACTS = 55
BROWSER_FIXED_ARGUMENTS = (
    "--headless=new",
    "--no-sandbox",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-component-extensions-with-background-pages",
    "--disable-client-side-phishing-detection",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-extensions",
    "--disable-popup-blocking",
    "--disable-skia-graphite",
    "--disable-sync",
    "--disable-features=MediaRouter,OptimizationHints,Translate",
    "--force-device-scale-factor=1",
    "--hide-scrollbars",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
    "--metrics-recording-only",
    "--no-default-browser-check",
    "--no-first-run",
    "--no-proxy-server",
    "--run-all-compositor-stages-before-draw",
    "--virtual-time-budget=25000",
    "--window-size=640,640",
)
CAPTURE_SEMANTICS = {
    "scope": "bounded-official-runtime-still-captures",
    "official_runtime_execution_claimed": True,
    "standalone_execution_attestation_claimed": False,
    "browser_identity_scope": "launcher-executable-and-reported-version",
    "capture_bytes_recorded": True,
    "human_review_claimed": False,
    "visual_quality_claimed": False,
    "safe_range_claimed": False,
    "continuous_time_safety_claimed": False,
    "inter_attachment_seam_safety_claimed": False,
    "motion_instance_v3_emitted": False,
    "version_neutral_motion_contract_emitted": False,
    "publishable": False,
    "release_authority": False,
    "content_digests_are_compiler_seals": True,
    "detached_validation_scope": "structure-and-internal-consistency",
    "upstream_replay_requires_exact_inputs": True,
}
CAPTURE_RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": sorted([
        "continuous_time_safety_unproven",
        "manual_visual_review_required",
        "preview_only_timeline",
        "reviewed_seam_anchors_missing",
        "safe_range_unproven",
    ]),
}


def body_sway_runtime_capture_compiler_profile() -> dict[str, Any]:
    """Return the sole bounded capture compiler profile."""

    return {
        "id": COMPILER_ID,
        "version": COMPILER_VERSION,
        "artifact_set_digest_domain": ARTIFACT_SET_DIGEST_DOMAIN,
        "case_stream_digest_domain": CASE_STREAM_DIGEST_DOMAIN,
        "limits": {
            "max_capture_document_bytes": MAX_CAPTURE_DOCUMENT_BYTES,
            "max_capture_artifacts": MAX_CAPTURE_ARTIFACTS,
        },
    }


def body_sway_runtime_capture_runner_profile() -> dict[str, Any]:
    """Return the fixed execution profile claimed by the runner."""

    return {
        "id": RUNNER_ID,
        "version": RUNNER_VERSION,
        "supported_host_os": "windows",
        "host": "127.0.0.1",
        "transport": "loopback-http-post",
        "case_order": "exact-capture-plan-order",
        "case_isolation": "fresh-browser-profile",
        "completion_signal": "collector-terminal-capture",
        "network_dependency": "none",
        "chromium_sandbox": "disabled-for-owned-job",
        "chromium_sandbox_reason": (
            "required-for-owned-inner-job-chromium-compatibility"
        ),
        "input_trust": (
            "pinned-runtime-and-compiler-generated-local-assets-only"
        ),
        "content_boundary": "loopback-only-csp-no-external-assets",
        "browser_executable_stability": {
            "mechanism": "windows-deny-write-delete-file-handle",
            "share_mode": "file-share-read-only",
            "scope": "before-snapshot-through-final-exact-replay",
            "mapped_page_identity_claimed": False,
        },
        "process_tree_control": {
            "windows": {
                "creation": "create-suspended",
                "assignment": (
                    "new-empty-inner-kill-on-close-job-before-primary-thread-resume"
                ),
                "inherited_parent_jobs": "allowed-as-outer-job",
                "verification": "exact-inner-job-membership-before-resume",
                "image_identity": (
                    "query-launched-image-path-and-rehash-launcher-before-resume"
                ),
                "cleanup": "close-job-then-bounded-root-wait",
            },
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
