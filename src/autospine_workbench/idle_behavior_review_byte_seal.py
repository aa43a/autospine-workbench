"""Full-byte, alias-safe seals for immutable P10 replay directories."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat


_DOMAIN = b"autospine-idle-review-replay-cache-seal/v1"
_MAX_FILES = 4096
_MAX_BYTES = 768 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024


class IdleBehaviorReviewReplayCacheError(RuntimeError):
    """Raised when immutable replay inputs cannot be sealed safely."""


def seal_exact_directories(root: Path, paths: tuple[Path, ...]) -> str:
    """Hash every path, inventory entry, file length, and file byte."""

    digest = hashlib.sha256()
    digest.update(_DOMAIN)
    file_count = 0
    byte_count = 0
    for directory in paths:
        trusted = trusted_directory(root, directory)
        relative_root = trusted.relative_to(root).as_posix()
        _feed(digest, b"D", relative_root.encode("utf-8"))
        stack = [(trusted, relative_root)]
        while stack:
            current, relative = stack.pop()
            children = _children(current)
            for child in reversed(children):
                child_relative = f"{relative}/{child.name}"
                metadata = child.lstat()
                if _is_alias(child):
                    raise IdleBehaviorReviewReplayCacheError(
                        "Exact replay cache input contains a path alias"
                    )
                if stat.S_ISDIR(metadata.st_mode):
                    _feed(digest, b"D", child_relative.encode("utf-8"))
                    stack.append((child, child_relative))
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    raise IdleBehaviorReviewReplayCacheError(
                        "Exact replay cache inventory is not regular"
                    )
                file_count += 1
                byte_count += metadata.st_size
                if file_count > _MAX_FILES or byte_count > _MAX_BYTES:
                    raise IdleBehaviorReviewReplayCacheError(
                        "Exact replay cache input exceeds its resource limit"
                    )
                _feed(digest, b"F", child_relative.encode("utf-8"))
                _hash_file(digest, child, metadata)
    return digest.hexdigest()


def trusted_root(path: Path) -> Path:
    """Resolve and validate one cache state root without aliases."""

    try:
        lexical = Path(os.path.abspath(os.fspath(Path(path))))
        metadata = lexical.lstat()
        if _is_alias(lexical) or not stat.S_ISDIR(metadata.st_mode):
            raise IdleBehaviorReviewReplayCacheError(
                "Exact replay cache root is unsafe"
            )
        for parent in lexical.parents:
            parent_metadata = parent.lstat()
            if _is_alias(parent) or not stat.S_ISDIR(parent_metadata.st_mode):
                raise IdleBehaviorReviewReplayCacheError(
                    "Exact replay cache root is unsafe"
                )
        root = lexical.resolve(strict=True)
    except IdleBehaviorReviewReplayCacheError:
        raise
    except (OSError, RuntimeError) as exc:
        raise IdleBehaviorReviewReplayCacheError(
            "Exact replay cache root is unavailable"
        ) from exc
    return trusted_directory(root, root)


def trusted_directory(root: Path, path: Path) -> Path:
    """Resolve one contained directory and reject aliased components."""

    try:
        lexical = Path(path)
        resolved = lexical.resolve(strict=True)
        relative = resolved.relative_to(root)
        root_metadata = resolved.lstat()
        if _is_alias(lexical) or _is_alias(resolved) \
                or not stat.S_ISDIR(root_metadata.st_mode):
            raise IdleBehaviorReviewReplayCacheError(
                "Exact replay cache directory is unsafe"
            )
        current = root
        for component in relative.parts:
            current = current / component
            metadata = current.lstat()
            if _is_alias(current) or not stat.S_ISDIR(metadata.st_mode):
                raise IdleBehaviorReviewReplayCacheError(
                    "Exact replay cache directory is unsafe"
                )
    except (OSError, RuntimeError, ValueError) as exc:
        raise IdleBehaviorReviewReplayCacheError(
            "Exact replay cache directory is unavailable"
        ) from exc
    return resolved


def _hash_file(digest, path: Path, before) -> None:
    file_digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            remaining = before.st_size
            while remaining:
                block = handle.read(min(_CHUNK_BYTES, remaining))
                if not block:
                    break
                file_digest.update(block)
                remaining -= len(block)
            extra = handle.read(1)
            finished = os.fstat(handle.fileno())
        after = path.lstat()
    except OSError as exc:
        raise IdleBehaviorReviewReplayCacheError(
            "Exact replay cache input cannot be read"
        ) from exc
    if remaining or extra or not (
        _identity(before) == _identity(opened)
        == _identity(finished) == _identity(after)
    ):
        raise IdleBehaviorReviewReplayCacheError(
            "Exact replay cache input changed while being sealed"
        )
    _feed(digest, b"S", before.st_size.to_bytes(8, "big"))
    _feed(digest, b"H", file_digest.digest())


def _children(path: Path) -> list[Path]:
    try:
        children = sorted(path.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise IdleBehaviorReviewReplayCacheError(
            "Exact replay cache directory cannot be enumerated"
        ) from exc
    folded = [child.name.casefold() for child in children]
    if len(folded) != len(set(folded)):
        raise IdleBehaviorReviewReplayCacheError(
            "Exact replay cache inventory contains case aliases"
        )
    return children


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


def _identity(value) -> tuple[int, ...]:
    return (
        value.st_mode, value.st_size, value.st_mtime_ns,
        getattr(value, "st_dev", 0), getattr(value, "st_ino", 0),
    )


def _feed(digest, kind: bytes, value: bytes) -> None:
    digest.update(kind)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)
