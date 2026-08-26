"""Small alias-safe filesystem primitives for visual review JSON history."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from .body_sway_visual_review_profile import MAX_VISUAL_REVIEW_DOCUMENT_BYTES
from .manifest_artifacts import require_safe_token
from .safe_input_files import read_real_file, strict_json_object
from .spine42_bundle_files import (
    existing_exact_child,
    is_alias,
    require_real_directory,
    sync_directory,
)


class BodySwayVisualReviewFilesError(RuntimeError):
    """Raised when immutable visual-review JSON files are unsafe."""


def exact_payload(payload: bytes, document, digest: str) -> bytes:
    canonical = json.dumps(
        document, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if payload != canonical or len(payload) > MAX_VISUAL_REVIEW_DOCUMENT_BYTES \
            or hashlib.sha256(payload).hexdigest() != digest:
        raise BodySwayVisualReviewFilesError(
            "Visual review bytes are non-canonical or inconsistently sealed"
        )
    return payload


def publication_parent(root, project, namespace, primary) -> Path:
    current = _safe_root(root, create=True)
    for name in ("builds", project, namespace, primary):
        require_safe_token(name, "Visual review path component")
        found = existing_exact_child(current, name)
        if found is None:
            try:
                (current / name).mkdir()
            except FileExistsError:
                pass
            found = existing_exact_child(current, name)
        if found is None:
            raise BodySwayVisualReviewFilesError(
                "Visual review hierarchy disappeared"
            )
        current = require_real_directory(found, "Visual review hierarchy")
    return current


def publish_document(
    parent: Path, digest: str, payload: bytes,
) -> tuple[Path, bool]:
    return publish_named_document(parent, f"{digest}.json", payload)


def publish_named_document(
    parent: Path,
    name: str,
    payload: bytes,
    *,
    staging_parent: Path | None = None,
) -> tuple[Path, bool]:
    """Atomically append one exact named file, allowing byte-identical reuse."""

    require_safe_token(name, "Visual review document name")
    found = existing_exact_child(parent, name)
    if found is not None:
        if read_real_file(found, MAX_VISUAL_REVIEW_DOCUMENT_BYTES, name) != payload:
            raise BodySwayVisualReviewFilesError(
                "Existing visual review history conflicts with its address"
            )
        return found, True
    temporary = None
    try:
        staging = staging_parent or parent
        require_real_directory(staging, "Visual review staging directory")
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{hashlib.sha256(payload).hexdigest()[:12]}.",
            suffix=".tmp",
            dir=staging,
        )
        temporary = Path(raw_path)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        destination = parent / name
        try:
            os.link(temporary, destination)
            reused = False
            sync_directory(parent)
        except FileExistsError:
            found = existing_exact_child(parent, name)
            if found is None:
                raise
            destination, reused = found, True
        if read_real_file(
            destination, MAX_VISUAL_REVIEW_DOCUMENT_BYTES, name
        ) != payload:
            raise BodySwayVisualReviewFilesError(
                "Published visual review history failed readback"
            )
        return destination, reused
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def read_document(
    root, project: str, namespace: str, primary: str, digest: str,
) -> bytes:
    current = existing_parent(root, project, namespace, primary)
    return read_named_document(current, f"{digest}.json", digest=digest)


def existing_parent(root, project: str, namespace: str, primary: str) -> Path:
    """Resolve an existing exact publication parent without creating state."""

    current = _safe_root(root, create=False)
    for name in ("builds", project, namespace, primary):
        found = existing_exact_child(current, name)
        if found is None:
            raise BodySwayVisualReviewFilesError(
                "Exact visual review address does not exist"
            )
        current = require_real_directory(found, "Visual review hierarchy")
    return current


def read_named_document(
    parent: Path, name: str, *, digest: str | None = None,
) -> bytes:
    """Read one exact named canonical JSON file without following aliases."""

    require_safe_token(name, "Visual review document name")
    found = existing_exact_child(parent, name)
    if found is None or is_alias(found):
        raise BodySwayVisualReviewFilesError(
            "Exact visual review document does not exist"
        )
    payload = read_real_file(
        found, MAX_VISUAL_REVIEW_DOCUMENT_BYTES, "Visual review document"
    )
    document = strict_json_object(payload, "Visual review document")
    expected_digest = digest or hashlib.sha256(payload).hexdigest()
    return exact_payload(payload, document, expected_digest)


def require_document_bytes(
    root, project: str, namespace: str, primary: str,
    digest: str, expected: bytes,
) -> None:
    """Require one already-published history item to match exact value bytes."""

    if read_document(root, project, namespace, primary, digest) != expected:
        raise BodySwayVisualReviewFilesError(
            "Published visual review predecessor bytes are inconsistent"
        )


def exact_subdirectory(parent: Path, name: str, *, create: bool) -> Path:
    """Resolve one exact real child directory, optionally creating it."""

    require_safe_token(name, "Visual review directory name")
    found = existing_exact_child(parent, name)
    if found is None and create:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        found = existing_exact_child(parent, name)
    if found is None:
        raise BodySwayVisualReviewFilesError(
            "Exact visual review directory does not exist"
        )
    return require_real_directory(found, "Visual review directory")


def _safe_root(value: Path, *, create: bool) -> Path:
    absolute = Path(os.path.abspath(os.fspath(Path(value))))
    if not create:
        return require_real_directory(absolute, "Visual review state root")
    current = Path(absolute.parts[0])
    require_real_directory(current, "Visual review state-root ancestor")
    for name in absolute.parts[1:]:
        child = current / name
        try:
            child.lstat()
        except FileNotFoundError:
            try:
                child.mkdir()
            except FileExistsError:
                pass
        current = require_real_directory(child, "Visual review state-root ancestor")
    return current
