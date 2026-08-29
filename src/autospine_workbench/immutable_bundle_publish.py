"""Atomic write-once publication for :mod:`immutable_bundle_fs`."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from typing import TYPE_CHECKING

from .atomic_staging import create_same_parent_staging
from .immutable_bundle_fs import (
    ImmutableBundleFSError,
    _child,
    _ensure_dir,
    _inventory,
    _real_dir,
    _sha,
)

if TYPE_CHECKING:
    from .immutable_bundle_fs import ImmutableThreeFileBundleFS


@dataclass(frozen=True, slots=True)
class PublishedImmutableBundle:
    path: Path
    primary_sha256: str
    bundle_sha256: str
    reused: bool


def publish_exact_bundle(
    store: ImmutableThreeFileBundleFS,
    primary_sha256: str,
    bundle_sha256: str,
    files: Mapping[str, bytes],
) -> PublishedImmutableBundle:
    """Atomically publish only at the caller-supplied final SHA address."""
    primary, address = _sha(primary_sha256), _sha(bundle_sha256)
    payloads = store._bounded(files)
    if store._address(payloads) != address:
        raise ImmutableBundleFSError("publication bytes do not match final address")
    staging: Path | None = None
    parent: Path | None = None
    try:
        parent = _publication_parent(store, primary)
        existing = _child(parent, address)
        if existing is not None:
            _require_same(store, primary, address, payloads)
            return PublishedImmutableBundle(existing, primary, address, True)
        staging = create_same_parent_staging(
            parent, prefix=f".{address[:12]}.",
        )
        _real_dir(staging, "staging directory")
        for name, data in zip(store.ordered_names, payloads, strict=True):
            _write(staging / name, data)
        inventory = _inventory(staging, store.ordered_names)
        if any(inventory[name].lstat().st_size != len(data)
               for name, data in zip(store.ordered_names, payloads, strict=True)):
            raise ImmutableBundleFSError("staged bundle file size differs")
        destination = parent / address
        try:
            os.rename(staging, destination)
            staging = None
            _require_same(store, primary, address, payloads)
            return PublishedImmutableBundle(destination, primary, address, False)
        except OSError:
            existing = _child(parent, address)
            if existing is None:
                raise
            _require_same(store, primary, address, payloads)
            return PublishedImmutableBundle(existing, primary, address, True)
    except ImmutableBundleFSError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ImmutableBundleFSError(
            "could not atomically publish exact bundle",
        ) from exc
    finally:
        if staging is not None:
            _remove_stage(staging, parent)


def _publication_parent(store: ImmutableThreeFileBundleFS, primary: str) -> Path:
    root = _safe_root(store.root)
    return _ensure_dir(_ensure_dir(root, store.namespace), primary)


def _safe_root(root: Path) -> Path:
    current = Path(root.parts[0])
    _real_dir(current, "bundle root ancestor")
    for name in root.parts[1:]:
        child = current / name
        try:
            child.lstat()
        except FileNotFoundError:
            try:
                child.mkdir()
            except FileExistsError:
                pass
            except OSError as exc:
                raise ImmutableBundleFSError(
                    "could not create bundle root"
                ) from exc
        current = _real_dir(child, "bundle root ancestor")
    return current


def _require_same(store, primary: str, address: str, payloads) -> None:
    if store.read(primary, address).payloads != payloads:
        raise ImmutableBundleFSError("existing exact bundle has different bytes")


def _write(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _remove_stage(path: Path, parent: Path | None) -> None:
    if parent is None or path.parent != parent or not _staging_name(path.name):
        return
    try:
        _real_dir(parent, "staging parent")
        _real_dir(path, "staging directory")
        if path.resolve(strict=True).parent == parent.resolve(strict=True):
            shutil.rmtree(path)
    except (ImmutableBundleFSError, OSError, RuntimeError):
        return


def _staging_name(name: str) -> bool:
    return len(name) >= 15 and name[0] == "." and name[13] == "." \
        and all(character in "0123456789abcdef" for character in name[1:13]) \
        and bool(name[14:]) and all(
            character.isalnum() or character in "_-" for character in name[14:]
        )
