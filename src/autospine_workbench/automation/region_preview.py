"""Exact P2 region setup previews, without P3 or release authority."""

from __future__ import annotations

import hashlib
from functools import wraps
from pathlib import Path
from typing import Any, Mapping

from ..manifest_bundle import LayerManifestBundleReader
from ..resolved_project import canonical_sha256
from ..rig_bundle_integrity import verify_rig_bundle_directory
from ..rig_bundle_validation import validate_bundle_inputs
from ..spine42_atlas import build_spine42_atlas
from ..spine42_contract import canonical_spine42_json, spine42_target_profile
from ..spine42_export_validation import validate_spine42_export
from ..spine42_json_adapter import build_spine42_json
from .region_preview_store import (
    RegionPreviewBundle, RegionPreviewError, preview_path, publish_preview,
    read_preview, require_sources, safe_path, preview_schema,
)


def _boundary(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except RegionPreviewError:
            raise
        except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
            raise RegionPreviewError(f"Region preview validation failed: {exc}") from exc
    return wrapped


@_boundary
def build_region_preview(
    state_root: Path, project_id: str, manifest_bundle_sha: str,
    rig_sha: str, rig_bundle_sha: str, *, target_version="4.2",
) -> dict[str, Any]:
    """Compile and read back an immutable preview from exact reviewed P2 inputs."""
    sources = require_sources({
        "layer_manifest_sha256": manifest_bundle_sha,
        "rig_sha256": rig_sha, "rig_bundle_sha256": rig_bundle_sha,
    })
    files = _compile(state_root, project_id, sources, target_version=target_version)
    published = publish_preview(state_root, project_id, files, target_version=target_version)
    return verify_region_preview(
        state_root, project_id, published,
        expected_source_addresses=sources, target_version=target_version,
    ).addresses


@_boundary
def verify_region_preview(
    state_root: Path, project_id: str, bundle_sha256: str, *,
    expected_source_addresses: Mapping[str, str] | None = None,
    target_version="4.2",
) -> RegionPreviewBundle:
    """Verify exact files and rebuild from verified immutable P2 sources."""
    bundle = read_preview(state_root, project_id, bundle_sha256, target_version=target_version)
    sources = bundle.addresses["source_addresses"]
    if expected_source_addresses is not None and sources != require_sources(
        expected_source_addresses
    ):
        raise RegionPreviewError("Preview source addresses differ from request")
    rebuilt = _compile(state_root, project_id, sources, target_version=target_version)
    if bundle.files != rebuilt:
        raise RegionPreviewError("Preview differs from exact P2 rebuild")
    return bundle


def _compile(
    state_root: Path, project_id: str, sources: Mapping[str, str], *, target_version="4.2",
) -> dict[str, bytes]:
    # Validate the project token and every existing state ancestor before reading.
    preview_path(state_root, project_id, "0" * 64, target_version=target_version)
    rig_path = Path(state_root) / "builds" / project_id / "rig-ir" / (
        sources["rig_sha256"]
    ) / sources["rig_bundle_sha256"]
    safe_path(rig_path)
    manifest_path = Path(state_root) / "builds" / project_id / "layer-manifests" / (
        sources["layer_manifest_sha256"]
    )
    safe_path(manifest_path)
    manifest = LayerManifestBundleReader(state_root).load(
        project_id, sources["layer_manifest_sha256"],
    )
    verified = verify_rig_bundle_directory(
        rig_path, expected_project_id=project_id,
    )
    rig = verified.rig
    validate_bundle_inputs(project_id, rig, verified.run, verified.probes, manifest.path)
    if (
        verified.rig_sha256 != sources["rig_sha256"]
        or verified.bundle_sha256 != sources["rig_bundle_sha256"]
        or rig["source"]["layer_manifest_sha256"] != manifest.sha256
        or verified.run["inputs"]["layer_manifest_sha256"] != manifest.sha256
    ):
        raise RegionPreviewError("P2 region preview source chain differs")
    if any(document["qa"]["status"] != "passed" for document in (manifest.manifest, rig)) \
            or verified.probes["status"] != "passed" \
            or verified.run["compiler"]["config"]["allow_manual_required"]:
        raise RegionPreviewError("P2 region preview requires reviewed passing inputs")
    if any(item["type"] != "region" for item in rig["attachments"]):
        raise RegionPreviewError("Region preview does not support mesh attachments")
    pngs = verified.region_pngs
    sources_by_id = {
        item["id"]: pngs[item["image_path"]] for item in rig["attachments"]
    }
    source_hashes = {
        name: hashlib.sha256(data).hexdigest() for name, data in sources_by_id.items()
    }
    atlas = build_spine42_atlas(sources_by_id, page_name="skeleton.png")
    build_json, validate_export, target_profile = _adapter(target_version)
    skeleton = build_json(rig)
    export = validate_export(
        skeleton, atlas.atlas_bytes, atlas.png_bytes, source_hashes,
        expected_skeleton_hash=skeleton["skeleton"]["hash"], clip_id=None,
    )
    source = {
        "schema": preview_schema("source", target_version), "project_id": project_id,
        "source_addresses": dict(sources), "adapter": target_profile(),
        "profile": "reviewed-region-setup-v1", "authority": "none",
    }
    qa = {
        "schema": "autospine.region-preview-qa/v1", "status": "passed",
        "source_sha256": canonical_sha256(source), "authority": "none",
        "runtime_status": "not_run", "setup_rgba_sha256": verified.setup["image"]["rgba_sha256"],
        "metrics": {"bones": export.bone_count, "slots": export.slot_count,
                    "attachments": export.attachment_count, "animations": 0},
        "checks": ["p2_exact_bundle", "p2_setup_reconstruction", "spine_cross_file"],
    }
    return {
        "skeleton.json": export.skeleton_json_bytes,
        "skeleton.atlas": export.atlas_bytes, "skeleton.png": export.png_bytes,
        "source.json": canonical_spine42_json(source),
        "qa.json": canonical_spine42_json(qa),
    }


def _adapter(target_version):
    if target_version == "4.2":
        return build_spine42_json, validate_spine42_export, spine42_target_profile
    from ..targets.spine43.contract import spine43_target_profile
    from ..targets.spine43.json_adapter import build_spine43_json
    from ..targets.spine43.validation import validate_spine43_export

    return build_spine43_json, validate_spine43_export, spine43_target_profile
