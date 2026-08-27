"""Atomic immutable publication for P10.7 Spine 4.2 bundles."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

from .spine42_v3_bundle_contract import (
    Spine42V3BundleContract,
    Spine42V3BundleContractError,
    build_spine42_v3_bundle_contract,
)
from .spine42_v3_bundle_files import (
    Spine42V3BundleFilesError,
    existing_exact_child,
    publication_parent,
    read_bundle_files,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)
from .spine42_v3_bundle_integrity import (
    Spine42V3BundleIntegrityError,
    Spine42V3BundleSnapshot,
    verify_spine42_v3_bundle_snapshot,
)
from .spine42_v3_current_heads import (
    Spine42V3CurrentHeadsError,
    load_motion_instance_v3_and_dynamic_source,
    observe_spine42_v3_current_heads,
    require_same_spine42_v3_heads,
)
from .spine42_v3_pipeline import (
    VerifiedSpine42V3Pipeline,
    VerifiedSpine42V3PipelineError,
)
from .spine42_v3_pipeline_result import VerifiedSpine42V3Compilation


class Spine42V3BundleStoreError(RuntimeError):
    """Raised when one v3 adapter bundle cannot be safely published."""


@dataclass(frozen=True, slots=True)
class PublishedSpine42V3Bundle:
    path: Path
    project_id: str
    clip_id: str
    skeleton_json_sha256: str
    bundle_sha256: str
    run_document_sha256: str
    reused: bool


class Spine42V3BundleStore:
    """Build and publish five files under skeleton/bundle SHA addresses."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self,
        project_id: str,
        motion_instance_v3_sha256: str,
        motion_instance_v3_bundle_sha256: str,
    ) -> PublishedSpine42V3Bundle:
        """Seal current heads around compilation and immutable publication."""

        parent: Path | None = None
        staging: Path | None = None
        try:
            motion, source = load_motion_instance_v3_and_dynamic_source(
                self.state_root, project_id, motion_instance_v3_sha256,
                motion_instance_v3_bundle_sha256,
            )
            before = observe_spine42_v3_current_heads(self.state_root, source)
            compilation = VerifiedSpine42V3Pipeline(self.state_root).build(
                project_id, motion_instance_v3_sha256,
                motion_instance_v3_bundle_sha256,
            )
            _require_compilation_source(compilation, motion)
            contract = _contract(compilation)
            after_build = observe_spine42_v3_current_heads(
                self.state_root, source
            )
            require_same_spine42_v3_heads(before, after_build)
            parent = publication_parent(
                self.state_root, contract.project_id,
                contract.skeleton_json_sha256,
            )
            destination = existing_exact_child(parent, contract.bundle_sha256)
            if destination is not None:
                _verify(destination, contract)
                reused = True
            else:
                staging = Path(tempfile.mkdtemp(
                    prefix=f".{contract.bundle_sha256[:12]}.", dir=parent,
                ))
                require_real_directory(staging, "Spine v3 staging directory")
                for name, data in contract.document_bytes.items():
                    write_file(staging / name, data)
                _verify(staging, contract, staging=True)
                sync_directory(staging)
                destination, reused = self._commit(staging, parent, contract)
                if not reused:
                    staging = None
            _verify(destination, contract)
            after_publish = observe_spine42_v3_current_heads(
                self.state_root, source
            )
            require_same_spine42_v3_heads(before, after_publish)
            return _published(destination, contract, reused=reused)
        except Spine42V3BundleStoreError:
            raise
        except (
            AttributeError, KeyError, OSError, RuntimeError,
            Spine42V3BundleContractError, Spine42V3BundleFilesError,
            Spine42V3BundleIntegrityError, Spine42V3CurrentHeadsError,
            VerifiedSpine42V3PipelineError, TypeError, ValueError,
        ) as exc:
            raise Spine42V3BundleStoreError(
                "Could not atomically publish Spine v3 bundle"
            ) from exc
        finally:
            if staging is not None:
                remove_staging(staging, parent)

    @staticmethod
    def _commit(staging, parent, contract):
        try:
            destination = parent / contract.bundle_sha256
            os.rename(staging, destination)
        except OSError:
            destination = existing_exact_child(parent, contract.bundle_sha256)
            if destination is None:
                raise
            _verify(destination, contract)
            return destination, True
        sync_directory(parent)
        return destination, False


def _contract(compilation) -> Spine42V3BundleContract:
    if type(compilation) is not VerifiedSpine42V3Compilation:
        raise Spine42V3BundleStoreError(
            "Spine v3 compilation type is invalid"
        )
    contract = build_spine42_v3_bundle_contract(
        compilation.project_id,
        compilation.clip_id,
        compilation.p3_source,
        compilation.motion_instance_v3_source,
        compilation.skeleton_json,
        compilation.atlas_bytes,
        compilation.png_bytes,
        compilation.source_image_sha256s,
    )
    if contract.document_bytes != compilation.document_bytes \
            or contract.bundle_sha256 != compilation.bundle_sha256:
        raise Spine42V3BundleStoreError(
            "Spine v3 compilation differs from its pure contract"
        )
    return contract


def _require_compilation_source(compilation, motion) -> None:
    if compilation.project_id != motion.project_id \
            or compilation.clip_id != motion.clip_id \
            or compilation.motion_instance_v3_sha256 \
                != motion.motion_instance_v3_sha256 \
            or compilation.motion_instance_v3_bundle_sha256 \
                != motion.bundle_sha256 \
            or compilation.admission_sha256 != motion.admission_sha256:
        raise Spine42V3BundleStoreError(
            "Spine v3 compilation source was cross-wired"
        )


def _verify(directory, contract, *, staging=False) -> None:
    verified = verify_spine42_v3_bundle_snapshot(
        Spine42V3BundleSnapshot(directory, read_bundle_files(directory)),
        expected_project_id=contract.project_id,
        expected_skeleton_json_sha256=contract.skeleton_json_sha256,
        expected_bundle_sha256=contract.bundle_sha256,
        require_address_path=not staging,
    )
    if verified.contract_identities != contract.identities \
            or verified.document_bytes != contract.document_bytes:
        raise Spine42V3BundleStoreError(
            "Spine v3 directory differs from its exact contract"
        )


def _published(path, contract, *, reused):
    return PublishedSpine42V3Bundle(
        path, contract.project_id, contract.clip_id,
        contract.skeleton_json_sha256, contract.bundle_sha256,
        contract.run_document_sha256, reused,
    )


__all__ = [
    "PublishedSpine42V3Bundle", "Spine42V3BundleStore",
    "Spine42V3BundleStoreError",
]
