"""Exact historical and cheap readback reader for P10.6b v2 bundles."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
import json
from pathlib import Path
from typing import Any

from .body_sway_dynamic_seam_bundle_reader_v2 import (
    BodySwayDynamicSeamBundleReaderV2,
    BodySwayDynamicSeamBundleReaderV2Error,
    VerifiedBodySwayDynamicSeamBundleV2,
)
from .immutable_bundle_fs import ImmutableBundleFSError
from .motion_instance_v3_bundle_contract_v2 import (
    DOCUMENT_NAMES,
    MotionInstanceV3BundleContractV2,
    MotionInstanceV3BundleContractV2Error,
    build_motion_instance_v3_bundle_contract_v2,
)
from .motion_instance_v3_bundle_fs_v2 import (
    MotionInstanceV3BundleFSV2Error,
    motion_instance_v3_bundle_fs_v2,
)
from .motion_instance_v3_bundle_run_v2 import (
    MotionInstanceV3BundleRunV2Error,
    require_motion_instance_v3_bundle_run_v2,
)
from .motion_instance_v3_prepared_v2 import (
    MotionInstanceV3PreparedV2Error,
    PreparedMotionInstanceV3V2,
    replay_motion_instance_v3_prepared_v2,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)
from .safe_input_files import SafeInputFileError, strict_json_object


class MotionInstanceV3BundleReaderV2Error(RuntimeError):
    """Raised when exact P10.6b v2 bytes cannot replay."""


def _build_reader_types():
    receipt = object()

    @dataclass(frozen=True, slots=True)
    class VerifiedMotionInstanceV3BundleV2:
        path: Path
        project_id: str
        clip_id: str
        admission_sha256: str
        source_set_sha256: str
        source_document_sha256: str
        dynamic_seam_probe_sha256: str
        dynamic_seam_bundle_sha256: str
        motion_instance_v2_sha256: str
        reviewed_motion_bundle_sha256: str
        motion_instance_v3_sha256: str
        motion_instance_v3_profile_sha256: str
        motion_domain_sha256: str
        rotation_timeline_sha256: str
        base_channels_sha256: str
        rig_ir_sha256: str
        target_profile_sha256: str
        run_sha256: str
        bundle_sha256: str
        _documents: tuple[tuple[str, bytes], ...] = field(repr=False)
        _verification_receipt: InitVar[object] = None

        def __post_init__(self, _verification_receipt: object) -> None:
            if _verification_receipt is not receipt:
                raise MotionInstanceV3BundleReaderV2Error(
                    "Verified P10.6b v2 bundles are reader-issued only"
                )

        @property
        def inventory(self) -> tuple[str, ...]:
            return tuple(name for name, _data in self._documents)

        @property
        def document_bytes(self) -> dict[str, bytes]:
            return dict(self._documents)

        @property
        def identities(self) -> dict[str, str]:
            return {
                name: getattr(self, name) for name in (
                    "admission_sha256", "source_set_sha256",
                    "source_document_sha256",
                    "dynamic_seam_probe_sha256",
                    "dynamic_seam_bundle_sha256",
                    "motion_instance_v2_sha256",
                    "reviewed_motion_bundle_sha256",
                    "motion_instance_v3_sha256",
                    "motion_instance_v3_profile_sha256",
                    "motion_domain_sha256", "rotation_timeline_sha256",
                    "base_channels_sha256", "rig_ir_sha256",
                    "target_profile_sha256", "run_sha256", "bundle_sha256",
                )
            }

        def document(self, name: str) -> dict[str, Any]:
            try:
                return json.loads(dict(self._documents)[name])
            except KeyError as exc:
                raise KeyError(name) from exc

    @dataclass(frozen=True, slots=True)
    class MotionInstanceV3BundleReaderV2:
        state_root: Path

        def __post_init__(self) -> None:
            object.__setattr__(self, "state_root", Path(self.state_root))

        def load(
            self,
            project_id: str,
            motion_instance_v3_sha256: str,
            bundle_sha256: str,
            *,
            dynamic_bundle: VerifiedBodySwayDynamicSeamBundleV2 | None = None,
            reviewed_bundle: VerifiedReviewedMotionBundle | None = None,
            prepared: PreparedMotionInstanceV3V2 | None = None,
        ) -> VerifiedMotionInstanceV3BundleV2:
            """Read one explicit address; never inspect current heads."""

            try:
                snapshot = motion_instance_v3_bundle_fs_v2(
                    self.state_root, project_id,
                ).read(motion_instance_v3_sha256, bundle_sha256)
                documents = {
                    name: snapshot.file_bytes(name) for name in DOCUMENT_NAMES
                }
                parsed = {
                    name: strict_json_object(documents[name], name)
                    for name in DOCUMENT_NAMES
                }
                run = parsed[DOCUMENT_NAMES[2]]
                require_motion_instance_v3_bundle_run_v2(run)
                _require_run_address(
                    run, project_id, motion_instance_v3_sha256,
                )
                dynamic_bundle = _dynamic(
                    self.state_root, project_id, run, dynamic_bundle,
                )
                reviewed_bundle = _reviewed(
                    self.state_root, project_id, run, reviewed_bundle,
                )
                _require_dependencies(run, dynamic_bundle, reviewed_bundle)
                if prepared is None:
                    prepared = replay_motion_instance_v3_prepared_v2(
                        parsed[DOCUMENT_NAMES[0]], dynamic_bundle,
                        reviewed_bundle,
                    )
                contract = build_motion_instance_v3_bundle_contract_v2(
                    prepared, parsed[DOCUMENT_NAMES[1]], dynamic_bundle,
                    reviewed_bundle,
                )
                _require_exact_contract(
                    contract, project_id, motion_instance_v3_sha256,
                    bundle_sha256, documents,
                )
                return _verified(snapshot.path, contract, receipt)
            except MotionInstanceV3BundleReaderV2Error:
                raise
            except _FAILURES as exc:
                raise MotionInstanceV3BundleReaderV2Error(
                    "P10.6b v2 historical bundle verification failed"
                ) from exc

    def _verified(path, contract, token):
        names = (
            "project_id", "clip_id", "admission_sha256",
            "source_set_sha256", "source_document_sha256",
            "dynamic_seam_probe_sha256", "dynamic_seam_bundle_sha256",
            "motion_instance_v2_sha256", "reviewed_motion_bundle_sha256",
            "motion_instance_v3_sha256",
            "motion_instance_v3_profile_sha256", "motion_domain_sha256",
            "rotation_timeline_sha256", "base_channels_sha256",
            "rig_ir_sha256", "target_profile_sha256", "run_sha256",
            "bundle_sha256",
        )
        values = tuple(getattr(contract, name) for name in names)
        items = tuple(contract.document_bytes.items())
        return VerifiedMotionInstanceV3BundleV2(
            path, *values, items, token,
        )

    return VerifiedMotionInstanceV3BundleV2, MotionInstanceV3BundleReaderV2


def _require_run_address(run, project_id, primary_sha):
    if run["project_id"] != project_id \
            or run["outputs"]["motion_instance_v3_sha256"] != primary_sha:
        raise MotionInstanceV3BundleReaderV2Error(
            "P10.6b v2 run differs from its explicit address"
        )


def _require_exact_contract(contract, project, primary, bundle, documents):
    if type(contract) is not MotionInstanceV3BundleContractV2 \
            or contract.project_id != project \
            or contract.motion_instance_v3_sha256 != primary \
            or contract.bundle_sha256 != bundle \
            or contract.document_bytes != documents:
        raise MotionInstanceV3BundleReaderV2Error(
            "P10.6b v2 bundle differs from its exact contract"
        )
    return contract


def _dynamic(state_root, project_id, run, supplied):
    address = run["inputs"]["body_sway_dynamic_seam_v2"]
    if supplied is None:
        return BodySwayDynamicSeamBundleReaderV2(state_root).load(
            project_id, address["probe_sha256"], address["bundle_sha256"],
        )
    if type(supplied) is not VerifiedBodySwayDynamicSeamBundleV2:
        raise MotionInstanceV3BundleReaderV2Error(
            "P10.6b v2 dynamic seam input is not reader-issued"
        )
    return supplied


def _reviewed(state_root, project_id, run, supplied):
    p9 = run["inputs"]["p9"]
    if supplied is None:
        return VerifiedReviewedMotionBundleReader(state_root).load(
            project_id, p9["motion_instance_v2_sha256"], p9["bundle_sha256"],
        )
    if type(supplied) is not VerifiedReviewedMotionBundle:
        raise MotionInstanceV3BundleReaderV2Error(
            "P10.6b v2 P9 input is not an exact verified bundle"
        )
    return supplied


def _require_dependencies(run, dynamic, reviewed):
    address = run["inputs"]["body_sway_dynamic_seam_v2"]
    expected_dynamic = {
        "source_set_sha256": dynamic.source_set_sha256,
        "source_document_sha256": dynamic.source_document_sha256,
        "probe_sha256": dynamic.probe_sha256,
        "bundle_sha256": dynamic.bundle_sha256,
    }
    expected_p9 = {
        "motion_instance_v2_sha256": reviewed.motion_instance_v2_sha256,
        "bundle_sha256": reviewed.bundle_sha256,
    }
    if address != expected_dynamic or run["inputs"]["p9"] != expected_p9:
        raise MotionInstanceV3BundleReaderV2Error(
            "P10.6b v2 upstream bundles differ from run provenance"
        )


(
    VerifiedMotionInstanceV3BundleV2,
    MotionInstanceV3BundleReaderV2,
) = _build_reader_types()


_FAILURES = (
    AttributeError, BodySwayDynamicSeamBundleReaderV2Error,
    ImmutableBundleFSError, KeyError, MotionInstanceV3BundleContractV2Error,
    MotionInstanceV3BundleFSV2Error, MotionInstanceV3BundleRunV2Error,
    MotionInstanceV3PreparedV2Error, OSError, OverflowError,
    RecursionError, RuntimeError, SafeInputFileError, TypeError,
    UnicodeError, ValueError, VerifiedReviewedMotionBundleReaderError,
)


__all__ = [
    "MotionInstanceV3BundleReaderV2",
    "MotionInstanceV3BundleReaderV2Error",
    "VerifiedMotionInstanceV3BundleV2",
]
