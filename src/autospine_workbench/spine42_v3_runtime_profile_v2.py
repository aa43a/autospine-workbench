"""Version-isolated P10.7b v2 runtime-source and plan profile."""

from __future__ import annotations

import json
from typing import Any

from .resolved_project import canonical_sha256
from .spine42_v3_bundle_contract_v2 import (
    BUNDLE_ADDRESS_DOMAIN as UPSTREAM_ADDRESS_DOMAIN,
)
from .spine42_v3_bundle_files_v2 import NAMESPACE as UPSTREAM_NAMESPACE
from .spine42_v3_runtime_profile import (
    MAX_CAPTURE_ARTIFACTS,
    MAX_COMPOSITE_CASES,
    MAX_SETUP_ATTACHMENTS,
    TICKS_PER_SECOND,
    spine42_v3_runtime_profile,
)


SOURCE_CONTRACT_FORMAT = "autospine-spine42-v3-runtime-source-contract"
SOURCE_CONTRACT_VERSION = 2
SOURCE_CONTRACT_HASH_DOMAIN = (
    "autospine-spine42-v3-runtime-source-contract/v2"
)
PROFILE_FORMAT = "autospine-spine42-v3-runtime-raster-profile"
PROFILE_VERSION = 2
PROFILE_HASH_DOMAIN = "autospine-spine42-v3-runtime-raster-profile/v2"
PLAN_HASH_DOMAIN = "autospine-spine42-v3-runtime-raster-plan/v2"
ADMISSION_HASH_DOMAIN = (
    "autospine-spine42-v3-runtime-source-admission/v2"
)

P10_7A_V2_IDENTITY_FIELDS = (
    "adapter_profile_sha256", "source_contract_sha256",
    "motion_instance_v3_source_sha256", "p3_rig_sha256",
    "p3_bundle_sha256", "motion_instance_v3_sha256",
    "motion_instance_v3_bundle_sha256", "admission_sha256",
    "source_set_sha256", "source_document_sha256",
    "dynamic_seam_probe_sha256", "dynamic_seam_bundle_sha256",
    "motion_instance_v2_sha256", "reviewed_motion_bundle_sha256",
    "motion_instance_v3_profile_sha256", "motion_domain_sha256",
    "rotation_timeline_sha256", "base_channels_sha256", "rig_ir_sha256",
    "target_profile_sha256", "motion_instance_v3_run_sha256",
    "skeleton_json_sha256", "atlas_sha256", "png_sha256",
    "run_identity_sha256", "run_document_sha256", "report_sha256",
    "bundle_sha256",
)

_SOURCE_CONTRACT = {
    "format": SOURCE_CONTRACT_FORMAT,
    "format_version": SOURCE_CONTRACT_VERSION,
    "accepted_upstream": {
        "format": "autospine-spine42-v3-export-run",
        "format_version": 2,
        "filesystem_namespace": UPSTREAM_NAMESPACE,
        "bundle_address_domain": UPSTREAM_ADDRESS_DOMAIN.decode("ascii"),
        "address_fields": [
            "project_id", "skeleton_json_sha256", "bundle_sha256",
        ],
        "identity_fields": list(P10_7A_V2_IDENTITY_FIELDS),
    },
    "version_policy": {
        "accepts_p10_7a_v1": False,
        "accepts_p10_7a_v2": True,
        "cross_version_coercion": False,
    },
    "scope": "read-only-official-runtime-capture-planning",
}


def spine42_v3_runtime_source_contract_v2() -> dict[str, Any]:
    """Return a detached exact-upstream source contract."""

    return _copy(_SOURCE_CONTRACT)


def spine42_v3_runtime_source_contract_sha256_v2() -> str:
    return canonical_sha256({
        "domain": SOURCE_CONTRACT_HASH_DOMAIN,
        "source_contract": _SOURCE_CONTRACT,
    })


def spine42_v3_runtime_profile_v2() -> dict[str, Any]:
    """Return the v2 planning profile without claiming runtime execution."""

    profile = spine42_v3_runtime_profile()
    profile["format"] = PROFILE_FORMAT
    profile["format_version"] = PROFILE_VERSION
    profile["source_contract_sha256"] = (
        spine42_v3_runtime_source_contract_sha256_v2()
    )
    profile["browser_execution"] = {
        **profile["browser_execution"],
        "runner": "spine42-v3-v2-owned-job-browser-runner",
        "runner_version": "2.0.0",
    }
    return profile


def spine42_v3_runtime_profile_sha256_v2() -> str:
    return canonical_sha256({
        "domain": PROFILE_HASH_DOMAIN,
        "profile": spine42_v3_runtime_profile_v2(),
    })


def _copy(value):
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "ADMISSION_HASH_DOMAIN", "MAX_CAPTURE_ARTIFACTS",
    "MAX_COMPOSITE_CASES", "MAX_SETUP_ATTACHMENTS",
    "P10_7A_V2_IDENTITY_FIELDS", "PLAN_HASH_DOMAIN", "PROFILE_FORMAT",
    "PROFILE_HASH_DOMAIN", "PROFILE_VERSION", "SOURCE_CONTRACT_FORMAT",
    "SOURCE_CONTRACT_HASH_DOMAIN", "SOURCE_CONTRACT_VERSION",
    "TICKS_PER_SECOND", "spine42_v3_runtime_profile_sha256_v2",
    "spine42_v3_runtime_profile_v2",
    "spine42_v3_runtime_source_contract_sha256_v2",
    "spine42_v3_runtime_source_contract_v2",
]
