"""Semantic and reproducibility verification for snapshotted P3 mesh bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

from .mesh_bundle_contract import (
    DOCUMENT_NAMES,
    MeshBundleContractError,
    build_mesh_bundle_contract,
)
from .mesh_eligibility import HingeTarget
from .mesh_probe_report import MeshProbeReportError, require_mesh_probe_report
from .mesh_visual_artifacts import (
    MeshVisualArtifactsError,
    require_mesh_visual_artifacts,
)
from .verified_mesh_compiler import VerifiedMeshCompiler, VerifiedMeshCompilerError


_TARGET_FIELDS = frozenset({"attachment_id", "source_layer_id", "side",
                            "proximal_bone_id", "distal_bone_id"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class MeshBundleIntegrityError(ValueError):
    """Raised when stored bytes cannot be reproduced from their exact P2 inputs."""


@dataclass(frozen=True, slots=True)
class MeshBundleSnapshot:
    """One read of every admitted file in an already secured bundle directory."""

    directory: Path
    document_items: tuple[tuple[str, bytes], ...] = field(repr=False)
    png_items: tuple[tuple[str, bytes], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedMeshBundle:
    """Frozen verified identities with isolated document and PNG accessors."""

    path: Path
    project_id: str
    rig_sha256: str
    run_sha256: str
    probes_sha256: str
    visuals_sha256: str
    bundle_sha256: str
    base_rig_sha256: str
    base_bundle_sha256: str
    layer_manifest_sha256: str
    resolved_project_sha256: str
    _document_json_items: tuple[tuple[str, str], ...] = field(repr=False)
    _png_items: tuple[tuple[str, bytes], ...] = field(repr=False)
    _source_png_items: tuple[tuple[str, bytes], ...] = field(
        default=(), repr=False
    )

    def _document(self, name: str) -> dict[str, Any]:
        return json.loads(dict(self._document_json_items)[name])

    @property
    def rig(self) -> dict[str, Any]:
        return self._document("rig.json")

    @property
    def run_manifest(self) -> dict[str, Any]:
        return self._document("run-manifest.json")

    @property
    def probes(self) -> dict[str, Any]:
        return self._document("probes.json")

    @property
    def visuals(self) -> dict[str, Any]:
        return self._document("visuals.json")

    @property
    def pngs(self) -> dict[str, bytes]:
        return dict(self._png_items)

    @property
    def source_pngs(self) -> dict[str, bytes]:
        """Return exact P2 source PNG snapshots keyed by canonical image path."""

        return dict(self._source_png_items)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _ in (*self._document_json_items, *self._png_items))


def verify_mesh_bundle_snapshot(
    snapshot: MeshBundleSnapshot,
    *,
    state_root: Path,
    expected_project_id: str,
    expected_rig_sha256: str,
    expected_bundle_sha256: str,
) -> VerifiedMeshBundle:
    """Validate addresses, dependencies, probes, visuals, and exact stored bytes."""

    try:
        if not isinstance(snapshot, MeshBundleSnapshot):
            raise MeshBundleIntegrityError("Mesh bundle snapshot is invalid")
        raw_documents = _exact_items(snapshot.document_items, set(DOCUMENT_NAMES), bytes)
        pngs = _exact_items(snapshot.png_items, None, bytes)
        documents = {name: _strict_json(data, name)
                     for name, data in raw_documents.items()}
        rig, run, probes, visuals = (documents[name] for name in DOCUMENT_NAMES)
        contract = build_mesh_bundle_contract(
            expected_project_id, rig, run, probes, visuals, pngs
        )
        if contract.document_bytes != raw_documents:
            raise MeshBundleIntegrityError(
                "Mesh bundle JSON bytes are not strict canonical snapshots"
            )
        if contract.png_bytes_by_path != pngs:
            raise MeshBundleIntegrityError("Mesh bundle PNG snapshot differs")
        if (
            contract.project_id != expected_project_id
            or contract.rig_sha256 != expected_rig_sha256
            or contract.bundle_sha256 != expected_bundle_sha256
        ):
            raise MeshBundleIntegrityError(
                "Mesh bundle differs from its requested content address"
            )
        _address(snapshot.directory, contract)

        inputs = run.get("inputs")
        if not isinstance(inputs, Mapping):
            raise MeshBundleIntegrityError("Mesh compile inputs are invalid")
        base_rig = _identity(inputs.get("base_rig_sha256"), "base RigIR", _SHA256)
        base_bundle = _identity(
            inputs.get("base_bundle_sha256"), "base bundle", _SHA256
        )
        layer_manifest = _identity(
            inputs.get("layer_manifest_sha256"), "layer manifest", _SHA256
        )
        resolved_project = _identity(
            inputs.get("resolved_project_sha256"), "resolved project", _SHA256
        )
        compiled = VerifiedMeshCompiler(Path(state_root)).compile(
            expected_project_id, base_rig, base_bundle
        )
        if (
            compiled.project_id != expected_project_id
            or compiled.base_rig_sha256 != base_rig
            or compiled.base_bundle_sha256 != base_bundle
            or compiled.manifest_sha256 != layer_manifest
        ):
            raise MeshBundleIntegrityError(
                "Verified compiler identities differ from stored inputs"
            )
        compiled_rig, compiled_run = compiled.rig, compiled.run_manifest
        if _canonical(compiled_rig) != raw_documents["rig.json"] or \
                _canonical(compiled_run) != raw_documents["run-manifest.json"]:
            raise MeshBundleIntegrityError(
                "Stored mesh compilation differs from exact current dependencies"
            )
        targets = _targets(compiled.targets)
        expected_summary = f"converted={len(targets)}" if targets else "reviewed-noop"
        if compiled.status != expected_summary:
            raise MeshBundleIntegrityError("Mesh compiler target summary is inconsistent")
        require_mesh_probe_report(probes, rig=rig, run=run, targets=targets)
        target_images = compiled.target_images
        require_mesh_visual_artifacts(
            visuals, pngs, rig=rig, run=run, probes=probes,
            targets=targets, target_images=target_images,
        )
        json_items = tuple(
            (name, raw_documents[name].decode("utf-8")) for name in DOCUMENT_NAMES
        )
        return VerifiedMeshBundle(
            path=snapshot.directory,
            project_id=contract.project_id,
            rig_sha256=contract.rig_sha256,
            run_sha256=contract.run_sha256,
            probes_sha256=contract.probes_sha256,
            visuals_sha256=contract.visuals_sha256,
            bundle_sha256=contract.bundle_sha256,
            base_rig_sha256=base_rig,
            base_bundle_sha256=base_bundle,
            layer_manifest_sha256=layer_manifest,
            resolved_project_sha256=resolved_project,
            _document_json_items=json_items,
            _png_items=tuple(sorted(pngs.items())),
            _source_png_items=tuple(sorted(compiled.source_png_bytes.items())),
        )
    except MeshBundleIntegrityError:
        raise
    except (
        MeshBundleContractError,
        MeshProbeReportError,
        MeshVisualArtifactsError,
        VerifiedMeshCompilerError,
        UnicodeError,
        json.JSONDecodeError,
        RuntimeError,
        TypeError,
        ValueError,
        KeyError,
        AttributeError,
        OverflowError,
    ) as exc:
        raise MeshBundleIntegrityError(
            f"Mesh bundle integrity verification failed: {exc}"
        ) from exc


def _strict_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise MeshBundleIntegrityError(
                        f"Mesh bundle JSON contains a duplicate key: {label}"
                    )
                result[key] = value
            return result

        def nonfinite(value):
            raise MeshBundleIntegrityError(
                f"Mesh bundle JSON contains a non-finite number: {label}"
            )

        value = json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
    except MeshBundleIntegrityError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise MeshBundleIntegrityError(f"Mesh bundle JSON is invalid: {label}") from exc
    if not isinstance(value, dict):
        raise MeshBundleIntegrityError(f"Mesh bundle JSON must be an object: {label}")
    return value


def _targets(value: Any) -> tuple[HingeTarget, ...]:
    if not isinstance(value, list):
        raise MeshBundleIntegrityError("Verified compiler targets must be a JSON array")
    result, attachment_ids, source_ids = [], set(), set()
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != _TARGET_FIELDS:
            raise MeshBundleIntegrityError("Verified compiler target fields are invalid")
        fields = {key: _identity(raw.get(key), key, _SAFE_ID) for key in _TARGET_FIELDS}
        side = fields["side"]
        if side not in {"left", "right"} or \
                fields["proximal_bone_id"] != f"thigh.{side}" or \
                fields["distal_bone_id"] != f"calf.{side}" or \
                fields["attachment_id"] != fields["source_layer_id"]:
            raise MeshBundleIntegrityError("Verified compiler target profile is invalid")
        attachment, source = fields["attachment_id"].casefold(), fields["source_layer_id"].casefold()
        if attachment in attachment_ids or source in source_ids:
            raise MeshBundleIntegrityError("Verified compiler targets are duplicated")
        attachment_ids.add(attachment)
        source_ids.add(source)
        result.append(HingeTarget(**fields))
    return tuple(sorted(result, key=lambda item: item.attachment_id))


def _exact_items(items, expected, item_type) -> dict[str, Any]:
    if not isinstance(items, tuple):
        raise MeshBundleIntegrityError("Mesh bundle snapshot inventory is invalid")
    result = {}
    for key, value in items:
        if not isinstance(key, str) or key in result or not isinstance(value, item_type):
            raise MeshBundleIntegrityError("Mesh bundle snapshot inventory is invalid")
        result[key] = value
    if expected is not None and set(result) != expected:
        raise MeshBundleIntegrityError("Mesh bundle document snapshot is incomplete")
    return result


def _address(path: Path, contract) -> None:
    if path.name != contract.bundle_sha256 or path.parent.name != contract.rig_sha256 \
            or path.parent.parent.name != "mesh-rig-ir" \
            or path.parent.parent.parent.name != contract.project_id:
        raise MeshBundleIntegrityError("Mesh bundle content-address path is invalid")


def _identity(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise MeshBundleIntegrityError(f"Mesh bundle {label} identity is invalid")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
