"""Safe read-only command services for P9 reviewed policy compilation."""

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
from .motion_policy_decision import (
    MotionPolicyDecisionError,
    build_motion_policy_decision,
)
from .motion_policy_decision_validation import (
    MAX_DOCUMENT_BYTES as MAX_DECISION_BYTES,
)
from .reviewed_motion_policy import (
    ReviewedMotionPolicyError,
    compile_reviewed_motion_policy,
)
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)


class P9PolicyCommandError(RuntimeError):
    """Raised when safe P9 review inputs cannot compile read-only output."""


@dataclass(frozen=True, slots=True)
class P9PolicyCommandResult:
    input_paths: tuple[Path, ...]
    report_sha256: str
    report: dict[str, Any]


def compile_motion_policy_decision_command(
    foot_candidates_path: Path,
    depth_candidates_path: Path,
    review_input_path: Path,
) -> P9PolicyCommandResult:
    """Compile explicit human choices without publishing or inferring values."""

    try:
        foot = _json(foot_candidates_path, MAX_FOOT_BYTES, "Foot candidates")
        depth = _json(
            depth_candidates_path, MAX_DEPTH_BYTES, "Depth candidates"
        )
        review = _json(
            review_input_path, MAX_DECISION_BYTES, "Motion policy review input"
        )
        expected = {
            "review", "decisions", "root_release_keys",
            "draw_order_loop_reset",
        }
        if set(review) != expected:
            raise P9PolicyCommandError(
                "Motion policy review-input fields are unsupported"
            )
        value = build_motion_policy_decision(
            foot,
            depth,
            review=review["review"],
            decisions=review["decisions"],
            root_release_keys=review["root_release_keys"],
            draw_order_loop_reset=review["draw_order_loop_reset"],
        )
        return P9PolicyCommandResult(
            input_paths=(
                foot_candidates_path, depth_candidates_path, review_input_path,
            ),
            report_sha256=value.sha256,
            report=value.document,
        )
    except P9PolicyCommandError:
        raise
    except _ERRORS as exc:
        raise P9PolicyCommandError(
            f"Motion-policy decision command failed: {exc}"
        ) from exc


def compile_reviewed_motion_policy_command(
    state_root: Path,
    project_id: str,
    foot_candidates_path: Path,
    depth_candidates_path: Path,
    decision_path: Path,
    *,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
) -> P9PolicyCommandResult:
    """Compile a runtime-neutral reviewed policy against one exact P3 bundle."""

    try:
        foot = _json(foot_candidates_path, MAX_FOOT_BYTES, "Foot candidates")
        depth = _json(
            depth_candidates_path, MAX_DEPTH_BYTES, "Depth candidates"
        )
        decision = _json(
            decision_path, MAX_DECISION_BYTES, "Motion policy decision"
        )
        mesh = VerifiedMeshBundleReader(state_root).load(
            project_id, p3_rig_sha256, p3_bundle_sha256
        )
        value = compile_reviewed_motion_policy(
            decision, foot, depth, mesh
        )
        return P9PolicyCommandResult(
            input_paths=(
                foot_candidates_path, depth_candidates_path,
                decision_path, mesh.path,
            ),
            report_sha256=value.sha256,
            report=value.document,
        )
    except P9PolicyCommandError:
        raise
    except _ERRORS as exc:
        raise P9PolicyCommandError(
            f"Reviewed motion-policy command failed: {exc}"
        ) from exc


def _json(path: Path, maximum: int, label: str) -> dict[str, Any]:
    return strict_json_object(read_real_file(path, maximum, label), label)


_ERRORS = (
    AttributeError,
    KeyError,
    MotionPolicyDecisionError,
    OSError,
    OverflowError,
    RecursionError,
    ReviewedMotionPolicyError,
    SafeInputFileError,
    TypeError,
    ValueError,
    VerifiedMeshBundleReaderError,
)
