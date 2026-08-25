"""Atomic immutable storage for exact reproducible MotionIR bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from .motion_bundle_contract import (
    MotionBundleContract,
    MotionBundleContractError,
    build_motion_bundle_contract,
)


class MotionBundleStoreError(RuntimeError):
    """Raised when an immutable motion bundle cannot be safely published."""

@dataclass(frozen=True, slots=True)
class PublishedMotionBundle:
    path: Path
    clip_id: str
    clip_sha256: str
    run_sha256: str
    bundle_sha256: str
    reused: bool

class MotionBundleStore:
    """Publish one admitted exact inventory under clip and bundle SHAs."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self,
        motion_ir: Mapping[str, Any],
        run_manifest: Mapping[str, Any],
        *,
        raw_bvh: bytes | None = None,
        bvh_map: Mapping[str, Any] | None = None,
    ) -> PublishedMotionBundle:
        try:
            contract = _build_contract(
                motion_ir, run_manifest, raw_bvh=raw_bvh, bvh_map=bvh_map,
            )
        except MotionBundleContractError as exc:
            raise MotionBundleStoreError("motion bundle publication input is invalid") from exc
        staging: Path | None = None
        clip_parent: Path | None = None
        try:
            state_root = _safe_state_root(self.state_root)
            clip_parent = _exact_directory(
                _exact_directory(state_root, "motions"), contract.clip_sha256,
            )
            _require_within(state_root, clip_parent)
            destination = _existing_child(clip_parent, contract.bundle_sha256)
            if destination is not None:
                _verify(destination, contract, content_address=True)
                return _published(destination, contract, reused=True)
            staging = Path(tempfile.mkdtemp(
                prefix=f".{contract.bundle_sha256[:12]}.", dir=clip_parent,
            ))
            _require_real_directory(staging, "motion bundle staging directory")
            for name, data in contract.document_bytes.items():
                _write_file(staging / name, data)
            _verify(staging, contract, content_address=False)
            _sync_directory(staging)
            try:
                destination = clip_parent / contract.bundle_sha256
                os.rename(staging, destination)
                staging = None
                _sync_directory(clip_parent)
                reused = False
            except OSError:
                destination = _existing_child(clip_parent, contract.bundle_sha256)
                if destination is None:
                    raise
                _verify(destination, contract, content_address=True)
                reused = True
            _verify(destination, contract, content_address=True)
            return _published(destination, contract, reused=reused)
        except MotionBundleStoreError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise MotionBundleStoreError("could not atomically publish motion bundle") from exc
        finally:
            if staging is not None:
                _remove_staging(staging, clip_parent)

def _published(
    path: Path, contract: MotionBundleContract, *, reused: bool,
) -> PublishedMotionBundle:
    return PublishedMotionBundle(
        path, contract.clip_id, contract.clip_sha256, contract.run_sha256,
        contract.bundle_sha256, reused,
    )

def _safe_state_root(root: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(root)))
    parts = absolute.parts
    current = Path(parts[0])
    _require_real_directory(current, "motion bundle state-root ancestor")
    for name in parts[1:]:
        current = _state_component(current, name)
    return _require_real_directory(current, "motion bundle state root")

def _state_component(parent: Path, name: str) -> Path:
    child = parent / name
    try:
        child.lstat()
    except FileNotFoundError:
        try:
            child.mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise MotionBundleStoreError("could not create motion state root") from exc
    except OSError as exc:
        raise MotionBundleStoreError("motion state-root ancestor cannot be read") from exc
    return _require_real_directory(child, "motion bundle state-root ancestor")

def _exact_directory(parent: Path, name: str) -> Path:
    found = _existing_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise MotionBundleStoreError("could not create motion bundle hierarchy") from exc
        found = _existing_child(parent, name)
    if found is None:
        raise MotionBundleStoreError("motion bundle hierarchy disappeared")
    return _require_real_directory(found, f"motion bundle path {name}")

def _existing_child(parent: Path, name: str) -> Path | None:
    _require_real_directory(parent, "motion bundle parent")
    try:
        matches = [item for item in parent.iterdir()
                   if item.name.casefold() == name.casefold()]
    except OSError as exc:
        raise MotionBundleStoreError("motion bundle hierarchy cannot be enumerated") from exc
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name or _is_alias(matches[0]):
        raise MotionBundleStoreError(f"motion bundle path is aliased: {name}")
    return matches[0]

def _write_file(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())

def _verify(
    directory: Path, contract: MotionBundleContract, *, content_address: bool,
) -> None:
    directory = _require_real_directory(directory, "motion bundle directory")
    if content_address and directory.name != contract.bundle_sha256:
        raise MotionBundleStoreError("motion bundle has the wrong content-address path")
    expected = contract.document_bytes
    files = _inventory(directory)
    if set(files) != set(expected):
        raise MotionBundleStoreError("motion bundle inventory is incomplete or has extra entries")
    actual = {name: _read_exact(files[name], len(data)) for name, data in expected.items()}
    if actual != expected:
        raise MotionBundleStoreError("motion bundle document bytes changed")
    try:
        kwargs = {}
        if contract.source_kind == "bvh":
            kwargs = {
                "raw_bvh": actual["source.bvh"],
                "bvh_map": json.loads(actual["map.json"]),
            }
        rebuilt = build_motion_bundle_contract(
            json.loads(actual["motion.json"]),
            json.loads(actual["run-manifest.json"]),
            **kwargs,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, MotionBundleContractError) as exc:
        raise MotionBundleStoreError("motion bundle semantic rebuild failed") from exc
    if rebuilt != contract:
        raise MotionBundleStoreError("motion bundle semantic identity changed")

def _inventory(root: Path) -> dict[str, Path]:
    try:
        children = list(root.iterdir())
    except OSError as exc:
        raise MotionBundleStoreError("motion bundle inventory cannot be read") from exc
    result: dict[str, Path] = {}
    for child in children:
        if _is_alias(child):
            raise MotionBundleStoreError("motion bundle inventory contains an alias")
        try:
            mode = child.lstat().st_mode
        except OSError as exc:
            raise MotionBundleStoreError("motion bundle entry cannot be inspected") from exc
        if not stat.S_ISREG(mode):
            raise MotionBundleStoreError("motion bundle contains a non-regular entry")
        result[child.name] = child
    return result

def _read_exact(path: Path, expected_size: int) -> bytes:
    if _is_alias(path):
        raise MotionBundleStoreError("motion bundle file is aliased")
    try:
        if path.lstat().st_size != expected_size:
            raise MotionBundleStoreError("motion bundle file size differs")
        with path.open("rb") as handle:
            data = handle.read(expected_size + 1)
    except OSError as exc:
        raise MotionBundleStoreError("motion bundle file cannot be read") from exc
    if len(data) != expected_size:
        raise MotionBundleStoreError("motion bundle file changed while being read")
    return data

def _require_real_directory(path: Path, label: str) -> Path:
    if _is_alias(path):
        raise MotionBundleStoreError(f"{label} is aliased")
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise MotionBundleStoreError(f"{label} is not a real directory")
    except OSError as exc:
        raise MotionBundleStoreError(f"{label} cannot be inspected") from exc
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
        trusted = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        if os.path.commonpath((trusted, resolved)) != str(trusted):
            raise MotionBundleStoreError("motion bundle hierarchy escaped its state root")
    except (OSError, ValueError) as exc:
        raise MotionBundleStoreError("motion bundle hierarchy cannot be resolved") from exc

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
        _require_real_directory(parent, "motion bundle staging parent")
        _require_real_directory(path, "motion bundle staging directory")
        if path.resolve(strict=True).parent != parent.resolve(strict=True):
            return
        _require_within(parent, path)
    except (MotionBundleStoreError, OSError, RuntimeError):
        return
    try:
        shutil.rmtree(path.resolve(strict=True))
    except OSError:
        return

def _staging_name(name: str) -> bool:
    if len(name) < 15 or name[0] != "." or name[13] != ".":
        return False
    return all(character in "0123456789abcdef" for character in name[1:13]) and \
        bool(name[14:]) and all(
            character.isalnum() or character in "_-" for character in name[14:]
        )


def _build_contract(motion_ir, run_manifest, *, raw_bvh, bvh_map):
    if raw_bvh is None and bvh_map is None:
        return build_motion_bundle_contract(motion_ir, run_manifest)
    return build_motion_bundle_contract(
        motion_ir, run_manifest, raw_bvh=raw_bvh, bvh_map=bvh_map,
    )
