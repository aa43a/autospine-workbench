"""Exact-address compile and historical verify commands for P10.5d v2."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import json
from typing import Any

from .body_sway_dynamic_seam_bundle_contract_v2 import DOCUMENT_NAMES
from .body_sway_dynamic_seam_bundle_reader_v2 import (
    BodySwayDynamicSeamBundleReaderV2,
    BodySwayDynamicSeamBundleReaderV2Error,
)
from .body_sway_dynamic_seam_bundle_store_v2 import (
    BodySwayDynamicSeamBundleStoreV2,
    BodySwayDynamicSeamBundleStoreV2Error,
)
from .body_sway_dynamic_seam_head_checks_v2 import (
    BodySwayDynamicSeamHeadCheckV2Error,
    _observe_admitted_body_sway_dynamic_seam_heads_v2,
)
from .body_sway_dynamic_seam_probe_validation_v2 import (
    BodySwayDynamicSeamProbeV2ValidationError,
    require_body_sway_dynamic_seam_probe_v2,
)
from .body_sway_dynamic_seam_source_v2 import (
    BodySwayDynamicSeamSourceV2Error,
    build_body_sway_dynamic_seam_source_v2,
)
from .body_sway_dynamic_seam_v2 import (
    BodySwayDynamicSeamProbeV2Error,
    compile_body_sway_dynamic_seam_probe_v2,
)
from .p10_dynamic_seam_inputs_v2 import (
    P10DynamicSeamInputsV2Error,
    load_p10_dynamic_seam_inputs_v2,
)
from .project_store import ProjectStore
from .seam_anchor_review_json import canonical_json_bytes


Progress = Callable[[str, int, int], None]


class P10DynamicSeamCommandV2Error(RuntimeError):
    """Raised when exact P10.5d v2 compile or verification fails closed."""


@dataclass(frozen=True, slots=True)
class P10DynamicSeamCommandResultV2:
    project_id: str
    clip_id: str
    probe_sha256: str
    bundle_sha256: str
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


def compile_body_sway_dynamic_seam_probe_v2_command(
    capture_job_reader,
    project_store: ProjectStore,
    project_id: str,
    safety_run_id: str,
    *,
    continuous_proof_sha256: str,
    reviewed_set_sha256: str,
    reviewed_set_bundle_sha256: str,
    on_progress: Progress | None = None,
) -> P10DynamicSeamCommandResultV2:
    """Compile and publish between pre/post exact current-head checks."""

    try:
        if type(project_store) is not ProjectStore \
                or not callable(getattr(capture_job_reader, "get", None)) \
                or on_progress is not None and not callable(on_progress):
            raise P10DynamicSeamCommandV2Error(
                "P10.5d v2 requires exact read-only stores"
            )
        _progress(on_progress, "exact_inputs", 0, 1)
        inputs = load_p10_dynamic_seam_inputs_v2(
            project_store.state_root, project_id, safety_run_id,
            continuous_proof_sha256=continuous_proof_sha256,
            reviewed_set_sha256=reviewed_set_sha256,
            reviewed_set_bundle_sha256=reviewed_set_bundle_sha256,
        )
        bundle = inputs.reviewed_bundle
        source = build_body_sway_dynamic_seam_source_v2(
            continuous_proof_v2=inputs.continuous_proof,
            seam_anchor_candidates_v1=bundle.candidates,
            seam_anchor_review_decision_v1=bundle.decision,
            reviewed_seam_anchor_set_v1=bundle.reviewed_set,
            reviewed_set_v1_bundle_sha256=bundle.bundle_sha256,
        )
        _require_input_identity(inputs, source)
        _progress(on_progress, "exact_inputs", 1, 1)
        before = _observe_admitted_body_sway_dynamic_seam_heads_v2(
            capture_job_reader, project_store, source,
        )
        probe = compile_body_sway_dynamic_seam_probe_v2(
            source, on_progress=on_progress,
        )
        validation_progress = None if on_progress is None else (
            lambda _stage, current, total: on_progress(
                "dynamic_seam_validation_segments", current, total,
            )
        )
        require_body_sway_dynamic_seam_probe_v2(
            probe.document, on_progress=validation_progress,
        )
        prepublish = _observe_admitted_body_sway_dynamic_seam_heads_v2(
            capture_job_reader, project_store, source,
        )
        _require_same_heads(before, prepublish)
        _progress(on_progress, "publication", 0, 1)
        published = BodySwayDynamicSeamBundleStoreV2(
            project_store.state_root
        ).publish(source, probe.document)
        postpublish = _observe_admitted_body_sway_dynamic_seam_heads_v2(
            capture_job_reader, project_store, source,
        )
        _require_same_heads(prepublish, postpublish)
        verified = BodySwayDynamicSeamBundleReaderV2(
            project_store.state_root
        ).load(
            published.project_id,
            published.probe_sha256,
            published.bundle_sha256,
        )
        if verified.source != source \
                or verified.probe != probe.document:
            raise P10DynamicSeamCommandV2Error(
                "P10.5d v2 published documents differ on exact readback"
            )
        _progress(on_progress, "publication", 1, 1)
        document = {
            "status": "compiled",
            "project_id": published.project_id,
            "clip_id": published.clip_id,
            "upstream": {
                "safety_run_id": inputs.safety_run_id,
                "continuous_proof_sha256":
                    inputs.continuous_proof_sha256,
                "reviewed_set_sha256": inputs.reviewed_set_sha256,
                "reviewed_set_bundle_sha256":
                    inputs.reviewed_set_bundle_sha256,
            },
            "source_set_sha256": published.source_set_sha256,
            "source_document_sha256": published.source_document_sha256,
            "probe_sha256": published.probe_sha256,
            "bundle_sha256": published.bundle_sha256,
            "bundle_inventory": list(DOCUMENT_NAMES),
            "reused": published.reused,
            "probe_status": probe.document["status"],
            "summary": probe.document["summary"],
            "claims": probe.document["claims"],
            "release_gate": probe.document["release_gate"],
            "head_observation": {
                "scope": "compile_time",
                "before": before.document,
                "prepublish": prepublish.document,
                "postpublish": postpublish.document,
                "checks": {
                    "before_prepublish": "exact_match",
                    "prepublish_postpublish": "exact_match",
                },
                "permanent_authority_claimed": False,
            },
        }
        return P10DynamicSeamCommandResultV2(
            published.project_id, published.clip_id,
            published.probe_sha256, published.bundle_sha256,
            _canonical(document),
        )
    except P10DynamicSeamCommandV2Error:
        raise
    except _FAILURES as exc:
        raise P10DynamicSeamCommandV2Error(
            "P10.5d v2 compilation failed closed"
        ) from exc


def verify_body_sway_dynamic_seam_bundle_v2_command(
    state_root, project_id, *, probe_sha256, bundle_sha256,
) -> P10DynamicSeamCommandResultV2:
    """Verify immutable historical bytes without claiming current authority."""

    try:
        verified = BodySwayDynamicSeamBundleReaderV2(state_root).load(
            project_id, probe_sha256, bundle_sha256,
        )
        probe, manifest = verified.probe, verified.manifest
        document = {
            "status": "verified",
            "project_id": verified.project_id,
            "clip_id": verified.clip_id,
            "source_set_sha256": verified.source_set_sha256,
            "source_document_sha256": verified.source_document_sha256,
            "probe_sha256": verified.probe_sha256,
            "bundle_sha256": verified.bundle_sha256,
            "bundle_inventory": list(DOCUMENT_NAMES),
            "authority_scope": manifest["authority_scope"],
            "probe_status": probe["status"],
            "summary": probe["summary"],
            "claims": probe["claims"],
            "release_gate": probe["release_gate"],
            "current_head_checked": False,
            "permanent_current_authority_claimed": False,
        }
        return P10DynamicSeamCommandResultV2(
            verified.project_id, verified.clip_id,
            verified.probe_sha256, verified.bundle_sha256,
            _canonical(document),
        )
    except P10DynamicSeamCommandV2Error:
        raise
    except _FAILURES as exc:
        raise P10DynamicSeamCommandV2Error(
            "P10.5d v2 historical verification failed closed"
        ) from exc


def _require_input_identity(inputs, source):
    if source["project_id"] != inputs.project_id \
            or source[
                "body_sway_continuous_preview_proof_v2_sha256"
            ] != inputs.continuous_proof_sha256 \
            or source["reviewed_seam_anchor_set_v1_sha256"] \
                != inputs.reviewed_set_sha256 \
            or source["reviewed_seam_anchor_set_v1_bundle_sha256"] \
                != inputs.reviewed_set_bundle_sha256:
        raise P10DynamicSeamCommandV2Error(
            "P10.5d v2 source closure differs from explicit addresses"
        )


def _require_same_heads(left, right):
    if left.identity_sha256 != right.identity_sha256 \
            or left.canonical_bytes != right.canonical_bytes:
        raise P10DynamicSeamCommandV2Error(
            "P10.5d v2 current review heads changed during publication"
        )


def _progress(callback, stage, current, total):
    if callback is not None:
        callback(stage, current, total)


def _canonical(value):
    return canonical_json_bytes(value).decode("utf-8")


_FAILURES = (
    AttributeError, BodySwayDynamicSeamBundleReaderV2Error,
    BodySwayDynamicSeamBundleStoreV2Error,
    BodySwayDynamicSeamHeadCheckV2Error,
    BodySwayDynamicSeamProbeV2Error,
    BodySwayDynamicSeamProbeV2ValidationError,
    BodySwayDynamicSeamSourceV2Error, KeyError, OSError,
    OverflowError, P10DynamicSeamInputsV2Error, RecursionError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "P10DynamicSeamCommandResultV2", "P10DynamicSeamCommandV2Error",
    "compile_body_sway_dynamic_seam_probe_v2_command",
    "verify_body_sway_dynamic_seam_bundle_v2_command",
]
