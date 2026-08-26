"""Read-only exact-chain application service for P10.3a preview packages."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any

from .body_sway_preview_inputs import (
    BodySwayPreviewInputError,
    require_body_sway_preview_inputs,
)
from .body_sway_probe_inputs import (
    BodySwayProbeInputError,
    require_body_sway_probe_inputs,
)
from .p10_exact_chain import P10ExactChainError, load_p10_exact_chain
from .p10_preview_replay_spec import (
    P10PreviewReplaySpec,
    build_p10_preview_replay_spec,
)
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)
from .temporary_body_sway_preview import (
    TemporaryBodySwayPreview,
    TemporaryBodySwayPreviewError,
    compile_temporary_body_sway_preview,
    require_exact_temporary_body_sway_preview,
)


MAX_INPUT_DOCUMENT_BYTES = 64 * 1024 * 1024


class P10PreviewCommandError(RuntimeError):
    """Raised when exact persisted inputs cannot form one preview package."""


@dataclass(frozen=True, slots=True)
class P10PreviewCommandResult:
    """Frozen identities and privately held five-file package bytes."""

    input_paths: tuple[Path, ...]
    idle_behavior_candidates_sha256: str
    idle_behavior_decision_sha256: str
    body_sway_probe_report_sha256: str
    temporary_preview_sha256: str
    artifact_set_sha256: str
    _preview: TemporaryBodySwayPreview = field(repr=False)
    _replay_spec: P10PreviewReplaySpec = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return self._preview.document

    @property
    def artifact_bytes(self) -> dict[str, bytes]:
        return self._preview.artifact_bytes

    @property
    def artifact_files(self) -> list[dict[str, Any]]:
        return self.document["artifacts"]["files"]


def compile_body_sway_preview_command(
    state_root: Path,
    project_id: str,
    candidates_path: Path,
    decision_path: Path,
    probe_report_path: Path,
    *,
    layer_manifest_sha256: str,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
    motion_instance_v2_sha256: str,
    reviewed_motion_bundle_sha256: str,
) -> P10PreviewCommandResult:
    """Replay P3/P5/P9/P10 and compile five immutable bytes without writing."""

    try:
        replay_spec = build_p10_preview_replay_spec(
            state_root, project_id,
            candidates_path, decision_path, probe_report_path,
            layer_manifest_sha256=layer_manifest_sha256,
            p3_rig_sha256=p3_rig_sha256,
            p3_bundle_sha256=p3_bundle_sha256,
            motion_instance_sha256=motion_instance_sha256,
            motion_retarget_bundle_sha256=motion_retarget_bundle_sha256,
            motion_instance_v2_sha256=motion_instance_v2_sha256,
            reviewed_motion_bundle_sha256=reviewed_motion_bundle_sha256,
        )
        paths = replay_spec.evidence_paths
        chain = load_p10_exact_chain(
            replay_spec.state_root,
            replay_spec.project_id,
            **replay_spec.exact_chain_kwargs,
        )
        candidates, decision, report = tuple(
            _document(path, label) for path, label in zip(paths, (
                "Idle behavior candidates", "Idle behavior decision",
                "Body-sway probe report",
            ), strict=True)
        )
        probe_inputs = require_body_sway_probe_inputs(
            chain.manifest,
            candidates,
            decision,
            chain.mesh_bundle,
            chain.retarget_bundle,
            chain.reviewed_contract,
        )
        preview_inputs = require_body_sway_preview_inputs(
            probe_inputs, report
        )
        preview = compile_temporary_body_sway_preview(
            preview_inputs, chain.mesh_bundle
        )
        replay_sha = require_exact_temporary_body_sway_preview(
            preview_inputs, chain.mesh_bundle,
            preview.document, preview.artifact_bytes,
        )
        if replay_sha != preview.sha256:
            raise P10PreviewCommandError(
                "Temporary preview identity changed during exact replay"
            )
        source = preview_inputs.source
        return P10PreviewCommandResult(
            input_paths=(*chain.input_paths, *paths),
            idle_behavior_candidates_sha256=
                source["idle_behavior_candidates_sha256"],
            idle_behavior_decision_sha256=
                source["idle_behavior_decision_sha256"],
            body_sway_probe_report_sha256=preview_inputs.report_sha256,
            temporary_preview_sha256=preview.sha256,
            artifact_set_sha256=preview.artifact_set_sha256,
            _preview=preview,
            _replay_spec=replay_spec,
        )
    except P10PreviewCommandError:
        raise
    except _ERRORS as exc:
        raise P10PreviewCommandError(
            f"Body-sway preview command failed: {exc}"
        ) from exc


def _document(path: Path, label: str) -> dict[str, Any]:
    return strict_json_object(
        read_real_file(path, MAX_INPUT_DOCUMENT_BYTES, label), label
    )


def preview_artifact_sha256s(result: P10PreviewCommandResult) -> dict[str, str]:
    """Return detached exact artifact hashes without exposing their bytes."""

    if type(result) is not P10PreviewCommandResult:
        raise P10PreviewCommandError("Preview command result is invalid")
    return {
        path: hashlib.sha256(raw).hexdigest()
        for path, raw in result.artifact_bytes.items()
    }


def require_exact_preview_for_mount(
    result: P10PreviewCommandResult,
) -> TemporaryBodySwayPreview:
    """Rebuild persisted inputs and reject any cached-result divergence."""

    if type(result) is not P10PreviewCommandResult \
            or type(result._replay_spec) is not P10PreviewReplaySpec:
        raise P10PreviewCommandError("Preview command result is invalid")
    try:
        spec = result._replay_spec
        replay = compile_body_sway_preview_command(
            spec.state_root,
            spec.project_id,
            *spec.evidence_paths,
            **spec.exact_chain_kwargs,
        )
        for name in _PUBLIC_SHA_FIELDS:
            if getattr(result, name) != getattr(replay, name):
                raise P10PreviewCommandError(
                    f"Preview command {name} changed during mount replay"
                )
        if result.input_paths != replay.input_paths:
            raise P10PreviewCommandError(
                "Preview command input paths changed during mount replay"
            )
        if result._preview.canonical_bytes != replay._preview.canonical_bytes:
            raise P10PreviewCommandError(
                "Preview manifest changed during mount replay"
            )
        if result._preview.artifact_bytes != replay._preview.artifact_bytes:
            raise P10PreviewCommandError(
                "Preview artifact bytes changed during mount replay"
            )
        return replay._preview
    except P10PreviewCommandError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise P10PreviewCommandError(
            f"Preview mount replay failed: {exc}"
        ) from exc


_PUBLIC_SHA_FIELDS = (
    "idle_behavior_candidates_sha256",
    "idle_behavior_decision_sha256",
    "body_sway_probe_report_sha256",
    "temporary_preview_sha256",
    "artifact_set_sha256",
)


_ERRORS = (
    AttributeError,
    BodySwayPreviewInputError,
    BodySwayProbeInputError,
    KeyError,
    OSError,
    OverflowError,
    P10ExactChainError,
    RecursionError,
    SafeInputFileError,
    TemporaryBodySwayPreviewError,
    TypeError,
    UnicodeError,
    ValueError,
)
