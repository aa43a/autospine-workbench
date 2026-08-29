"""Atomic immutable store for content-addressed P10.7b evidence."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .atomic_staging import create_same_parent_staging
from .spine42_v3_bundle_files import (
    Spine42V3BundleFilesError,
    existing_exact_child,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)
from .spine42_v3_runtime_bundle import (
    NAMESPACE,
    Spine42V3RuntimeBundle,
    Spine42V3RuntimeBundleError,
    build_spine42_v3_runtime_bundle,
)
from .spine42_v3_runtime_evidence import Spine42V3RuntimeEvidence
from .spine42_v3_runtime_reader import (
    Spine42V3RuntimeReaderError,
    snapshot_spine42_v3_runtime_directory,
)


class Spine42V3RuntimeStoreError(RuntimeError):
    """Raised when runtime evidence cannot be published safely."""


@dataclass(frozen=True, slots=True)
class PublishedSpine42V3RuntimeEvidence:
    path: Path
    project_id: str
    clip_id: str
    spine42_v3_bundle_sha256: str
    skeleton_json_sha256: str
    run_document_sha256: str
    manifest_sha256: str
    metrics_sha256: str
    capture_bundle_sha256: str
    reused: bool


class Spine42V3RuntimeStore:
    """Publish manifest, metrics, and captures below two exact SHAs."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self, evidence: Spine42V3RuntimeEvidence,
    ) -> PublishedSpine42V3RuntimeEvidence:
        """Validate before state creation and atomically publish exact bytes."""

        try:
            bundle = build_spine42_v3_runtime_bundle(evidence)
        except Spine42V3RuntimeBundleError as exc:
            raise Spine42V3RuntimeStoreError(
                "Runtime evidence publication input is invalid"
            ) from exc
        parent: Path | None = None
        staging: Path | None = None
        try:
            parent = _publication_parent(self.state_root, bundle)
            destination = existing_exact_child(parent, bundle.bundle_sha256)
            if destination is not None:
                _verify(destination, bundle, require_address=True)
                return _published(destination, bundle, reused=True)
            staging = create_same_parent_staging(
                parent, prefix=f".{bundle.bundle_sha256[:12]}.",
            )
            require_real_directory(staging, "Runtime evidence staging")
            captures = staging / "captures"
            captures.mkdir()
            require_real_directory(captures, "Runtime evidence captures")
            for relative, payload in bundle.file_items:
                write_file(staging / relative, payload)
            _verify(staging, bundle, require_address=False)
            sync_directory(captures)
            sync_directory(staging)
            destination, reused = _commit(staging, parent, bundle)
            if not reused:
                staging = None
            _verify(destination, bundle, require_address=True)
            return _published(destination, bundle, reused=reused)
        except Spine42V3RuntimeStoreError:
            raise
        except (
            OSError, RuntimeError, Spine42V3BundleFilesError,
            Spine42V3RuntimeReaderError, TypeError, ValueError,
        ) as exc:
            raise Spine42V3RuntimeStoreError(
                "Could not atomically publish runtime evidence"
            ) from exc
        finally:
            if staging is not None:
                remove_staging(staging, parent)


def _commit(staging, parent, bundle) -> tuple[Path, bool]:
    """Never reinterpret a post-rename parent-sync failure as reuse."""

    try:
        destination = parent / bundle.bundle_sha256
        os.rename(staging, destination)
    except OSError:
        destination = existing_exact_child(parent, bundle.bundle_sha256)
        if destination is None:
            raise
        _verify(destination, bundle, require_address=True)
        return destination, True
    sync_directory(parent)
    return destination, False


def _publication_parent(root: Path, bundle: Spine42V3RuntimeBundle) -> Path:
    current = _safe_state_root(root)
    for name in (
        "builds", bundle.project_id, NAMESPACE,
        bundle.spine42_v3_bundle_sha256,
    ):
        current = _ensure_directory(current, name)
    return current


def _safe_state_root(value: Path) -> Path:
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(value))))
    except (OSError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimeStoreError(
            "Runtime evidence state root is invalid"
        ) from exc
    current = Path(absolute.parts[0])
    require_real_directory(current, "Runtime evidence state-root ancestor")
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
                raise Spine42V3RuntimeStoreError(
                    "Runtime evidence state root cannot be created"
                ) from exc
        current = require_real_directory(
            child, "Runtime evidence state-root ancestor"
        )
    return current


def _ensure_directory(parent: Path, name: str) -> Path:
    found = existing_exact_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        found = existing_exact_child(parent, name)
    if found is None:
        raise Spine42V3RuntimeStoreError(
            "Runtime evidence hierarchy disappeared"
        )
    return require_real_directory(found, f"Runtime evidence path {name}")


def _verify(directory, expected, *, require_address) -> None:
    verified = snapshot_spine42_v3_runtime_directory(
        directory, require_address=require_address,
    )
    if verified.bundle.file_items != expected.file_items \
            or verified.bundle != expected:
        raise Spine42V3RuntimeStoreError(
            "Runtime evidence directory differs from its exact contract"
        )


def _published(path, bundle, *, reused):
    return PublishedSpine42V3RuntimeEvidence(
        path, bundle.project_id, bundle.clip_id,
        bundle.spine42_v3_bundle_sha256, bundle.skeleton_json_sha256,
        bundle.run_document_sha256, bundle.manifest_sha256,
        bundle.metrics_sha256, bundle.bundle_sha256, reused,
    )


__all__ = [
    "PublishedSpine42V3RuntimeEvidence", "Spine42V3RuntimeStore",
    "Spine42V3RuntimeStoreError",
]
