"""Exact reproducibility verification for immutable P5 retarget bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .manifest_artifacts import LayerManifestError, require_sha256
from .motion_retarget_bundle_contract import (
    DOCUMENT_NAMES,
    MAX_INSTANCE_BYTES,
    MAX_MESH_REPORT_BYTES,
    MAX_RETARGET_REPORT_BYTES,
    MAX_RUN_BYTES,
    MAX_TARGET_PROFILE_BYTES,
    MotionRetargetBundleContractError,
    build_motion_retarget_bundle_contract,
)
from .motion_retarget_pipeline import (
    VerifiedMotionRetargetPipeline,
    VerifiedMotionRetargetPipelineError,
)
from .safe_input_files import strict_json_object


_LIMITS = (MAX_TARGET_PROFILE_BYTES, MAX_INSTANCE_BYTES, MAX_RUN_BYTES,
           MAX_RETARGET_REPORT_BYTES, MAX_MESH_REPORT_BYTES)
_SOURCE_FIELDS = (
    "p3_rig_sha256", "p3_bundle_sha256", "p4_profile_sha256",
    "p4_bundle_sha256", "motion_clip_sha256", "motion_bundle_sha256",
)


class MotionRetargetBundleIntegrityError(ValueError):
    """Raised when stored P5 bytes cannot be exactly rebuilt."""


@dataclass(frozen=True, slots=True)
class MotionRetargetBundleSnapshot:
    """The single admitted read of every file in one secured bundle."""

    directory: Path
    document_items: tuple[tuple[str, bytes], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedMotionRetargetBundle:
    """Frozen verified identities with fresh document accessors."""

    path: Path
    project_id: str
    clip_id: str
    target_profile_sha256: str
    instance_sha256: str
    run_document_sha256: str
    retarget_report_sha256: str
    mesh_regression_sha256: str
    bundle_sha256: str
    _source_items: tuple[tuple[str, str], ...] = field(repr=False)
    _document_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    def _document(self, name: str) -> dict[str, Any]:
        return json.loads(dict(self._document_items)[name])

    @property
    def target_profile(self) -> dict[str, Any]:
        return self._document("target-profile.json")

    @property
    def motion_instance(self) -> dict[str, Any]:
        return self._document("instance.json")

    @property
    def run_manifest(self) -> dict[str, Any]:
        return self._document("run-manifest.json")

    @property
    def retarget_report(self) -> dict[str, Any]:
        return self._document("retarget-report.json")

    @property
    def mesh_regression(self) -> dict[str, Any]:
        return self._document("mesh-regression.json")

    @property
    def source_addresses(self) -> dict[str, str]:
        return dict(self._source_items)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._document_items)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._document_items)


def verify_motion_retarget_bundle_snapshot(
    snapshot: MotionRetargetBundleSnapshot,
    *,
    state_root: Path,
    expected_project_id: str,
    expected_instance_sha256: str,
    expected_bundle_sha256: str,
) -> VerifiedMotionRetargetBundle:
    """Validate the pure contract, then rebuild from exact upstream bundles."""

    try:
        if not isinstance(snapshot, MotionRetargetBundleSnapshot):
            raise MotionRetargetBundleIntegrityError(
                "Motion retarget bundle snapshot is invalid")
        raw = _exact_items(snapshot.document_items)
        documents = {
            name: strict_json_object(data, f"Retarget bundle {name}")
            for name, data in raw.items()
        }
        values = tuple(documents[name] for name in DOCUMENT_NAMES)
        contract = build_motion_retarget_bundle_contract(
            expected_project_id, *values
        )
        if contract.document_bytes != raw:
            raise MotionRetargetBundleIntegrityError(
                "Retarget bundle JSON bytes are not canonical snapshots")
        if (
            contract.project_id != expected_project_id
            or contract.instance_sha256 != expected_instance_sha256
            or contract.bundle_sha256 != expected_bundle_sha256
        ):
            raise MotionRetargetBundleIntegrityError(
                "Retarget bundle differs from its requested content address")
        _require_address(snapshot.directory, Path(state_root), contract)
        sources = _source_addresses(values[0], values[1])
        rebuilt = VerifiedMotionRetargetPipeline(Path(state_root)).build(
            contract.project_id,
            *(sources[field] for field in _SOURCE_FIELDS),
        )
        rebuilt_values = (
            rebuilt.target_profile,
            rebuilt.motion_instance,
            rebuilt.retarget_run,
            rebuilt.retarget_report,
            rebuilt.mesh_regression,
        )
        rebuilt_contract = build_motion_retarget_bundle_contract(
            contract.project_id, *rebuilt_values
        )
        _require_pipeline_identities(rebuilt, contract, sources)
        if rebuilt_contract != contract or rebuilt_contract.document_bytes != raw:
            raise MotionRetargetBundleIntegrityError(
                "Stored retarget bytes differ from exact pipeline rebuild"
            )
        return VerifiedMotionRetargetBundle(
            path=snapshot.directory,
            project_id=contract.project_id,
            clip_id=contract.clip_id,
            target_profile_sha256=contract.target_profile_sha256,
            instance_sha256=contract.instance_sha256,
            run_document_sha256=contract.run_document_sha256,
            retarget_report_sha256=contract.report_sha256,
            mesh_regression_sha256=contract.mesh_report_sha256,
            bundle_sha256=contract.bundle_sha256,
            _source_items=tuple((field, sources[field]) for field in _SOURCE_FIELDS),
            _document_items=tuple((name, raw[name]) for name in DOCUMENT_NAMES),
        )
    except MotionRetargetBundleIntegrityError:
        raise
    except (
        LayerManifestError,
        MotionRetargetBundleContractError,
        VerifiedMotionRetargetPipelineError,
        AttributeError,
        KeyError,
        OverflowError,
        RuntimeError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise MotionRetargetBundleIntegrityError(
            f"Motion retarget bundle integrity verification failed: {exc}"
        ) from exc


def _exact_items(items: Any) -> dict[str, bytes]:
    if type(items) is not tuple or len(items) != len(DOCUMENT_NAMES):
        raise MotionRetargetBundleIntegrityError(
            "Retarget bundle snapshot inventory is invalid")
    result: dict[str, bytes] = {}
    total = 0
    for index, item in enumerate(items):
        if type(item) is not tuple or len(item) != 2:
            raise MotionRetargetBundleIntegrityError(
                "Retarget bundle snapshot inventory is invalid"
            )
        name, data = item
        if name != DOCUMENT_NAMES[index] or type(data) is not bytes:
            raise MotionRetargetBundleIntegrityError(
                "Retarget bundle snapshot inventory is invalid"
            )
        if len(data) > _LIMITS[index]:
            raise MotionRetargetBundleIntegrityError(
                "Retarget bundle byte budget is exceeded"
            )
        total += len(data)
        result[name] = data
    if total > sum(_LIMITS):
        raise MotionRetargetBundleIntegrityError(
            "Retarget bundle byte budget is exceeded")
    return result


def _source_addresses(target: Mapping[str, Any], instance: Mapping[str, Any]):
    target_source = target["source"]
    p3 = target_source["p3"]
    motion = instance["source"]
    values = {
        "p3_rig_sha256": p3["rig_sha256"],
        "p3_bundle_sha256": p3["bundle_sha256"],
        "p4_profile_sha256": target_source["p4_profile_sha256"],
        "p4_bundle_sha256": target_source["p4_bundle_sha256"],
        "motion_clip_sha256": motion["motion_ir_sha256"],
        "motion_bundle_sha256": motion["motion_bundle_sha256"],
    }
    for field, value in values.items():
        require_sha256(value, field)
    return values


def _require_pipeline_identities(rebuilt, contract, sources) -> None:
    expected_outputs = {
        "target_profile_sha256": contract.target_profile_sha256,
        "motion_instance_sha256": contract.instance_sha256,
        "retarget_run_identity_sha256": rebuilt.motion_instance["source"][
            "retarget_run_identity_sha256"
        ],
        "retarget_run_document_sha256": contract.run_document_sha256,
        "retarget_report_sha256": contract.report_sha256,
        "mesh_regression_sha256": contract.mesh_report_sha256,
    }
    inputs = rebuilt.input_sha256s
    if (
        rebuilt.project_id != contract.project_id
        or rebuilt.clip_id != contract.clip_id
        or rebuilt.output_sha256s != expected_outputs
        or any(inputs.get(field) != value for field, value in sources.items())
    ):
        raise MotionRetargetBundleIntegrityError(
            "Exact pipeline identity inventory differs from stored evidence"
        )


def _require_address(path: Path, state_root: Path, contract: Any) -> None:
    try:
        trusted = state_root.resolve(strict=True)
        resolved = Path(path).resolve(strict=True)
        expected = (
            trusted / "builds" / contract.project_id / "motion-instances"
            / contract.instance_sha256 / contract.bundle_sha256
        )
        expected_resolved = expected.resolve(strict=True)
        resolved.relative_to(trusted)
    except (OSError, RuntimeError, ValueError) as exc:
        raise MotionRetargetBundleIntegrityError(
            "Retarget bundle content-address path is invalid"
        ) from exc
    if resolved != expected_resolved or expected_resolved != expected:
        raise MotionRetargetBundleIntegrityError(
            "Retarget bundle content-address path is invalid"
        )
