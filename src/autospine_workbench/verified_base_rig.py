"""Trusted, immutable read boundary for a reviewed P2 RigIR base bundle."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import stat
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .mesh_contract import (
    MeshContractError,
    build_mesh_compile_run,
    require_base_region_rig,
    require_mesh_compile_run,
)
from .rig_bundle_integrity import verify_rig_bundle_directory
from .rig_bundle_validation import RigBundleError


class VerifiedBaseRigReaderError(RuntimeError):
    """Raised when a requested P2 base bundle cannot be trusted for P3."""


@dataclass(frozen=True, slots=True)
class VerifiedBaseRig:
    """Isolated P2 base snapshot; JSON accessors return independent values."""

    path: Path
    rig_sha256: str
    bundle_sha256: str
    _rig_json: str
    _run_manifest_json: str
    _probe_report_json: str
    _setup_document_json: str
    _region_png_items: tuple[tuple[str, bytes], ...] = field(
        default=(), repr=False
    )

    @property
    def rig(self) -> dict[str, Any]:
        return json.loads(self._rig_json)

    @property
    def run_manifest(self) -> dict[str, Any]:
        return json.loads(self._run_manifest_json)

    @property
    def probe_report(self) -> dict[str, Any]:
        return json.loads(self._probe_report_json)

    @property
    def setup_document(self) -> dict[str, Any]:
        return json.loads(self._setup_document_json)

    @property
    def region_pngs(self) -> dict[str, bytes]:
        """Return an isolated mapping of exact P2 attachment image snapshots."""

        return dict(self._region_png_items)


class VerifiedBaseRigReader:
    """Load one exact content-addressed P2 bundle without following aliases."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def load(
        self,
        project_id: str,
        base_rig_sha256: str,
        base_bundle_sha256: str,
    ) -> VerifiedBaseRig:
        try:
            project_id = require_safe_token(project_id, "Project id")
            base_rig_sha256 = require_sha256(
                base_rig_sha256, "Base RigIR digest"
            )
            base_bundle_sha256 = require_sha256(
                base_bundle_sha256, "Base bundle digest"
            )
        except LayerManifestError as exc:
            raise VerifiedBaseRigReaderError(
                "Verified base RigIR identity is invalid"
            ) from exc

        path = self._resolve(
            project_id, base_rig_sha256, base_bundle_sha256
        )
        try:
            verified = verify_rig_bundle_directory(
                path,
                require_content_address=True,
                expected_project_id=project_id,
            )
            if (
                verified.directory != path
                or verified.project_id != project_id
                or verified.rig_sha256 != base_rig_sha256
                or verified.bundle_sha256 != base_bundle_sha256
            ):
                raise VerifiedBaseRigReaderError(
                    "Verified base RigIR differs from its requested content address"
                )
            identity = require_base_region_rig(verified.rig, verified.run)
            if identity["project_id"] != project_id:
                raise VerifiedBaseRigReaderError(
                    "Verified base RigIR belongs to another project"
                )
            mesh_run = build_mesh_compile_run(
                verified.rig,
                verified.run,
                base_bundle_sha256=base_bundle_sha256,
            )
            require_mesh_compile_run(
                mesh_run,
                base_rig=verified.rig,
                base_run=verified.run,
                base_bundle_sha256=base_bundle_sha256,
            )
            return VerifiedBaseRig(
                path=verified.directory,
                rig_sha256=verified.rig_sha256,
                bundle_sha256=verified.bundle_sha256,
                _rig_json=_encode(verified.rig),
                _run_manifest_json=_encode(verified.run),
                _probe_report_json=_encode(verified.probes),
                _setup_document_json=_encode(verified.setup),
                _region_png_items=tuple(sorted(verified.region_pngs.items())),
            )
        except VerifiedBaseRigReaderError:
            raise
        except (RigBundleError, MeshContractError, TypeError, ValueError) as exc:
            raise VerifiedBaseRigReaderError(
                "Verified base RigIR bundle is invalid or unsupported"
            ) from exc

    def _resolve(
        self, project_id: str, rig_sha256: str, bundle_sha256: str
    ) -> Path:
        try:
            if _is_path_alias(self.state_root):
                raise VerifiedBaseRigReaderError(
                    "Verified base RigIR path is unsafe"
                )
            trusted_root = self.state_root.resolve(strict=True)
            if not trusted_root.is_dir():
                raise VerifiedBaseRigReaderError(
                    "Verified base RigIR state root is not a directory"
                )
            current = trusted_root
            for component in (
                "builds",
                project_id,
                "rig-ir",
                rig_sha256,
                bundle_sha256,
            ):
                current = _exact_directory(current, component)
            resolved = current.resolve(strict=True)
            resolved.relative_to(trusted_root)
        except VerifiedBaseRigReaderError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise VerifiedBaseRigReaderError(
                "Verified base RigIR bundle was not found"
            ) from exc
        if resolved != current or _is_path_alias(resolved):
            raise VerifiedBaseRigReaderError(
                "Verified base RigIR path is unsafe"
            )
        return resolved


def _exact_directory(parent: Path, name: str) -> Path:
    if _is_path_alias(parent):
        raise VerifiedBaseRigReaderError("Verified base RigIR path is unsafe")
    try:
        matches = [
            child for child in parent.iterdir()
            if child.name.casefold() == name.casefold()
        ]
    except OSError as exc:
        raise VerifiedBaseRigReaderError(
            "Verified base RigIR bundle was not found"
        ) from exc
    if (
        len(matches) != 1
        or matches[0].name != name
        or _is_path_alias(matches[0])
        or not matches[0].is_dir()
    ):
        raise VerifiedBaseRigReaderError(
            "Verified base RigIR path is missing, aliased, or case-mismatched"
        )
    return matches[0]


def _is_path_alias(path: Path) -> bool:
    """Reject symlinks plus every junction/reparse marker exposed by Python."""

    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(getattr(metadata, "st_file_attributes", 0) & reparse)
    except OSError:
        return True


def _encode(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
