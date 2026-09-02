"""Current-head-gated atomic publication for P10.7a v2 bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from .atomic_staging import create_same_parent_staging
from .motion_instance_v3_bundle_reader_v2 import VerifiedMotionInstanceV3BundleV2
from .project_store import ProjectStore, ProjectStoreError
from .spine42_v3_bundle_contract_v2 import (
    Spine42V3BundleContractV2,
    Spine42V3BundleContractV2Error,
    build_spine42_v3_bundle_contract_v2,
)
from .spine42_v3_bundle_files_v2 import (
    Spine42V3BundleFilesV2Error,
    existing_exact_child,
    publication_parent,
    read_bundle_files,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)
from .spine42_v3_bundle_integrity_v2 import (
    Spine42V3BundleIntegrityV2Error,
    Spine42V3BundleSnapshotV2,
    verify_spine42_v3_bundle_snapshot_v2,
)
from .spine42_v3_bundle_reader_v2 import (
    VerifiedSpine42V3BundleReaderV2,
    VerifiedSpine42V3BundleReaderV2Error,
)
from .spine42_v3_current_heads_v2 import (
    Spine42V3CurrentHeadsV2Error,
    observe_spine42_v3_current_heads_v2,
    require_same_spine42_v3_heads_v2,
)
from .spine42_v3_pipeline_result_v2 import VerifiedSpine42V3CompilationV2


class Spine42V3BundleStoreV2Error(RuntimeError):
    """Raised when P10.7a v2 cannot publish under stable review heads."""


@dataclass(frozen=True, slots=True)
class PublishedSpine42V3BundleV2:
    path: Path
    project_id: str
    clip_id: str
    skeleton_json_sha256: str
    bundle_sha256: str
    run_document_sha256: str
    report_sha256: str
    reused: bool
    _verified: object = field(repr=False)

    @property
    def verified_bundle(self):
        return self._verified


class Spine42V3BundleStoreV2:
    """Publish one compiled closure after a second current-head read."""

    def __init__(self, capture_job_reader, project_store: ProjectStore) -> None:
        self.capture_job_reader = capture_job_reader
        self.project_store = project_store

    def publish(
        self,
        compilation: VerifiedSpine42V3CompilationV2,
        motion_bundle: VerifiedMotionInstanceV3BundleV2,
        before,
    ) -> PublishedSpine42V3BundleV2:
        """Reject pre-publication drift, publish, exact-read, recheck heads."""

        parent: Path | None = None
        staging: Path | None = None
        try:
            _require_inputs(
                self.capture_job_reader, self.project_store,
                compilation, motion_bundle,
            )
            source = _dynamic_source(motion_bundle)
            _require_compilation_source(compilation, motion_bundle)
            after_compile = observe_spine42_v3_current_heads_v2(
                self.capture_job_reader, self.project_store, source,
            )
            require_same_spine42_v3_heads_v2(before, after_compile)
            contract = _contract(compilation)
            parent = publication_parent(
                self.project_store.state_root, contract.project_id,
                contract.skeleton_json_sha256,
            )
            destination = existing_exact_child(parent, contract.bundle_sha256)
            if destination is not None:
                _verify(destination, contract)
                reused = True
            else:
                staging = create_same_parent_staging(
                    parent, prefix=f".{contract.bundle_sha256[:12]}.",
                )
                require_real_directory(staging, "P10.7a v2 staging directory")
                for name, data in contract.document_bytes.items():
                    write_file(staging / name, data)
                _verify(staging, contract, staging=True)
                sync_directory(staging)
                destination, reused = self._commit(
                    staging, parent, contract,
                )
                if not reused:
                    staging = None
            verified = VerifiedSpine42V3BundleReaderV2(
                self.project_store.state_root,
            ).load(
                contract.project_id, contract.skeleton_json_sha256,
                contract.bundle_sha256, expected=compilation,
            )
            if verified.document_bytes != contract.document_bytes \
                    or verified.contract_identities != contract.identities:
                raise Spine42V3BundleStoreV2Error(
                    "P10.7a v2 exact readback differs from its contract"
                )
            after_publish = observe_spine42_v3_current_heads_v2(
                self.capture_job_reader, self.project_store, source,
            )
            require_same_spine42_v3_heads_v2(before, after_publish)
            return PublishedSpine42V3BundleV2(
                destination, contract.project_id, contract.clip_id,
                contract.skeleton_json_sha256, contract.bundle_sha256,
                contract.run_document_sha256, contract.report_sha256,
                reused, verified,
            )
        except Spine42V3BundleStoreV2Error:
            raise
        except _FAILURES as exc:
            raise Spine42V3BundleStoreV2Error(
                "Could not atomically publish P10.7a v2 bundle"
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


def _require_inputs(capture, store, compilation, motion) -> None:
    if type(store) is not ProjectStore \
            or not callable(getattr(capture, "get", None)) \
            or type(compilation) is not VerifiedSpine42V3CompilationV2 \
            or type(motion) is not VerifiedMotionInstanceV3BundleV2:
        raise Spine42V3BundleStoreV2Error(
            "P10.7a v2 publication requires exact issued inputs"
        )


def _dynamic_source(motion):
    try:
        source = motion.document(
            "body-sway-motion-consumer-admission-v2.json"
        )["source"]["body_sway_dynamic_seam_probe_v2"]["source"]
        if type(source) is not dict:
            raise TypeError
        return source
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise Spine42V3BundleStoreV2Error(
            "P10.7a v2 dynamic source is invalid"
        ) from exc


def _require_compilation_source(compilation, motion) -> None:
    if compilation.project_id != motion.project_id \
            or compilation.clip_id != motion.clip_id \
            or compilation.motion_instance_v3_sha256 \
                != motion.motion_instance_v3_sha256 \
            or compilation.motion_instance_v3_bundle_sha256 \
                != motion.bundle_sha256 \
            or compilation.admission_sha256 != motion.admission_sha256 \
            or compilation.motion_instance_v3_source \
                != _motion_source(motion):
        raise Spine42V3BundleStoreV2Error(
            "P10.7a v2 compilation source is cross-wired"
        )


def _motion_source(motion):
    return dict(motion.identities)


def _contract(compilation) -> Spine42V3BundleContractV2:
    contract = build_spine42_v3_bundle_contract_v2(
        compilation.project_id, compilation.clip_id,
        compilation.p3_source, compilation.motion_instance_v3_source,
        compilation.skeleton_json, compilation.atlas_bytes,
        compilation.png_bytes, compilation.source_image_sha256s,
    )
    if contract.document_bytes != compilation.document_bytes \
            or contract.identities != compilation.contract_identities:
        raise Spine42V3BundleStoreV2Error(
            "P10.7a v2 compilation differs from its pure contract"
        )
    return contract


def _verify(directory, contract, *, staging=False) -> None:
    verified = verify_spine42_v3_bundle_snapshot_v2(
        Spine42V3BundleSnapshotV2(directory, read_bundle_files(directory)),
        expected_project_id=contract.project_id,
        expected_skeleton_json_sha256=contract.skeleton_json_sha256,
        expected_bundle_sha256=contract.bundle_sha256,
        require_address_path=not staging,
    )
    if verified.identities != contract.identities \
            or verified.document_bytes != contract.document_bytes:
        raise Spine42V3BundleStoreV2Error(
            "P10.7a v2 directory differs from its exact contract"
        )


_FAILURES = (
    AttributeError, KeyError, OSError, OverflowError, ProjectStoreError,
    RecursionError, RuntimeError, Spine42V3BundleContractV2Error,
    Spine42V3BundleFilesV2Error, Spine42V3BundleIntegrityV2Error,
    Spine42V3CurrentHeadsV2Error, TypeError, UnicodeError, ValueError,
    VerifiedSpine42V3BundleReaderV2Error,
)


__all__ = [
    "PublishedSpine42V3BundleV2", "Spine42V3BundleStoreV2",
    "Spine42V3BundleStoreV2Error",
]
