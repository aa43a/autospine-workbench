"""Read-only filesystem boundary for P9 evidence and candidate probes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .depth_order_candidates import (
    DepthOrderCandidateError,
    compile_depth_order_candidates,
)
from .depth_pair_policy import MAX_DOCUMENT_BYTES as MAX_DEPTH_POLICY_BYTES
from .foot_lock_candidate import (
    FootLockCandidateError,
    compile_foot_lock_candidates,
)
from .heading_evidence import HeadingEvidenceError, compile_heading_evidence
from .kimodo_policy_evidence import (
    KimodoPolicyEvidenceError,
    compile_kimodo_policy_evidence,
)
from .kimodo_policy_map_validation import (
    MAX_DOCUMENT_BYTES as MAX_POLICY_MAP_BYTES,
)
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
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
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)


class P9ReadOnlyCommandError(RuntimeError):
    """Raised when an exact P9 read-only command cannot finish."""


@dataclass(frozen=True, slots=True)
class P9ReadOnlyCommandResult:
    """One canonical report and the exact bundle paths used to derive it."""

    input_bundle_paths: tuple[Path, ...]
    report_sha256: str
    report: dict[str, Any]


def compile_kimodo_policy_evidence_command(
    state_root: Path,
    *,
    motion_sha256: str,
    motion_bundle_sha256: str,
    projected_motion_sha256: str,
    projected_bundle_sha256: str,
) -> P9ReadOnlyCommandResult:
    """Compile candidate-free ancillary-array evidence from exact P7/P8."""

    try:
        p7, p8 = _p7_p8(
            state_root, motion_sha256, motion_bundle_sha256,
            projected_motion_sha256, projected_bundle_sha256,
        )
        result = compile_kimodo_policy_evidence(p7, p8)
        return _result(result, p7.path, p8.path)
    except P9ReadOnlyCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise P9ReadOnlyCommandError(
            f"Kimodo policy evidence command failed: {exc}"
        ) from exc


def compile_heading_evidence_command(
    state_root: Path,
    policy_map_path: Path,
    *,
    motion_sha256: str,
    motion_bundle_sha256: str,
    projected_motion_sha256: str,
    projected_bundle_sha256: str,
) -> P9ReadOnlyCommandResult:
    """Compile reviewed heading evidence without publishing state."""

    try:
        policy = _json_file(
            policy_map_path, MAX_POLICY_MAP_BYTES, "Kimodo policy map"
        )
        p7, p8 = _p7_p8(
            state_root, motion_sha256, motion_bundle_sha256,
            projected_motion_sha256, projected_bundle_sha256,
        )
        raw = compile_kimodo_policy_evidence(p7, p8)
        result = compile_heading_evidence(raw.document, policy, p7, p8)
        return _result(result, p7.path, p8.path)
    except P9ReadOnlyCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise P9ReadOnlyCommandError(
            f"Heading evidence command failed: {exc}"
        ) from exc


def probe_foot_lock_command(
    state_root: Path,
    project_id: str,
    *,
    projected_motion_sha256: str,
    projected_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
    max_correction_reference_ratio: float,
    max_residual_px: float,
) -> P9ReadOnlyCommandResult:
    """Compile target-specific foot-lock candidates from exact P8/P5."""

    try:
        p8, p5 = _p8_p5(
            state_root, project_id,
            projected_motion_sha256, projected_bundle_sha256,
            motion_instance_sha256, motion_retarget_bundle_sha256,
        )
        result = compile_foot_lock_candidates(
            p8, p5,
            max_correction_reference_ratio=max_correction_reference_ratio,
            max_residual_px=max_residual_px,
        )
        return _result(result, p8.path, p5.path)
    except P9ReadOnlyCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise P9ReadOnlyCommandError(
            f"Foot-lock probe command failed: {exc}"
        ) from exc


def probe_depth_order_command(
    state_root: Path,
    project_id: str,
    policy_path: Path,
    *,
    projected_motion_sha256: str,
    projected_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
) -> P9ReadOnlyCommandResult:
    """Compile reviewed pairwise depth candidates from exact P8/P5/P3."""

    try:
        policy = _json_file(
            policy_path, MAX_DEPTH_POLICY_BYTES, "Depth pair policy"
        )
        p8, p5 = _p8_p5(
            state_root, project_id,
            projected_motion_sha256, projected_bundle_sha256,
            motion_instance_sha256, motion_retarget_bundle_sha256,
        )
        p3 = VerifiedMeshBundleReader(state_root).load(
            project_id, p3_rig_sha256, p3_bundle_sha256
        )
        result = compile_depth_order_candidates(p8, p5, p3, policy)
        return _result(result, p8.path, p5.path, p3.path)
    except P9ReadOnlyCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise P9ReadOnlyCommandError(
            f"Depth-order probe command failed: {exc}"
        ) from exc


def _p7_p8(state, motion_sha, motion_bundle, projected_sha, projected_bundle):
    p7 = VerifiedMotionBundleReader(state).load(motion_sha, motion_bundle)
    p8 = VerifiedProjectedMotionBundleReader(state).load(
        projected_sha, projected_bundle
    )
    return p7, p8


def _p8_p5(state, project, projected_sha, projected_bundle,
           instance_sha, retarget_bundle):
    p8 = VerifiedProjectedMotionBundleReader(state).load(
        projected_sha, projected_bundle
    )
    p5 = VerifiedMotionRetargetBundleReader(state).load(
        project, instance_sha, retarget_bundle
    )
    return p8, p5


def _json_file(path: Path, maximum: int, label: str) -> dict[str, Any]:
    return strict_json_object(read_real_file(path, maximum, label), label)


def _result(value, *paths: Path) -> P9ReadOnlyCommandResult:
    return P9ReadOnlyCommandResult(
        input_bundle_paths=tuple(Path(path) for path in paths),
        report_sha256=value.sha256,
        report=value.document,
    )


_DOMAIN_ERRORS = (
    AttributeError,
    DepthOrderCandidateError,
    FootLockCandidateError,
    HeadingEvidenceError,
    KimodoPolicyEvidenceError,
    KeyError,
    OSError,
    OverflowError,
    RecursionError,
    SafeInputFileError,
    TypeError,
    ValueError,
    VerifiedMeshBundleReaderError,
    VerifiedMotionBundleReaderError,
    VerifiedMotionRetargetBundleReaderError,
    VerifiedProjectedMotionBundleReaderError,
)
