"""Exact current Preview v2 source retained for P10.4b v2 analysis."""

from __future__ import annotations

from dataclasses import dataclass, field

from .body_sway_derived_cache import (
    BodySwayDerivedCacheError, body_sway_derived_cache_key,
    process_body_sway_derived_cache,
)
from .body_sway_preview_inputs_v2 import (
    BodySwayPreviewInputV2Error, BodySwayPreviewInputsV2,
    require_body_sway_preview_inputs_v2,
)
from .body_sway_preview_projection_v2 import (
    BodySwayPreviewProjectionV2, BodySwayPreviewProjectionV2Error,
    compile_body_sway_preview_projection_v2,
)
from .body_sway_probe_application import _compile_derived
from .body_sway_probe_inputs import (
    BodySwayProbeInputError, require_body_sway_probe_inputs,
)
from .capture_framing_verified_head import (
    CaptureFramingVerifiedHeadError, read_capture_framing_verified_head,
)
from .idle_behavior_review_head import (
    IdleBehaviorReviewHeadError, read_idle_behavior_review_head,
)
from .idle_behavior_review_replay import (
    IdleBehaviorReviewReplayError, replay_idle_behavior_review_package,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .p10_preview_v2_cache import P10PreviewV2CacheRecord
from .p10_preview_v2_result import P10PreviewV2CommandError
from .p10_preview_v2_service import (
    compile_cached_body_sway_preview_v2_record,
    p10_preview_v2_record_is_current,
)
from .project_store import ProjectStore, ProjectStoreError


class P10SafetyAnalysisSourceV2Error(RuntimeError):
    """Raised when a current Preview v2 source cannot be reconstructed."""


@dataclass(frozen=True, slots=True)
class P10SafetyAnalysisSourceV2:
    """Process-local exact inputs; no persistent authority is implied."""

    package_id: str
    record: P10PreviewV2CacheRecord = field(repr=False)
    preview_inputs: BodySwayPreviewInputsV2 = field(repr=False)
    projection: BodySwayPreviewProjectionV2 = field(repr=False)
    mesh_bundle: VerifiedMeshBundle = field(repr=False)

    @property
    def project_id(self) -> str:
        return self.preview_inputs.project_id

    @property
    def clip_id(self) -> str:
        return self.preview_inputs.clip_id


def replay_current_p10_safety_analysis_source_v2(
    store: ProjectStore, package_id: str,
) -> P10SafetyAnalysisSourceV2:
    """Rebuild exact P10.2/P10.2b inputs around a revalidated Preview v2."""

    try:
        if type(store) is not ProjectStore:
            raise P10SafetyAnalysisSourceV2Error(
                "P10.4b v2 source requires a ProjectStore"
            )
        record = compile_cached_body_sway_preview_v2_record(
            store, package_id,
        )
        evidence = replay_idle_behavior_review_package(
            store.state_root, record.address,
        )
        p10_head = read_idle_behavior_review_head(
            store.state_root, evidence.candidates.document,
        )
        if p10_head.decision is None:
            raise P10SafetyAnalysisSourceV2Error(
                "P10.4b v2 source has no current P10.1 decision"
            )
        inputs = require_body_sway_probe_inputs(
            evidence.manifest, evidence.candidates.document,
            p10_head.decision.document, evidence.mesh_bundle,
            evidence.retarget_bundle, evidence.reviewed_contract,
        )
        derived_key = body_sway_derived_cache_key(
            store.state_root, record.address,
            evidence.candidates.sha256, p10_head,
        )
        derived = process_body_sway_derived_cache().get_or_compile(
            derived_key,
            lambda: _compile_derived(inputs, p10_head, package_id),
        )
        report = derived.canvas_adjustment.reviewed_report
        candidate = derived.capture_framing
        if candidate is None or candidate.sha256 \
                != record.framing_candidate.sha256:
            raise P10SafetyAnalysisSourceV2Error(
                "P10.4b v2 framing candidate differs from Preview v2"
            )
        framing = read_capture_framing_verified_head(
            store.state_root, candidate,
        )
        if framing.decision is None:
            raise P10SafetyAnalysisSourceV2Error(
                "P10.4b v2 framing head is unavailable"
            )
        preview_inputs = require_body_sway_preview_inputs_v2(
            inputs, report, candidate, framing.decision, framing.snapshot,
            state_root=store.state_root, package_id=package_id,
        )
        projection = compile_body_sway_preview_projection_v2(preview_inputs)
        _require_preview_binding(record, preview_inputs, projection)
        if not p10_preview_v2_record_is_current(store, record):
            raise P10SafetyAnalysisSourceV2Error(
                "P10.4b v2 source changed during reconstruction"
            )
        return P10SafetyAnalysisSourceV2(
            package_id, record, preview_inputs, projection,
            evidence.mesh_bundle,
        )
    except P10SafetyAnalysisSourceV2Error:
        raise
    except _FAILURES as exc:
        raise P10SafetyAnalysisSourceV2Error(
            "P10.4b v2 exact source replay failed"
        ) from exc


def _require_preview_binding(record, inputs, projection) -> None:
    preview = record.result._preview
    document = preview.document
    source = document["source"]
    if document["project_id"] != inputs.project_id \
            or document["clip_id"] != inputs.clip_id \
            or document["timing"] != inputs.timing \
            or document["selection"] != inputs.selection \
            or source["body_sway_probe_report_sha256"] \
                != inputs.report_sha256 \
            or document["projection"] != projection.public_metadata:
        raise P10SafetyAnalysisSourceV2Error(
            "P10.4b v2 projection differs from the current Preview v2"
        )


_FAILURES = (
    BodySwayDerivedCacheError, BodySwayPreviewInputV2Error,
    BodySwayPreviewProjectionV2Error, BodySwayProbeInputError,
    CaptureFramingVerifiedHeadError, IdleBehaviorReviewHeadError,
    IdleBehaviorReviewReplayError, KeyError, OSError, OverflowError,
    P10PreviewV2CommandError, ProjectStoreError, RecursionError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "P10SafetyAnalysisSourceV2", "P10SafetyAnalysisSourceV2Error",
    "replay_current_p10_safety_analysis_source_v2",
]
