"""Atomic immutable storage for canonical P4 profile and probe bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from .ik_bundle_contract import (
    IkBundleContract,
    IkBundleContractError,
    build_ik_bundle_contract,
)


class IkBundleStoreError(RuntimeError):
    """Raised when an immutable P4 bundle cannot be published or reused safely."""


@dataclass(frozen=True, slots=True)
class PublishedIkBundle:
    path: Path
    profile_sha256: str
    bundle_sha256: str


class IkBundleStore:
    """Publish exactly profile.json and probes.json under a double SHA address."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self,
        project_id: str,
        profile: Mapping[str, Any],
        probes: Mapping[str, Any],
    ) -> PublishedIkBundle:
        try:
            contract = build_ik_bundle_contract(project_id, profile, probes)
        except IkBundleContractError as exc:
            raise IkBundleStoreError("IK bundle publication input is invalid") from exc
        staging: Path | None = None
        profile_parent: Path | None = None
        try:
            profile_parent = _publication_parent(self.state_root, contract)
            destination = _existing_child(profile_parent, contract.bundle_sha256)
            if destination is not None:
                _verify(destination, contract, content_address=True)
                return _published(destination, contract)
            staging = Path(tempfile.mkdtemp(
                prefix=f".{contract.bundle_sha256[:12]}.", dir=profile_parent
            ))
            _require_real_directory(staging, "IK bundle staging directory")
            _write_contract(staging, contract)
            _verify(staging, contract, content_address=False)
            _sync_directory(staging)
            try:
                destination = profile_parent / contract.bundle_sha256
                os.rename(staging, destination)
                staging = None
                _sync_directory(profile_parent)
            except OSError:
                destination = _existing_child(profile_parent, contract.bundle_sha256)
                if destination is None:
                    raise
                _verify(destination, contract, content_address=True)
            _verify(destination, contract, content_address=True)
            return _published(destination, contract)
        except IkBundleStoreError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise IkBundleStoreError("could not atomically publish IK bundle") from exc
        finally:
            if staging is not None:
                _remove_staging(staging, profile_parent)


def _published(path: Path, contract: IkBundleContract) -> PublishedIkBundle:
    return PublishedIkBundle(path, contract.profile_sha256, contract.bundle_sha256)


def _publication_parent(state_root: Path, contract: IkBundleContract) -> Path:
    try:
        state_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise IkBundleStoreError("could not create IK bundle state root") from exc
    current = _require_real_directory(state_root, "IK bundle state root")
    for name in (
        "builds", contract.project_id, "ik-targets", contract.profile_sha256,
    ):
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
            raise IkBundleStoreError("could not create IK bundle hierarchy") from exc
        found = _existing_child(parent, name)
    if found is None:
        raise IkBundleStoreError("IK bundle hierarchy disappeared")
    return _require_real_directory(found, f"IK bundle path {name}")


def _existing_child(parent: Path, name: str) -> Path | None:
    _require_real_directory(parent, "IK bundle parent")
    try:
        matches = [
            item for item in parent.iterdir()
            if item.name.casefold() == name.casefold()
        ]
    except OSError as exc:
        raise IkBundleStoreError("IK bundle hierarchy cannot be enumerated") from exc
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name or _is_alias(matches[0]):
        raise IkBundleStoreError(f"IK bundle path is aliased: {name}")
    return matches[0]


def _write_contract(staging: Path, contract: IkBundleContract) -> None:
    for name, data in contract.document_bytes.items():
        _write_file(staging / name, data)


def _write_file(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _verify(
    directory: Path,
    contract: IkBundleContract,
    *,
    content_address: bool,
) -> None:
    directory = _require_real_directory(directory, "IK bundle directory")
    if content_address and directory.name != contract.bundle_sha256:
        raise IkBundleStoreError("IK bundle has the wrong content-address path")
    expected = contract.document_bytes
    files = _inventory(directory)
    if set(files) != set(expected):
        raise IkBundleStoreError("IK bundle inventory is incomplete or has extra entries")
    if len({name.casefold() for name in files}) != len(files):
        raise IkBundleStoreError("IK bundle inventory contains case aliases")
    for name, data in expected.items():
        if _read_exact(files[name], len(data)) != data:
            raise IkBundleStoreError(f"IK bundle file was changed: {name}")


def _inventory(root: Path) -> dict[str, Path]:
    try:
        children = list(root.iterdir())
    except OSError as exc:
        raise IkBundleStoreError("IK bundle inventory cannot be read") from exc
    result: dict[str, Path] = {}
    folded: set[str] = set()
    for child in children:
        key = child.name.casefold()
        if key in folded or _is_alias(child):
            raise IkBundleStoreError("IK bundle inventory contains an alias")
        folded.add(key)
        try:
            mode = child.lstat().st_mode
        except OSError as exc:
            raise IkBundleStoreError("IK bundle entry cannot be inspected") from exc
        if not stat.S_ISREG(mode):
            raise IkBundleStoreError("IK bundle contains a non-regular entry")
        result[child.name] = child
    return result


def _read_exact(path: Path, expected_size: int) -> bytes:
    if _is_alias(path):
        raise IkBundleStoreError("IK bundle file is aliased")
    try:
        if path.lstat().st_size != expected_size:
            raise IkBundleStoreError("IK bundle file size differs")
        with path.open("rb") as handle:
            data = handle.read(expected_size + 1)
    except OSError as exc:
        raise IkBundleStoreError("IK bundle file cannot be read") from exc
    if len(data) != expected_size:
        raise IkBundleStoreError("IK bundle file changed while being read")
    return data


def _require_real_directory(path: Path, label: str) -> Path:
    if _is_alias(path):
        raise IkBundleStoreError(f"{label} is aliased")
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise IkBundleStoreError(f"{label} is not a real directory")
    except OSError as exc:
        raise IkBundleStoreError(f"{label} cannot be inspected") from exc
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
            raise IkBundleStoreError("IK bundle hierarchy escaped its state root")
    except (OSError, ValueError) as exc:
        raise IkBundleStoreError("IK bundle hierarchy cannot be resolved") from exc


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
        _require_real_directory(parent, "IK bundle staging parent")
        _require_real_directory(path, "IK bundle staging directory")
        resolved_parent = parent.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        if resolved_path.parent != resolved_parent:
            return
        _require_within(parent, path)
    except (IkBundleStoreError, OSError, RuntimeError):
        return
    try:
        shutil.rmtree(resolved_path)
    except OSError:
        return


def _staging_name(name: str) -> bool:
    if len(name) < 15 or name[0] != "." or name[13] != ".":
        return False
    return all(character in "0123456789abcdef" for character in name[1:13]) and \
        bool(name[14:]) and all(
            character.isalnum() or character in "_-" for character in name[14:]
        )
