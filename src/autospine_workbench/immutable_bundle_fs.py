"""Fail-closed filesystem primitive for immutable three-file bundles."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .immutable_bundle_publish import PublishedImmutableBundle
_HEX = frozenset("0123456789abcdef")
_MAGIC = b"autospine.immutable-bundle.v1\x00"

class ImmutableBundleFSError(RuntimeError):
    """An exact immutable bundle could not be used safely."""

@dataclass(frozen=True, slots=True)
class ImmutableBundleSnapshot:
    path: Path
    primary_sha256: str
    bundle_sha256: str
    ordered_names: tuple[str, str, str]
    payloads: tuple[bytes, bytes, bytes]

    def file_bytes(self, name: str) -> bytes:
        try:
            return self.payloads[self.ordered_names.index(name)]
        except ValueError as exc:
            raise KeyError(name) from exc

def framed_bundle_sha256(
    domain: str, ordered_names: Sequence[str], files: Mapping[str, bytes],
) -> str:
    """Hash the domain, ordered names, lengths, and bytes with explicit framing."""
    names = _names(ordered_names)
    payloads = _payloads(names, files)
    if not isinstance(domain, str) or not domain or "\x00" in domain:
        raise ValueError("bundle address domain must be a non-empty string without NUL")
    digest = hashlib.sha256(_MAGIC)
    for value in (domain.encode(), len(names).to_bytes(8, "big")):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    for name, data in zip(names, payloads, strict=True):
        for value in (name.encode(), data):
            digest.update(len(value).to_bytes(8, "big"))
            digest.update(value)
    return digest.hexdigest()

class ImmutableThreeFileBundleFS:
    """Publish/read only ``root/namespace/SHA/SHA`` exact addresses."""

    def __init__(
        self, root: Path, *, namespace: str, domain: str,
        ordered_names: Sequence[str], max_file_bytes: int,
        max_total_bytes: int,
    ) -> None:
        self.root = Path(os.path.abspath(os.fspath(Path(root))))
        self.namespace = _component(namespace, "bundle namespace")
        self.domain = domain
        self.ordered_names = _names(ordered_names)
        for value, label in (
            (max_file_bytes, "max_file_bytes"),
            (max_total_bytes, "max_total_bytes"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        framed_bundle_sha256(domain, self.ordered_names, {
            name: b"" for name in self.ordered_names
        })

    def address(self, files: Mapping[str, bytes]) -> str:
        return self._address(self._bounded(files))

    def exact_path(self, primary_sha256: str, bundle_sha256: str) -> Path:
        return self.root / self.namespace / _sha(primary_sha256) / _sha(bundle_sha256)

    def read(self, primary_sha256: str, bundle_sha256: str) -> ImmutableBundleSnapshot:
        primary, address = _sha(primary_sha256), _sha(bundle_sha256)
        namespace = _existing_dir(self.root, self.namespace, "namespace")
        parent = _existing_dir(namespace, primary, "primary hash")
        directory = _existing_dir(parent, address, "bundle hash")
        inventory = _inventory(directory, self.ordered_names)
        values, total = [], 0
        for name in self.ordered_names:
            data = _read_once(inventory[name], self.max_file_bytes)
            total += len(data)
            if total > self.max_total_bytes:
                raise ImmutableBundleFSError("bundle exceeds its total byte limit")
            values.append(data)
        payloads = tuple(values)
        if self._address(payloads) != address:
            raise ImmutableBundleFSError("bundle bytes do not match their exact address")
        return ImmutableBundleSnapshot(
            directory, primary, address, self.ordered_names, payloads,
        )

    def publish(
        self, primary_sha256: str, bundle_sha256: str,
        files: Mapping[str, bytes],
    ) -> PublishedImmutableBundle:
        """Delegate atomic write-once publication to the isolated writer."""
        from .immutable_bundle_publish import publish_exact_bundle
        return publish_exact_bundle(self, primary_sha256, bundle_sha256, files)

    def _address(self, values) -> str:
        files = dict(zip(self.ordered_names, values, strict=True))
        return framed_bundle_sha256(self.domain, self.ordered_names, files)

    def _bounded(self, files) -> tuple[bytes, bytes, bytes]:
        values = _payloads(self.ordered_names, files)
        total = 0
        for data in values:
            if len(data) > self.max_file_bytes:
                raise ImmutableBundleFSError("bundle file exceeds its byte limit")
            total += len(data)
            if total > self.max_total_bytes:
                raise ImmutableBundleFSError("bundle exceeds its total byte limit")
        return values

def _names(values: Sequence[str]) -> tuple[str, str, str]:
    names = tuple(values)
    if len(names) != 3:
        raise ValueError("immutable bundle requires exactly three file names")
    for name in names:
        _component(name, "bundle file name")
    if len({name.casefold() for name in names}) != 3:
        raise ValueError("bundle file names must be case-insensitively unique")
    return names  # type: ignore[return-value]


def _payloads(names, files) -> tuple[bytes, bytes, bytes]:
    if len(files) != 3 or set(files) != set(names):
        raise ImmutableBundleFSError("bundle payload inventory is not exact")
    if len({str(name).casefold() for name in files}) != 3:
        raise ImmutableBundleFSError("bundle payload inventory has case aliases")
    values = tuple(files[name] for name in names)
    if any(not isinstance(data, bytes) for data in values):
        raise ImmutableBundleFSError("bundle payloads must be bytes")
    return values  # type: ignore[return-value]

def _component(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise ValueError(f"{label} must be one non-empty path component")
    if Path(value).name != value or any(c in value for c in "/\\\x00"):
        raise ValueError(f"{label} must be one non-empty path component")
    return value

def _sha(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in _HEX for c in value):
        raise ImmutableBundleFSError("bundle address requires lowercase SHA-256")
    return value

def _ensure_dir(parent: Path, name: str) -> Path:
    found = _child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        found = _child(parent, name)
    if found is None:
        raise ImmutableBundleFSError("bundle hierarchy disappeared")
    return _real_dir(found, f"bundle path {name}")

def _existing_dir(parent: Path, name: str, label: str) -> Path:
    found = _child(_real_dir(parent, f"{label} parent"), name)
    if found is None:
        raise ImmutableBundleFSError(f"exact {label} does not exist")
    return _real_dir(found, label)

def _child(parent: Path, name: str) -> Path | None:
    _real_dir(parent, "bundle parent")
    try:
        matches = [p for p in parent.iterdir() if p.name.casefold() == name.casefold()]
    except OSError as exc:
        raise ImmutableBundleFSError("bundle hierarchy cannot be enumerated") from exc
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name or _alias(matches[0]):
        raise ImmutableBundleFSError(f"bundle path is aliased: {name}")
    return matches[0]


def _inventory(root: Path, names) -> dict[str, Path]:
    root = _real_dir(root, "bundle directory")
    try:
        children = list(root.iterdir())
    except OSError as exc:
        raise ImmutableBundleFSError("bundle inventory cannot be enumerated") from exc
    if len(children) != 3 or {p.name for p in children} != set(names):
        raise ImmutableBundleFSError("bundle inventory is missing, extra, or wrong-case")
    if len({p.name.casefold() for p in children}) != 3:
        raise ImmutableBundleFSError("bundle inventory contains case aliases")
    for child in children:
        if _alias(child) or not stat.S_ISREG(child.lstat().st_mode):
            raise ImmutableBundleFSError("bundle contains an aliased or non-file entry")
    return {child.name: child for child in children}

def _read_once(path: Path, limit: int) -> bytes:
    if _alias(path):
        raise ImmutableBundleFSError("bundle file is aliased")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ImmutableBundleFSError("bundle file is invalid or too large")
            data = os.read(descriptor, limit + 1)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except ImmutableBundleFSError:
        raise
    except OSError as exc:
        raise ImmutableBundleFSError("bundle file cannot be read safely") from exc
    before_identity = (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
    )
    if len(data) != before.st_size or before_identity != after_identity:
        raise ImmutableBundleFSError("bundle file changed while being read")
    return data

def _real_dir(path: Path, label: str) -> Path:
    if _alias(path):
        raise ImmutableBundleFSError(f"{label} is aliased")
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise ImmutableBundleFSError(f"{label} is not a real directory")
        absolute = Path(os.path.abspath(os.fspath(path)))
        if any(_alias(parent) for parent in absolute.parents):
            raise ImmutableBundleFSError(f"{label} path contains an alias")
    except OSError as exc:
        raise ImmutableBundleFSError(f"{label} cannot be inspected") from exc
    return path


def _alias(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    junction = getattr(path, "is_junction", None)
    try:
        is_junction = callable(junction) and junction()
    except OSError:
        is_junction = True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or is_junction or bool(
        getattr(info, "st_file_attributes", 0) & reparse,
    )
