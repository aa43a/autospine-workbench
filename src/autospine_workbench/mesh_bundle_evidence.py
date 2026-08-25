"""Read-only discovery and compact UI evidence for verified P3 mesh bundles."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path
import re
import stat
from typing import Any
from urllib.parse import quote

from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_ADDRESSES = 4096


class MeshBundleEvidenceError(RuntimeError):
    """Raised when discovery or verified evidence projection cannot be trusted."""


class MeshBundleEvidenceNotFound(MeshBundleEvidenceError):
    """Raised when an exact requested address or image is absent."""


class MeshBundleEvidenceRepository:
    """Discover addresses, then use the strict reader for every detailed read."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def list(self, project_id: str) -> dict[str, Any]:
        project = _identity(project_id, _SAFE_ID, "project")
        items = [
            {"rig_sha256": rig_sha, "bundle_sha256": bundle_sha}
            for rig_sha, bundle_sha in _discover(self.state_root, project)
        ]
        return {
            "format": "autospine-mesh-bundle-evidence-index",
            "format_version": 1,
            "project_id": project,
            "count": len(items),
            "items": items,
        }

    def read(
        self, project_id: str, rig_sha256: str, bundle_sha256: str
    ) -> dict[str, Any]:
        verified = self._load(project_id, rig_sha256, bundle_sha256)
        return _detail(verified)

    def image(
        self, project_id: str, rig_sha256: str,
        bundle_sha256: str, png_sha256: str,
    ) -> bytes:
        verified = self._load(project_id, rig_sha256, bundle_sha256)
        digest = _identity(png_sha256, _SHA256, "PNG")
        artifacts = verified.visuals.get("artifacts")
        if not isinstance(artifacts, list):
            raise MeshBundleEvidenceError("Verified visual artifacts are invalid")
        paths = sorted({item.get("path") for item in artifacts
                        if item.get("png_sha256") == digest})
        if not paths:
            raise MeshBundleEvidenceNotFound("Mesh evidence PNG was not found")
        pngs = verified.pngs
        data = pngs.get(paths[0])
        if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != digest:
            raise MeshBundleEvidenceError("Verified mesh evidence PNG binding changed")
        return data

    def _load(self, project_id: str, rig_sha256: str, bundle_sha256: str):
        project = _identity(project_id, _SAFE_ID, "project")
        rig_sha = _identity(rig_sha256, _SHA256, "rig")
        bundle_sha = _identity(bundle_sha256, _SHA256, "bundle")
        if (rig_sha, bundle_sha) not in set(_discover(self.state_root, project)):
            raise MeshBundleEvidenceNotFound("Mesh bundle address was not found")
        try:
            return VerifiedMeshBundleReader(self.state_root).load(
                project, rig_sha, bundle_sha
            )
        except VerifiedMeshBundleReaderError as exc:
            raise MeshBundleEvidenceError("Mesh bundle failed strict verification") from exc


def _detail(verified) -> dict[str, Any]:
    rig, probes, visuals = verified.rig, verified.probes, verified.visuals
    attachments = _index(rig.get("attachments"), "id", "mesh attachments")
    probe_items = _index(probes.get("attachments"), "attachment_id", "mesh probes")
    artifacts = visuals.get("artifacts")
    targets = visuals.get("targets")
    if not isinstance(artifacts, list) or not isinstance(targets, list):
        raise MeshBundleEvidenceError("Verified mesh visual index is invalid")
    hinges = [
        _hinge(verified, target, attachments, probe_items, artifacts)
        for target in targets
    ]
    hinges.sort(key=lambda item: item["attachment_id"])
    return {
        "format": "autospine-mesh-bundle-evidence",
        "format_version": 1,
        "project_id": verified.project_id,
        "source": {
            "base_rig_sha256": verified.base_rig_sha256,
            "base_bundle_sha256": verified.base_bundle_sha256,
            "layer_manifest_sha256": verified.layer_manifest_sha256,
            "resolved_project_sha256": verified.resolved_project_sha256,
            "rig_sha256": verified.rig_sha256,
            "run_sha256": verified.run_sha256,
            "probes_sha256": verified.probes_sha256,
            "visuals_sha256": verified.visuals_sha256,
            "bundle_sha256": verified.bundle_sha256,
        },
        "status": "converted" if hinges else "reviewed-noop",
        "summary": visuals.get("summary"),
        "hinges": hinges,
    }


def _hinge(verified, target, attachments, probes, artifacts) -> dict[str, Any]:
    if not isinstance(target, Mapping):
        raise MeshBundleEvidenceError("Verified mesh target is invalid")
    identifier = target.get("attachment_id")
    attachment, probe = attachments.get(identifier), probes.get(identifier)
    if not isinstance(attachment, Mapping) or not isinstance(probe, Mapping):
        raise MeshBundleEvidenceError("Verified mesh target evidence is incomplete")
    vertices, triangles = attachment.get("vertices"), attachment.get("triangles")
    action = probe.get("action_probe")
    bend = action.get("distal_bend") if isinstance(action, Mapping) else None
    if not isinstance(vertices, list) or not isinstance(triangles, list) \
            or not isinstance(bend, Mapping):
        raise MeshBundleEvidenceError("Verified mesh topology or bend evidence is invalid")
    negative = _safe_magnitude(bend, "negative")
    positive = _safe_magnitude(bend, "positive")
    selected = [item for item in artifacts if item.get("id") == identifier]
    keyed = {item.get("pose"): item for item in selected}
    if len(selected) != 3 or set(keyed) != {"weights", "setup", "widest-safe"}:
        raise MeshBundleEvidenceError("Verified target visual set is incomplete")
    return {
        "attachment_id": identifier,
        "source_layer_id": target.get("source_layer_id"),
        "side": target.get("side"),
        "proximal_bone_id": target.get("proximal_bone_id"),
        "distal_bone_id": target.get("distal_bone_id"),
        "vertex_count": len(vertices),
        "triangle_count": len(triangles) // 3,
        "continuous_safe_angle_deg": {
            "minimum": -negative,
            "maximum": positive,
        },
        "images": {
            "heatmap": _image_ref(verified, keyed["weights"]),
            "setup": _image_ref(verified, keyed["setup"]),
            "widest_safe": _image_ref(verified, keyed["widest-safe"]),
        },
    }


def _image_ref(verified, artifact) -> dict[str, Any]:
    digest = artifact.get("png_sha256")
    base = "/api/projects/{}/mesh-bundles/{}/{}/images/{}".format(
        quote(verified.project_id, safe=""), verified.rig_sha256,
        verified.bundle_sha256, digest,
    )
    return {
        "path": artifact.get("path"),
        "png_sha256": digest,
        "width": artifact.get("width"),
        "height": artifact.get("height"),
        "angle_deg": artifact.get("angle_deg"),
        "url": base,
    }


def _safe_magnitude(bend: Mapping[str, Any], direction: str) -> int:
    item = bend.get(direction)
    value = item.get("max_contiguous_magnitude_deg") if isinstance(item, Mapping) else None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 135:
        raise MeshBundleEvidenceError("Verified safe bend evidence is invalid")
    return value


def _index(value: Any, key: str, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        raise MeshBundleEvidenceError(f"Verified {label} are invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for item in value:
        identifier = item.get(key) if isinstance(item, Mapping) else None
        if not isinstance(identifier, str) or identifier in result:
            raise MeshBundleEvidenceError(f"Verified {label} are invalid")
        result[identifier] = item
    return result


def _discover(root: Path, project_id: str) -> tuple[tuple[str, str], ...]:
    current = Path(root)
    if not current.exists():
        return ()
    for name in ("builds", project_id, "mesh-rig-ir"):
        current = _exact_child(current, name)
        if current is None:
            return ()
    result: list[tuple[str, str]] = []
    for rig in _children(current):
        if not _SHA256.fullmatch(rig.name):
            continue
        _real_directory(rig)
        for bundle in _children(rig):
            if not _SHA256.fullmatch(bundle.name):
                continue
            _real_directory(bundle)
            result.append((rig.name, bundle.name))
            if len(result) > _MAX_ADDRESSES:
                raise MeshBundleEvidenceError("Mesh bundle discovery limit was exceeded")
    return tuple(sorted(result))


def _exact_child(parent: Path, name: str) -> Path | None:
    _real_directory(parent)
    try:
        matches = [item for item in parent.iterdir()
                   if item.name.casefold() == name.casefold()]
    except OSError as exc:
        raise MeshBundleEvidenceError("Mesh bundle discovery path cannot be enumerated") from exc
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name or _alias(matches[0]):
        raise MeshBundleEvidenceError("Mesh bundle discovery path is case-aliased")
    return _real_directory(matches[0])


def _children(path: Path) -> list[Path]:
    _real_directory(path)
    try:
        items = list(path.iterdir())
    except OSError as exc:
        raise MeshBundleEvidenceError("Mesh bundle addresses cannot be enumerated") from exc
    folded: set[str] = set()
    for item in items:
        key = item.name.casefold()
        if key in folded or _alias(item):
            raise MeshBundleEvidenceError("Mesh bundle discovery contains an alias")
        folded.add(key)
    return items


def _real_directory(path: Path) -> Path:
    try:
        if _alias(path) or not stat.S_ISDIR(path.lstat().st_mode):
            raise MeshBundleEvidenceError("Mesh bundle discovery path is not a directory")
    except OSError as exc:
        raise MeshBundleEvidenceError("Mesh bundle discovery path cannot be inspected") from exc
    return path


def _alias(path: Path) -> bool:
    try:
        info = path.lstat()
        junction = getattr(path, "is_junction", None)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return stat.S_ISLNK(info.st_mode) or bool(callable(junction) and junction()) \
            or bool(getattr(info, "st_file_attributes", 0) & reparse)
    except OSError:
        return True


def _identity(value: Any, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise MeshBundleEvidenceNotFound(f"Mesh bundle {label} identity is invalid")
    return value
