"""Read-only exact-address command for P10.5a seam candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .manifest_bundle import (
    LayerManifestBundleError,
    LayerManifestBundleReader,
)
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from .seam_anchor_candidates import (
    SeamAnchorCandidateError,
    SeamAnchorCandidates,
    compile_seam_anchor_candidates,
)


class SeamAnchorCandidateCommandError(RuntimeError):
    """Raised when exact static inputs cannot produce seam candidates."""


@dataclass(frozen=True, slots=True)
class SeamAnchorCandidateCommandResult:
    """Public candidate identity plus private exact input locations."""

    input_paths: tuple[Path, Path] = field(repr=False)
    seam_anchor_candidates_sha256: str
    _candidates: SeamAnchorCandidates = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        """Return an isolated canonical candidate document."""

        return self._candidates.document


def compile_seam_anchor_candidates_command(
    state_root: Path,
    project_id: str,
    *,
    layer_manifest_sha256: str,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
) -> SeamAnchorCandidateCommandResult:
    """Replay two exact read boundaries and compile without writing state."""

    try:
        state = Path(state_root)
        manifest = LayerManifestBundleReader(state).load(
            project_id, layer_manifest_sha256
        )
        mesh = VerifiedMeshBundleReader(state).load(
            project_id, p3_rig_sha256, p3_bundle_sha256
        )
        candidates = compile_seam_anchor_candidates(
            manifest.manifest, mesh
        )
        return SeamAnchorCandidateCommandResult(
            input_paths=(manifest.path, mesh.path),
            seam_anchor_candidates_sha256=candidates.sha256,
            _candidates=candidates,
        )
    except SeamAnchorCandidateCommandError:
        raise
    except _FAILURES as exc:
        raise SeamAnchorCandidateCommandError(
            "Seam-anchor candidate command failed"
        ) from exc


_FAILURES = (
    AttributeError,
    KeyError,
    LayerManifestBundleError,
    OSError,
    OverflowError,
    RecursionError,
    SeamAnchorCandidateError,
    TypeError,
    UnicodeError,
    ValueError,
    VerifiedMeshBundleReaderError,
)
