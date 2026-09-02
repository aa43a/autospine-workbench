"""Atomic immutable store for content-addressed P10.7b v2 evidence."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .atomic_staging import create_same_parent_staging
from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .spine42_v3_bundle_files import (
    Spine42V3BundleFilesError, existing_exact_child, remove_staging,
    require_real_directory, sync_directory, write_file,
)
from .spine42_v3_runtime_bundle_v2 import (
    NAMESPACE, Spine42V3RuntimeBundleV2, Spine42V3RuntimeBundleV2Error,
    build_spine42_v3_runtime_bundle_v2,
)
from .spine42_v3_runtime_evidence_v2 import (
    Spine42V3RuntimeEvidenceV2, Spine42V3RuntimeEvidenceV2Error,
    _require_issued_spine42_v3_runtime_evidence_v2,
)
from .spine42_v3_runtime_reader_v2 import (
    Spine42V3RuntimeReaderV2Error,
    _snapshot_spine42_v3_runtime_bundle_v2,
)


class Spine42V3RuntimeStoreV2Error(RuntimeError):
    """Raised when v2 runtime evidence cannot be published safely."""


@dataclass(frozen=True, slots=True)
class PublishedSpine42V3RuntimeEvidenceV2:
    path: Path
    project_id: str
    clip_id: str
    skeleton_json_sha256: str
    spine42_v3_bundle_sha256: str
    evidence_sha256: str
    capture_bundle_sha256: str
    reused: bool


class Spine42V3RuntimeStoreV2:
    """Publish v2 evidence below its four-part immutable address."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self, evidence: Spine42V3RuntimeEvidenceV2,
    ) -> PublishedSpine42V3RuntimeEvidenceV2:
        """Fully validate before creating state, then atomically publish."""

        upstream, bundle = _validated_input(evidence)
        parent: Path | None = None
        staging: Path | None = None
        try:
            parent = _publication_parent(self.state_root, bundle)
            destination = existing_exact_child(parent, bundle.bundle_sha256)
            if destination is not None:
                _verify(destination, upstream, bundle, require_address=True)
                return _published(destination, bundle, reused=True)
            staging = create_same_parent_staging(
                parent, prefix=f".{bundle.bundle_sha256[:12]}.",
            )
            require_real_directory(staging, "Runtime evidence v2 staging")
            captures = staging / "captures"
            captures.mkdir()
            require_real_directory(captures, "Runtime evidence v2 captures")
            for relative, payload in bundle.file_items:
                write_file(staging / relative, payload)
            _verify(staging, upstream, bundle, require_address=False)
            sync_directory(captures)
            sync_directory(staging)
            destination, reused = _commit(staging, parent, upstream, bundle)
            if not reused:
                staging = None
            _verify(destination, upstream, bundle, require_address=True)
            return _published(destination, bundle, reused=reused)
        except Spine42V3RuntimeStoreV2Error:
            raise
        except _FAILURES as exc:
            raise Spine42V3RuntimeStoreV2Error(
                "Could not atomically publish runtime evidence v2"
            ) from exc
        finally:
            if staging is not None:
                remove_staging(staging, parent)


def _validated_input(evidence):
    try:
        upstream, items = _require_issued_spine42_v3_runtime_evidence_v2(
            evidence
        )
        bundle = build_spine42_v3_runtime_bundle_v2(evidence)
        if bundle.file_items != items or (
            bundle.project_id, bundle.clip_id,
            bundle.skeleton_json_sha256, bundle.spine42_v3_bundle_sha256,
        ) != (
            upstream.project_id, upstream.clip_id,
            upstream.skeleton_json_sha256, upstream.bundle_sha256,
        ):
            raise Spine42V3RuntimeStoreV2Error(
                "Runtime evidence v2 input identities disagree"
            )
        _address(bundle)
        require_sha256(bundle.bundle_sha256, "Runtime v2 capture bundle")
        return upstream, bundle
    except Spine42V3RuntimeStoreV2Error:
        raise
    except (
        LayerManifestError, Spine42V3RuntimeBundleV2Error,
        Spine42V3RuntimeEvidenceV2Error, TypeError, ValueError,
    ) as exc:
        raise Spine42V3RuntimeStoreV2Error(
            "Runtime evidence v2 publication input is invalid"
        ) from exc


def _commit(staging, parent, upstream, bundle):
    """Never reinterpret a post-rename parent-sync failure as reuse."""

    try:
        destination = parent / bundle.bundle_sha256
        os.rename(staging, destination)
    except OSError:
        destination = existing_exact_child(parent, bundle.bundle_sha256)
        if destination is None:
            raise
        _verify(destination, upstream, bundle, require_address=True)
        return destination, True
    sync_directory(parent)
    return destination, False


def _publication_parent(root, bundle):
    project, skeleton, upstream = _address(bundle)
    current = _safe_state_root(root)
    for name in ("builds", project, NAMESPACE, skeleton, upstream):
        current = _ensure_directory(current, name)
    try:
        current.resolve(strict=True).relative_to(
            _absolute(root).resolve(strict=True)
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise Spine42V3RuntimeStoreV2Error(
            "Runtime evidence v2 hierarchy escaped its state root"
        ) from exc
    return current


def _address(bundle):
    return (
        require_safe_token(bundle.project_id, "Runtime v2 project id"),
        require_sha256(bundle.skeleton_json_sha256, "Runtime v2 skeleton"),
        require_sha256(
            bundle.spine42_v3_bundle_sha256, "Runtime v2 P10.7a bundle",
        ),
    )


def _absolute(value):
    try:
        return Path(os.path.abspath(os.fspath(Path(value))))
    except (OSError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimeStoreV2Error(
            "Runtime evidence v2 state root is invalid"
        ) from exc


def _safe_state_root(value):
    absolute = _absolute(value)
    current = Path(absolute.parts[0])
    require_real_directory(current, "Runtime v2 state-root ancestor")
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
                raise Spine42V3RuntimeStoreV2Error(
                    "Runtime evidence v2 state root cannot be created"
                ) from exc
        current = require_real_directory(
            child, "Runtime v2 state-root ancestor",
        )
    return current


def _ensure_directory(parent, name):
    found = existing_exact_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        found = existing_exact_child(parent, name)
    if found is None:
        raise Spine42V3RuntimeStoreV2Error(
            "Runtime evidence v2 hierarchy disappeared"
        )
    return require_real_directory(found, f"Runtime evidence v2 path {name}")


def _verify(path, upstream, expected, *, require_address):
    actual = _snapshot_spine42_v3_runtime_bundle_v2(
        path, upstream, require_address=require_address,
    )
    if actual != expected or actual.file_items != expected.file_items:
        raise Spine42V3RuntimeStoreV2Error(
            "Runtime evidence v2 directory differs from its exact contract"
        )


def _published(path, bundle, *, reused):
    return PublishedSpine42V3RuntimeEvidenceV2(
        path, bundle.project_id, bundle.clip_id,
        bundle.skeleton_json_sha256, bundle.spine42_v3_bundle_sha256,
        bundle.evidence_sha256, bundle.bundle_sha256, reused,
    )


_FAILURES = (
    OSError, RuntimeError, Spine42V3BundleFilesError,
    Spine42V3RuntimeBundleV2Error, Spine42V3RuntimeEvidenceV2Error,
    Spine42V3RuntimeReaderV2Error, TypeError, ValueError,
)


__all__ = [
    "PublishedSpine42V3RuntimeEvidenceV2", "Spine42V3RuntimeStoreV2",
    "Spine42V3RuntimeStoreV2Error",
]
