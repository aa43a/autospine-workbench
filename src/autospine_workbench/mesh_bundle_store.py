"""Atomic immutable storage for validated P3 mesh bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
from typing import Any

from .atomic_staging import create_same_parent_staging
from .mesh_bundle_contract import (
    MeshBundleContract,
    MeshBundleContractError,
    build_mesh_bundle_contract,
)


class MeshBundleStoreError(RuntimeError):
    """Raised when an immutable mesh bundle cannot be safely published or reused."""


@dataclass(frozen=True, slots=True)
class PublishedMeshBundle:
    path: Path
    rig_sha256: str
    bundle_sha256: str


class MeshBundleStore:
    """Publish canonical documents and visual PNGs under their content address."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(self, project_id: str, rig: Mapping[str, Any], run: Mapping[str, Any],
                probes: Mapping[str, Any], visuals: Mapping[str, Any],
                png_by_path: Mapping[str, bytes]) -> PublishedMeshBundle:
        try:
            contract = build_mesh_bundle_contract(
                project_id, rig, run, probes, visuals, png_by_path
            )
        except MeshBundleContractError as exc:
            raise MeshBundleStoreError("mesh bundle publication input is invalid") from exc
        staging: Path | None = None
        rig_parent: Path | None = None
        try:
            rig_parent = _publication_parent(self.state_root, contract)
            destination = _existing_child(rig_parent, contract.bundle_sha256)
            if destination is not None:
                _verify(destination, contract, content_address=True)
                return _published(destination, contract)
            staging = create_same_parent_staging(
                rig_parent, prefix=f".{contract.bundle_sha256[:12]}.",
            )
            _require_real_directory(staging, "mesh bundle staging directory")
            _write_contract(staging, contract)
            _verify(staging, contract, content_address=False)
            _sync_directory(staging)
            try:
                os.rename(staging, rig_parent / contract.bundle_sha256)
                destination, staging = rig_parent / contract.bundle_sha256, None
                _sync_directory(rig_parent)
            except OSError:
                destination = _existing_child(rig_parent, contract.bundle_sha256)
                if destination is None:
                    raise
                _verify(destination, contract, content_address=True)
            _verify(destination, contract, content_address=True)
            return _published(destination, contract)
        except MeshBundleStoreError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise MeshBundleStoreError("could not atomically publish mesh bundle") from exc
        finally:
            if staging is not None:
                _remove_staging(staging, rig_parent)


def _published(path: Path, contract: MeshBundleContract) -> PublishedMeshBundle:
    return PublishedMeshBundle(path, contract.rig_sha256, contract.bundle_sha256)


def _publication_parent(state_root: Path, contract: MeshBundleContract) -> Path:
    try:
        state_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MeshBundleStoreError("could not create mesh bundle state root") from exc
    current = _require_real_directory(state_root, "mesh bundle state root")
    for name in ("builds", contract.project_id, "mesh-rig-ir", contract.rig_sha256):
        current = _exact_directory(current, name)
    _require_within(state_root, current)
    return current


def _exact_directory(parent: Path, name: str) -> Path:
    found = _existing_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise MeshBundleStoreError("could not create mesh bundle hierarchy") from exc
        found = _existing_child(parent, name)
    if found is None:
        raise MeshBundleStoreError("mesh bundle hierarchy disappeared")
    return _require_real_directory(found, f"mesh bundle path {name}")


def _existing_child(parent: Path, name: str) -> Path | None:
    _require_real_directory(parent, "mesh bundle parent")
    try:
        matches = [item for item in parent.iterdir()
                   if item.name.casefold() == name.casefold()]
    except OSError as exc:
        raise MeshBundleStoreError("mesh bundle hierarchy cannot be enumerated") from exc
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name or _is_alias(matches[0]):
        raise MeshBundleStoreError(f"mesh bundle path is aliased: {name}")
    return matches[0]


def _write_contract(staging: Path, contract: MeshBundleContract) -> None:
    for relative, data in (*contract.document_bytes.items(),
                           *contract.png_bytes_by_path.items()):
        parts = relative.split("/")
        parent = staging
        for part in parts[:-1]:
            parent = _exact_directory(parent, part)
        _write_file(parent / parts[-1], data)
    _sync_tree(staging)


def _write_file(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _verify(directory: Path, contract: MeshBundleContract, *, content_address: bool) -> None:
    directory = _require_real_directory(directory, "mesh bundle directory")
    if content_address and directory.name != contract.bundle_sha256:
        raise MeshBundleStoreError("mesh bundle has the wrong content-address path")
    expected = {**contract.document_bytes, **contract.png_bytes_by_path}
    expected_dirs = {relative.split("/", 1)[0] for relative in expected if "/" in relative}
    files, directories = _inventory(directory)
    if set(files) != set(expected) or directories != expected_dirs:
        raise MeshBundleStoreError("mesh bundle inventory is incomplete or has extra entries")
    if len({name.casefold() for name in files}) != len(files):
        raise MeshBundleStoreError("mesh bundle inventory contains case aliases")
    for relative, data in expected.items():
        if _read_exact(files[relative], len(data)) != data:
            raise MeshBundleStoreError(f"mesh bundle file was changed: {relative}")


def _inventory(root: Path) -> tuple[dict[str, Path], set[str]]:
    files: dict[str, Path] = {}
    directories: set[str] = set()
    pending = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            raise MeshBundleStoreError("mesh bundle inventory cannot be read") from exc
        folded: set[str] = set()
        for child in children:
            if child.name.casefold() in folded or _is_alias(child):
                raise MeshBundleStoreError("mesh bundle inventory contains an alias")
            folded.add(child.name.casefold())
            relative = f"{prefix}/{child.name}" if prefix else child.name
            try:
                mode = child.lstat().st_mode
            except OSError as exc:
                raise MeshBundleStoreError("mesh bundle entry cannot be inspected") from exc
            if stat.S_ISDIR(mode):
                directories.add(relative)
                pending.append((child, relative))
            elif stat.S_ISREG(mode):
                files[relative] = child
            else:
                raise MeshBundleStoreError("mesh bundle contains a non-regular entry")
    return files, directories


def _read_exact(path: Path, expected_size: int) -> bytes:
    if _is_alias(path):
        raise MeshBundleStoreError("mesh bundle file is aliased")
    try:
        if path.lstat().st_size != expected_size:
            raise MeshBundleStoreError("mesh bundle file size differs")
        with path.open("rb") as handle:
            data = handle.read(expected_size + 1)
    except OSError as exc:
        raise MeshBundleStoreError("mesh bundle file cannot be read") from exc
    return data


def _require_real_directory(path: Path, label: str) -> Path:
    if _is_alias(path):
        raise MeshBundleStoreError(f"{label} is aliased")
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise MeshBundleStoreError(f"{label} is not a real directory")
    except OSError as exc:
        raise MeshBundleStoreError(f"{label} cannot be inspected") from exc
    return path


def _is_alias(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    junction = getattr(path, "is_junction", None)
    try:
        if callable(junction) and junction():
            return True
    except OSError:
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & reparse)


def _require_within(root: Path, path: Path) -> None:
    try:
        if os.path.commonpath((root.resolve(strict=True), path.resolve(strict=True))) != \
                str(root.resolve(strict=True)):
            raise MeshBundleStoreError("mesh bundle hierarchy escaped its state root")
    except (OSError, ValueError) as exc:
        raise MeshBundleStoreError("mesh bundle hierarchy cannot be resolved") from exc


def _sync_tree(root: Path) -> None:
    directories = [root]
    for item in root.iterdir():
        if item.is_dir():
            directories.append(item)
    for directory in reversed(directories):
        _sync_directory(directory)


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_staging(path: Path, parent: Path | None) -> None:
    if parent is None or path.parent != parent or not _staging_name(path.name):
        return
    try:
        _require_real_directory(parent, "mesh bundle staging parent")
        _require_real_directory(path, "mesh bundle staging directory")
        resolved_parent = parent.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        if resolved_path.parent != resolved_parent:
            return
        _require_within(parent, path)
    except (MeshBundleStoreError, OSError, RuntimeError):
        return
    try:
        shutil.rmtree(resolved_path)
    except OSError:
        return


def _staging_name(name: str) -> bool:
    if len(name) < 15 or name[0] != "." or name[13] != ".":
        return False
    return all(character in "0123456789abcdef" for character in name[1:13]) and \
        bool(name[14:]) and all(character.isalnum() or character in "_-" for character in name[14:])
