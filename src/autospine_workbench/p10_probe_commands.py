"""Read-only exact-chain application service for P10.2 body-sway probes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .body_sway_probe_inputs import (
    BodySwayProbeInputError,
    require_body_sway_probe_inputs,
)
from .body_sway_probe_report import (
    BodySwayProbeReportError,
    compile_body_sway_probe_report,
)
from .p10_exact_chain import P10ExactChainError, load_p10_exact_chain
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)


MAX_INPUT_DOCUMENT_BYTES = 64 * 1024 * 1024


class P10ProbeCommandError(RuntimeError):
    """Raised when exact inputs cannot produce one diagnostic report."""


@dataclass(frozen=True, slots=True)
class P10ProbeCommandResult:
    """Diagnostic report and all six explicit input paths and identities."""

    input_paths: tuple[Path, ...]
    idle_behavior_candidates_sha256: str
    idle_behavior_decision_sha256: str
    body_sway_probe_report_sha256: str
    document: dict[str, Any]


def compile_body_sway_probe_command(
    state_root: Path,
    project_id: str,
    candidates_path: Path,
    decision_path: Path,
    *,
    layer_manifest_sha256: str,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
    motion_instance_v2_sha256: str,
    reviewed_motion_bundle_sha256: str,
) -> P10ProbeCommandResult:
    """Read six exact inputs once, admit them, and run the pure compiler."""

    try:
        candidate_path, decision_path = Path(candidates_path), Path(decision_path)
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
        candidates = _document(candidate_path, "Idle behavior candidates")
        decision = _document(decision_path, "Idle behavior decision")
        inputs = require_body_sway_probe_inputs(
            chain.manifest,
            candidates,
            decision,
            chain.mesh_bundle,
            chain.retarget_bundle,
            chain.reviewed_contract,
        )
        compiled = compile_body_sway_probe_report(inputs)
        source = inputs.source
        return P10ProbeCommandResult(
            input_paths=(*chain.input_paths, candidate_path, decision_path),
            idle_behavior_candidates_sha256=(
                source["idle_behavior_candidates_sha256"]
            ),
            idle_behavior_decision_sha256=(
                source["idle_behavior_decision_sha256"]
            ),
            body_sway_probe_report_sha256=compiled.sha256,
            document=compiled.document,
        )
    except P10ProbeCommandError:
        raise
    except _ERRORS as exc:
        raise P10ProbeCommandError(
            f"Body-sway probe command failed: {exc}"
        ) from exc


def _document(path: Path, label: str) -> dict[str, Any]:
    return strict_json_object(
        read_real_file(path, MAX_INPUT_DOCUMENT_BYTES, label), label
    )


_ERRORS = (
    AttributeError,
    BodySwayProbeInputError,
    BodySwayProbeReportError,
    KeyError,
    OSError,
    OverflowError,
    P10ExactChainError,
    RecursionError,
    SafeInputFileError,
    TypeError,
    UnicodeError,
    ValueError,
)
