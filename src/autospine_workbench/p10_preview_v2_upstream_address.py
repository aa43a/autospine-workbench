"""Lightweight content-address verification for persisted Preview v2 inputs."""

from __future__ import annotations

from pathlib import Path

from .mesh_bundle_contract import (
    DOCUMENT_NAMES as MESH_DOCUMENT_NAMES,
    MeshBundleContractError, build_mesh_bundle_contract,
)
from .mesh_bundle_reader import (
    VerifiedMeshBundleReaderError,
    _resolve_bundle as resolve_mesh_bundle,
    _snapshot as snapshot_mesh_bundle,
)
from .motion_retarget_bundle_contract import (
    DOCUMENT_NAMES as RETARGET_DOCUMENT_NAMES,
    MotionRetargetBundleContractError,
    build_motion_retarget_bundle_contract,
)
from .motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReaderError,
    _resolve_bundle as resolve_retarget_bundle,
    _snapshot as snapshot_retarget_bundle,
)
from .p10_preview_v2_cache import P10PreviewV2CacheRecord
from .safe_input_files import SafeInputFileError, strict_json_object


class P10PreviewV2UpstreamAddressError(RuntimeError):
    """Raised when immutable P3/P5 bytes differ from their exact addresses."""


def require_current_p10_preview_v2_upstreams(
    state_root: Path,
    record: P10PreviewV2CacheRecord,
) -> None:
    """Verify P3/P5 content addresses without reproducing their pipelines."""

    if type(record) is not P10PreviewV2CacheRecord:
        raise P10PreviewV2UpstreamAddressError(
            "Preview v2 upstream record is invalid"
        )
    try:
        root = Path(state_root)
        project = record.address.project_id
        source = record.candidates.document["source"]
        _require_mesh(root, project, source["p3"])
        _require_retarget(root, project, record.result.clip_id, source)
    except P10PreviewV2UpstreamAddressError:
        raise
    except _ERRORS as exc:
        raise P10PreviewV2UpstreamAddressError(
            "Preview v2 immutable upstream address verification failed"
        ) from exc


def _require_mesh(root, project, p3):
    directory = resolve_mesh_bundle(
        root, project, p3["rig_sha256"], p3["bundle_sha256"],
    )
    snapshot = snapshot_mesh_bundle(directory)
    raw, documents = _documents(
        snapshot.document_items, MESH_DOCUMENT_NAMES, "P3",
    )
    pngs = dict(snapshot.png_items)
    contract = build_mesh_bundle_contract(
        project, *(documents[name] for name in MESH_DOCUMENT_NAMES), pngs,
    )
    run_inputs = documents["run-manifest.json"]["inputs"]
    expected = (
        p3["rig_sha256"], p3["run_sha256"], p3["probes_sha256"],
        p3["visuals_sha256"], p3["bundle_sha256"],
        p3["base_rig_sha256"], p3["base_bundle_sha256"],
        p3["layer_manifest_sha256"], p3["resolved_project_sha256"],
    )
    actual = (
        contract.rig_sha256, contract.run_sha256, contract.probes_sha256,
        contract.visuals_sha256, contract.bundle_sha256,
        run_inputs["base_rig_sha256"], run_inputs["base_bundle_sha256"],
        run_inputs["layer_manifest_sha256"],
        run_inputs["resolved_project_sha256"],
    )
    if contract.document_bytes != raw \
            or contract.png_bytes_by_path != pngs or actual != expected:
        raise P10PreviewV2UpstreamAddressError(
            "Preview v2 P3 bytes differ from their exact address"
        )


def _require_retarget(root, project, clip_id, source):
    p3, p5 = source["p3"], source["p5"]
    directory = resolve_retarget_bundle(
        root, project, p5["instance_sha256"], p5["bundle_sha256"],
    )
    snapshot = snapshot_retarget_bundle(directory)
    raw, documents = _documents(
        snapshot.document_items, RETARGET_DOCUMENT_NAMES, "P5",
    )
    contract = build_motion_retarget_bundle_contract(
        project, *(documents[name] for name in RETARGET_DOCUMENT_NAMES),
    )
    p3_source = documents["target-profile.json"]["source"]["p3"]
    expected = (
        clip_id, p5["target_profile_sha256"], p5["instance_sha256"],
        p5["run_sha256"], p5["retarget_report_sha256"],
        p5["mesh_regression_sha256"], p5["bundle_sha256"],
        p3["rig_sha256"], p3["bundle_sha256"],
    )
    actual = (
        contract.clip_id, contract.target_profile_sha256,
        contract.instance_sha256, contract.run_document_sha256,
        contract.report_sha256, contract.mesh_report_sha256,
        contract.bundle_sha256,
        p3_source["rig_sha256"], p3_source["bundle_sha256"],
    )
    if contract.document_bytes != raw or actual != expected:
        raise P10PreviewV2UpstreamAddressError(
            "Preview v2 P5 bytes differ from their exact address"
        )


def _documents(items, names, label):
    if type(items) is not tuple \
            or tuple(name for name, _raw in items) != tuple(names):
        raise P10PreviewV2UpstreamAddressError(
            f"Preview v2 {label} inventory differs"
        )
    raw = dict(items)
    documents = {
        name: strict_json_object(raw[name], f"Preview v2 {label} {name}")
        for name in names
    }
    return raw, documents


_ERRORS = (
    AttributeError, KeyError, MeshBundleContractError,
    MotionRetargetBundleContractError, OSError, OverflowError,
    SafeInputFileError, TypeError, UnicodeError, ValueError,
    VerifiedMeshBundleReaderError, VerifiedMotionRetargetBundleReaderError,
)


__all__ = [
    "P10PreviewV2UpstreamAddressError",
    "require_current_p10_preview_v2_upstreams",
]
