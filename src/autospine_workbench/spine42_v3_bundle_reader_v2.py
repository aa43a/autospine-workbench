"""Reader-issued exact historical bundles for P10.7a v2."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
import json
from pathlib import Path
from typing import Any

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .spine42_v3_bundle_contract_v2 import Spine42V3BundleContractV2
from .spine42_v3_bundle_files_v2 import (
    Spine42V3BundleFilesV2Error,
    existing_bundle_path,
    read_bundle_files,
)
from .spine42_v3_bundle_integrity_v2 import (
    Spine42V3BundleIntegrityV2Error,
    Spine42V3BundleSnapshotV2,
    verify_spine42_v3_bundle_snapshot_v2,
)
from .spine42_v3_pipeline_result_v2 import VerifiedSpine42V3CompilationV2


class VerifiedSpine42V3BundleReaderV2Error(RuntimeError):
    """Raised when one exact P10.7a v2 closure cannot be replayed."""


def _build_reader_types():
    receipt = object()

    @dataclass(frozen=True, slots=True)
    class VerifiedSpine42V3BundleV2:
        path: Path
        project_id: str
        clip_id: str
        adapter_profile_sha256: str
        source_contract_sha256: str
        motion_instance_v3_source_sha256: str
        p3_rig_sha256: str
        p3_bundle_sha256: str
        motion_instance_v3_sha256: str
        motion_instance_v3_bundle_sha256: str
        admission_sha256: str
        source_set_sha256: str
        source_document_sha256: str
        dynamic_seam_probe_sha256: str
        dynamic_seam_bundle_sha256: str
        motion_instance_v2_sha256: str
        reviewed_motion_bundle_sha256: str
        motion_instance_v3_profile_sha256: str
        motion_domain_sha256: str
        rotation_timeline_sha256: str
        base_channels_sha256: str
        rig_ir_sha256: str
        target_profile_sha256: str
        motion_instance_v3_run_sha256: str
        skeleton_json_sha256: str
        atlas_sha256: str
        png_sha256: str
        run_identity_sha256: str
        run_document_sha256: str
        report_sha256: str
        bundle_sha256: str
        _source_images: tuple[tuple[str, str], ...] = field(repr=False)
        _documents: tuple[tuple[str, bytes], ...] = field(repr=False)
        _verification_receipt: InitVar[object] = None

        def __post_init__(self, _verification_receipt: object) -> None:
            if _verification_receipt is not receipt:
                raise VerifiedSpine42V3BundleReaderV2Error(
                    "Verified P10.7a v2 bundles are reader-issued only"
                )

        @property
        def inventory(self) -> tuple[str, ...]:
            return tuple(name for name, _data in self._documents)

        @property
        def document_bytes(self) -> dict[str, bytes]:
            return dict(self._documents)

        @property
        def source_image_sha256s(self) -> dict[str, str]:
            return dict(self._source_images)

        @property
        def p3_source(self) -> dict[str, str]:
            return {
                "rig_sha256": self.p3_rig_sha256,
                "bundle_sha256": self.p3_bundle_sha256,
            }

        @property
        def motion_instance_v3_source(self) -> dict[str, str]:
            names = (
                "motion_instance_v3_sha256", "bundle_sha256",
                "admission_sha256", "source_set_sha256",
                "source_document_sha256", "dynamic_seam_probe_sha256",
                "dynamic_seam_bundle_sha256", "motion_instance_v2_sha256",
                "reviewed_motion_bundle_sha256",
                "motion_instance_v3_profile_sha256", "motion_domain_sha256",
                "rotation_timeline_sha256", "base_channels_sha256",
                "rig_ir_sha256", "target_profile_sha256", "run_sha256",
            )
            values = (
                self.motion_instance_v3_sha256,
                self.motion_instance_v3_bundle_sha256,
                self.admission_sha256, self.source_set_sha256,
                self.source_document_sha256, self.dynamic_seam_probe_sha256,
                self.dynamic_seam_bundle_sha256,
                self.motion_instance_v2_sha256,
                self.reviewed_motion_bundle_sha256,
                self.motion_instance_v3_profile_sha256,
                self.motion_domain_sha256, self.rotation_timeline_sha256,
                self.base_channels_sha256, self.rig_ir_sha256,
                self.target_profile_sha256, self.motion_instance_v3_run_sha256,
            )
            return dict(zip(names, values, strict=True))

        @property
        def contract_identities(self) -> dict[str, str]:
            excluded = {"path", "project_id", "clip_id", "_source_images",
                        "_documents", "_verification_receipt"}
            return {
                name: getattr(self, name)
                for name in self.__dataclass_fields__ if name not in excluded
            }

        @property
        def skeleton_json(self) -> dict[str, Any]:
            return self._json("skeleton.json")

        @property
        def run_manifest(self) -> dict[str, Any]:
            return self._json("run-manifest.json")

        @property
        def export_report(self) -> dict[str, Any]:
            return self._json("export-report.json")

        def _json(self, name: str) -> dict[str, Any]:
            return json.loads(dict(self._documents)[name])

    @dataclass(frozen=True, slots=True)
    class VerifiedSpine42V3BundleReaderV2:
        state_root: Path

        def __post_init__(self) -> None:
            object.__setattr__(self, "state_root", Path(self.state_root))

        def load(
            self,
            project_id: str,
            skeleton_json_sha256: str,
            bundle_sha256: str,
            *,
            expected: VerifiedSpine42V3CompilationV2 | None = None,
        ) -> VerifiedSpine42V3BundleV2:
            """Read once; historical replay never observes current heads."""

            try:
                project = require_safe_token(project_id, "Project id")
                skeleton_sha = require_sha256(
                    skeleton_json_sha256, "P10.7a v2 skeleton"
                )
                bundle_sha = require_sha256(
                    bundle_sha256, "P10.7a v2 bundle"
                )
                path = existing_bundle_path(
                    self.state_root, project, skeleton_sha, bundle_sha,
                )
                contract = verify_spine42_v3_bundle_snapshot_v2(
                    Spine42V3BundleSnapshotV2(path, read_bundle_files(path)),
                    expected_project_id=project,
                    expected_skeleton_json_sha256=skeleton_sha,
                    expected_bundle_sha256=bundle_sha,
                )
                candidate = VerifiedSpine42V3CompilationV2.from_contract(
                    contract
                )
                if expected is None:
                    from .spine42_v3_pipeline_v2 import (
                        VerifiedSpine42V3PipelineV2,
                    )
                    rebuilt = VerifiedSpine42V3PipelineV2(
                        self.state_root
                    ).rebuild_and_verify(candidate)
                    _require_compilation(candidate, rebuilt)
                else:
                    _require_compilation(candidate, expected)
                return _verified(path, contract, receipt)
            except VerifiedSpine42V3BundleReaderV2Error:
                raise
            except _FAILURES as exc:
                raise VerifiedSpine42V3BundleReaderV2Error(
                    "Verified P10.7a v2 bundle load failed"
                ) from exc

    def _verified(path, contract, token):
        names = tuple(VerifiedSpine42V3CompilationV2.__dataclass_fields__)[:-2]
        values = tuple(getattr(contract, name) for name in names)
        return VerifiedSpine42V3BundleV2(
            path, *values, tuple(sorted(contract.source_image_sha256s.items())),
            tuple(contract.document_bytes.items()), token,
        )

    return VerifiedSpine42V3BundleV2, VerifiedSpine42V3BundleReaderV2


def _require_compilation(actual, expected) -> None:
    if type(expected) is not VerifiedSpine42V3CompilationV2 \
            or actual.project_id != expected.project_id \
            or actual.clip_id != expected.clip_id \
            or actual.contract_identities != expected.contract_identities \
            or actual.source_image_sha256s != expected.source_image_sha256s \
            or actual.document_bytes != expected.document_bytes:
        raise VerifiedSpine42V3BundleReaderV2Error(
            "P10.7a v2 bytes differ from exact source replay"
        )


(
    VerifiedSpine42V3BundleV2,
    VerifiedSpine42V3BundleReaderV2,
) = _build_reader_types()


_FAILURES = (
    AttributeError, KeyError, LayerManifestError, OSError, OverflowError,
    RecursionError, RuntimeError, Spine42V3BundleFilesV2Error,
    Spine42V3BundleIntegrityV2Error, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "VerifiedSpine42V3BundleReaderV2",
    "VerifiedSpine42V3BundleReaderV2Error",
    "VerifiedSpine42V3BundleV2",
]
