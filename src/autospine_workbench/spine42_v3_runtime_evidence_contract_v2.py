"""Pure manifest and inventory helpers for runtime evidence v2."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import MappingProxyType

from .browser_version_identity import browser_version_identity_sha256
from .png_rgba import RgbaPngError, decode_rgba_png
from .spine42_v3_runtime_capture_core import (
    MAX_CAPTURE_BYTES, MAX_CAPTURE_TOTAL_BYTES,
)

MANIFEST_NAME = "capture-manifest-v2.json"
PLAN_NAME = "official-runtime-capture-plan-v2.json"
ADMISSION_NAME = "official-runtime-source-admission-v2.json"
SESSIONS_NAME = "runtime-session-set-v2.json"
REPORTS_NAME = "runtime-reports-v2.json"
FIXED_NAMES = (MANIFEST_NAME, PLAN_NAME, ADMISSION_NAME, SESSIONS_NAME,
               REPORTS_NAME)
FORMAT = "autospine-spine42-v3-runtime-capture"
FORMAT_VERSION = 2
_AUTHORITY_ITEMS = tuple({
    "official_runtime_loaded": True,
    "runtime_capture_completed": True,
    "isolated_attachment_raster_captured": True,
    "human_visual_reviewed": False,
    "attachment_area_overlap_assessed": False,
    "dynamic_seam_safety": False,
    "full_attachment_boundary_continuity": False,
    "raster_metrics_computed": False,
    "raster_visual_quality_approved": False,
    "runtime_equivalence": False,
    "publishable_spine_timeline": False,
    "persistent_current_head_authority": False,
    "release_authority": False,
}.items())
_RELEASE_REASONS = (
        "human_visual_review_missing", "attachment_area_overlap_unassessed",
        "dynamic_seam_safety_unproven",
        "full_attachment_boundary_continuity_unproven",
        "raster_metrics_missing", "raster_visual_quality_unapproved",
        "runtime_equivalence_unproven", "publishable_timeline_not_granted",
        "persistent_current_head_authority_not_granted",
        "release_authority_not_granted",
)
AUTHORITY = MappingProxyType(dict(_AUTHORITY_ITEMS))
RELEASE_GATE = MappingProxyType({
    "status": "blocked", "reason_codes": _RELEASE_REASONS,
})


def manifest(bundle, source, runtime, browser, sessions, fixed, artifacts):
    return {
        "format": FORMAT, "format_version": FORMAT_VERSION,
        "project_id": bundle.project_id, "clip_id": bundle.clip_id,
        "source": {
            "skeleton_json_sha256": bundle.skeleton_json_sha256,
            "spine42_v3_bundle_sha256": bundle.bundle_sha256,
            "run_document_sha256": bundle.run_document_sha256,
            "source_admission_sha256": source.admission_sha256,
            "capture_plan_sha256": source.capture_plan_sha256,
            "runtime_session_set_sha256": sessions.sha256,
            "runtime_reports_sha256": sha(fixed[REPORTS_NAME]),
        },
        "runtime": {
            **sessions.plan["runtime"],
            "package_json_sha256": runtime.package_json_sha256,
            "license_sha256": runtime.license_sha256,
            "license_acknowledged": True,
            "license_file_presence_is_authorization": False,
        },
        "browser": {
            "family": browser.family, "reported_version": browser.reported_version,
            "version_output_sha256": browser.version_output_sha256,
            "executable_sha256": browser.executable_sha256,
            "size_bytes": browser.size_bytes,
        },
        "documents": [
            {"name": name, "sha256": sha(raw), "size_bytes": len(raw)}
            for name, raw in fixed.items()
        ],
        "artifacts": artifacts, "authority": dict(_AUTHORITY_ITEMS),
        "status": "captured_unreviewed", "release_gate": {
            "status": "blocked", "reason_codes": list(_RELEASE_REASONS),
        },
    }


def manifest_from_stored(bundle, stored, sessions, fixed, artifacts, error):
    runtime, browser = stored.get("runtime", {}), stored.get("browser", {})
    for value in (runtime.get("package_json_sha256"),
                  runtime.get("license_sha256"),
                  browser.get("executable_sha256")):
        require_digest(value, error)
    if browser.get("version_output_sha256") != browser_version_identity_sha256(
        browser.get("family"), browser.get("reported_version")
    ) or type(browser.get("size_bytes")) is not int \
            or browser.get("size_bytes", 0) <= 0:
        raise error("Browser identity is invalid")
    source = stored.get("source", {})
    if source.get("source_admission_sha256") != \
            sessions.source_admission["admission_sha256"] \
            or source.get("capture_plan_sha256") != \
            sessions.plan["capture_plan_sha256"] \
            or source.get("runtime_session_set_sha256") != sessions.sha256:
        raise error("Source identities are invalid")
    proxy = type("Stored", (), {
        "admission_sha256": source["source_admission_sha256"],
        "capture_plan_sha256": source["capture_plan_sha256"],
    })()
    return manifest(
        bundle, proxy, type("Runtime", (), runtime)(),
        type("Browser", (), browser)(), sessions, fixed, artifacts,
    )


def artifacts(plan, captures, error):
    rows, total = [], 0
    capture = plan["capture"]
    expected_size = (
        capture["viewport"]["width"] * capture["device_pixel_ratio"],
        capture["viewport"]["height"] * capture["device_pixel_ratio"],
    )
    for artifact in plan["artifacts"]:
        identifier, name = artifact["artifact_id"], artifact["path"]
        raw = captures.get(identifier)
        if not safe_png(name) or type(raw) is not bytes \
                or not 0 < len(raw) <= MAX_CAPTURE_BYTES:
            raise error("Capture artifact is invalid")
        try:
            image = decode_rgba_png(raw, source_name=name)
        except RgbaPngError as exc:
            raise error("Capture PNG cannot be decoded exactly") from exc
        if (image.width, image.height) != expected_size:
            raise error("Capture PNG dimensions differ from the plan")
        total += len(raw)
        rows.append({
            "artifact_id": identifier, "logical_path": name,
            "stored_path": f"captures/{name}", "kind": artifact["kind"],
            "case_id": artifact["case_id"], "sha256": sha(raw),
            "size_bytes": len(raw),
        })
    if set(captures) != {row["artifact_id"] for row in rows} \
            or total > MAX_CAPTURE_TOTAL_BYTES:
        raise error("Capture inventory is invalid")
    return rows


def captures(manifest_value, files, plan, error):
    rows = manifest_value.get("artifacts")
    if type(rows) is not list or len(rows) != len(plan["artifacts"]):
        raise error("Capture inventory is invalid")
    result = {}
    for row in rows:
        path = row.get("stored_path") if type(row) is dict else None
        if type(path) is not str or path not in files:
            raise error("Capture path is invalid")
        result[row["artifact_id"]] = files[path]
    expected_names = set(FIXED_NAMES) | {row["stored_path"] for row in rows}
    if set(files) != expected_names or len(result) != len(rows):
        raise error("Capture file inventory is not exact")
    return result


def safe_png(value):
    return type(value) is str and Path(value).name == value \
        and value.endswith(".png") and "\\" not in value and "\0" not in value


def require_digest(value, error):
    if type(value) is not str or len(value) != 64 \
            or any(char not in "0123456789abcdef" for char in value):
        raise error("Digest identity is invalid")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "ADMISSION_NAME", "AUTHORITY", "FIXED_NAMES", "FORMAT", "FORMAT_VERSION",
    "MANIFEST_NAME", "PLAN_NAME", "RELEASE_GATE", "REPORTS_NAME",
    "SESSIONS_NAME", "artifacts", "captures", "manifest",
    "manifest_from_stored", "sha",
]
