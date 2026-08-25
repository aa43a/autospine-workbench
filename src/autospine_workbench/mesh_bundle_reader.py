"""Secure read-only boundary for exact content-addressed P3 mesh bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .mesh_bundle_contract import (
    DOCUMENT_NAMES,
    MAX_ARTIFACTS,
    MAX_ARTIFACT_PNG_BYTES,
    MAX_DOCUMENT_BYTES,
    MAX_TOTAL_JSON_BYTES,
    MAX_TOTAL_PNG_BYTES,
)
from .mesh_bundle_integrity import (
    MeshBundleIntegrityError,
    MeshBundleSnapshot,
    VerifiedMeshBundle,
    verify_mesh_bundle_snapshot,
)


_PNG_DIRECTORIES = frozenset({"weights", "poses"})


class VerifiedMeshBundleReaderError(RuntimeError):
    """Raised when an exact P3 bundle cannot be snapshotted and fully verified."""


@dataclass(frozen=True, slots=True)
class VerifiedMeshBundleReader:
    """Resolve no aliases and verify one immutable bundle without writing state."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self,
        project_id: str,
        rig_sha256: str,
        bundle_sha256: str,
    ) -> VerifiedMeshBundle:
        """Read every admitted bundle file once, then reproduce all evidence."""

        try:
            project = require_safe_token(project_id, "Project id")
            rig_sha = require_sha256(rig_sha256, "Mesh RigIR digest")
            bundle_sha = require_sha256(bundle_sha256, "Mesh bundle digest")
        except LayerManifestError as exc:
            raise VerifiedMeshBundleReaderError(
                "Verified mesh bundle identity is invalid"
            ) from exc
        try:
            directory = _resolve_bundle(
                self.state_root, project, rig_sha, bundle_sha
            )
            snapshot = _snapshot(directory)
            verified = verify_mesh_bundle_snapshot(
                snapshot,
                state_root=self.state_root,
                expected_project_id=project,
                expected_rig_sha256=rig_sha,
                expected_bundle_sha256=bundle_sha,
            )
            if verified.path != directory:
                raise VerifiedMeshBundleReaderError(
                    "Verified mesh bundle path changed during verification"
                )
            return verified
        except VerifiedMeshBundleReaderError:
            raise
        except (
            MeshBundleIntegrityError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            KeyError,
            OverflowError,
        ) as exc:
            raise VerifiedMeshBundleReaderError(
                f"Verified mesh bundle load failed: {exc}"
            ) from exc


def _resolve_bundle(root: Path, project: str, rig_sha: str, bundle_sha: str) -> Path:
    try:
        if _is_alias(root):
            raise VerifiedMeshBundleReaderError("Mesh bundle state root is aliased")
        trusted = root.resolve(strict=True)
        _real_directory(trusted, "mesh bundle state root")
        current = trusted
        for name in ("builds", project, "mesh-rig-ir", rig_sha, bundle_sha):
            current = _exact_directory(current, name)
        resolved = current.resolve(strict=True)
        resolved.relative_to(trusted)
        if resolved != current or _is_alias(resolved):
            raise VerifiedMeshBundleReaderError("Mesh bundle path is aliased")
        return resolved
    except VerifiedMeshBundleReaderError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerifiedMeshBundleReaderError(
            "Exact mesh bundle path was not found"
        ) from exc


def _exact_directory(parent: Path, name: str) -> Path:
    _real_directory(parent, "mesh bundle parent")
    children = _children(parent)
    matches = [item for item in children if item.name.casefold() == name.casefold()]
    if len(matches) != 1 or matches[0].name != name:
        raise VerifiedMeshBundleReaderError(
            f"Mesh bundle path is missing or case-mismatched: {name}"
        )
    return _real_directory(matches[0], f"mesh bundle path {name}")


def _snapshot(root: Path) -> MeshBundleSnapshot:
    root_entries = _children(root)
    documents: dict[str, Path] = {}
    png_paths: dict[str, Path] = {}
    directories: set[str] = set()
    for child in root_entries:
        if child.name in DOCUMENT_NAMES:
            documents[child.name] = _regular_file(child, child.name)
        elif child.name in _PNG_DIRECTORIES:
            directory = _real_directory(child, f"mesh bundle {child.name}")
            directories.add(child.name)
            for image in _children(directory):
                if not image.name.endswith(".png"):
                    raise VerifiedMeshBundleReaderError(
                        "Mesh bundle artifact inventory is invalid"
                    )
                relative = f"{child.name}/{image.name}"
                png_paths[relative] = _regular_file(image, relative)
        else:
            raise VerifiedMeshBundleReaderError(
                "Mesh bundle has an unexpected root entry"
            )
    if set(documents) != set(DOCUMENT_NAMES):
        raise VerifiedMeshBundleReaderError("Mesh bundle documents are incomplete")
    if directories != {path.split("/", 1)[0] for path in png_paths}:
        raise VerifiedMeshBundleReaderError(
            "Mesh bundle artifact directories are incomplete or empty"
        )
    all_paths = (*documents, *png_paths)
    if len({item.casefold() for item in all_paths}) != len(all_paths):
        raise VerifiedMeshBundleReaderError("Mesh bundle paths are case aliases")
    if len(png_paths) > MAX_ARTIFACTS:
        raise VerifiedMeshBundleReaderError("Mesh bundle has too many PNG artifacts")

    document_items, json_total = [], 0
    for name in DOCUMENT_NAMES:
        data = _read_snapshot(documents[name], MAX_DOCUMENT_BYTES, name)
        json_total += len(data)
        if json_total > MAX_TOTAL_JSON_BYTES:
            raise VerifiedMeshBundleReaderError("Mesh bundle JSON budget is exceeded")
        document_items.append((name, data))
    png_items, png_total = [], 0
    for name, path in sorted(png_paths.items()):
        data = _read_snapshot(path, MAX_ARTIFACT_PNG_BYTES, name)
        png_total += len(data)
        if png_total > MAX_TOTAL_PNG_BYTES:
            raise VerifiedMeshBundleReaderError("Mesh bundle PNG budget is exceeded")
        png_items.append((name, data))
    return MeshBundleSnapshot(root, tuple(document_items), tuple(png_items))


def _children(directory: Path) -> list[Path]:
    try:
        items = list(directory.iterdir())
    except OSError as exc:
        raise VerifiedMeshBundleReaderError(
            "Mesh bundle directory cannot be enumerated"
        ) from exc
    folded: set[str] = set()
    for item in items:
        key = item.name.casefold()
        if key in folded or _is_alias(item):
            raise VerifiedMeshBundleReaderError(
                "Mesh bundle directory contains a case alias"
            )
        folded.add(key)
    return items


def _read_snapshot(path: Path, maximum: int, label: str) -> bytes:
    try:
        metadata = path.lstat()
        size = metadata.st_size
        if not stat.S_ISREG(metadata.st_mode) or _is_alias(path):
            raise VerifiedMeshBundleReaderError(f"{label} is not a regular file")
        if size > maximum:
            raise VerifiedMeshBundleReaderError(f"{label} exceeds its byte limit")
        with path.open("rb") as handle:
            data = handle.read(maximum + 1)
    except VerifiedMeshBundleReaderError:
        raise
    except OSError as exc:
        raise VerifiedMeshBundleReaderError(f"{label} cannot be read") from exc
    if len(data) != size:
        raise VerifiedMeshBundleReaderError(f"{label} changed while being read")
    return data


def _regular_file(path: Path, label: str) -> Path:
    try:
        if _is_alias(path) or not stat.S_ISREG(path.lstat().st_mode):
            raise VerifiedMeshBundleReaderError(f"{label} is not a regular file")
    except OSError as exc:
        raise VerifiedMeshBundleReaderError(f"{label} cannot be inspected") from exc
    return path


def _real_directory(path: Path, label: str) -> Path:
    try:
        if _is_alias(path) or not stat.S_ISDIR(path.lstat().st_mode):
            raise VerifiedMeshBundleReaderError(f"{label} is not a real directory")
    except OSError as exc:
        raise VerifiedMeshBundleReaderError(f"{label} cannot be inspected") from exc
    return path


def _is_alias(path: Path) -> bool:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            return True
        junction = getattr(path, "is_junction", None)
        if callable(junction) and junction():
            return True
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(getattr(metadata, "st_file_attributes", 0) & reparse)
    except OSError:
        return True
