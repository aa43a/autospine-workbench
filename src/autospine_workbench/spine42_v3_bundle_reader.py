"""Exact-address historical reader for P10.7 Spine 4.2 bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .spine42_v3_bundle_files import (
    Spine42V3BundleFilesError,
    existing_bundle_path,
    read_bundle_files,
)
from .spine42_v3_bundle_integrity import (
    Spine42V3BundleIntegrityError,
    Spine42V3BundleSnapshot,
    VerifiedSpine42V3Bundle,
    verify_spine42_v3_bundle_snapshot,
)
from .spine42_v3_pipeline import (
    VerifiedSpine42V3Pipeline,
    VerifiedSpine42V3PipelineError,
)


class VerifiedSpine42V3BundleReaderError(RuntimeError):
    """Raised when an exact Spine v3 closure cannot be replayed."""


@dataclass(frozen=True, slots=True)
class VerifiedSpine42V3BundleReader:
    """Read five files once and rebuild them from exact P3/MIv3 inputs."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self,
        project_id: str,
        skeleton_json_sha256: str,
        bundle_sha256: str,
    ) -> VerifiedSpine42V3Bundle:
        """Load one immutable address without observing current review heads."""

        try:
            project = require_safe_token(project_id, "Project id")
            skeleton_sha = require_sha256(
                skeleton_json_sha256, "Spine v3 skeleton"
            )
            bundle_sha = require_sha256(bundle_sha256, "Spine v3 bundle")
            path = existing_bundle_path(
                self.state_root, project, skeleton_sha, bundle_sha
            )
            verified = verify_spine42_v3_bundle_snapshot(
                Spine42V3BundleSnapshot(path, read_bundle_files(path)),
                expected_project_id=project,
                expected_skeleton_json_sha256=skeleton_sha,
                expected_bundle_sha256=bundle_sha,
            )
            rebuilt = VerifiedSpine42V3Pipeline(self.state_root).build(
                project,
                verified.motion_instance_v3_sha256,
                verified.motion_instance_v3_bundle_sha256,
            )
            _require_rebuild(verified, rebuilt)
            return verified
        except VerifiedSpine42V3BundleReaderError:
            raise
        except (
            LayerManifestError, Spine42V3BundleFilesError,
            Spine42V3BundleIntegrityError, VerifiedSpine42V3PipelineError,
            AttributeError, KeyError, OSError, RuntimeError,
            TypeError, ValueError,
        ) as exc:
            raise VerifiedSpine42V3BundleReaderError(
                "Verified Spine v3 bundle load failed"
            ) from exc


def _require_rebuild(verified, rebuilt) -> None:
    if rebuilt.project_id != verified.project_id \
            or rebuilt.clip_id != verified.clip_id \
            or rebuilt.contract_identities != verified.contract_identities \
            or rebuilt.source_image_sha256s != verified.source_image_sha256s \
            or rebuilt.document_bytes != verified.document_bytes:
        raise VerifiedSpine42V3BundleReaderError(
            "Spine v3 bytes differ from exact source replay"
        )


__all__ = [
    "VerifiedSpine42V3BundleReader",
    "VerifiedSpine42V3BundleReaderError",
]
