"""Path-free detached document projection for a P10.7b v2 runtime run."""

from __future__ import annotations

import json

from .spine42_v3_runtime_session_core import canonical_json


def build_spine42_v3_runtime_run_document_v2(run) -> dict:
    """Project a detached non-release authority summary."""

    return json.loads(canonical_json({
        "format": "autospine-spine42-v3-runtime-run",
        "format_version": 2, "status": "captured_unreviewed",
        "project_id": run.project_id, "clip_id": run.clip_id,
        "skeleton_json_sha256": run.skeleton_json_sha256,
        "spine42_v3_bundle_sha256": run.spine42_v3_bundle_sha256,
        "source_admission_sha256": run.source_admission_sha256,
        "capture_plan_sha256": run.capture_plan_sha256,
        "session_set_sha256": run.session_set_sha256,
        "runtime": {
            "package_json_sha256": run.runtime_package_json_sha256,
            "license_sha256": run.runtime_license_sha256,
            "license_acknowledged": run.license_acknowledged,
        },
        "browser": {
            "family": run.browser_family,
            "reported_version": run.browser_reported_version,
            "version_output_sha256": run.browser_version_output_sha256,
            "executable_sha256": run.browser_executable_sha256,
            "executable_size_bytes": run.browser_executable_size_bytes,
        },
        "artifact_ids": [key for key, _data in run._capture_items],
        "artifact_count": run.artifact_count,
        "authority": {
            "raster_metrics_computed": False,
            "raster_visual_quality": False,
            "human_visual_reviewed": False,
            "persistent_current_head_authority": False,
        },
        "release": {
            "publishable_spine_timeline": False,
            "release_authority": False,
        },
    }))


__all__ = ["build_spine42_v3_runtime_run_document_v2"]
