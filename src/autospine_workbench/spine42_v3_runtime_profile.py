"""Pinned bounds and identities for P10.7b runtime raster sampling."""

from __future__ import annotations

import json
from typing import Any

from .body_sway_runtime_capture_profile import (
    BROWSER_FIXED_ARGUMENTS as LEGACY_BROWSER_FIXED_ARGUMENTS,
)
from .resolved_project import canonical_sha256
from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION
from .spine42_runtime_contract import (
    DEFAULT_BACKGROUND,
    DEFAULT_DPR,
    DEFAULT_VIEWPORT,
    RUNTIME_NPM_INTEGRITY,
)
from .spine42_runtime_profile import (
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)
from .spine42_v3_runtime_capture_page import (
    CAPTURE_CSS_SHA256,
    CAPTURE_JS_SHA256,
)


PROFILE_FORMAT = "autospine-spine42-v3-runtime-raster-profile"
PROFILE_VERSION = 1
PROFILE_HASH_DOMAIN = "autospine-spine42-v3-runtime-raster-profile/v1"
PLAN_HASH_DOMAIN = "autospine-spine42-v3-runtime-raster-plan/v1"
METRICS_HASH_DOMAIN = "autospine-spine42-v3-raster-metrics/v1"
TICKS_PER_SECOND = 1_000_000
MAX_COMPOSITE_CASES = 55
MAX_SETUP_ATTACHMENTS = 32
MAX_CAPTURE_ARTIFACTS = MAX_COMPOSITE_CASES * (2 + MAX_SETUP_ATTACHMENTS)
TRANSPARENT_BACKGROUND = "#00000000"
ALPHA_THRESHOLD = 1
BROWSER_FIXED_ARGUMENTS = tuple(
    argument for argument in LEGACY_BROWSER_FIXED_ARGUMENTS
    if not argument.startswith("--virtual-time-budget=")
)

_PROFILE = {
    "format": PROFILE_FORMAT,
    "format_version": PROFILE_VERSION,
    "runtime": {
        "package": SPINE_RUNTIME_PACKAGE,
        "version": SPINE_RUNTIME_VERSION,
        "npm_integrity": RUNTIME_NPM_INTEGRITY,
        "javascript_sha256": SPINE_PLAYER_JAVASCRIPT_SHA256,
        "stylesheet_sha256": SPINE_PLAYER_STYLESHEET_SHA256,
    },
    "harness": {
        "javascript_sha256": CAPTURE_JS_SHA256,
        "stylesheet_sha256": CAPTURE_CSS_SHA256,
    },
    "browser_execution": {
        "runner": "spine42-v3-owned-job-browser-runner",
        "runner_version": "1.0.0",
        "page_lifetime": "collector-terminal",
        "fixed_arguments": list(BROWSER_FIXED_ARGUMENTS),
    },
    "capture": {
        "viewport": {
            "width": DEFAULT_VIEWPORT[0],
            "height": DEFAULT_VIEWPORT[1],
        },
        "device_pixel_ratio": DEFAULT_DPR,
        "preserve_drawing_buffer": True,
        "opaque_background": DEFAULT_BACKGROUND,
        "transparent_background": TRANSPARENT_BACKGROUND,
        "ticks_per_second": TICKS_PER_SECOND,
    },
    "bounds": {
        "max_composite_cases": MAX_COMPOSITE_CASES,
        "max_setup_attachments": MAX_SETUP_ATTACHMENTS,
        "max_capture_artifacts": MAX_CAPTURE_ARTIFACTS,
    },
    "sampling": {
        "fixed_duration_fractions": [
            "0/8", "1/8", "2/8", "3/8", "4/8",
            "5/8", "6/8", "7/8", "8/8",
        ],
        "include_track_local_extrema": True,
        "include_event_and_draw_order_boundaries": True,
        "loop_neighbor_offsets_ticks": [0, 1, -1, 0],
        "scope": "bounded-discrete-samples-only",
    },
    "raster": {
        "alpha_threshold_inclusive": ALPHA_THRESHOLD,
        "isolate_composition": "binary-or",
        "pixel_neighborhood": "four-connected",
    },
}


def spine42_v3_runtime_profile() -> dict[str, Any]:
    """Return a detached copy of the immutable capture profile."""

    return json.loads(json.dumps(
        _PROFILE, allow_nan=False, sort_keys=True, separators=(",", ":")
    ))


def spine42_v3_runtime_profile_sha256() -> str:
    """Return the domain-separated profile identity."""

    return canonical_sha256({
        "domain": PROFILE_HASH_DOMAIN,
        "profile": _PROFILE,
    })


__all__ = [
    "ALPHA_THRESHOLD", "BROWSER_FIXED_ARGUMENTS", "MAX_CAPTURE_ARTIFACTS",
    "MAX_COMPOSITE_CASES", "MAX_SETUP_ATTACHMENTS",
    "METRICS_HASH_DOMAIN", "PLAN_HASH_DOMAIN", "PROFILE_FORMAT",
    "PROFILE_VERSION", "TICKS_PER_SECOND", "TRANSPARENT_BACKGROUND",
    "spine42_v3_runtime_profile", "spine42_v3_runtime_profile_sha256",
]
