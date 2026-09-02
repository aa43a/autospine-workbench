"""Strict replay validation for P10.4b2 continuous proof v2."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_amplitude_envelope_validation_v2 import (
    body_sway_amplitude_envelope_candidate_sha256_v2,
    require_body_sway_amplitude_envelope_candidate_v2,
)
from .body_sway_continuous_proof_profile_v2 import (
    MAX_DOCUMENT_BYTES, continuous_source_sha256_v2,
)
from .body_sway_continuous_proof_sealed_validation_v2 import (
    require_body_sway_continuous_sealed_analysis_v2,
)
from .body_sway_preview_projection_v2 import BodySwayPreviewProjectionV2
from .body_sway_preview_projection_validation_v2 import (
    require_body_sway_preview_projection_v2,
)
from .body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context_for_viewport,
)
from .motion_instance_v2_validation import (
    motion_instance_v2_sha256, require_motion_instance_v2,
)
from .motion_target_validation import require_motion_target_profile
from .resolved_project import canonical_sha256
from .temporary_body_sway_preview_validation_v2 import (
    require_temporary_body_sway_preview_manifest_v2,
)


FORMAT = "autospine-body-sway-continuous-preview-proof"
FORMAT_VERSION = 2
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "problem", "segments", "analyzer", "claims", "status",
    "release_gate", "summary",
}
_ANALYSIS = {"problem", "segments", "claims", "status", "summary"}
_SOURCE = {
    "source_set_sha256", "amplitude_envelope_candidate_v2_sha256",
    "amplitude_envelope_candidate_v2", "rig_ir_sha256", "rig_ir",
    "target_profile_sha256", "target_profile",
    "motion_instance_v2_sha256", "motion_instance_v2",
    "temporary_preview_v2_sha256", "temporary_preview_v2",
    "preview_projection_v2_sha256", "preview_projection_v2",
    "reviewed_world_viewport",
}


class BodySwayContinuousProofValidationV2Error(ValueError):
    """Raised when v2 proof evidence is detached, forged, or overclaims."""


def require_body_sway_continuous_preview_proof_v2(
    document: Mapping[str, Any],
    *, on_progress=None,
) -> None:
    try:
        root, source = _require_sealed_root(document)
        from .body_sway_continuous_proof_v2 import _analyze
        expected = _analyze(source, on_progress=on_progress)
        actual = {field: root.get(field) for field in _ANALYSIS}
        if _canonical(actual) != _canonical(expected):
            raise BodySwayContinuousProofValidationV2Error(
                "Continuous proof v2 differs from exact recomputation"
            )
    except BodySwayContinuousProofValidationV2Error:
        raise
    except Exception as exc:
        raise BodySwayContinuousProofValidationV2Error(
            f"Continuous proof v2 validation failed: {exc}"
        ) from exc


def require_sealed_body_sway_continuous_preview_proof_v2(
    document: Mapping[str, Any],
) -> None:
    """Validate every sealed field except costly interval recomputation."""

    try:
        _require_sealed_root(document)
    except BodySwayContinuousProofValidationV2Error:
        raise
    except Exception as exc:
        raise BodySwayContinuousProofValidationV2Error(
            f"Continuous proof v2 validation failed: {exc}"
        ) from exc


def _require_sealed_root(document):
    root = _bounded_copy(document)
    if set(root) != _TOP or root.get("format") != FORMAT \
            or type(root.get("format_version")) is not int \
            or root["format_version"] != FORMAT_VERSION:
        raise BodySwayContinuousProofValidationV2Error(
            "Continuous proof v2 format is unsupported"
        )
    source, context = _require_source(root.get("source"))
    candidate = source["amplitude_envelope_candidate_v2"]
    if root.get("project_id") != candidate["project_id"] \
            or root.get("clip_id") != candidate["clip_id"]:
        raise BodySwayContinuousProofValidationV2Error(
            "Continuous proof v2 project or clip differs"
        )
    require_body_sway_continuous_sealed_analysis_v2(
        root, source, context,
    )
    return root, source


def body_sway_continuous_preview_proof_sha256_v2(document) -> str:
    require_body_sway_continuous_preview_proof_v2(document)
    return canonical_sha256(document)


def _require_source(value):
    if not isinstance(value, Mapping) or set(value) != _SOURCE:
        raise BodySwayContinuousProofValidationV2Error(
            "Continuous proof v2 source fields are unsupported"
        )
    source = json.loads(_canonical(value))
    candidate = source["amplitude_envelope_candidate_v2"]
    require_body_sway_amplitude_envelope_candidate_v2(candidate)
    rig, target = source["rig_ir"], source["target_profile"]
    motion = source["motion_instance_v2"]
    preview, projection = (
        source["temporary_preview_v2"],
        source["preview_projection_v2"],
    )
    require_motion_target_profile(target)
    require_motion_instance_v2(motion, target_profile=target)
    require_temporary_body_sway_preview_manifest_v2(preview)
    context = prepare_body_sway_geometry_context_for_viewport(
        rig, target, source["reviewed_world_viewport"],
    )
    projection_value = BodySwayPreviewProjectionV2(_canonical(projection))
    report = candidate["source"]["reviewed_probe_report"]
    admission_source = candidate["source"]["review_admission_v2"]["source"]
    preview_source = admission_source["preview_source"]
    require_body_sway_preview_projection_v2(
        projection, project_id=candidate["project_id"],
        clip_id=candidate["clip_id"], report=report,
        motion_sha256=source["motion_instance_v2_sha256"],
        framing_candidate_sha256=
            preview_source["capture_framing_candidate_sha256"],
        framing_decision_sha256=
            preview_source["capture_framing_decision_sha256"],
        framing_revision=preview_source["capture_framing_revision"],
        reviewed_world_viewport=source["reviewed_world_viewport"],
    )
    identities = {
        "candidate": body_sway_amplitude_envelope_candidate_sha256_v2(
            candidate
        ),
        "rig": canonical_sha256(rig), "target": canonical_sha256(target),
        "motion": motion_instance_v2_sha256(motion),
        "preview": canonical_sha256(preview),
        "projection": canonical_sha256(projection),
    }
    expected = {
        "candidate": source["amplitude_envelope_candidate_v2_sha256"],
        "rig": source["rig_ir_sha256"],
        "target": source["target_profile_sha256"],
        "motion": source["motion_instance_v2_sha256"],
        "preview": source["temporary_preview_v2_sha256"],
        "projection": source["preview_projection_v2_sha256"],
    }
    if identities != expected \
            or continuous_source_sha256_v2(source) \
                != source["source_set_sha256"]:
        raise BodySwayContinuousProofValidationV2Error(
            "Continuous proof v2 source digests differ"
        )
    _require_cross_chain(
        source, candidate, report, rig, target, motion,
        preview, projection_value,
    )
    return source, context


def _require_cross_chain(
    source, candidate, report, rig, target, motion, preview, projection,
):
    project, clip = candidate["project_id"], candidate["clip_id"]
    p3, p5, p9 = report["source"]["p3"], report["source"]["p5"], \
        report["source"]["p9"]
    preview_source = preview["source"]
    projection_doc = projection.document
    if canonical_sha256(rig) != p3["rig_sha256"] \
            or canonical_sha256(target) != p5["target_profile_sha256"] \
            or motion_instance_v2_sha256(motion) \
                != p9["motion_instance_v2_sha256"] \
            or preview["project_id"] != project \
            or preview["clip_id"] != clip \
            or projection_doc["project_id"] != project \
            or projection_doc["clip_id"] != clip \
            or preview["timing"] != candidate["timing"] \
            or preview["selection"] != candidate["reviewed_selection"] \
            or projection_doc["timing"] != candidate["timing"] \
            or projection_doc["selection"] != candidate["reviewed_selection"]:
        raise BodySwayContinuousProofValidationV2Error(
            "Continuous proof v2 source chain is cross-wired"
        )
    viewport = source["reviewed_world_viewport"]
    if candidate["source"]["temporary_preview_v2_sha256"] \
            != canonical_sha256(preview) \
            or candidate["source"]["preview_projection_v2_sha256"] \
                != projection.sha256 \
            or candidate["source"]["reviewed_world_viewport"] != viewport \
            or preview_source["body_sway_probe_report_sha256"] \
                != candidate["source"]["review_admission_v2"][
                    "source"
                ]["preview_source"]["body_sway_probe_report_sha256"] \
            or preview["projection"] != projection.public_metadata \
            or projection_doc["capture_framing"]["world_viewport"] \
                != viewport \
            or preview["capture_plan"]["world_viewport"] != viewport:
        raise BodySwayContinuousProofValidationV2Error(
            "Continuous proof v2 Preview/world viewport binding differs"
        )


def _bounded_copy(value):
    raw = _canonical(value).encode("utf-8")
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise BodySwayContinuousProofValidationV2Error(
            "Continuous proof v2 exceeds its byte limit"
        )
    copied = json.loads(raw)
    if not isinstance(copied, dict):
        raise BodySwayContinuousProofValidationV2Error(
            "Continuous proof v2 must be an object"
        )
    return copied


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


__all__ = [
    "BodySwayContinuousProofValidationV2Error",
    "body_sway_continuous_preview_proof_sha256_v2",
    "require_sealed_body_sway_continuous_preview_proof_v2",
    "require_body_sway_continuous_preview_proof_v2",
]
