"""Read-only exact-address reader for MotionInstance v3 bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .motion_instance_v3_bundle_contract import (
    MotionInstanceV3BundleContractError,
    motion_instance_v3_bundle_address_sha256,
)
from .motion_instance_v3_bundle_files import (
    MotionInstanceV3BundleFilesError,
    existing_bundle_path,
    read_bundle_files,
)
from .motion_instance_v3_bundle_integrity import (
    MotionInstanceV3BundleIntegrityError,
    MotionInstanceV3BundleSnapshot,
    VerifiedMotionInstanceV3Bundle,
    verify_motion_instance_v3_bundle_snapshot,
)
from .motion_instance_v3_bundle_run import (
    MotionInstanceV3BundleRunError,
    require_motion_instance_v3_bundle_run,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)
from .safe_input_files import SafeInputFileError, strict_json_object


class VerifiedMotionInstanceV3BundleReaderError(RuntimeError):
    """Raised when an exact v3 bundle cannot be replayed."""


@dataclass(frozen=True, slots=True)
class VerifiedMotionInstanceV3BundleReader:
    """Read three files once and replay exact P10.6a/P9/v3/run bytes."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self,
        project_id: str,
        motion_instance_v3_sha256: str,
        bundle_sha256: str,
        *,
        reviewed_bundle: VerifiedReviewedMotionBundle | None = None,
    ) -> VerifiedMotionInstanceV3Bundle:
        """Load one explicit address; never scan or consult a latest link."""

        try:
            directory = existing_bundle_path(
                self.state_root, project_id,
                motion_instance_v3_sha256, bundle_sha256,
            )
            items = read_bundle_files(directory)
            if motion_instance_v3_bundle_address_sha256(
                project_id, motion_instance_v3_sha256, items
            ) != bundle_sha256:
                raise VerifiedMotionInstanceV3BundleReaderError(
                    "MotionInstance v3 bytes differ from their explicit address"
                )
            run = strict_json_object(
                dict(items)["run-manifest.json"], "run-manifest.json"
            )
            require_motion_instance_v3_bundle_run(run)
            if run["project_id"] != project_id \
                    or run["outputs"]["motion_instance_v3_sha256"] \
                    != motion_instance_v3_sha256:
                raise VerifiedMotionInstanceV3BundleReaderError(
                    "MotionInstance v3 run differs from its explicit address"
                )
            if reviewed_bundle is None:
                p9 = run["inputs"]["p9"]
                reviewed_bundle = VerifiedReviewedMotionBundleReader(
                    self.state_root
                ).load(
                    project_id,
                    p9["motion_instance_v2_sha256"],
                    p9["bundle_sha256"],
                )
            return verify_motion_instance_v3_bundle_snapshot(
                MotionInstanceV3BundleSnapshot(directory, items),
                expected_project_id=project_id,
                expected_motion_instance_v3_sha256=
                    motion_instance_v3_sha256,
                expected_bundle_sha256=bundle_sha256,
                reviewed_bundle=reviewed_bundle,
            )
        except VerifiedMotionInstanceV3BundleReaderError:
            raise
        except (
            MotionInstanceV3BundleContractError,
            MotionInstanceV3BundleFilesError,
            MotionInstanceV3BundleIntegrityError,
            MotionInstanceV3BundleRunError, SafeInputFileError,
            VerifiedReviewedMotionBundleReaderError, AttributeError,
            KeyError, OSError, RuntimeError, TypeError, ValueError,
        ) as exc:
            raise VerifiedMotionInstanceV3BundleReaderError(
                f"Verified MotionInstance v3 load failed: {exc}"
            ) from exc


__all__ = [
    "VerifiedMotionInstanceV3BundleReader",
    "VerifiedMotionInstanceV3BundleReaderError",
]
