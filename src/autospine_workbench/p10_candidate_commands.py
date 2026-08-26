"""Exact-read application service for P10 idle-behavior candidates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .idle_behavior_candidates import (
    IdleBehaviorCandidateError,
    compile_idle_behavior_candidates,
)
from .p10_exact_chain import P10ExactChainError, load_p10_exact_chain


class P10CandidateCommandError(RuntimeError):
    """Raised when one exact P10 candidate compilation cannot finish."""


@dataclass(frozen=True, slots=True)
class P10CandidateCommandResult:
    """Canonical candidate document plus every exact input path read."""

    input_paths: tuple[Path, ...]
    idle_behavior_candidates_sha256: str
    document: dict[str, Any]


def compile_idle_behavior_candidates_command(
    state_root: Path,
    project_id: str,
    *,
    layer_manifest_sha256: str,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
    motion_instance_v2_sha256: str,
    reviewed_motion_bundle_sha256: str,
) -> P10CandidateCommandResult:
    """Read four exact bundles, replay P9, then invoke the pure compiler."""

    try:
        chain = load_p10_exact_chain(
            state_root,
            project_id,
            layer_manifest_sha256=layer_manifest_sha256,
            p3_rig_sha256=p3_rig_sha256,
            p3_bundle_sha256=p3_bundle_sha256,
            motion_instance_sha256=motion_instance_sha256,
            motion_retarget_bundle_sha256=motion_retarget_bundle_sha256,
            motion_instance_v2_sha256=motion_instance_v2_sha256,
            reviewed_motion_bundle_sha256=reviewed_motion_bundle_sha256,
        )
        compiled = compile_idle_behavior_candidates(
            chain.manifest,
            chain.mesh_bundle,
            chain.retarget_bundle,
            chain.reviewed_contract,
        )
        return P10CandidateCommandResult(
            input_paths=chain.input_paths,
            idle_behavior_candidates_sha256=compiled.sha256,
            document=compiled.document,
        )
    except P10CandidateCommandError:
        raise
    except _ERRORS as exc:
        raise P10CandidateCommandError(
            f"Idle behavior candidate command failed: {exc}"
        ) from exc

_ERRORS = (
    AttributeError,
    IdleBehaviorCandidateError,
    KeyError,
    OSError,
    OverflowError,
    P10ExactChainError,
    RecursionError,
    TypeError,
    UnicodeError,
    ValueError,
)
