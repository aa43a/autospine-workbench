"""Alias-safe persistent cache for exact P10.3c v2 mount snapshots."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile

from .manifest_artifacts import LayerManifestError, require_sha256
from .p10_preview_v2_cache import (
    P10PreviewV2CacheLocator, P10PreviewV2CacheRecord,
)
from .p10_visual_review_v2_mount_snapshot import (
    MountSnapshotError, canonical_mount_snapshot,
    mount_snapshot_document, record_from_mount_snapshot,
)
from .safe_input_files import (
    SafeInputFileError, read_real_file, strict_json_object,
)
from .spine42_bundle_files import (
    Spine42BundleFilesError, existing_exact_child,
    require_real_directory, sync_directory,
)


NAMESPACE = "p10-visual-review-v2-mounts"
MAX_MOUNT_SNAPSHOT_BYTES = 256 * 1024 * 1024


class P10VisualReviewV2MountStoreError(RuntimeError):
    """Raised when a derived mount snapshot is unsafe or cross-wired."""


class P10VisualReviewV2MountStore:
    """Persist replaceable acceleration bytes without review authority."""

    def __init__(self, state_root: Path) -> None:
        try:
            root = Path(os.path.abspath(os.fspath(Path(state_root))))
            self._state_root = require_real_directory(root, "Mount cache root")
        except (OSError, Spine42BundleFilesError, TypeError, ValueError) as exc:
            raise P10VisualReviewV2MountStoreError(
                "Mount cache state root is unsafe"
            ) from exc

    def save(self, job_id: str, record: P10PreviewV2CacheRecord) -> None:
        """Atomically replace one job's derived snapshot in the same directory."""

        try:
            job = require_sha256(job_id, "Mount cache job")
            self._require_locator(record.key.locator)
            payload = canonical_mount_snapshot(
                mount_snapshot_document(job, record)
            )
            if not payload or len(payload) > MAX_MOUNT_SNAPSHOT_BYTES:
                raise MountSnapshotError("Snapshot exceeds its byte limit")
            self._replace(self._namespace(create=True), f"{job}.json", payload)
        except P10VisualReviewV2MountStoreError:
            raise
        except _FAILURES as exc:
            raise P10VisualReviewV2MountStoreError(
                "Mount cache snapshot could not be saved"
            ) from exc

    def load(
        self, job_id: str, locator: P10PreviewV2CacheLocator, *,
        expected_preview_sha256: str,
        expected_artifact_set_sha256: str,
    ) -> P10PreviewV2CacheRecord | None:
        """Load an exact job snapshot; absence is a cache miss, not an error."""

        try:
            job = require_sha256(job_id, "Mount cache job")
            self._require_locator(locator)
            preview_sha = require_sha256(
                expected_preview_sha256, "Expected mount preview",
            )
            artifact_sha = require_sha256(
                expected_artifact_set_sha256, "Expected mount artifacts",
            )
            parent = self._namespace(create=False)
            if parent is None:
                return None
            found = existing_exact_child(parent, f"{job}.json")
            if found is None:
                return None
            raw = read_real_file(
                found, MAX_MOUNT_SNAPSHOT_BYTES, "Mount cache snapshot",
            )
            document = strict_json_object(raw, "Mount cache snapshot")
            if canonical_mount_snapshot(document) != raw:
                raise MountSnapshotError("Snapshot is not canonical JSON")
            return record_from_mount_snapshot(
                document, job, locator, preview_sha, artifact_sha,
            )
        except P10VisualReviewV2MountStoreError:
            raise
        except _FAILURES as exc:
            raise P10VisualReviewV2MountStoreError(
                "Mount cache snapshot is corrupt or cross-wired"
            ) from exc

    def _require_locator(self, locator: P10PreviewV2CacheLocator) -> None:
        if type(locator) is not P10PreviewV2CacheLocator:
            raise MountSnapshotError("Mount cache locator differs")
        require_sha256(locator.package_id, "Mount cache package")
        require_sha256(locator.compiler_inventory_sha256, "Mount compiler")
        if Path(locator.state_root).resolve(strict=True) \
                != self._state_root.resolve(strict=True):
            raise MountSnapshotError(
                "Mount cache locator belongs to another state root"
            )

    def _namespace(self, *, create: bool) -> Path | None:
        current = self._state_root
        for name in ("cache", NAMESPACE):
            found = existing_exact_child(current, name)
            if found is None and create:
                try:
                    (current / name).mkdir()
                except FileExistsError:
                    pass
                found = existing_exact_child(current, name)
            if found is None:
                return None
            current = require_real_directory(found, "Mount cache namespace")
        return current

    @staticmethod
    def _replace(parent: Path | None, name: str, payload: bytes) -> None:
        if parent is None:
            raise P10VisualReviewV2MountStoreError(
                "Mount cache namespace disappeared"
            )
        found = existing_exact_child(parent, name)
        if found is not None and not stat.S_ISREG(found.lstat().st_mode):
            raise P10VisualReviewV2MountStoreError(
                "Mount cache destination is not a regular file"
            )
        temporary = None
        try:
            descriptor, raw_path = tempfile.mkstemp(
                prefix=".mount-", suffix=".tmp", dir=parent,
            )
            temporary = Path(raw_path)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, parent / name)
            temporary = None
            sync_directory(parent)
            if read_real_file(
                parent / name, MAX_MOUNT_SNAPSHOT_BYTES,
                "Mount cache readback",
            ) != payload:
                raise P10VisualReviewV2MountStoreError(
                    "Mount cache readback differs"
                )
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


_FAILURES = (
    AttributeError, KeyError, LayerManifestError, MountSnapshotError,
    OSError, OverflowError, RecursionError, RuntimeError,
    SafeInputFileError, Spine42BundleFilesError, TypeError,
    UnicodeError, ValueError,
)


__all__ = [
    "P10VisualReviewV2MountStore",
    "P10VisualReviewV2MountStoreError",
]
