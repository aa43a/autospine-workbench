"""Read-only exact-address reader for reviewed-motion bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mesh_bundle_integrity import VerifiedMeshBundle
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReader,
    VerifiedMotionRetargetBundleReaderError,
)
from .reviewed_motion_bundle_contract import (
    ReviewedMotionBundleContractError,
    reviewed_motion_bundle_address_sha256,
)
from .reviewed_motion_bundle_files import (
    ReviewedMotionBundleFilesError,
    existing_bundle_path,
    read_bundle_files,
)
from .reviewed_motion_bundle_integrity import (
    ReviewedMotionBundleIntegrityError,
    ReviewedMotionBundleSnapshot,
    VerifiedReviewedMotionBundle,
    verify_reviewed_motion_bundle_snapshot,
)
from .reviewed_motion_bundle_run import (
    ReviewedMotionBundleRunError,
    require_reviewed_motion_bundle_run,
)
from .safe_input_files import SafeInputFileError, strict_json_object


class VerifiedReviewedMotionBundleReaderError(RuntimeError):
    """Raised when an exact reviewed-motion bundle cannot be replayed."""


@dataclass(frozen=True, slots=True)
class VerifiedReviewedMotionBundleChain:
    """One exact P3/P5/P9 load whose upstream values may be reused."""

    mesh_bundle: VerifiedMeshBundle
    retarget_bundle: VerifiedMotionRetargetBundle
    reviewed_bundle: VerifiedReviewedMotionBundle


@dataclass(frozen=True, slots=True)
class VerifiedReviewedMotionBundleReader:
    """Read six files once and rebuild them from exact P3/P5 dependencies."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self,
        project_id: str,
        motion_instance_v2_sha256: str,
        bundle_sha256: str,
        *,
        mesh_bundle: VerifiedMeshBundle | None = None,
        retarget_bundle: VerifiedMotionRetargetBundle | None = None,
    ) -> VerifiedReviewedMotionBundle:
        """Load only one explicit address; never scan or consult a latest link."""

        return self.load_chain(
            project_id,
            motion_instance_v2_sha256,
            bundle_sha256,
            mesh_bundle=mesh_bundle,
            retarget_bundle=retarget_bundle,
        ).reviewed_bundle

    def load_chain(
        self,
        project_id: str,
        motion_instance_v2_sha256: str,
        bundle_sha256: str,
        *,
        mesh_bundle: VerifiedMeshBundle | None = None,
        retarget_bundle: VerifiedMotionRetargetBundle | None = None,
    ) -> VerifiedReviewedMotionBundleChain:
        """Load P9 plus the exact P3/P5 values used to verify it."""

        try:
            if (mesh_bundle is None) != (retarget_bundle is None):
                raise VerifiedReviewedMotionBundleReaderError(
                    "Both exact P3 and P5 upstream bundles are required"
                )
            directory = existing_bundle_path(
                self.state_root, project_id,
                motion_instance_v2_sha256, bundle_sha256,
            )
            items = read_bundle_files(directory)
            if reviewed_motion_bundle_address_sha256(
                project_id, motion_instance_v2_sha256, items
            ) != bundle_sha256:
                raise VerifiedReviewedMotionBundleReaderError(
                    "Reviewed-motion bytes differ from their explicit address"
                )
            snapshot = ReviewedMotionBundleSnapshot(directory, items)
            if mesh_bundle is None and retarget_bundle is None:
                run = strict_json_object(
                    dict(items)["run-manifest.json"], "run-manifest.json"
                )
                require_reviewed_motion_bundle_run(run)
                if run["project_id"] != project_id:
                    raise VerifiedReviewedMotionBundleReaderError(
                        "Reviewed-motion run project differs from its address"
                    )
                inputs = run["inputs"]
                mesh_bundle = VerifiedMeshBundleReader(self.state_root).load(
                    project_id,
                    inputs["p3"]["rig_sha256"],
                    inputs["p3"]["bundle_sha256"],
                )
                retarget_bundle = VerifiedMotionRetargetBundleReader(
                    self.state_root
                ).load(
                    project_id,
                    inputs["p5"]["instance_sha256"],
                    inputs["p5"]["bundle_sha256"],
                    mesh_bundle=mesh_bundle,
                )
            assert mesh_bundle is not None and retarget_bundle is not None
            reviewed = verify_reviewed_motion_bundle_snapshot(
                snapshot,
                expected_project_id=project_id,
                expected_motion_instance_v2_sha256=motion_instance_v2_sha256,
                expected_bundle_sha256=bundle_sha256,
                mesh_bundle=mesh_bundle,
                retarget_bundle=retarget_bundle,
            )
            return VerifiedReviewedMotionBundleChain(
                mesh_bundle, retarget_bundle, reviewed,
            )
        except VerifiedReviewedMotionBundleReaderError:
            raise
        except (
            ReviewedMotionBundleFilesError,
            ReviewedMotionBundleContractError,
            ReviewedMotionBundleIntegrityError,
            ReviewedMotionBundleRunError,
            SafeInputFileError,
            VerifiedMeshBundleReaderError,
            VerifiedMotionRetargetBundleReaderError,
            KeyError, OSError, RuntimeError, TypeError, ValueError,
        ) as exc:
            raise VerifiedReviewedMotionBundleReaderError(
                f"Verified reviewed-motion load failed: {exc}"
            ) from exc
