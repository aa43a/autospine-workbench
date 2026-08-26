"""Safe publish and exact-replay services for reviewed-motion bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .depth_order_candidate_validation import (
    MAX_DOCUMENT_BYTES as MAX_DEPTH_BYTES,
)
from .foot_lock_candidate_validation import (
    MAX_DOCUMENT_BYTES as MAX_FOOT_BYTES,
)
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from .motion_instance_v2_compiler import (
    MotionInstanceV2CompilerError,
    compile_motion_instance_v2,
)
from .motion_policy_decision_validation import (
    MAX_DOCUMENT_BYTES as MAX_DECISION_BYTES,
)
from .motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReader,
    VerifiedMotionRetargetBundleReaderError,
)
from .resolved_project import canonical_sha256
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)
from .reviewed_motion_bundle_contract import (
    ReviewedMotionBundleContract,
    ReviewedMotionBundleContractError,
    build_reviewed_motion_bundle_contract,
)
from .reviewed_motion_bundle_store import (
    PublishedReviewedMotionBundle,
    ReviewedMotionBundleStore,
    ReviewedMotionBundleStoreError,
)
from .reviewed_motion_policy_validation import (
    MAX_DOCUMENT_BYTES as MAX_POLICY_BYTES,
)
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)


class P9BundleCommandError(RuntimeError):
    """Raised when reviewed-motion publication or replay cannot finish."""


@dataclass(frozen=True, slots=True)
class P9BundleCommandResult:
    """Canonical report plus explicit read/write paths for wrapper output."""

    input_paths: tuple[Path, ...]
    output_path: Path | None
    reused: bool | None
    report_sha256: str
    report: dict[str, Any]


def publish_reviewed_motion_bundle_command(
    state_root: Path,
    project_id: str,
    foot_candidates_path: Path,
    depth_candidates_path: Path,
    decision_path: Path,
    reviewed_policy_path: Path,
    *,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
) -> P9BundleCommandResult:
    """Compile v2 in memory, then publish only through the exact store."""

    try:
        paths = (
            Path(foot_candidates_path), Path(depth_candidates_path),
            Path(decision_path), Path(reviewed_policy_path),
        )
        foot, depth, decision, policy = (
            _json(paths[0], MAX_FOOT_BYTES, "Foot-lock candidates"),
            _json(paths[1], MAX_DEPTH_BYTES, "Depth-order candidates"),
            _json(paths[2], MAX_DECISION_BYTES, "Motion-policy decision"),
            _json(paths[3], MAX_POLICY_BYTES, "Reviewed motion policy"),
        )
        mesh = VerifiedMeshBundleReader(state_root).load(
            project_id, p3_rig_sha256, p3_bundle_sha256
        )
        p5 = VerifiedMotionRetargetBundleReader(state_root).load(
            project_id, motion_instance_sha256,
            motion_retarget_bundle_sha256,
        )
        compiled = compile_motion_instance_v2(
            p5.motion_instance, p5.target_profile, policy
        )
        expected = build_reviewed_motion_bundle_contract(
            project_id, foot, depth, decision, policy, compiled.document,
            mesh, p5.motion_instance, p5.target_profile,
        )
        published = ReviewedMotionBundleStore(state_root).publish(
            project_id, foot, depth, decision, policy, compiled.document,
            mesh, p5,
        )
        _require_published(
            published,
            expected=expected,
        )
        report = _publish_report(
            published, mesh, p5, expected,
        )
        return P9BundleCommandResult(
            input_paths=(*paths, mesh.path, p5.path),
            output_path=published.path,
            reused=published.reused,
            report_sha256=canonical_sha256(report),
            report=report,
        )
    except P9BundleCommandError:
        raise
    except _ERRORS as exc:
        raise P9BundleCommandError(
            f"Reviewed-motion bundle publication failed: {exc}"
        ) from exc


def verify_reviewed_motion_bundle_command(
    state_root: Path,
    project_id: str,
    *,
    motion_instance_v2_sha256: str,
    reviewed_motion_bundle_sha256: str,
) -> P9BundleCommandResult:
    """Replay one explicit immutable address without creating any files."""

    try:
        verified = VerifiedReviewedMotionBundleReader(state_root).load(
            project_id, motion_instance_v2_sha256,
            reviewed_motion_bundle_sha256,
        )
        report = _verify_report(verified)
        return P9BundleCommandResult(
            input_paths=(verified.path,),
            output_path=None,
            reused=None,
            report_sha256=canonical_sha256(report),
            report=report,
        )
    except P9BundleCommandError:
        raise
    except _ERRORS as exc:
        raise P9BundleCommandError(
            f"Reviewed-motion bundle verification failed: {exc}"
        ) from exc


def _publish_report(
    published, mesh, p5, expected,
) -> dict[str, Any]:
    v2_sha = published.motion_instance_v2_sha256
    return {
        "format": "autospine-reviewed-motion-bundle-publication",
        "format_version": 1,
        "project_id": published.project_id,
        "clip_id": published.clip_id,
        "address": {
            "project_id": published.project_id,
            "motion_instance_v2_sha256": v2_sha,
            "bundle_sha256": published.bundle_sha256,
        },
        "source": {
            "p3_rig_sha256": mesh.rig_sha256,
            "p3_bundle_sha256": mesh.bundle_sha256,
            "p5_instance_sha256": p5.instance_sha256,
            "p5_bundle_sha256": p5.bundle_sha256,
            "p5_target_profile_sha256": p5.target_profile_sha256,
        },
        "identities": expected.identities,
    }


def _require_published(
    published: PublishedReviewedMotionBundle,
    *,
    expected: ReviewedMotionBundleContract,
) -> None:
    if type(published) is not PublishedReviewedMotionBundle \
            or published.project_id != expected.project_id \
            or published.clip_id != expected.clip_id \
            or published.motion_instance_v2_sha256 != \
            expected.motion_instance_v2_sha256 \
            or published.bundle_sha256 != expected.bundle_sha256 \
            or published.run_sha256 != expected.run_sha256 \
            or not isinstance(published.path, Path) \
            or not published.path.is_dir() \
            or type(published.reused) is not bool \
            or not _sha(published.bundle_sha256) \
            or not _sha(published.run_sha256):
        raise P9BundleCommandError(
            "Reviewed-motion store result postcondition failed"
        )
    suffix = (
        published.path.name,
        published.path.parent.name,
        published.path.parent.parent.name,
        published.path.parent.parent.parent.name,
        published.path.parent.parent.parent.parent.name,
    )
    expected = (
        published.bundle_sha256,
        expected.motion_instance_v2_sha256,
        "reviewed-motion-instances",
        expected.project_id,
        "builds",
    )
    if suffix != expected:
        raise P9BundleCommandError(
            "Reviewed-motion store path postcondition failed"
        )


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 \
        and all(character in "0123456789abcdef" for character in value)


def _verify_report(verified) -> dict[str, Any]:
    return {
        "format": "autospine-reviewed-motion-bundle-verification",
        "format_version": 1,
        "project_id": verified.project_id,
        "clip_id": verified.clip_id,
        "address": {
            "project_id": verified.project_id,
            "motion_instance_v2_sha256": verified.motion_instance_v2_sha256,
            "bundle_sha256": verified.bundle_sha256,
        },
        "identities": verified.identities,
        "verification": {
            "status": "passed",
            "replayed_from_exact_upstreams": True,
        },
    }


def _json(path: Path, maximum: int, label: str) -> dict[str, Any]:
    return strict_json_object(read_real_file(path, maximum, label), label)


_ERRORS = (
    AttributeError, KeyError, MotionInstanceV2CompilerError, OSError,
    OverflowError, RecursionError, ReviewedMotionBundleContractError,
    ReviewedMotionBundleStoreError,
    SafeInputFileError, TypeError, UnicodeError, ValueError,
    VerifiedMeshBundleReaderError, VerifiedMotionRetargetBundleReaderError,
    VerifiedReviewedMotionBundleReaderError,
)
