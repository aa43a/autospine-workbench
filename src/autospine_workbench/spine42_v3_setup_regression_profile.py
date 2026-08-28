"""Frozen algorithm identity for the bounded P10.7c comparison."""

from __future__ import annotations

import hashlib
import json

from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION
from .spine42_runtime_contract import (
    DEFAULT_BACKGROUND,
    DEFAULT_DPR,
    DEFAULT_VIEWPORT,
    RUNTIME_NPM_INTEGRITY,
)


HASH_DOMAIN = "autospine-spine42-v3-setup-regression-profile/v1"
COMPARISON_PROFILE = {
    "format": "autospine-spine42-v3-setup-regression-profile",
    "format_version": 1,
    "selector": {
        "case_id": "setup",
        "animation": None,
        "tick": 0,
        "time_seconds": 0.0,
        "artifact_kind": "opaque_composite",
        "cardinality": "exactly-one",
    },
    "pixels": {
        "decode": "strict-png-to-rgba8-v1",
        "metric": "rgba-byte-absolute-difference-v1",
        "threshold_rule": "reject-when-strictly-greater",
    },
    "runtime": {
        "package": SPINE_RUNTIME_PACKAGE,
        "version": SPINE_RUNTIME_VERSION,
        "npm_integrity": RUNTIME_NPM_INTEGRITY,
    },
    "capture": {
        "viewport": {"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
        "device_pixel_ratio": DEFAULT_DPR,
        "background": DEFAULT_BACKGROUND,
    },
}


def _canonical(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


COMPARISON_PROFILE_SHA256 = hashlib.sha256(_canonical({
    "domain": HASH_DOMAIN,
    "profile": COMPARISON_PROFILE,
})).hexdigest()


__all__ = [
    "COMPARISON_PROFILE", "COMPARISON_PROFILE_SHA256", "HASH_DOMAIN",
]
