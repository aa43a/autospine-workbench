"""Filesystem service boundary for P7-to-P8 projected-motion bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .camera_model_validation import MAX_DOCUMENT_BYTES, CameraModelError
from .kimodo_camera_projection import (
    KimodoCameraProjectionError,
    compile_verified_kimodo_projection,
)
from .motion_bundle_reader import (
    VerifiedMotionBundleReader,
    VerifiedMotionBundleReaderError,
)
from .motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReader,
    VerifiedMotionRetargetBundleReaderError,
)
from .projected_motion_bundle_reader import (
    VerifiedProjectedMotionBundleReader,
    VerifiedProjectedMotionBundleReaderError,
)
from .projected_motion_bundle_store import (
    ProjectedMotionBundleStore,
    ProjectedMotionBundleStoreError,
)
from .projected_motion_compile_run import (
    ProjectedMotionCompileRunError,
    build_projected_motion_compile_run,
)
from .projected_motion_legacy import (
    ProjectedMotionLegacyError,
    compile_projected_motion_to_motion_ir,
)
from .projected_scale_probe import (
    ProjectedScaleProbeError,
    compile_projected_scale_probes,
)
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)


class ProjectedMotionCommandError(RuntimeError):
    """Raised when projected-motion compile or verification cannot finish."""


@dataclass(frozen=True, slots=True)
class ProjectedMotionBundleResult:
    path: Path
    clip_id: str
    camera_id: str
    depth_positive: str
    projected_motion_sha256: str
    camera_sha256: str
    run_sha256: str
    legacy_motion_sha256: str
    bundle_sha256: str
    p7_motion_sha256: str
    p7_bundle_sha256: str
    p7_run_sha256: str
    collapsed_sample_count: int
    minimum_foreshortening_ratio: float
    maximum_foreshortening_ratio: float
    reused: bool | None


@dataclass(frozen=True, slots=True)
class ProjectedScaleProbeCommandResult:
    """Candidate-only report and the two exact bundles that produced it."""

    projected_bundle_path: Path
    motion_retarget_bundle_path: Path
    report_sha256: str
    report: dict[str, Any]


def compile_projected_motion_bundle(
    state_root: Path,
    camera_path: Path,
    *,
    motion_clip_sha256: str,
    motion_bundle_sha256: str,
) -> ProjectedMotionBundleResult:
    """Compile one exact verified P7 bundle through one explicit camera."""

    try:
        camera = strict_json_object(
            read_real_file(camera_path, MAX_DOCUMENT_BYTES, "Camera model"),
            "Camera model",
        )
        source = VerifiedMotionBundleReader(state_root).load(
            motion_clip_sha256, motion_bundle_sha256
        )
        projected = compile_verified_kimodo_projection(source, camera)
        legacy = compile_projected_motion_to_motion_ir(projected.document)
        run = build_projected_motion_compile_run(
            source, camera, projected, legacy
        )
        published = ProjectedMotionBundleStore(state_root).publish(
            camera, projected.document, run.document
        )
        verified = VerifiedProjectedMotionBundleReader(state_root).load(
            published.projected_motion_sha256, published.bundle_sha256
        )
        return _result(verified, reused=published.reused)
    except ProjectedMotionCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise ProjectedMotionCommandError(
            f"Projected motion compilation failed: {exc}"
        ) from exc


def verify_projected_motion_bundle(
    state_root: Path,
    projected_motion_sha256: str,
    bundle_sha256: str,
) -> ProjectedMotionBundleResult:
    """Read and exactly replay one explicit P8 content address without writes."""

    try:
        verified = VerifiedProjectedMotionBundleReader(state_root).load(
            projected_motion_sha256, bundle_sha256
        )
        return _result(verified, reused=None)
    except ProjectedMotionCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise ProjectedMotionCommandError(
            f"Projected motion verification failed: {exc}"
        ) from exc


def probe_projected_scale(
    state_root: Path,
    project_id: str,
    *,
    projected_motion_sha256: str,
    projected_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
) -> ProjectedScaleProbeCommandResult:
    """Compile a read-only target-rig scale probe from two exact bundles."""

    try:
        projected = VerifiedProjectedMotionBundleReader(state_root).load(
            projected_motion_sha256, projected_bundle_sha256
        )
        retarget = VerifiedMotionRetargetBundleReader(state_root).load(
            project_id,
            motion_instance_sha256,
            motion_retarget_bundle_sha256,
        )
        report = compile_projected_scale_probes(
            projected, retarget.target_profile
        )
        return ProjectedScaleProbeCommandResult(
            projected_bundle_path=projected.path,
            motion_retarget_bundle_path=retarget.path,
            report_sha256=report.sha256,
            report=report.document,
        )
    except ProjectedMotionCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise ProjectedMotionCommandError(
            f"Projected scale probe failed: {exc}"
        ) from exc


def _result(verified, *, reused: bool | None) -> ProjectedMotionBundleResult:
    camera = verified.camera
    validation = verified.run_manifest["validation"]
    return ProjectedMotionBundleResult(
        path=verified.path,
        clip_id=verified.clip_id,
        camera_id=camera["camera_id"],
        depth_positive=camera["depth_positive"],
        projected_motion_sha256=verified.projected_motion_sha256,
        camera_sha256=verified.camera_sha256,
        run_sha256=verified.run_sha256,
        legacy_motion_sha256=verified.legacy_motion_sha256,
        bundle_sha256=verified.bundle_sha256,
        p7_motion_sha256=verified.p7_motion_sha256,
        p7_bundle_sha256=verified.p7_bundle_sha256,
        p7_run_sha256=verified.p7_run_sha256,
        collapsed_sample_count=validation["collapsed_sample_count"],
        minimum_foreshortening_ratio=validation["minimum_foreshortening_ratio"],
        maximum_foreshortening_ratio=validation["maximum_foreshortening_ratio"],
        reused=reused,
    )


_DOMAIN_ERRORS = (
    AttributeError,
    CameraModelError,
    KimodoCameraProjectionError,
    KeyError,
    OSError,
    OverflowError,
    ProjectedMotionBundleStoreError,
    ProjectedMotionCompileRunError,
    ProjectedMotionLegacyError,
    ProjectedScaleProbeError,
    RecursionError,
    SafeInputFileError,
    TypeError,
    ValueError,
    VerifiedMotionBundleReaderError,
    VerifiedMotionRetargetBundleReaderError,
    VerifiedProjectedMotionBundleReaderError,
)
