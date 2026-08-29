"""Atomic immutable storage for validated P5 motion-retarget bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Any

from .atomic_staging import create_same_parent_staging
from .motion_retarget_bundle_contract import (
    MotionRetargetBundleContract, MotionRetargetBundleContractError,
    build_motion_retarget_bundle_contract,
)

class MotionRetargetBundleStoreError(RuntimeError):
    """Raised when a retarget bundle cannot be published or reused safely."""

@dataclass(frozen=True, slots=True)
class PublishedMotionRetargetBundle:
    path: Path
    project_id: str
    clip_id: str
    target_profile_sha256: str
    instance_sha256: str
    run_document_sha256: str
    report_sha256: str
    mesh_report_sha256: str
    bundle_sha256: str
    reused: bool

class MotionRetargetBundleStore:
    """Publish the fixed five-document inventory under two exact SHA levels."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self,
        project_id: str,
        target_profile: Mapping[str, Any],
        instance: Mapping[str, Any],
        run_manifest: Mapping[str, Any],
        retarget_report: Mapping[str, Any],
        mesh_regression: Mapping[str, Any],
    ) -> PublishedMotionRetargetBundle:
        try:
            contract = build_motion_retarget_bundle_contract(
                project_id, target_profile, instance, run_manifest,
                retarget_report, mesh_regression)
        except MotionRetargetBundleContractError as exc:
            raise MotionRetargetBundleStoreError(
                "motion-retarget bundle publication input is invalid") from exc
        staging: Path | None = None
        instance_parent: Path | None = None
        try:
            instance_parent = _publication_parent(self.state_root, contract)
            destination = _existing_child(instance_parent, contract.bundle_sha256)
            if destination is not None:
                _verify(destination, contract, content_address=True)
                return _published(destination, contract, reused=True)
            staging = create_same_parent_staging(
                instance_parent, prefix=f".{contract.bundle_sha256[:12]}.",
            )
            _require_real_directory(staging, "retarget bundle staging directory")
            for name, data in contract.document_bytes.items():
                _write_file(staging / name, data)
            _verify(staging, contract, content_address=False)
            _sync_directory(staging)
            try:
                destination = instance_parent / contract.bundle_sha256
                os.rename(staging, destination)
                staging = None
                _sync_directory(instance_parent)
                reused = False
            except OSError:
                destination = _existing_child(instance_parent, contract.bundle_sha256)
                if destination is None:
                    raise
                _verify(destination, contract, content_address=True)
                reused = True
            _verify(destination, contract, content_address=True)
            return _published(destination, contract, reused=reused)
        except MotionRetargetBundleStoreError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise MotionRetargetBundleStoreError(
                "could not atomically publish motion-retarget bundle") from exc
        finally:
            if staging is not None:
                _remove_staging(staging, instance_parent)

def _published(path, contract, *, reused):
    return PublishedMotionRetargetBundle(
        path, contract.project_id, contract.clip_id,
        contract.target_profile_sha256, contract.instance_sha256,
        contract.run_document_sha256, contract.report_sha256,
        contract.mesh_report_sha256, contract.bundle_sha256, reused,
    )

def _publication_parent(
    state_root: Path, contract: MotionRetargetBundleContract,
) -> Path:
    current = _safe_state_root(state_root)
    for name in ("builds", contract.project_id, "motion-instances",
                 contract.instance_sha256):
        current = _exact_directory(current, name)
    return current

def _safe_state_root(root: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(root)))
    current = Path(absolute.parts[0])
    _require_real_directory(current, "retarget state-root ancestor")
    for name in absolute.parts[1:]:
        child = current / name
        try:
            child.lstat()
        except FileNotFoundError:
            try:
                child.mkdir()
            except FileExistsError:
                pass
            except OSError as exc:
                raise MotionRetargetBundleStoreError(
                    "could not create retarget state root") from exc
        except OSError as exc:
            raise MotionRetargetBundleStoreError(
                "retarget state-root ancestor cannot be read") from exc
        current = _require_real_directory(child, "retarget state-root ancestor")
    return current

def _exact_directory(parent: Path, name: str) -> Path:
    found = _existing_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise MotionRetargetBundleStoreError(
                "could not create retarget bundle hierarchy") from exc
        found = _existing_child(parent, name)
    if found is None:
        raise MotionRetargetBundleStoreError("retarget bundle hierarchy disappeared")
    return _require_real_directory(found, f"retarget bundle path {name}")

def _existing_child(parent: Path, name: str) -> Path | None:
    _require_real_directory(parent, "retarget bundle parent")
    try:
        matches = [item for item in parent.iterdir()
                   if item.name.casefold() == name.casefold()]
    except OSError as exc:
        raise MotionRetargetBundleStoreError(
            "retarget bundle hierarchy cannot be enumerated") from exc
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name or _is_alias(matches[0]):
        raise MotionRetargetBundleStoreError(
            f"retarget bundle path is aliased: {name}")
    return matches[0]

def _write_file(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())

def _verify(directory, contract, *, content_address):
    directory = _require_real_directory(directory, "retarget bundle directory")
    if content_address and directory.name != contract.bundle_sha256:
        raise MotionRetargetBundleStoreError(
            "retarget bundle has the wrong content-address path")
    expected = contract.document_bytes
    files = _inventory(directory)
    if set(files) != set(expected):
        raise MotionRetargetBundleStoreError(
            "retarget bundle inventory is incomplete or has extra entries")
    actual = {name: _read_exact(files[name], len(data))
              for name, data in expected.items()}
    if actual != expected:
        raise MotionRetargetBundleStoreError("retarget bundle document bytes changed")
    try:
        documents = [json.loads(actual[name]) for name in expected]
        rebuilt = build_motion_retarget_bundle_contract(contract.project_id, *documents)
    except (
        json.JSONDecodeError, UnicodeDecodeError,
        MotionRetargetBundleContractError,
    ) as exc:
        raise MotionRetargetBundleStoreError(
            "retarget bundle semantic rebuild failed") from exc
    if rebuilt != contract:
        raise MotionRetargetBundleStoreError("retarget bundle semantic identity changed")

def _inventory(root: Path) -> dict[str, Path]:
    try:
        children = list(root.iterdir())
    except OSError as exc:
        raise MotionRetargetBundleStoreError(
            "retarget bundle inventory cannot be read") from exc
    result: dict[str, Path] = {}
    folded: set[str] = set()
    for child in children:
        key = child.name.casefold()
        if key in folded or _is_alias(child):
            raise MotionRetargetBundleStoreError(
                "retarget bundle inventory contains an alias")
        folded.add(key)
        try:
            mode = child.lstat().st_mode
        except OSError as exc:
            raise MotionRetargetBundleStoreError(
                "retarget bundle entry cannot be inspected") from exc
        if not stat.S_ISREG(mode):
            raise MotionRetargetBundleStoreError(
                "retarget bundle contains a non-regular entry")
        result[child.name] = child
    return result

def _read_exact(path: Path, expected_size: int) -> bytes:
    if _is_alias(path):
        raise MotionRetargetBundleStoreError("retarget bundle file is aliased")
    try:
        if path.lstat().st_size != expected_size:
            raise MotionRetargetBundleStoreError("retarget bundle file size differs")
        with path.open("rb") as handle:
            data = handle.read(expected_size + 1)
    except OSError as exc:
        raise MotionRetargetBundleStoreError(
            "retarget bundle file cannot be read") from exc
    if len(data) != expected_size:
        raise MotionRetargetBundleStoreError(
            "retarget bundle file changed while being read")
    return data

def _require_real_directory(path: Path, label: str) -> Path:
    if _is_alias(path):
        raise MotionRetargetBundleStoreError(f"{label} is aliased")
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise MotionRetargetBundleStoreError(f"{label} is not a real directory")
    except OSError as exc:
        raise MotionRetargetBundleStoreError(f"{label} cannot be inspected") from exc
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
        _require_real_directory(parent, "retarget bundle staging parent")
        _require_real_directory(path, "retarget bundle staging directory")
        if path.resolve(strict=True).parent != parent.resolve(strict=True):
            return
    except (MotionRetargetBundleStoreError, OSError, RuntimeError):
        return
    try:
        shutil.rmtree(path.resolve(strict=True))
    except OSError:
        return

def _staging_name(name: str) -> bool:
    if len(name) < 15 or name[0] != "." or name[13] != ".":
        return False
    return all(character in "0123456789abcdef" for character in name[1:13]) \
        and bool(name[14:]) and all(
            character.isalnum() or character in "_-" for character in name[14:]
        )
