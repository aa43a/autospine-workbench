"""Frozen command result shared by Preview v2 compilation and its cache."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


class P10PreviewV2CommandError(RuntimeError):
    """Raised when a current package cannot form one exact Preview v2."""


@dataclass(frozen=True, slots=True)
class P10PreviewV2CommandResult:
    """Path-free identities plus privately retained replay inputs."""

    package_id: str
    project_id: str
    clip_id: str
    temporary_preview_v2_sha256: str
    artifact_set_sha256: str
    capture_framing_candidate_sha256: str
    capture_framing_decision_sha256: str
    capture_framing_revision: int
    case_count: int
    _preview: TemporaryBodySwayPreviewV2 = field(repr=False)
    _workspace_root: Path = field(repr=False)
    _state_root: Path = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return self._preview.document

    @property
    def artifact_bytes(self) -> dict[str, bytes]:
        return self._preview.artifact_bytes

    @property
    def cache_weight_bytes(self) -> int:
        return len(self._preview.canonical_bytes) + sum(
            len(value) for value in self._preview.artifact_bytes.values()
        )


def preview_v2_command_result(store, package_id, preview):
    source = preview.document["source"]
    return P10PreviewV2CommandResult(
        package_id=package_id,
        project_id=preview.document["project_id"],
        clip_id=preview.document["clip_id"],
        temporary_preview_v2_sha256=preview.sha256,
        artifact_set_sha256=preview.artifact_set_sha256,
        capture_framing_candidate_sha256=
            source["capture_framing_candidate_sha256"],
        capture_framing_decision_sha256=
            source["capture_framing_decision_sha256"],
        capture_framing_revision=source["capture_framing_revision"],
        case_count=len(preview.document["capture_plan"]["cases"]),
        _preview=preview,
        _workspace_root=store.workspace_root,
        _state_root=store.state_root,
    )


PUBLIC_FIELDS = (
    "package_id", "project_id", "clip_id",
    "temporary_preview_v2_sha256", "artifact_set_sha256",
    "capture_framing_candidate_sha256",
    "capture_framing_decision_sha256", "capture_framing_revision",
    "case_count",
)


__all__ = [
    "P10PreviewV2CommandError", "P10PreviewV2CommandResult",
    "PUBLIC_FIELDS", "preview_v2_command_result",
]
