"""Safe service boundary for exact P5 motion-retarget bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .motion_retarget_bundle_contract import (
    DOCUMENT_NAMES, MotionRetargetBundleContractError,
    build_motion_retarget_bundle_contract,
)
from .motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReader, VerifiedMotionRetargetBundleReaderError,
)
from .motion_retarget_bundle_store import (
    MotionRetargetBundleStore, MotionRetargetBundleStoreError,
)
from .motion_retarget_pipeline import (
    VerifiedMotionRetargetPipeline, VerifiedMotionRetargetPipelineError,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_FIELDS = (
    "p3_rig_sha256", "p3_bundle_sha256", "p4_profile_sha256",
    "p4_bundle_sha256", "motion_clip_sha256", "motion_bundle_sha256",
)
_OUTPUT_FIELDS = (
    "target_profile_sha256", "motion_instance_sha256",
    "retarget_run_identity_sha256", "retarget_run_document_sha256",
    "retarget_report_sha256", "mesh_regression_sha256",
)
_INPUT_FIELDS = (
    *(f"p3_{name}" for name in SOURCE_IDENTITY_FIELDS),
    "p4_profile_sha256", "p4_probes_sha256", "p4_bundle_sha256",
    "motion_clip_sha256", "motion_run_sha256", "motion_bundle_sha256",
)

class MotionRetargetCommandError(RuntimeError):
    """Raised when a P5 service stage disagrees with an exact identity."""

@dataclass(frozen=True, slots=True)
class MotionRetargetCommandResult:
    """Frozen complete identity and isolated SHA inventories."""
    path: Path
    project_id: str
    clip_id: str
    target_profile_sha256: str
    instance_sha256: str
    retarget_run_identity_sha256: str
    run_sha256: str
    report_sha256: str
    mesh_regression_sha256: str
    bundle_sha256: str
    summary: str
    reused: bool | None
    _source_items: tuple[tuple[str, str], ...] = field(repr=False)
    _input_items: tuple[tuple[str, str], ...] = field(repr=False)
    _output_items: tuple[tuple[str, str], ...] = field(repr=False)
    _document_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def source_addresses(self) -> dict[str, str]:
        return dict(self._source_items)
    @property
    def input_sha256s(self) -> dict[str, str]:
        return dict(self._input_items)
    @property
    def output_sha256s(self) -> dict[str, str]:
        return dict(self._output_items)
    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._document_items)
    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._document_items)

def compile_motion_retarget_bundle(
    state_root: Path, project_id: str, *, p3_rig_sha256: str,
    p3_bundle_sha256: str, p4_profile_sha256: str,
    p4_bundle_sha256: str, motion_clip_sha256: str,
    motion_bundle_sha256: str,
) -> MotionRetargetCommandResult:
    """Build, publish, and securely read back one exact retarget result."""
    requested = dict(zip(_SOURCE_FIELDS, (
        p3_rig_sha256, p3_bundle_sha256, p4_profile_sha256,
        p4_bundle_sha256, motion_clip_sha256, motion_bundle_sha256,
    )))
    try:
        pipeline = VerifiedMotionRetargetPipeline(state_root).build(
            project_id, *requested.values())
        values = (
            pipeline.target_profile, pipeline.motion_instance,
            pipeline.retarget_run, pipeline.retarget_report,
            pipeline.mesh_regression,
        )
        contract = build_motion_retarget_bundle_contract(project_id, *values)
        evidence = _require_pipeline(
            pipeline, project_id, requested, contract, values)
        published = MotionRetargetBundleStore(state_root).publish(
            project_id, *values)
        _require_publication(published, contract)
        verified = VerifiedMotionRetargetBundleReader(state_root).load(
            project_id, published.instance_sha256, published.bundle_sha256)
        return _result(
            verified, reused=published.reused, requested=requested,
            expected=(contract, *evidence), expected_path=published.path,
        )
    except MotionRetargetCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise MotionRetargetCommandError(
            f"Motion retarget bundle compilation failed: {exc}") from exc

def verify_motion_retarget_bundle(
    state_root: Path, project_id: str, *, instance_sha256: str,
    bundle_sha256: str,
) -> MotionRetargetCommandResult:
    """Securely verify one explicit bundle address without writing state."""

    try:
        verified = VerifiedMotionRetargetBundleReader(state_root).load(
            project_id, instance_sha256, bundle_sha256)
        return _result(verified, reused=None)
    except MotionRetargetCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise MotionRetargetCommandError(
            f"Motion retarget bundle verification failed: {exc}") from exc

def _require_pipeline(pipeline, project, requested, contract, values):
    inputs, outputs = pipeline.input_sha256s, pipeline.output_sha256s
    _sha_inventory(inputs, _INPUT_FIELDS, "pipeline input")
    _sha_inventory(outputs, _OUTPUT_FIELDS, "pipeline output")
    documents = {
        name: _canonical(value)
        for name, value in zip(DOCUMENT_NAMES, values)
    }
    summary = _summary(values[1], values[4])
    if (
        pipeline.project_id != project or pipeline.clip_id != contract.clip_id
        or _sources_from_inputs(inputs) != requested
        or outputs != _contract_outputs(contract, values[1])
        or documents != contract.document_bytes
        or pipeline.summary != summary
    ):
        raise MotionRetargetCommandError(
            "Motion retarget pipeline identity or evidence differs")
    return documents, inputs, outputs, summary

def _require_publication(published, contract) -> None:
    expected = {
        "project_id": contract.project_id, "clip_id": contract.clip_id,
        "target_profile_sha256": contract.target_profile_sha256,
        "instance_sha256": contract.instance_sha256,
        "run_document_sha256": contract.run_document_sha256,
        "report_sha256": contract.report_sha256,
        "mesh_report_sha256": contract.mesh_report_sha256,
        "bundle_sha256": contract.bundle_sha256,
    }
    if any(getattr(published, key, None) != value
           for key, value in expected.items()):
        raise MotionRetargetCommandError(
            "Published motion retarget identity differs from its contract")
    if type(getattr(published, "reused", None)) is not bool or not isinstance(
        getattr(published, "path", None), Path
    ):
        raise MotionRetargetCommandError(
            "Published motion retarget path or reuse status is invalid")

def _result(verified, *, reused, requested=None, expected=None,
            expected_path=None):
    documents = verified.document_bytes
    if verified.inventory != DOCUMENT_NAMES or set(documents) != set(DOCUMENT_NAMES):
        raise MotionRetargetCommandError("Verified retarget inventory is invalid")
    values = tuple(json.loads(documents[name]) for name in DOCUMENT_NAMES)
    contract = build_motion_retarget_bundle_contract(verified.project_id, *values)
    if contract.document_bytes != documents:
        raise MotionRetargetCommandError(
            "Verified retarget bytes are not canonical contract bytes")
    sources = verified.source_addresses
    _sha_inventory(sources, _SOURCE_FIELDS, "verified source address")
    inputs = _inputs(values[0], values[1])
    outputs = _contract_outputs(contract, values[1])
    summary = _summary(values[1], values[4])
    identities = {
        "project_id": contract.project_id, "clip_id": contract.clip_id,
        "target_profile_sha256": contract.target_profile_sha256,
        "instance_sha256": contract.instance_sha256,
        "run_document_sha256": contract.run_document_sha256,
        "retarget_report_sha256": contract.report_sha256,
        "mesh_regression_sha256": contract.mesh_report_sha256,
        "bundle_sha256": contract.bundle_sha256,
    }
    if any(getattr(verified, key, None) != value
           for key, value in identities.items()):
        raise MotionRetargetCommandError(
            "Verified retarget identity differs from canonical documents")
    if sources != _sources_from_inputs(inputs):
        raise MotionRetargetCommandError("Verified retarget sources are incomplete")
    if requested is not None and sources != requested:
        raise MotionRetargetCommandError("Verified retarget sources differ from request")
    if expected is not None and expected != (
        contract, documents, inputs, outputs, summary,
    ):
        raise MotionRetargetCommandError(
            "Verified retarget evidence differs from pipeline")
    path = getattr(verified, "path", None)
    if not isinstance(path, Path) or expected_path is not None and (
        path.resolve(strict=True) != Path(expected_path).resolve(strict=True)
    ):
        raise MotionRetargetCommandError(
            "Verified retarget path differs from publication")
    if reused is not None and type(reused) is not bool:
        raise MotionRetargetCommandError("Verified retarget reuse status is invalid")
    return MotionRetargetCommandResult(
        path, contract.project_id, contract.clip_id,
        contract.target_profile_sha256, contract.instance_sha256,
        outputs["retarget_run_identity_sha256"], contract.run_document_sha256,
        contract.report_sha256, contract.mesh_report_sha256,
        contract.bundle_sha256, summary, reused,
        _items(sources, _SOURCE_FIELDS), _items(inputs, _INPUT_FIELDS),
        _items(outputs, _OUTPUT_FIELDS), _items(documents, DOCUMENT_NAMES),
    )

def _inputs(target: Mapping[str, Any], instance: Mapping[str, Any]):
    p3, source = target["source"]["p3"], instance["source"]
    values = {
        **{f"p3_{field}": p3[field] for field in SOURCE_IDENTITY_FIELDS},
        "p4_profile_sha256": target["source"]["p4_profile_sha256"],
        "p4_probes_sha256": target["source"]["p4_probes_sha256"],
        "p4_bundle_sha256": target["source"]["p4_bundle_sha256"],
        "motion_clip_sha256": source["motion_ir_sha256"],
        "motion_run_sha256": source["motion_run_sha256"],
        "motion_bundle_sha256": source["motion_bundle_sha256"],
    }
    _sha_inventory(values, _INPUT_FIELDS, "verified input")
    return values

def _contract_outputs(contract, instance):
    values = {
        "target_profile_sha256": contract.target_profile_sha256,
        "motion_instance_sha256": contract.instance_sha256,
        "retarget_run_identity_sha256": instance["source"][
            "retarget_run_identity_sha256"],
        "retarget_run_document_sha256": contract.run_document_sha256,
        "retarget_report_sha256": contract.report_sha256,
        "mesh_regression_sha256": contract.mesh_report_sha256,
    }
    _sha_inventory(values, _OUTPUT_FIELDS, "verified output")
    return values

def _summary(instance, mesh):
    tracks, markers, value = instance["tracks"], instance["markers"], mesh["summary"]
    if type(tracks) is not list or type(markers) is not list or not isinstance(value, str):
        raise MotionRetargetCommandError("Verified retarget summary inputs are invalid")
    return f"clip={instance['clip_id']};tracks={len(tracks)};markers={len(markers)};mesh={value}"
def _sources_from_inputs(inputs): return {field: inputs[field] for field in _SOURCE_FIELDS}
def _sha_inventory(value, fields, label):
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise MotionRetargetCommandError(f"{label} inventory is invalid")
    if any(not isinstance(value[field], str) or not _SHA256.fullmatch(value[field])
           for field in fields):
        raise MotionRetargetCommandError(f"{label} contains an invalid SHA")
def _items(value, fields): return tuple((field, value[field]) for field in fields)
def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")

_DOMAIN_ERRORS = (
    AttributeError, KeyError, OSError, OverflowError, RecursionError,
    MotionRetargetBundleContractError, MotionRetargetBundleStoreError,
    VerifiedMotionRetargetBundleReaderError,
    VerifiedMotionRetargetPipelineError, RuntimeError, TypeError, ValueError,
)
