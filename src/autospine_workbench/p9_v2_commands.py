"""Read-only command services for MotionInstance and Spine adapter v2."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping

from .mesh_source_images import (
    VerifiedMeshSourceReader,
    VerifiedMeshSourceReaderError,
)
from .motion_instance_v2_compiler import (
    MotionInstanceV2CompilerError,
    compile_motion_instance_v2,
)
from .motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReader,
    VerifiedMotionRetargetBundleReaderError,
)
from .resolved_project import canonical_sha256
from .reviewed_motion_policy_validation import (
    MAX_DOCUMENT_BYTES,
    require_reviewed_motion_policy,
)
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)
from .spine42_atlas import Spine42AtlasError, build_spine42_atlas
from .spine42_contract import spine42_json_sha256
from .spine42_contract_v2 import (
    Spine42ContractV2Error,
    spine42_target_profile_v2,
)
from .spine42_json_adapter_v2 import build_spine42_json_v2


class P9V2CommandError(RuntimeError):
    """Raised when an exact read-only v2 command cannot finish."""


@dataclass(frozen=True, slots=True)
class P9V2CommandResult:
    """Canonical report plus every explicit input path that was read."""

    input_paths: tuple[Path, ...]
    report_sha256: str
    report: dict[str, Any]


def compile_motion_instance_v2_command(
    state_root: Path,
    project_id: str,
    reviewed_policy_path: Path,
    *,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
) -> P9V2CommandResult:
    """Compile a policy overlay from one exact P5 bundle without writing."""

    try:
        policy = _policy(reviewed_policy_path)
        p5 = VerifiedMotionRetargetBundleReader(state_root).load(
            project_id,
            motion_instance_sha256,
            motion_retarget_bundle_sha256,
        )
        _require_policy_p5_chain(policy, p5, project_id)
        compiled = compile_motion_instance_v2(
            p5.motion_instance, p5.target_profile, policy
        )
        return P9V2CommandResult(
            input_paths=(p5.path, Path(reviewed_policy_path)),
            report_sha256=compiled.sha256,
            report=compiled.document,
        )
    except P9V2CommandError:
        raise
    except _ERRORS as exc:
        raise P9V2CommandError(
            f"MotionInstance v2 command failed: {exc}"
        ) from exc


def export_spine42_v2_command(
    state_root: Path,
    project_id: str,
    reviewed_policy_path: Path,
    *,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
) -> P9V2CommandResult:
    """Compile an in-memory Spine v2 export and return no binary PNG data."""

    try:
        policy = _policy(reviewed_policy_path)
        p5 = VerifiedMotionRetargetBundleReader(state_root).load(
            project_id,
            motion_instance_sha256,
            motion_retarget_bundle_sha256,
        )
        mesh = VerifiedMeshSourceReader(state_root).load(
            project_id, p3_rig_sha256, p3_bundle_sha256
        )
        _require_policy_p5_chain(policy, p5, project_id)
        _require_p3_chain(policy, mesh, project_id)
        compiled = compile_motion_instance_v2(
            p5.motion_instance, p5.target_profile, policy
        )
        rig = mesh.rig
        skeleton = build_spine42_json_v2(
            rig,
            motion_instance=compiled.document,
            target_profile=p5.target_profile,
        )
        atlas = build_spine42_atlas(
            mesh.png_by_attachment, page_name="skeleton.png"
        )
        report = _export_report(
            project_id, mesh, p5, policy, compiled, skeleton, atlas
        )
        return P9V2CommandResult(
            input_paths=(
                mesh.path, p5.path, Path(reviewed_policy_path),
            ),
            report_sha256=canonical_sha256(report),
            report=report,
        )
    except P9V2CommandError:
        raise
    except _ERRORS as exc:
        raise P9V2CommandError(
            f"Spine 4.2 adapter v2 command failed: {exc}"
        ) from exc


def _policy(path: Path) -> dict[str, Any]:
    document = strict_json_object(
        read_real_file(path, MAX_DOCUMENT_BYTES, "Reviewed motion policy"),
        "Reviewed motion policy",
    )
    require_reviewed_motion_policy(document)
    return document


def _require_policy_p5_chain(
    policy: Mapping[str, Any], p5: Any, project_id: str
) -> None:
    expected = {
        "target_profile_sha256": p5.target_profile_sha256,
        "instance_sha256": p5.instance_sha256,
        "run_sha256": p5.run_document_sha256,
        "retarget_report_sha256": p5.retarget_report_sha256,
        "mesh_regression_sha256": p5.mesh_regression_sha256,
        "bundle_sha256": p5.bundle_sha256,
    }
    source = policy.get("source")
    p5_policy = source.get("p5") if isinstance(source, Mapping) else None
    p3_policy = source.get("p3") if isinstance(source, Mapping) else None
    target = p5.target_profile
    if (
        p5.project_id != project_id
        or p5.clip_id != policy.get("clip_id")
        or policy.get("project_id") != project_id
        or p5_policy != expected
        or canonical_sha256(p5.motion_instance) != p5.instance_sha256
        or canonical_sha256(target) != p5.target_profile_sha256
        or target.get("source", {}).get("p3") != p3_policy
    ):
        raise P9V2CommandError(
            "Reviewed policy differs from the exact P5/P3 source chain"
        )
    addresses = p5.source_addresses
    if addresses.get("p3_rig_sha256") != p3_policy.get("rig_sha256") \
            or addresses.get("p3_bundle_sha256") != p3_policy.get("bundle_sha256"):
        raise P9V2CommandError(
            "P5 source addresses differ from the reviewed P3 chain"
        )


def _require_p3_chain(policy: Mapping[str, Any], mesh: Any, project: str) -> None:
    p3 = policy["source"]["p3"]
    rig = mesh.rig
    if (
        mesh.project_id != project
        or mesh.p3_rig_sha256 != p3["rig_sha256"]
        or mesh.p3_bundle_sha256 != p3["bundle_sha256"]
        or canonical_sha256(rig) != mesh.p3_rig_sha256
    ):
        raise P9V2CommandError(
            "Explicit P3 bundle differs from the reviewed policy chain"
        )


def _export_report(project, mesh, p5, policy, compiled, skeleton, atlas):
    source_images = {
        item.name: item.source_sha256 for item in atlas.placements
    }
    return {
        "format": "autospine-spine42-v2-readonly-export",
        "format_version": 1,
        "project_id": project,
        "source": {
            "p3_rig_sha256": mesh.p3_rig_sha256,
            "p3_bundle_sha256": mesh.p3_bundle_sha256,
            "base_motion_instance_sha256": p5.instance_sha256,
            "base_retarget_bundle_sha256": p5.bundle_sha256,
            "target_profile_sha256": p5.target_profile_sha256,
            "reviewed_motion_policy_sha256": canonical_sha256(policy),
            "motion_instance_v2_sha256": compiled.sha256,
            "source_image_sha256s": source_images,
        },
        "adapter_profile": spine42_target_profile_v2(),
        "skeleton_json_sha256": spine42_json_sha256(skeleton),
        "skeleton_json": skeleton,
        "atlas_sha256": hashlib.sha256(atlas.atlas_bytes).hexdigest(),
        "atlas_text": atlas.atlas_text,
        "png_sha256": hashlib.sha256(atlas.png_bytes).hexdigest(),
    }


_ERRORS = (
    AttributeError,
    KeyError,
    MotionInstanceV2CompilerError,
    OSError,
    OverflowError,
    RecursionError,
    SafeInputFileError,
    Spine42AtlasError,
    Spine42ContractV2Error,
    TypeError,
    UnicodeError,
    ValueError,
    VerifiedMeshSourceReaderError,
    VerifiedMotionRetargetBundleReaderError,
)
