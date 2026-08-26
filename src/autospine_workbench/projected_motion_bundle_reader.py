"""Read-only exact-address reader for ProjectedMotionIR bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .immutable_bundle_fs import ImmutableBundleFSError
from .projected_motion_bundle_fs import projected_motion_bundle_fs
from .projected_motion_bundle_integrity import (
    ProjectedMotionBundleIntegrityError,
    VerifiedProjectedMotionBundle,
    verify_projected_motion_bundle_snapshot,
)


class VerifiedProjectedMotionBundleReaderError(RuntimeError):
    """Raised when an exact projected bundle cannot be read and replayed."""


@dataclass(frozen=True, slots=True)
class VerifiedProjectedMotionBundleReader:
    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self,
        projected_motion_sha256: str,
        bundle_sha256: str,
    ) -> VerifiedProjectedMotionBundle:
        """Read one exact snapshot, then reproduce it from its P7 source."""

        try:
            snapshot = projected_motion_bundle_fs(self.state_root).read(
                projected_motion_sha256, bundle_sha256
            )
            return verify_projected_motion_bundle_snapshot(
                snapshot, state_root=self.state_root
            )
        except VerifiedProjectedMotionBundleReaderError:
            raise
        except (
            ImmutableBundleFSError,
            ProjectedMotionBundleIntegrityError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VerifiedProjectedMotionBundleReaderError(
                f"Verified projected motion load failed: {exc}"
            ) from exc
